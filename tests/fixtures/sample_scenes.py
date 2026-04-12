from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from scenegram import (
    AppScene,
    Button,
    MenuContribution,
    MenuScene,
    PaginatedScene,
    SceneModule,
    SceneRole,
    command_entry,
)

SCENEGRAM_MODULE = SceneModule(
    name="fixtures.sample",
    package_name="tests.fixtures.sample_scenes",
    title="Fixture Scenes",
    description="Fixture module used by bootstrap tests",
    services={"sample_service": lambda: "module-value"},
    menu_entries=(
        MenuContribution(
            target_state="common.home",
            text="Каталог",
            target_scene="common.catalog",
            row=0,
            order=20,
        ),
    ),
    metadata={"kind": "fixtures"},
)


class HomeScene(MenuScene, state="common.home"):
    __abstract__ = False
    menu_text = "Home"
    static_rows = ((Button(text="Catalog"),),)
    home_for_roles = frozenset({SceneRole.USER.value})


class AdminScene(AppScene, state="admin.dashboard"):
    __abstract__ = False
    roles = frozenset({SceneRole.ADMIN.value})
    home_for_roles = frozenset({SceneRole.ADMIN.value})
    entrypoints = (command_entry("admin"),)


class CatalogScene(PaginatedScene, state="common.catalog"):
    __abstract__ = False

    async def render_page(self, event: Message | CallbackQuery, *, page: int = 1):
        return page
