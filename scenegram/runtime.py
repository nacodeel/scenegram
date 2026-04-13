from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from ._utils import maybe_await
from .contracts import (
    MenuContribution,
    SceneCleanup,
    SceneModule,
    SceneObserver,
    SceneObserverEvent,
)
from .di import NullContainer
from .tasks import SceneTaskRunner

RoleResolver = Callable[[Any], Awaitable[Iterable[str] | str | None] | Iterable[str] | str | None]

DEFAULT_CLEANUP = SceneCleanup(
    delete_previous_screen=True,
    delete_user_messages=False,
    remember_history=True,
)


@dataclass(slots=True)
class SceneRuntime:
    role_resolver: RoleResolver | None = None
    default_home: str | None = None
    home_by_role: dict[str, str] = field(default_factory=dict)
    roles_by_state: dict[str, frozenset[str]] = field(default_factory=dict)
    service_container: Any = field(default_factory=NullContainer)
    cleanup: SceneCleanup = field(default_factory=lambda: DEFAULT_CLEANUP)
    modules: dict[str, SceneModule] = field(default_factory=dict)
    menu_entries_by_state: dict[str, list[MenuContribution]] = field(default_factory=dict)
    scene_module_by_state: dict[str, str] = field(default_factory=dict)
    scene_map: dict[str, type] = field(default_factory=dict)
    callback_prefix_owners: dict[str, str] = field(default_factory=dict)
    observers: list[SceneObserver] = field(default_factory=list)
    task_runner: SceneTaskRunner = field(default_factory=SceneTaskRunner)

    def reset(self) -> None:
        self.role_resolver = None
        self.default_home = None
        self.home_by_role.clear()
        self.roles_by_state.clear()
        self.modules.clear()
        self.menu_entries_by_state.clear()
        self.scene_module_by_state.clear()
        self.scene_map.clear()
        self.callback_prefix_owners.clear()
        self.observers.clear()
        self.service_container = NullContainer()
        self.cleanup = DEFAULT_CLEANUP
        self.task_runner = SceneTaskRunner(observer=self._task_event)

    def register_modules(self, modules: Iterable[SceneModule]) -> None:
        self.modules.clear()
        self.menu_entries_by_state.clear()

        for module in modules:
            self.modules[module.name] = module
            if module.setup is not None:
                module.setup(module)
            for entry in module.menu_entries:
                self.menu_entries_by_state.setdefault(entry.target_state, []).append(entry)

        for entries in self.menu_entries_by_state.values():
            entries.sort(
                key=lambda item: (
                    item.row if item.row is not None else 10_000,
                    item.order,
                    item.text,
                )
            )

    def register_descriptors(self, descriptors: Iterable[Any]) -> None:
        self.roles_by_state.clear()
        self.scene_map.clear()
        for descriptor in descriptors:
            self.roles_by_state[descriptor.state] = descriptor.roles
            self.scene_map[descriptor.state] = descriptor.scene

    def roles_for_state(self, state: str) -> frozenset[str]:
        return self.roles_by_state.get(state, frozenset())

    def bind_scene_module(self, state: str, module_name: str | None) -> None:
        if module_name is None:
            self.scene_module_by_state.pop(state, None)
            return
        self.scene_module_by_state[state] = module_name

    def module_for_state(self, state: str) -> SceneModule | None:
        module_name = self.scene_module_by_state.get(state)
        if module_name is None:
            return None
        return self.modules.get(module_name)

    def scene_class_for(self, state: str) -> type | None:
        return self.scene_map.get(state)

    def menu_entries_for(self, state: str) -> list[MenuContribution]:
        return list(self.menu_entries_by_state.get(state, ()))

    def merge_cleanup(self, override: SceneCleanup | None = None) -> SceneCleanup:
        if override is None:
            return self.cleanup
        return SceneCleanup(
            delete_previous_screen=(
                self.cleanup.delete_previous_screen
                if override.delete_previous_screen is None
                else override.delete_previous_screen
            ),
            delete_user_messages=(
                self.cleanup.delete_user_messages
                if override.delete_user_messages is None
                else override.delete_user_messages
            ),
            remember_history=(
                self.cleanup.remember_history
                if override.remember_history is None
                else override.remember_history
            ),
        )

    def register_callback_prefix(self, prefix: str, owner: str) -> None:
        existing = self.callback_prefix_owners.get(prefix)
        if existing is not None and existing != owner:
            raise RuntimeError(
                f"Callback prefix collision for '{prefix}': {existing} vs {owner}"
            )
        self.callback_prefix_owners[prefix] = owner

    def register_callback_prefixes(self, bindings: dict[str, str]) -> None:
        self.callback_prefix_owners.clear()
        for prefix, owner in bindings.items():
            self.register_callback_prefix(prefix, owner)

    def observe(self, callback: SceneObserver) -> None:
        self.observers.append(callback)

    async def emit(
        self,
        name: str,
        *,
        scene: Any | None = None,
        state: str | None = None,
        target_state: str | None = None,
        event: Any | None = None,
        **metadata: Any,
    ) -> None:
        if not self.observers:
            return

        current_state = state
        if current_state is None and scene is not None:
            current_state = getattr(scene, "state_id", None)

        update_type = None
        if event is not None:
            update_type = getattr(event, "event_type", None) or type(event).__name__

        payload = SceneObserverEvent(
            name=name,
            state=current_state,
            target_state=target_state,
            update_type=update_type,
            metadata=dict(metadata),
        )
        for observer in self.observers:
            await maybe_await(observer(payload))

    async def _task_event(
        self,
        event_name: str,
        handle: Any,
        error: BaseException | None = None,
    ) -> None:
        await self.emit(
            f"task.{event_name}",
            state=None,
            target_state=None,
            event=None,
            task_id=handle.id,
            task_name=handle.name,
            status=getattr(handle, "status", None),
            task_metadata=dict(getattr(handle, "metadata", {}) or {}),
            error=repr(error) if error is not None else None,
        )


RUNTIME = SceneRuntime()
