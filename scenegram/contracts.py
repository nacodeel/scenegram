from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from aiogram.enums import ChatAction as TelegramChatAction

Provider = Callable[..., Any]
ProviderValue = Any | Provider
RoleSet = frozenset[str]


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
    interval: float = 4.5
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


ModuleSetup = Callable[["SceneModule"], Any]
ModuleCallback = Callable[..., Awaitable[Any] | Any]


@dataclass(slots=True, frozen=True)
class SceneModule:
    name: str
    package_name: str
    title: str = ""
    description: str = ""
    services: Mapping[str, ProviderValue] = field(default_factory=dict)
    menu_entries: tuple[MenuContribution, ...] = ()
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
            tags=self.tags,
            metadata=self.metadata,
            setup=self.setup,
        )


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
