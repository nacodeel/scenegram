from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, is_dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, cast

from aiogram.filters import CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import Message
from aiogram.utils.deep_linking import (
    create_start_link,
    create_startapp_link,
    create_startgroup_link,
)

from ._utils import call_with_optional_args
from .contracts import (
    DeepLinkContext,
    DeepLinkDelivery,
    DeepLinkKind,
    DeepLinkPolicy,
    DeepLinkRoute,
    DeepLinkStore,
    DeepLinkTarget,
    DeepLinkTicket,
)
from .formatting import RenderableText
from .roles import normalize_roles
from .runtime import RUNTIME
from .security import is_state_allowed, resolve_event_roles

if TYPE_CHECKING:
    from aiogram import Bot

    from .base import AppScene


INLINE_SIGNED_PREFIX = "sgs_"
INLINE_PLAIN_PREFIX = "sgp_"
STORED_PREFIX = "sgt_"
BUILTIN_SCENE_ROUTE = "scenegram.scene"
BUILTIN_REFERRAL_ROUTE = "scenegram.referral"


class DeepLinkError(RuntimeError):
    pass


class DeepLinkDecodeError(DeepLinkError):
    pass


class DeepLinkSignatureError(DeepLinkError):
    pass


class DeepLinkNotFoundError(DeepLinkError):
    pass


class DeepLinkExpiredError(DeepLinkError):
    pass


class DeepLinkExhaustedError(DeepLinkError):
    pass


class DeepLinkUserMismatchError(DeepLinkError):
    pass


class DeepLinkRouteNotFoundError(DeepLinkError):
    pass


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.astimezone(UTC).isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_jsonable(item) for item in value]
    return str(value)


def _compact_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _b64_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64_decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(f"{payload}{padding}".encode("ascii"))


def _sign(raw: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()[:10]


def _normalize_roles(
    route_roles: Iterable[str] | None,
    policy_roles: Iterable[str] | None,
) -> frozenset[str]:
    route = normalize_roles(route_roles or ("any",))
    policy = normalize_roles(policy_roles or ("any",))
    if "any" in route:
        return policy
    if "any" in policy:
        return route
    intersection = route & policy
    return intersection or frozenset()


def _policy_overrides(
    route: DeepLinkRoute | None,
    *,
    policy: DeepLinkPolicy | None = None,
    kind: DeepLinkKind | None = None,
    secure: bool | None = None,
    strategy: DeepLinkDelivery | None = None,
    ttl_seconds: int | None = None,
    one_time: bool = False,
    max_uses: int | None = None,
    app_name: str | None = None,
    user_id: int | None = None,
    roles: Iterable[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> DeepLinkPolicy:
    base = route.policy if route is not None else DeepLinkPolicy()
    merged = policy or base
    resolved_max_uses = merged.max_uses
    if one_time:
        resolved_max_uses = 1
    elif max_uses is not None:
        resolved_max_uses = max_uses
    return DeepLinkPolicy(
        kind=merged.kind if kind is None else kind,
        secure=merged.secure if secure is None else secure,
        strategy=merged.strategy if strategy is None else strategy,
        ttl_seconds=merged.ttl_seconds if ttl_seconds is None else ttl_seconds,
        max_uses=resolved_max_uses,
        app_name=merged.app_name if app_name is None else app_name,
        user_id=merged.user_id if user_id is None else user_id,
        roles=_normalize_roles(
            getattr(route, "roles", frozenset({"any"})),
            merged.roles if roles is None else normalize_roles(roles),
        ),
        metadata={**dict(merged.metadata), **dict(metadata or {})},
    )


def deep_link_scene(
    name: str,
    scene: str | None = None,
    *,
    payload_key: str | None = None,
    parser: Any | None = None,
    roles: Iterable[str] | None = None,
    back_target: str | None = None,
    action: Literal["to", "replace"] = "replace",
    reset_history: bool = True,
    description: str = "",
    policy: DeepLinkPolicy | None = None,
) -> DeepLinkRoute:
    return DeepLinkRoute(
        name=name,
        scene=scene,
        parser=parser,
        payload_key=payload_key,
        roles=normalize_roles(roles or ("any",)),
        back_target=back_target,
        action=action,
        reset_history=reset_history,
        description=description,
        policy=policy or DeepLinkPolicy(),
    )


def deep_link_handler(
    name: str,
    handler: Any,
    *,
    parser: Any | None = None,
    roles: Iterable[str] | None = None,
    description: str = "",
    policy: DeepLinkPolicy | None = None,
) -> DeepLinkRoute:
    return DeepLinkRoute(
        name=name,
        handler=handler,
        parser=parser,
        roles=normalize_roles(roles or ("any",)),
        description=description,
        policy=policy or DeepLinkPolicy(),
    )


class InMemoryDeepLinkStore:
    def __init__(self) -> None:
        self._tickets: dict[str, DeepLinkTicket] = {}

    async def issue(self, ticket: DeepLinkTicket) -> None:
        self._tickets[ticket.token] = ticket

    async def consume(
        self,
        token: str,
        *,
        user_id: int | None = None,
        now: datetime | None = None,
    ) -> DeepLinkTicket:
        ticket = self._tickets.get(token)
        if ticket is None:
            raise DeepLinkNotFoundError("Deep link not found")

        current = now or _utcnow()
        expires_at = ticket.expires_at
        if expires_at is not None and current >= expires_at:
            self._tickets.pop(token, None)
            raise DeepLinkExpiredError("Deep link expired")

        if ticket.user_id is not None and user_id is not None and ticket.user_id != user_id:
            raise DeepLinkUserMismatchError("Deep link belongs to another user")

        if ticket.max_uses is not None and ticket.uses >= ticket.max_uses:
            self._tickets.pop(token, None)
            raise DeepLinkExhaustedError("Deep link is already used")

        updated = replace(ticket, uses=ticket.uses + 1)
        self._tickets[token] = updated
        return updated

    async def revoke(self, token: str) -> None:
        self._tickets.pop(token, None)


def _ticket_expiry(ttl_seconds: int | None) -> datetime | None:
    if ttl_seconds is None:
        return None
    return _utcnow() + timedelta(seconds=ttl_seconds)


def _build_envelope(
    route: str,
    payload: Any,
    *,
    policy: DeepLinkPolicy,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {"r": route}
    normalized_payload = _jsonable(payload)
    if normalized_payload is not None:
        envelope["p"] = normalized_payload
    if policy.kind != "start":
        envelope["k"] = policy.kind
    if policy.roles and "any" not in policy.roles:
        envelope["o"] = sorted(policy.roles)
    if policy.metadata:
        envelope["x"] = _jsonable(policy.metadata)
    if policy.ttl_seconds is not None:
        envelope["e"] = int((_utcnow() + timedelta(seconds=policy.ttl_seconds)).timestamp())
    if policy.user_id is not None:
        envelope["u"] = policy.user_id
    return envelope


def _encode_inline(envelope: Mapping[str, Any], *, secret: str | None, secure: bool) -> str:
    raw = _compact_json(envelope)
    if secure:
        if not secret:
            raise DeepLinkSignatureError("Deep link secret is not configured")
        blob = _sign(raw, secret) + raw
        return f"{INLINE_SIGNED_PREFIX}{_b64_encode(blob)}"
    return f"{INLINE_PLAIN_PREFIX}{_b64_encode(raw)}"


def _decode_inline(
    token: str, *, secret: str | None
) -> tuple[Literal["plain", "signed"], dict[str, Any]]:
    if token.startswith(INLINE_SIGNED_PREFIX):
        encoded = token.removeprefix(INLINE_SIGNED_PREFIX)
        blob = _b64_decode(encoded)
        if len(blob) < 10:
            raise DeepLinkDecodeError("Malformed deep link payload")
        signature = blob[:10]
        raw = blob[10:]
        if not secret:
            raise DeepLinkSignatureError("Deep link secret is not configured")
        expected = _sign(raw, secret)
        if not hmac.compare_digest(signature, expected):
            raise DeepLinkSignatureError("Deep link signature mismatch")
        return "signed", json.loads(raw.decode("utf-8"))

    if token.startswith(INLINE_PLAIN_PREFIX):
        encoded = token.removeprefix(INLINE_PLAIN_PREFIX)
        raw = _b64_decode(encoded)
        return "plain", json.loads(raw.decode("utf-8"))

    raise DeepLinkDecodeError("Unsupported deep link payload")


def _extract_user_id(message: Message | None) -> int | None:
    if message is None:
        return None
    user = getattr(message, "from_user", None)
    return getattr(user, "id", None)


class DeepLinkManager:
    def __init__(
        self,
        *,
        bot: Bot | None = None,
        scene: AppScene | None = None,
    ) -> None:
        self._bot = bot
        self.scene_instance = scene

    def _resolve_bot(self, bot: Bot | None = None) -> Bot:
        if bot is not None:
            return bot
        if self._bot is not None:
            return self._bot
        if self.scene_instance is not None:
            event = self.scene_instance.current_event()
            message = getattr(event, "message", event)
            bot_instance = getattr(message, "bot", None)
            if bot_instance is not None:
                return bot_instance
        raise RuntimeError("Bot instance is required to create deep links")

    def _store(self) -> DeepLinkStore:
        if RUNTIME.deep_link_store is None:
            RUNTIME.deep_link_store = InMemoryDeepLinkStore()
        return RUNTIME.deep_link_store

    async def _telegram_link(
        self,
        token: str,
        *,
        bot: Bot | None = None,
        kind: DeepLinkKind = "start",
        app_name: str | None = None,
    ) -> str:
        bot_instance = self._resolve_bot(bot)
        if kind == "startgroup":
            return await create_startgroup_link(bot_instance, token, encode=False)
        if kind == "startapp":
            return await create_startapp_link(
                bot_instance,
                token,
                encode=False,
                app_name=app_name,
            )
        return await create_start_link(bot_instance, token, encode=False)

    async def create(
        self,
        route: str,
        payload: Any = None,
        *,
        bot: Bot | None = None,
        policy: DeepLinkPolicy | None = None,
        kind: DeepLinkKind | None = None,
        secure: bool | None = None,
        strategy: DeepLinkDelivery | None = None,
        ttl_seconds: int | None = None,
        one_time: bool = False,
        max_uses: int | None = None,
        app_name: str | None = None,
        user_id: int | None = None,
        roles: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        route_definition = RUNTIME.deep_link_route_for(route)
        resolved_policy = _policy_overrides(
            route_definition,
            policy=policy,
            kind=kind,
            secure=secure,
            strategy=strategy,
            ttl_seconds=ttl_seconds,
            one_time=one_time,
            max_uses=max_uses,
            app_name=app_name,
            user_id=user_id,
            roles=roles,
            metadata=metadata,
        )

        envelope = _build_envelope(route, payload, policy=resolved_policy)

        if resolved_policy.strategy == "plain" and resolved_policy.secure:
            raise ValueError("Plain deep links cannot be marked as secure")

        should_store = resolved_policy.strategy == "stored" or resolved_policy.max_uses is not None
        token: str | None = None

        if not should_store:
            if resolved_policy.secure and RUNTIME.deep_link_secret is None:
                if resolved_policy.strategy == "signed":
                    raise DeepLinkSignatureError("Deep link secret is not configured")
                should_store = True
            else:
                inline_secure = resolved_policy.secure and resolved_policy.strategy != "plain"
                encoded = _encode_inline(
                    envelope,
                    secret=RUNTIME.deep_link_secret,
                    secure=inline_secure,
                )
                if resolved_policy.strategy == "auto" and len(encoded) > 64:
                    should_store = True
                elif len(encoded) > 64:
                    raise ValueError("Deep link payload is too large for inline strategy")
                else:
                    token = encoded

        if should_store:
            token = f"{STORED_PREFIX}{secrets.token_urlsafe(18)}"
            ticket = DeepLinkTicket(
                token=token,
                route=route,
                payload=_jsonable(payload),
                kind=resolved_policy.kind,
                secure=resolved_policy.secure,
                roles=resolved_policy.roles,
                metadata=dict(resolved_policy.metadata),
                created_at=_utcnow(),
                expires_at=_ticket_expiry(resolved_policy.ttl_seconds),
                max_uses=resolved_policy.max_uses,
                uses=0,
                user_id=resolved_policy.user_id,
            )
            await self._store().issue(ticket)

        if token is None:
            raise RuntimeError("Deep link token was not created")

        if self.scene_instance is not None:
            await self.scene_instance.runtime.emit(
                "deep_link.created",
                scene=self.scene_instance,
                event=self.scene_instance.current_event(),
                target_state=getattr(route_definition, "scene", None),
                metadata={
                    "route": route,
                    "kind": resolved_policy.kind,
                    "strategy": "stored" if token.startswith(STORED_PREFIX) else "inline",
                    "secure": resolved_policy.secure,
                    "ttl_seconds": resolved_policy.ttl_seconds,
                    "max_uses": resolved_policy.max_uses,
                },
            )

        return await self._telegram_link(
            token,
            bot=bot,
            kind=resolved_policy.kind,
            app_name=resolved_policy.app_name,
        )

    async def scene(
        self,
        scene: str,
        *,
        payload: Mapping[str, Any] | None = None,
        back_target: str | None = None,
        action: Literal["to", "replace"] = "replace",
        reset_history: bool = True,
        bot: Bot | None = None,
        policy: DeepLinkPolicy | None = None,
        kind: DeepLinkKind | None = None,
        secure: bool | None = None,
        strategy: DeepLinkDelivery | None = None,
        ttl_seconds: int | None = None,
        one_time: bool = False,
        max_uses: int | None = None,
        app_name: str | None = None,
        user_id: int | None = None,
        roles: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        route_payload = {
            "scene": scene,
            "kwargs": dict(payload or {}),
            "back_target": back_target,
            "action": action,
            "reset_history": reset_history,
        }
        return await self.create(
            BUILTIN_SCENE_ROUTE,
            route_payload,
            bot=bot,
            policy=policy,
            kind=kind,
            secure=secure,
            strategy=strategy,
            ttl_seconds=ttl_seconds,
            one_time=one_time,
            max_uses=max_uses,
            app_name=app_name,
            user_id=user_id,
            roles=roles,
            metadata=metadata,
        )

    async def temporary_scene(
        self,
        scene: str,
        *,
        ttl_seconds: int,
        payload: Mapping[str, Any] | None = None,
        back_target: str | None = None,
        action: Literal["to", "replace"] = "replace",
        reset_history: bool = True,
        bot: Bot | None = None,
        secure: bool | None = None,
        strategy: DeepLinkDelivery | None = None,
        app_name: str | None = None,
        user_id: int | None = None,
        roles: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        return await self.scene(
            scene,
            payload=payload,
            back_target=back_target,
            action=action,
            reset_history=reset_history,
            bot=bot,
            ttl_seconds=ttl_seconds,
            secure=secure,
            strategy=strategy,
            app_name=app_name,
            user_id=user_id,
            roles=roles,
            metadata=metadata,
        )

    async def one_time_scene(
        self,
        scene: str,
        *,
        payload: Mapping[str, Any] | None = None,
        ttl_seconds: int | None = None,
        back_target: str | None = None,
        action: Literal["to", "replace"] = "replace",
        reset_history: bool = True,
        bot: Bot | None = None,
        secure: bool | None = None,
        strategy: DeepLinkDelivery | None = None,
        app_name: str | None = None,
        user_id: int | None = None,
        roles: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        return await self.scene(
            scene,
            payload=payload,
            back_target=back_target,
            action=action,
            reset_history=reset_history,
            bot=bot,
            ttl_seconds=ttl_seconds,
            one_time=True,
            secure=secure,
            strategy=strategy,
            app_name=app_name,
            user_id=user_id,
            roles=roles,
            metadata=metadata,
        )

    async def referral(
        self,
        referrer_id: int | str,
        *,
        target_scene: str | None = None,
        field: str = "referrer_id",
        campaign: str | None = None,
        data: Mapping[str, Any] | None = None,
        bot: Bot | None = None,
        policy: DeepLinkPolicy | None = None,
        kind: DeepLinkKind | None = None,
        secure: bool | None = None,
        strategy: DeepLinkDelivery | None = None,
        ttl_seconds: int | None = None,
        one_time: bool = False,
        app_name: str | None = None,
        user_id: int | None = None,
        roles: Iterable[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        route_payload = {
            "field": field,
            "value": referrer_id,
            "campaign": campaign,
            "data": dict(data or {}),
            "target_scene": target_scene
            or (self.scene_instance.state_id if self.scene_instance is not None else None),
        }
        return await self.create(
            BUILTIN_REFERRAL_ROUTE,
            route_payload,
            bot=bot,
            policy=policy,
            kind=kind,
            secure=secure,
            strategy=strategy,
            ttl_seconds=ttl_seconds,
            one_time=one_time,
            app_name=app_name,
            user_id=user_id,
            roles=roles,
            metadata=metadata,
        )

    async def resolve_token(
        self,
        token: str,
        *,
        user_id: int | None = None,
    ) -> DeepLinkContext:
        if token.startswith(STORED_PREFIX):
            ticket = await self._store().consume(token, user_id=user_id, now=_utcnow())
            remaining = None
            if ticket.max_uses is not None:
                remaining = max(ticket.max_uses - ticket.uses, 0)
            return DeepLinkContext(
                route=ticket.route,
                payload=ticket.payload,
                token=ticket.token,
                transport="stored",
                kind=ticket.kind,
                secure=ticket.secure,
                roles=ticket.roles,
                metadata=ticket.metadata,
                expires_at=ticket.expires_at,
                remaining_uses=remaining,
                user_id=ticket.user_id,
            )

        transport, envelope = _decode_inline(token, secret=RUNTIME.deep_link_secret)
        expires = envelope.get("e")
        expires_at = datetime.fromtimestamp(expires, tz=UTC) if expires is not None else None
        if expires_at is not None and _utcnow() >= expires_at:
            raise DeepLinkExpiredError("Deep link expired")
        bound_user_id = envelope.get("u")
        if bound_user_id is not None and user_id is not None and int(bound_user_id) != int(user_id):
            raise DeepLinkUserMismatchError("Deep link belongs to another user")

        return DeepLinkContext(
            route=str(envelope["r"]),
            payload=envelope.get("p"),
            token=token,
            transport=transport,
            kind=cast(DeepLinkKind, envelope.get("k", "start")),
            secure=transport == "signed",
            roles=normalize_roles(envelope.get("o", ("any",))),
            metadata=dict(envelope.get("x", {})),
            expires_at=expires_at,
            remaining_uses=None,
            user_id=bound_user_id,
        )

    async def resolve_command(
        self,
        command: CommandObject | str | None,
        *,
        user_id: int | None = None,
    ) -> DeepLinkContext | None:
        args = command.args if isinstance(command, CommandObject) else command
        if not args:
            return None
        return await self.resolve_token(args, user_id=user_id)

    async def _invoke_route_handler(
        self,
        route: DeepLinkRoute,
        event: Message,
        context: DeepLinkContext,
    ) -> Any:
        if route.handler is None:
            return None
        callback = route.handler
        if isinstance(callback, str):
            if self.scene_instance is None:
                raise RuntimeError("String deep link handlers require a scene instance")
            callback = getattr(self.scene_instance, callback)
        return await call_with_optional_args(callback, self.scene_instance, event, context)

    async def _invoke_route_parser(
        self,
        route: DeepLinkRoute,
        event: Message,
        context: DeepLinkContext,
    ) -> Any:
        if route.parser is None:
            return context.payload
        callback = route.parser
        if isinstance(callback, str):
            if self.scene_instance is None:
                raise RuntimeError("String deep link parsers require a scene instance")
            callback = getattr(self.scene_instance, callback)
        return await call_with_optional_args(callback, self.scene_instance, event, context)

    async def _ensure_roles(self, event: Message, roles: Iterable[str]) -> None:
        allowed = normalize_roles(roles)
        if not allowed or "any" in allowed:
            return
        resolved = await resolve_event_roles(event)
        if resolved & allowed:
            return
        raise PermissionError("Deep link access denied")

    async def _apply_target(self, target: DeepLinkTarget) -> Any:
        if self.scene_instance is None:
            return target
        if target.back_target is not None:
            await self.scene_instance.data.update(_back_target=target.back_target)
        if target.action == "to":
            return await self.scene_instance.nav.to(target.scene, **dict(target.kwargs))
        return await self.scene_instance.nav.replace(
            target.scene,
            reset_history=target.reset_history,
            **dict(target.kwargs),
        )

    async def _builtin_scene_target(self, context: DeepLinkContext) -> DeepLinkTarget:
        payload = dict(context.payload or {})
        target_scene = str(payload["scene"])
        kwargs = dict(payload.get("kwargs", {}))
        back_target = payload.get("back_target")
        action = str(payload.get("action", "replace"))
        reset_history = bool(payload.get("reset_history", True))
        return DeepLinkTarget(
            scene=target_scene,
            kwargs=kwargs,
            back_target=back_target,
            action="to" if action == "to" else "replace",
            reset_history=reset_history,
        )

    async def _builtin_referral_target(
        self,
        event: Message,
        context: DeepLinkContext,
    ) -> DeepLinkTarget | None:
        payload = dict(context.payload or {})
        if self.scene_instance is not None:
            field = str(payload.get("field", "referrer_id"))
            value = payload.get("value")
            extras = dict(payload.get("data", {}))
            await self.scene_instance.data.update({field: value, **extras})
            await self.scene_instance.runtime.emit(
                "deep_link.referral",
                scene=self.scene_instance,
                event=event,
                metadata={
                    "field": field,
                    "value": value,
                    "campaign": payload.get("campaign"),
                    "target_scene": payload.get("target_scene"),
                },
            )
        target_scene = payload.get("target_scene")
        if not target_scene:
            return None
        return DeepLinkTarget(scene=str(target_scene))

    async def execute(self, event: Message, context: DeepLinkContext) -> Any:
        await self._ensure_roles(event, context.roles)
        if context.route == BUILTIN_SCENE_ROUTE:
            target = await self._builtin_scene_target(context)
            if not is_state_allowed(target.scene, await resolve_event_roles(event)):
                raise PermissionError("Deep link target access denied")
            return await self._apply_target(target)

        if context.route == BUILTIN_REFERRAL_ROUTE:
            target = await self._builtin_referral_target(event, context)
            if target is not None:
                return await self._apply_target(target)
            return None

        route = RUNTIME.deep_link_route_for(context.route)
        if route is None:
            raise DeepLinkRouteNotFoundError(f"Unknown deep link route: {context.route}")

        await self._ensure_roles(event, route.roles)
        result = await self._invoke_route_handler(route, event, context)
        if isinstance(result, DeepLinkTarget):
            return await self._apply_target(result)
        if result is not None:
            return result

        if route.scene is None:
            return None

        parsed = await self._invoke_route_parser(route, event, context)
        if isinstance(parsed, DeepLinkTarget):
            return await self._apply_target(parsed)

        if parsed is None:
            parsed = context.payload

        kwargs: dict[str, Any]
        if isinstance(parsed, Mapping):
            kwargs = dict(parsed)
        elif route.payload_key is not None:
            kwargs = {route.payload_key: parsed}
        elif parsed in (None, ""):
            kwargs = {}
        else:
            kwargs = {"payload": parsed}

        target = DeepLinkTarget(
            scene=route.scene,
            kwargs=kwargs,
            back_target=route.back_target,
            action=route.action,
            reset_history=route.reset_history,
        )
        return await self._apply_target(target)

    async def dispatch(
        self,
        event: Message,
        command: CommandObject | str | None,
    ) -> DeepLinkContext | None:
        context = await self.resolve_command(command, user_id=_extract_user_id(event))
        if context is None:
            return None
        if self.scene_instance is not None:
            await self.scene_instance.runtime.emit(
                "deep_link.opened",
                scene=self.scene_instance,
                event=event,
                target_state=getattr(RUNTIME.deep_link_route_for(context.route), "scene", None),
                metadata={
                    "route": context.route,
                    "transport": context.transport,
                    "kind": context.kind,
                    "secure": context.secure,
                },
            )
        await self.execute(event, context)
        return context


class SceneDeepLinksProxy(DeepLinkManager):
    def __init__(self, scene: AppScene) -> None:
        super().__init__(scene=scene)


class _DeepLinkEntrySupport:
    deep_links: tuple[DeepLinkRoute, ...] = ()
    deep_link_invalid_text = "Ссылка повреждена."
    deep_link_expired_text = "Ссылка устарела."
    deep_link_used_text = "Ссылка уже использована."
    deep_link_unknown_text = "Ссылка не поддерживается."
    deep_link_forbidden_text = "Ссылка вам недоступна."
    deep_link_other_user_text = "Эта ссылка предназначена для другого пользователя."

    async def on_plain_start(
        self,
        message: Message,
        command: CommandObject | None = None,
    ) -> Any:
        return None

    async def on_deep_link_error(
        self,
        message: Message,
        error: DeepLinkError | PermissionError,
        command: CommandObject | None = None,
    ) -> Any:
        if isinstance(error, DeepLinkExpiredError):
            text: RenderableText = self.deep_link_expired_text
        elif isinstance(error, DeepLinkExhaustedError):
            text = self.deep_link_used_text
        elif isinstance(error, DeepLinkRouteNotFoundError):
            text = self.deep_link_unknown_text
        elif isinstance(error, DeepLinkUserMismatchError):
            text = self.deep_link_other_user_text
        elif isinstance(error, PermissionError):
            text = self.deep_link_forbidden_text
        else:
            text = self.deep_link_invalid_text

        await cast(Any, self).reply_notice(message, text)
        return await self.on_plain_start(message, command)

    async def handle_start_entry(
        self,
        message: Message,
        command: CommandObject | None = None,
    ) -> Any:
        if not command or not command.args:
            return await self.on_plain_start(message, command)
        try:
            proxy = cast(Any, self).deep_links
            return await proxy.dispatch(message, command)
        except (DeepLinkError, PermissionError) as exc:
            return await self.on_deep_link_error(message, exc, command)


def deep_link_entrypoint():
    from .bootstrap import message_entry

    return message_entry(CommandStart())


__all__ = [
    "BUILTIN_REFERRAL_ROUTE",
    "BUILTIN_SCENE_ROUTE",
    "DeepLinkContext",
    "DeepLinkDecodeError",
    "DeepLinkError",
    "DeepLinkExhaustedError",
    "DeepLinkExpiredError",
    "DeepLinkManager",
    "DeepLinkNotFoundError",
    "DeepLinkRouteNotFoundError",
    "DeepLinkSignatureError",
    "DeepLinkStore",
    "DeepLinkTarget",
    "DeepLinkTicket",
    "DeepLinkUserMismatchError",
    "INLINE_PLAIN_PREFIX",
    "INLINE_SIGNED_PREFIX",
    "InMemoryDeepLinkStore",
    "STORED_PREFIX",
    "SceneDeepLinksProxy",
    "_DeepLinkEntrySupport",
    "deep_link_entrypoint",
    "deep_link_handler",
    "deep_link_scene",
]
