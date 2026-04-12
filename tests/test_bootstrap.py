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
)
from scenegram.runtime import RUNTIME


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
