from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from ._utils import maybe_await


@dataclass(slots=True)
class TaskHandle:
    id: str
    name: str
    task: asyncio.Task[Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    status: str = "running"
    started_at: float = field(default_factory=perf_counter)
    finished_at: float | None = None
    error: str | None = None


@dataclass(slots=True)
class SceneTaskRunner:
    observer: Any | None = None
    tasks: dict[str, TaskHandle] = field(default_factory=dict)

    def spawn(
        self,
        name: str,
        coroutine: Coroutine[Any, Any, Any],
        *,
        task_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> TaskHandle:
        task_id = task_id or uuid.uuid4().hex
        task = asyncio.create_task(coroutine, name=name)
        handle = TaskHandle(id=task_id, name=name, task=task, metadata=dict(metadata or {}))
        self.tasks[task_id] = handle
        task.add_done_callback(lambda _: self._finalize(handle))
        self._notify("spawned", handle)
        return handle

    def get(self, task_id: str) -> TaskHandle | None:
        return self.tasks.get(task_id)

    def active(self) -> list[TaskHandle]:
        return [handle for handle in self.tasks.values() if handle.status == "running"]

    def forget(self, task_id: str) -> None:
        self.tasks.pop(task_id, None)

    def cancel(self, task_id: str) -> bool:
        handle = self.tasks.get(task_id)
        if handle is None or handle.task.done():
            return False
        handle.task.cancel()
        self._notify("cancel_requested", handle)
        return True

    def _finalize(self, handle: TaskHandle) -> None:
        handle.finished_at = perf_counter()
        if handle.task.cancelled():
            handle.status = "cancelled"
            self._notify("cancelled", handle)
            return
        error = handle.task.exception()
        if error is not None:
            handle.status = "failed"
            handle.error = repr(error)
            self._notify("failed", handle, error)
            return
        handle.status = "finished"
        self._notify("finished", handle)

    def _notify(
        self,
        event_name: str,
        handle: TaskHandle,
        error: BaseException | None = None,
    ) -> None:
        if self.observer is None:
            return
        result = self.observer(event_name, handle, error)
        if asyncio.iscoroutine(result):
            asyncio.create_task(maybe_await(result))
