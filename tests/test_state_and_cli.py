from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from scenegram import AppScene, SceneDataProxy, SceneTaskRunner, cb_namespace, state_model
from scenegram.cli import check_packages, render_module_template, render_scene_template


@dataclass(slots=True)
class DraftState:
    name: str | None = None
    email: str | None = None


class DraftScene(AppScene, state="tests.state"):
    __abstract__ = False
    draft = state_model(DraftState, key="_draft", default_factory=DraftState)


@pytest.mark.asyncio
async def test_data_proxy_mutate_commits_single_set_data(wizard) -> None:
    proxy = SceneDataProxy(wizard)

    async with proxy.mutate() as data:
        data["name"] = "Alice"
        data["age"] = 30

    assert wizard.data == {"name": "Alice", "age": 30}
    assert wizard.set_data_calls == [{"name": "Alice", "age": 30}]


@pytest.mark.asyncio
async def test_data_proxy_mutate_can_protect_framework_keys(wizard) -> None:
    wizard.data = {"_scene_stack": ["tests.menu"], "name": "Alice"}
    proxy = SceneDataProxy(wizard)

    with pytest.raises(KeyError, match="Protected scene data key"):
        async with proxy.mutate(protect_reserved=True) as data:
            data["_scene_stack"] = []

    assert wizard.data == {"_scene_stack": ["tests.menu"], "name": "Alice"}


@pytest.mark.asyncio
async def test_state_model_descriptor_get_patch_and_reset(wizard) -> None:
    scene = DraftScene(wizard)

    assert await scene.draft.get() == DraftState()

    await scene.draft.patch(name="Alice")
    assert await scene.draft.get() == DraftState(name="Alice", email=None)

    await scene.draft.set(email="alice@example.com")
    assert await scene.draft.get() == DraftState(name=None, email="alice@example.com")

    await scene.draft.reset()
    assert await scene.draft.get() == DraftState()


def test_callback_namespace_builds_stable_prefix() -> None:
    namespace = cb_namespace("catalog.module")

    assert namespace.callback_prefix("item-open") == namespace.callback_prefix("item-open")
    assert namespace.callback_prefix("item-open").startswith("sg")


def test_cli_renderers_include_requested_values() -> None:
    scene_template = render_scene_template(
        state="common.start",
        class_name="StartScene",
        home_scene="common.home",
    )
    module_template = render_module_template(
        name="catalog",
        package_name="bot.scenes.catalog",
        target_state="catalog.list",
        menu_target="common.start",
    )

    assert 'class StartScene(MenuScene, state="common.start")' in scene_template
    assert 'home_scene = "common.home"' in scene_template
    assert 'name="catalog"' in module_template
    assert 'target_scene="catalog.list"' in module_template


def test_cli_check_packages_reports_discovery_summary() -> None:
    output = check_packages("tests.fixtures.sample_scenes")

    assert "scenegram check ok" in output
    assert "scenes: 3" in output


@pytest.mark.asyncio
async def test_task_runner_tracks_finished_and_cancelled_tasks() -> None:
    runner = SceneTaskRunner()

    async def finish() -> str:
        return "ok"

    async def wait_forever() -> None:
        await asyncio.sleep(10)

    finished = runner.spawn("finish", finish())
    cancelled = runner.spawn("cancel", wait_forever())

    await finished.task
    assert runner.get(finished.id).status == "finished"
    assert runner.active() == [cancelled]

    assert runner.cancel(cancelled.id) is True
    await asyncio.gather(cancelled.task, return_exceptions=True)
    assert runner.get(cancelled.id).status == "cancelled"
