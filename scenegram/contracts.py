from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from aiogram.enums import ChatAction as TelegramChatAction

Provider = Callable[..., Any]
ProviderValue = Any | Provider
RoleSet = frozenset[str]
ObserverSet = frozenset[str]
DeepLinkKind = Literal["start", "startgroup", "startapp"]
DeepLinkDelivery = Literal["auto", "plain", "signed", "stored"]


class SupportsResolve(Protocol):
    def resolve(
        self,
        key: str,
        *,
        scene: Any | None = None,
        module: SceneModule | None = None,
        default: Any = ...,
    ) -> Any: ...


@dataclass(slots=True, frozen=True)
class SceneActionConfig:
    action: str = TelegramChatAction.TYPING
    interval: float = 5.0
    initial_sleep: float = 0.0
    enabled: bool = True


@dataclass(slots=True, frozen=True)
class SceneCleanup:
    delete_previous_screen: bool | None = None
    delete_user_messages: bool | None = None
    remember_history: bool | None = None


@dataclass(slots=True, frozen=True)
class BreadcrumbItem:
    state: str
    label: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class MenuContribution:
    target_state: str
    text: str
    target_scene: str
    roles: RoleSet = field(default_factory=lambda: frozenset({"any"}))
    row: int | None = None
    order: int = 100


@dataclass(slots=True, frozen=True)
class SceneMiddleware:
    middleware: Any
    observers: ObserverSet = field(
        default_factory=lambda: frozenset({"message", "callback_query"})
    )
    outer: bool = True
    factory: bool = False


def scene_middleware(
    middleware: Any,
    *observers: str,
    outer: bool = True,
    factory: bool = False,
) -> SceneMiddleware:
    normalized = frozenset(observers or ("message", "callback_query"))
    return SceneMiddleware(
        middleware=middleware,
        observers=normalized,
        outer=outer,
        factory=factory,
    )


ModuleSetup = Callable[["SceneModule"], Any]
ModuleCallback = Callable[..., Awaitable[Any] | Any]
SceneObserver = Callable[["SceneObserverEvent"], Awaitable[Any] | Any]


@dataclass(slots=True, frozen=True)
class SceneModule:
    name: str
    package_name: str
    title: str = ""
    description: str = ""
    services: Mapping[str, ProviderValue] = field(default_factory=dict)
    menu_entries: tuple[MenuContribution, ...] = ()
    deep_links: tuple[DeepLinkRoute, ...] = ()
    middlewares: tuple[SceneMiddleware, ...] = ()
    tags: frozenset[str] = frozenset()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    setup: ModuleSetup | None = None

    def with_services(self, **services: ProviderValue) -> SceneModule:
        merged = dict(self.services)
        merged.update(services)
        return SceneModule(
            name=self.name,
            package_name=self.package_name,
            title=self.title,
            description=self.description,
            services=merged,
            menu_entries=self.menu_entries,
            deep_links=self.deep_links,
            middlewares=self.middlewares,
            tags=self.tags,
            metadata=self.metadata,
            setup=self.setup,
        )

    def with_menu_entries(self, *entries: MenuContribution) -> SceneModule:
        return SceneModule(
            name=self.name,
            package_name=self.package_name,
            title=self.title,
            description=self.description,
            services=self.services,
            menu_entries=(*self.menu_entries, *entries),
            deep_links=self.deep_links,
            middlewares=self.middlewares,
            tags=self.tags,
            metadata=self.metadata,
            setup=self.setup,
        )

    def with_deep_links(self, *routes: DeepLinkRoute) -> SceneModule:
        return SceneModule(
            name=self.name,
            package_name=self.package_name,
            title=self.title,
            description=self.description,
            services=self.services,
            menu_entries=self.menu_entries,
            deep_links=(*self.deep_links, *routes),
            middlewares=self.middlewares,
            tags=self.tags,
            metadata=self.metadata,
            setup=self.setup,
        )

    def with_middlewares(self, *middlewares: SceneMiddleware) -> SceneModule:
        return SceneModule(
            name=self.name,
            package_name=self.package_name,
            title=self.title,
            description=self.description,
            services=self.services,
            menu_entries=self.menu_entries,
            deep_links=self.deep_links,
            middlewares=(*self.middlewares, *middlewares),
            tags=self.tags,
            metadata=self.metadata,
            setup=self.setup,
        )


@dataclass(slots=True, frozen=True)
class SceneObserverEvent:
    name: str
    state: str | None = None
    target_state: str | None = None
    update_type: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class DeepLinkPolicy:
    kind: DeepLinkKind = "start"
    secure: bool = True
    strategy: DeepLinkDelivery = "auto"
    ttl_seconds: int | None = None
    max_uses: int | None = None
    app_name: str | None = None
    user_id: int | None = None
    roles: RoleSet = field(default_factory=lambda: frozenset({"any"}))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def permanent(
        cls,
        *,
        kind: DeepLinkKind = "start",
        secure: bool = True,
        strategy: DeepLinkDelivery = "auto",
        app_name: str | None = None,
        user_id: int | None = None,
        roles: RoleSet | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> DeepLinkPolicy:
        return cls(
            kind=kind,
            secure=secure,
            strategy=strategy,
            app_name=app_name,
            user_id=user_id,
            roles=frozenset({"any"}) if roles is None else frozenset(roles),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def temporary(
        cls,
        ttl_seconds: int,
        *,
        kind: DeepLinkKind = "start",
        secure: bool = True,
        strategy: DeepLinkDelivery = "auto",
        app_name: str | None = None,
        user_id: int | None = None,
        roles: RoleSet | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> DeepLinkPolicy:
        return cls(
            kind=kind,
            secure=secure,
            strategy=strategy,
            ttl_seconds=ttl_seconds,
            app_name=app_name,
            user_id=user_id,
            roles=frozenset({"any"}) if roles is None else frozenset(roles),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def one_time(
        cls,
        *,
        ttl_seconds: int | None = None,
        kind: DeepLinkKind = "start",
        secure: bool = True,
        strategy: DeepLinkDelivery = "auto",
        app_name: str | None = None,
        user_id: int | None = None,
        roles: RoleSet | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> DeepLinkPolicy:
        return cls(
            kind=kind,
            secure=secure,
            strategy=strategy,
            ttl_seconds=ttl_seconds,
            max_uses=1,
            app_name=app_name,
            user_id=user_id,
            roles=frozenset({"any"}) if roles is None else frozenset(roles),
            metadata=dict(metadata or {}),
        )


@dataclass(slots=True, frozen=True)
class DeepLinkTarget:
    scene: str
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    action: Literal["to", "replace"] = "replace"
    back_target: str | None = None
    reset_history: bool = True


@dataclass(slots=True, frozen=True)
class DeepLinkRoute:
    name: str
    scene: str | None = None
    handler: ModuleCallback | str | None = None
    parser: ModuleCallback | str | None = None
    payload_key: str | None = None
    roles: RoleSet = field(default_factory=lambda: frozenset({"any"}))
    back_target: str | None = None
    action: Literal["to", "replace"] = "replace"
    reset_history: bool = True
    description: str = ""
    policy: DeepLinkPolicy = field(default_factory=DeepLinkPolicy)


@dataclass(slots=True, frozen=True)
class DeepLinkContext:
    route: str
    payload: Any = None
    token: str = ""
    transport: Literal["plain", "signed", "stored"] = "plain"
    kind: DeepLinkKind = "start"
    secure: bool = True
    roles: RoleSet = field(default_factory=lambda: frozenset({"any"}))
    metadata: Mapping[str, Any] = field(default_factory=dict)
    expires_at: datetime | None = None
    remaining_uses: int | None = None
    user_id: int | None = None


@dataclass(slots=True, frozen=True)
class DeepLinkTicket:
    token: str
    route: str
    payload: Any = None
    kind: DeepLinkKind = "start"
    secure: bool = True
    roles: RoleSet = field(default_factory=lambda: frozenset({"any"}))
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    expires_at: datetime | None = None
    max_uses: int | None = None
    uses: int = 0
    user_id: int | None = None


class DeepLinkStore(Protocol):
    async def issue(self, ticket: DeepLinkTicket) -> None: ...

    async def consume(
        self,
        token: str,
        *,
        user_id: int | None = None,
        now: datetime | None = None,
    ) -> DeepLinkTicket: ...

    async def revoke(self, token: str) -> None: ...


@dataclass(slots=True, frozen=True)
class CrudListItem:
    id: str
    title: str
    description: str | None = None
    badge: str | None = None


@dataclass(slots=True, frozen=True)
class CrudPage:
    items: Sequence[CrudListItem]
    page: int
    pages: int
    total: int


@dataclass(slots=True, frozen=True)
class CrudDetailField:
    label: str
    value: Any


class CrudAdapter(Protocol):
    async def list_items(self, scene: Any, page: int, per_page: int) -> CrudPage: ...

    async def get_item(self, scene: Any, item_id: str) -> Any: ...

    async def get_item_title(self, scene: Any, item: Any) -> str: ...

    async def get_item_fields(self, scene: Any, item: Any) -> Sequence[CrudDetailField]: ...

    async def delete_item(self, scene: Any, item: Any) -> None: ...


@dataclass(slots=True, frozen=True)
class BroadcastReport:
    job_id: str
    total: int
    sent: int
    failed: int
    duration_seconds: float
    errors: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


class BroadcastAdapter(Protocol):
    async def iter_recipients(self, scene: Any) -> Any: ...

    async def send(self, scene: Any, recipient_id: int, content: Any) -> Any: ...

    async def on_complete(self, scene: Any, report: BroadcastReport) -> Any: ...
