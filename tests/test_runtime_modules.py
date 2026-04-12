from __future__ import annotations

import pytest

from scenegram import (
    RUNTIME,
    BroadcastReport,
    BroadcastResult,
    BroadcastScene,
    broadcast_module,
    crud_module,
)


class BroadcastAdapterStub:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.reports: list[BroadcastReport] = []

    async def iter_recipients(self, scene):
        return [101, 102, 103]

    async def send(self, scene, recipient_id: int, content: str) -> None:
        self.sent.append((recipient_id, content))

    async def on_complete(self, scene, report: BroadcastReport) -> None:
        self.reports.append(report)


class DemoBroadcastScene(BroadcastScene, state="tests.broadcast"):
    __abstract__ = False
    broadcast_concurrency = 2
    broadcast_rate_limit = 0
    broadcast_timeout = 1.0

    def __init__(self, wizard, adapter: BroadcastAdapterStub) -> None:
        super().__init__(wizard)
        self.broadcast_adapter = adapter
        self.completed_report: BroadcastReport | None = None

    async def on_broadcast_complete(self, report: BroadcastReport) -> None:
        self.completed_report = report


def test_crud_module_builds_portable_menu_manifest() -> None:
    module = crud_module(
        name="catalog",
        package_name="bot.scenes.catalog",
        list_state="catalog.list",
        menu_target="common.start",
        menu_text="Каталог",
        crud="adapter",
    )

    assert module.name == "catalog"
    assert module.services["crud"] == "adapter"
    assert module.menu_entries[0].target_scene == "catalog.list"
    assert module.metadata["list_state"] == "catalog.list"


def test_broadcast_module_builds_portable_menu_manifest() -> None:
    module = broadcast_module(
        name="broadcast",
        package_name="bot.scenes.broadcast",
        scene_state="admin.broadcast",
        menu_target="admin.dashboard",
        menu_text="Рассылка",
        broadcast="adapter",
    )

    assert module.name == "broadcast"
    assert module.services["broadcast"] == "adapter"
    assert module.menu_entries[0].target_scene == "admin.broadcast"


@pytest.mark.asyncio
async def test_broadcast_scene_spawns_background_job_and_reports_real_task_id(wizard) -> None:
    from tests.conftest import FakeMessage

    adapter = BroadcastAdapterStub()
    scene = DemoBroadcastScene(wizard, adapter)
    message = FakeMessage()

    await scene.on_form_submit(message, BroadcastResult(content="Hello"))

    task_id = wizard.data["_broadcast_task_id"]
    handle = RUNTIME.task_runner.get(task_id)

    assert handle is not None
    assert handle.metadata["scene"] == "tests.broadcast"
    assert handle.metadata["module"] is None

    await handle.task

    assert adapter.sent == [(101, "Hello"), (102, "Hello"), (103, "Hello")]
    assert adapter.reports[0].job_id == task_id
    assert scene.completed_report is not None
    assert scene.completed_report.job_id == task_id
