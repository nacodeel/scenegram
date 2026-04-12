from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .contracts import BreadcrumbItem


class SceneHistoryProxy:
    def __init__(self, data_proxy: Any, *, key: str = "_history") -> None:
        self._data = data_proxy
        self._key = key

    async def trail(self) -> list[BreadcrumbItem]:
        raw = await self._data.get(self._key, [])
        return [
            BreadcrumbItem(
                state=item["state"],
                label=item["label"],
                payload=item.get("payload", {}),
            )
            for item in raw
        ]

    async def set(self, items: list[BreadcrumbItem]) -> None:
        await self._data.update({self._key: [asdict(item) for item in items]})

    async def clear(self) -> None:
        await self.set([])

    async def push(self, state: str, label: str, *, payload: dict[str, Any] | None = None) -> None:
        trail = await self.trail()
        trail.append(BreadcrumbItem(state=state, label=label, payload=payload or {}))
        await self.set(trail)

    async def replace_current(
        self,
        state: str,
        label: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        trail = await self.trail()
        item = BreadcrumbItem(state=state, label=label, payload=payload or {})
        if trail and trail[-1].state == state:
            trail[-1] = item
        else:
            trail.append(item)
        await self.set(trail)

    async def pop(self) -> BreadcrumbItem | None:
        trail = await self.trail()
        if not trail:
            return None
        item = trail.pop()
        await self.set(trail)
        return item

    async def text(self, separator: str = " / ") -> str:
        trail = await self.trail()
        return separator.join(item.label for item in trail)
