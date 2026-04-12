from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from scenegram import AppScene, Button, MenuScene, PaginatedScene, SceneRole, command_entry


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
