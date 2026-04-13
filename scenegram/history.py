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


class SceneStackProxy:
    def __init__(self, data_proxy: Any, *, key: str = "_scene_stack") -> None:
        self._data = data_proxy
        self._key = key

    async def states(self) -> list[str]:
        raw = await self._data.get(self._key, [])
        return [str(state) for state in raw if isinstance(state, str) and state]

    async def set(self, states: list[str]) -> None:
        normalized = [str(state) for state in states if state]
        await self._data.update({self._key: normalized})

    async def clear(self) -> None:
        await self.set([])

    async def current(self) -> str | None:
        states = await self.states()
        if not states:
            return None
        return states[-1]

    async def ensure(self, state: str) -> list[str]:
        states = await self.states()
        if not states or states[-1] != state:
            states.append(state)
            await self.set(states)
        return states

    async def push(self, state: str) -> list[str]:
        return await self.ensure(state)

    async def replace_current(self, state: str) -> list[str]:
        states = await self.states()
        if states:
            states[-1] = state
        else:
            states.append(state)
        await self.set(states)
        return states

    async def reset(self, state: str) -> list[str]:
        states = [state]
        await self.set(states)
        return states

    async def pop(self) -> str | None:
        states = await self.states()
        if not states:
            return None
        current = states.pop()
        await self.set(states)
        return current

    async def back_target(self, current_state: str) -> str | None:
        states = await self.states()
        if len(states) < 2:
            return None
        if states[-1] != current_state:
            return states[-1]
        return states[-2]

    async def previous_before(self, target_state: str) -> str | None:
        states = await self.states()
        for index in range(len(states) - 1, -1, -1):
            if states[index] != target_state:
                continue
            if index == 0:
                return None
            return states[index - 1]
        return None
