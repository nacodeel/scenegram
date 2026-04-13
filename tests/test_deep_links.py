from __future__ import annotations

from types import SimpleNamespace

import pytest

from scenegram import (
    AppScene,
    DeepLinkExhaustedError,
    DeepLinkManager,
    DeepLinkMenuScene,
    DeepLinkPolicy,
    DeepLinkSignatureError,
    InMemoryDeepLinkStore,
    create_scenes_router,
    deep_link_scene,
)
from scenegram.runtime import RUNTIME

from .conftest import FakeBot, FakeMessage


class DeepLinkBot(FakeBot):
    async def me(self):
        return SimpleNamespace(username="ScenegramBot")


def extract_start_arg(link: str) -> str:
    return link.split("=", 1)[1]


class PlainStartScene(DeepLinkMenuScene, state="common.start"):
    __abstract__ = False
    menu_text = "Главное меню"


class ProductStartScene(DeepLinkMenuScene, state="product.start"):
    __abstract__ = False
    menu_text = "Product start"
    deep_links = (
        deep_link_scene(
            "product.open",
            "catalog.detail",
            payload_key="item_id",
            back_target="catalog.list",
        ),
    )


class DummyTargetScene(AppScene, state="catalog.detail"):
    __abstract__ = False


@pytest.mark.asyncio
async def test_deep_link_menu_scene_plain_start_renders_menu(wizard) -> None:
    scene = PlainStartScene(wizard)
    message = FakeMessage(bot=DeepLinkBot(), text="/start")
    message.from_user = SimpleNamespace(id=100)

    await scene.handle_start_entry(message)

    assert message.answer_calls
    assert message.answer_calls[0]["text"] == "Главное меню"


@pytest.mark.asyncio
async def test_scene_link_uses_signed_inline_when_secret_is_configured() -> None:
    RUNTIME.deep_link_secret = "super-secret"
    RUNTIME.deep_link_store = InMemoryDeepLinkStore()

    from scenegram.deep_links import INLINE_SIGNED_PREFIX

    link = await DeepLinkManager(bot=DeepLinkBot()).create(
        "p",
        "s",
        policy=DeepLinkPolicy(strategy="signed"),
    )
    token = extract_start_arg(link)
    context = await DeepLinkManager(bot=DeepLinkBot()).resolve_token(token, user_id=100)

    assert token.startswith(INLINE_SIGNED_PREFIX)
    assert context.route == "p"
    assert context.transport == "signed"
    assert context.payload == "s"


@pytest.mark.asyncio
async def test_one_time_scene_link_falls_back_to_store_and_consumes_once() -> None:
    RUNTIME.deep_link_store = InMemoryDeepLinkStore()

    from scenegram.deep_links import STORED_PREFIX

    link = await DeepLinkManager(bot=DeepLinkBot()).one_time_scene(
        "catalog.detail",
        payload={"item_id": "starter"},
    )
    token = extract_start_arg(link)

    assert token.startswith(STORED_PREFIX)

    manager = DeepLinkManager(bot=DeepLinkBot())
    context = await manager.resolve_token(token, user_id=42)
    assert context.transport == "stored"
    assert context.payload["scene"] == "catalog.detail"

    with pytest.raises(DeepLinkExhaustedError):
        await manager.resolve_token(token, user_id=42)


@pytest.mark.asyncio
async def test_signed_strategy_without_secret_raises() -> None:
    RUNTIME.deep_link_secret = None
    RUNTIME.deep_link_store = InMemoryDeepLinkStore()

    with pytest.raises(DeepLinkSignatureError):
        await DeepLinkManager(bot=DeepLinkBot()).create(
            "custom.route",
            {"value": "x"},
            policy=DeepLinkPolicy(strategy="signed"),
        )


@pytest.mark.asyncio
async def test_dispatch_scene_route_sets_back_target_and_navigates(wizard) -> None:
    RUNTIME.deep_link_store = InMemoryDeepLinkStore()
    RUNTIME.register_deep_link_routes(ProductStartScene.deep_links)

    scene = ProductStartScene(wizard)
    message = FakeMessage(bot=DeepLinkBot(), text="/start")
    message.from_user = SimpleNamespace(id=100)

    link = await scene.deep_links.create(
        "product.open",
        "starter",
        bot=DeepLinkBot(),
        secure=False,
    )
    token = extract_start_arg(link)

    await scene.deep_links.dispatch(message, token)

    assert wizard.data["_back_target"] == "catalog.list"
    assert wizard.manager.enter_calls[-1][0] == "catalog.detail"
    assert wizard.manager.enter_calls[-1][2] == {"item_id": "starter"}


def test_create_scenes_router_registers_deep_link_routes() -> None:
    create_scenes_router(
        package_name="tests.fixtures.deep_link_scenes",
        default_home="deep.start",
    )

    assert set(RUNTIME.deep_link_routes) == {"fixture.module", "fixture.scene"}
    assert RUNTIME.deep_link_routes["fixture.scene"].scene == "deep.target"
