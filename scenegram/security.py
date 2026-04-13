from __future__ import annotations

import inspect
from typing import Any

from aiogram.fsm.scene import Scene
from aiogram.types import CallbackQuery, Message

from .roles import SceneRole, normalize_role
from .runtime import RUNTIME

ACCESS_DENIED_TEXT = "Недостаточно прав"


def resolve_target_state(target: type[Scene] | str | Any | None) -> str | None:
    if target is None:
        return None
    if isinstance(target, str):
        return target
    scene_config = getattr(target, "__scene_config__", None)
    state = getattr(scene_config, "state", None)
    if state is not None:
        return str(state)
    state = getattr(target, "state", None)
    if isinstance(state, str):
        return state
    if state is not None:
        return str(state)
    return None


async def resolve_event_roles(event: Any) -> set[str]:
    if RUNTIME.role_resolver is None:
        return {SceneRole.USER.value}

    resolved = RUNTIME.role_resolver(event)
    if inspect.isawaitable(resolved):
        resolved = await resolved

    if resolved is None:
        return set()
    if isinstance(resolved, str):
        return {normalize_role(resolved)}
    return {normalize_role(role) for role in resolved}


def state_roles(state: str | None) -> frozenset[str]:
    if state is None:
        return frozenset()
    return RUNTIME.roles_for_state(state)


def is_state_allowed(state: str | None, roles: set[str]) -> bool:
    if state is None:
        return True
    allowed = state_roles(state)
    if not allowed or SceneRole.ANY.value in allowed:
        return True
    return bool(roles & allowed)


async def fallback_state_for_access(
    *,
    target_state: str | None,
    roles: set[str],
    scene: Any | None = None,
) -> str | None:
    candidates: list[str] = []
    if scene is not None:
        home_scene = getattr(scene, "home_scene", None)
        if home_scene:
            candidates.append(home_scene)
    for role in sorted(roles):
        target = RUNTIME.home_by_role.get(role)
        if target:
            candidates.append(target)
    if RUNTIME.default_home:
        candidates.append(RUNTIME.default_home)

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate == target_state or candidate in seen:
            continue
        seen.add(candidate)
        if is_state_allowed(candidate, roles):
            return candidate
    return None


async def notify_access_denied(event: Any, text: str = ACCESS_DENIED_TEXT) -> None:
    if isinstance(event, CallbackQuery) or (
        callable(getattr(event, "answer", None)) and hasattr(event, "message")
    ):
        await event.answer(text)
        return
    if isinstance(event, Message) or callable(getattr(event, "answer", None)):
        await event.answer(text=text)


class SecureScenesManagerProxy:
    def __init__(self, manager: Any, *, scene: Any | None = None) -> None:
        self._manager = manager
        self.scene = scene

    def __getattr__(self, name: str) -> Any:
        return getattr(self._manager, name)

    @property
    def event(self) -> Any:
        return getattr(self._manager, "event", None)

    @event.setter
    def event(self, value: Any) -> None:
        self._manager.event = value

    async def enter(self, scene: Any, _check_active: bool = True, **kwargs: Any) -> Any:
        target_state = resolve_target_state(scene)
        if target_state is None:
            return await self._manager.enter(scene, _check_active=_check_active, **kwargs)

        event = self.event
        roles = await resolve_event_roles(event)
        if is_state_allowed(target_state, roles):
            return await self._manager.enter(scene, _check_active=_check_active, **kwargs)

        if self.scene is not None:
            await self.scene.runtime.emit(
                "scene.access_denied",
                scene=self.scene,
                target_state=target_state,
                event=event,
                roles=sorted(roles),
            )
        await notify_access_denied(
            event,
            getattr(self.scene, "access_denied_text", ACCESS_DENIED_TEXT),
        )
        fallback = await fallback_state_for_access(
            target_state=target_state,
            roles=roles,
            scene=self.scene,
        )
        if fallback is not None:
            return await self._manager.enter(fallback, _check_active=False, **kwargs)
        return None


__all__ = [
    "ACCESS_DENIED_TEXT",
    "SecureScenesManagerProxy",
    "fallback_state_for_access",
    "is_state_allowed",
    "notify_access_denied",
    "resolve_event_roles",
    "resolve_target_state",
]
