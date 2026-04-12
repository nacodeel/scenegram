from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from .contracts import MenuContribution, SceneCleanup, SceneModule
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
    service_container: Any = field(default_factory=NullContainer)
    cleanup: SceneCleanup = field(default_factory=lambda: DEFAULT_CLEANUP)
    modules: dict[str, SceneModule] = field(default_factory=dict)
    menu_entries_by_state: dict[str, list[MenuContribution]] = field(default_factory=dict)
    scene_module_by_state: dict[str, str] = field(default_factory=dict)
    task_runner: SceneTaskRunner = field(default_factory=SceneTaskRunner)

    def reset(self) -> None:
        self.role_resolver = None
        self.default_home = None
        self.home_by_role.clear()
        self.modules.clear()
        self.menu_entries_by_state.clear()
        self.scene_module_by_state.clear()
        self.service_container = NullContainer()
        self.cleanup = DEFAULT_CLEANUP
        self.task_runner = SceneTaskRunner()

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


RUNTIME = SceneRuntime()
