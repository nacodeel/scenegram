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
    scene_middleware,
)


class TaggedMiddleware:
    def __init__(self, tag: str) -> None:
        self.tag = tag

    async def __call__(self, handler, event, data):
        return await handler(event, data)


def build_module_message_middleware(*, scene=None, module=None):
    return TaggedMiddleware(f"module:{module.name}:{scene.__name__}")


def build_scene_message_middleware(*, scene=None, module=None):
    return TaggedMiddleware(f"scene:{scene.__name__}")

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
    middlewares=(scene_middleware(build_module_message_middleware, "message", factory=True),),
    metadata={"kind": "fixtures"},
)


class HomeScene(MenuScene, state="common.home"):
    __abstract__ = False
    menu_text = "Home"
    static_rows = ((Button(text="Catalog"),),)
    home_for_roles = frozenset({SceneRole.USER.value})
    middlewares = (scene_middleware(build_scene_message_middleware, "message", factory=True),)


class AdminScene(AppScene, state="admin.dashboard"):
    __abstract__ = False
    roles = frozenset({SceneRole.ADMIN.value})
    home_for_roles = frozenset({SceneRole.ADMIN.value})
    entrypoints = (command_entry("admin"),)


class CatalogScene(PaginatedScene, state="common.catalog"):
    __abstract__ = False

    async def render_page(self, event: Message | CallbackQuery, *, page: int = 1):
        return page
