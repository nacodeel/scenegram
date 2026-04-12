from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import uuid4

from aiogram.types import CallbackQuery, Message
from aiogram.utils.formatting import Bold, as_key_value, as_list

from ._utils import maybe_await
from .contracts import BroadcastAdapter, BroadcastReport, MenuContribution, SceneModule
from .patterns import FormField, FormScene
from .ui import Button, Navigate, inline_menu


async def _iterate_recipients(source: Any) -> list[int]:
    if hasattr(source, "__aiter__"):
        result: list[int] = []
        async for item in source:
            result.append(int(item))
        return result
    return [int(item) for item in source]


@dataclass(slots=True)
class BroadcastResult:
    content: str


class BroadcastScene(FormScene):
    __abstract__ = True

    result_model = BroadcastResult
    use_confirm_step = True
    fields = (
        FormField(
            name="content",
            prompt="Введите текст рассылки",
            summary_label="Сообщение",
        ),
    )
    broadcast_adapter_key = "broadcast"
    broadcast_adapter: BroadcastAdapter | None = None
    broadcast_rate_limit = 30
    broadcast_timeout = 5.0
    broadcast_concurrency = 30
    broadcast_title = "Рассылка"
    background_task_name = "scenegram.broadcast"

    async def resolve_broadcast_adapter(self) -> BroadcastAdapter:
        if self.broadcast_adapter is not None:
            return self.broadcast_adapter
        return await self.require_service(self.broadcast_adapter_key)

    async def on_form_submit(self, event: Message | CallbackQuery, result: BroadcastResult) -> Any:
        adapter = await self.resolve_broadcast_adapter()
        task_id = uuid4().hex
        handle = self.runtime.task_runner.spawn(
            self.background_task_name,
            self._run_broadcast_job(task_id, adapter, result.content),
            task_id=task_id,
            metadata={"scene": self.state_id, "module": self.module.name if self.module else None},
        )
        await self.data.update(_broadcast_task_id=handle.id)
        return await self.show(
            event,
            as_list(
                Bold(self.broadcast_title),
                as_key_value("Задача", handle.id),
                as_key_value("Статус", "Запущена"),
                sep="\n\n",
            ),
            reply_markup=inline_menu(
                [[Button(text="🏠 В меню", callback_data=Navigate.home(self.home_scene or ""))]]
            ),
        )

    async def _run_broadcast_job(
        self,
        task_id: str,
        adapter: BroadcastAdapter,
        content: str,
    ) -> None:
        started_at = perf_counter()
        recipients = await _iterate_recipients(await maybe_await(adapter.iter_recipients(self)))
        semaphore = asyncio.Semaphore(max(1, self.broadcast_concurrency))
        sent = 0
        failed = 0
        errors: list[str] = []
        lock = asyncio.Lock()

        async def send_one(recipient_id: int) -> None:
            nonlocal sent, failed
            async with semaphore:
                try:
                    await asyncio.wait_for(
                        adapter.send(self, recipient_id, content),
                        timeout=self.broadcast_timeout,
                    )
                except Exception as exc:  # pragma: no cover - covered through counters
                    async with lock:
                        failed += 1
                        errors.append(f"{recipient_id}: {exc}")
                    return

                async with lock:
                    sent += 1

        tasks: list[asyncio.Task[Any]] = []
        delay = 0.0 if self.broadcast_rate_limit <= 0 else 1 / self.broadcast_rate_limit
        for recipient_id in recipients:
            tasks.append(asyncio.create_task(send_one(recipient_id)))
            if delay:
                await asyncio.sleep(delay)

        if tasks:
            await asyncio.gather(*tasks)

        report = BroadcastReport(
            job_id=task_id,
            total=len(recipients),
            sent=sent,
            failed=failed,
            duration_seconds=round(perf_counter() - started_at, 4),
            errors=tuple(errors),
            metadata={"scene": self.state_id},
        )
        await maybe_await(adapter.on_complete(self, report))
        await maybe_await(self.on_broadcast_complete(report))

    async def on_broadcast_complete(self, report: BroadcastReport) -> None:
        return None


def broadcast_module(
    *,
    name: str,
    package_name: str,
    scene_state: str,
    menu_target: str,
    menu_text: str = "📣 Рассылка",
    menu_row: int | None = None,
    menu_order: int = 100,
    **services: Any,
) -> SceneModule:
    return SceneModule(
        name=name,
        package_name=package_name,
        title="Broadcast",
        description="Portable background broadcast scene pack",
        services=services,
        menu_entries=(
            MenuContribution(
                target_state=menu_target,
                text=menu_text,
                target_scene=scene_state,
                row=menu_row,
                order=menu_order,
            ),
        ),
        tags=frozenset({"broadcast", "background"}),
    )


__all__ = ["BroadcastResult", "BroadcastScene", "broadcast_module"]
