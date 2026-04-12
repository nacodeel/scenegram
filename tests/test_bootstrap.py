from __future__ import annotations

from types import SimpleNamespace

import pytest

from scenegram import AppScene, SceneRole
from scenegram.bootstrap import (
    RoleAllowed,
    command_entry,
    create_scenes_router,
    discover_scene_classes,
    discover_scene_descriptors,
    discover_scene_modules,
)
from scenegram.contracts import scene_middleware
from scenegram.runtime import RUNTIME


class TaggedMiddleware:
    def __init__(self, tag: str) -> None:
        self.tag = tag

    async def __call__(self, handler, event, data):
        return await handler(event, data)


def test_discover_scene_descriptors_returns_sorted_states() -> None:
    descriptors = discover_scene_descriptors("tests.fixtures.sample_scenes", AppScene)

    assert [descriptor.state for descriptor in descriptors] == [
        "admin.dashboard",
        "common.catalog",
        "common.home",
    ]


def test_discover_scene_classes_matches_descriptors() -> None:
    descriptors = discover_scene_descriptors("tests.fixtures.sample_scenes", AppScene)
    scenes = discover_scene_classes("tests.fixtures.sample_scenes", AppScene)

    assert scenes == [descriptor.scene for descriptor in descriptors]


def test_create_scenes_router_returns_scene_map() -> None:
    result = create_scenes_router(
        package_name="tests.fixtures.sample_scenes",
        default_home="common.home",
    )

    assert sorted(result.scene_map) == ["admin.dashboard", "common.catalog", "common.home"]
    assert result.scenes == list(result.scene_map.values())
    assert sorted(result.modules) == ["fixtures.sample"]
    assert result.modules["fixtures.sample"].metadata["kind"] == "fixtures"


def test_create_scenes_router_accepts_multiple_packages() -> None:
    result = create_scenes_router(
        package_name=("tests.fixtures.sample_scenes", "tests.fixtures.extra_scenes"),
        default_home="common.home",
    )

    assert sorted(result.scene_map) == [
        "admin.dashboard",
        "common.catalog",
        "common.home",
        "manager.dashboard",
    ]


def test_create_scenes_router_registers_role_homes() -> None:
    create_scenes_router(
        package_name=("tests.fixtures.sample_scenes", "tests.fixtures.extra_scenes"),
        default_home="common.home",
    )

    assert RUNTIME.home_by_role == {
        SceneRole.ADMIN.value: "admin.dashboard",
        SceneRole.MANAGER.value: "manager.dashboard",
        SceneRole.USER.value: "common.home",
    }


def test_discover_scene_modules_reads_scenegram_module_manifest() -> None:
    modules = discover_scene_modules("tests.fixtures.sample_scenes")

    assert sorted(modules) == ["fixtures.sample"]
    assert modules["fixtures.sample"].package_name == "tests.fixtures.sample_scenes"


def test_create_scenes_router_applies_global_module_and_scene_middlewares() -> None:
    result = create_scenes_router(
        package_name="tests.fixtures.sample_scenes",
        middlewares=(
            scene_middleware(
                lambda *, scene=None, module=None: TaggedMiddleware(
                    f"global:{scene.__name__}:{module.name if module else 'none'}"
                ),
                "message",
                factory=True,
            ),
        ),
    )

    scene_router = next(
        router for router in result.router.sub_routers if router.name == "scene:common.home"
    )
    tags = [middleware.tag for middleware in scene_router.message.outer_middleware._middlewares]

    assert tags == [
        "global:HomeScene:fixtures.sample",
        "module:fixtures.sample:HomeScene",
        "scene:HomeScene",
    ]


def test_command_entry_requires_at_least_one_command() -> None:
    with pytest.raises(ValueError):
        command_entry()


@pytest.mark.asyncio
async def test_role_allowed_accepts_sync_role_resolver() -> None:
    filter_ = RoleAllowed(lambda event: {SceneRole.ADMIN.value}, {SceneRole.ADMIN.value})
    event = SimpleNamespace(from_user=SimpleNamespace(id=1))

    assert await filter_(event) is True


@pytest.mark.asyncio
async def test_role_allowed_rejects_unknown_user() -> None:
    filter_ = RoleAllowed(lambda event: {SceneRole.ADMIN.value}, {SceneRole.ADMIN.value})
    event = SimpleNamespace(message=SimpleNamespace(from_user=None))

    assert await filter_(event) is False


@pytest.mark.asyncio
async def test_role_allowed_accepts_async_role_resolver() -> None:
    async def resolve_roles(event):
        return {SceneRole.MANAGER.value}

    filter_ = RoleAllowed(resolve_roles, {SceneRole.MANAGER.value})
    event = SimpleNamespace(from_user=SimpleNamespace(id=1))

    assert await filter_(event) is True


@pytest.mark.asyncio
async def test_role_allowed_rejects_non_matching_role() -> None:
    filter_ = RoleAllowed(lambda event: {SceneRole.USER.value}, {SceneRole.ADMIN.value})
    event = SimpleNamespace(from_user=SimpleNamespace(id=1))

    assert await filter_(event) is False
