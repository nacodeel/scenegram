from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TaskHandle:
    id: str
    name: str
    task: asyncio.Task[Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SceneTaskRunner:
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
        task.add_done_callback(lambda _: self.tasks.pop(task_id, None))
        return handle

    def get(self, task_id: str) -> TaskHandle | None:
        return self.tasks.get(task_id)

    def active(self) -> list[TaskHandle]:
        return list(self.tasks.values())
