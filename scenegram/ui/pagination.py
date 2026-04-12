from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil
from typing import Any, TypeVar

from aiogram.fsm.scene import on
from aiogram.types import CallbackQuery, Message

from ..base import AppScene
from .callbacks import PageNav
from .keyboards import Button, nav_row, noop_button

ItemT = TypeVar("ItemT")


@dataclass(slots=True)
class PageWindow[ItemT]:
    items: Sequence[ItemT]
    page: int
    pages: int
    total: int
    per_page: int
    prev_page: int
    next_page: int


class PaginatedScene(AppScene):
    __abstract__ = True
    page_size = 8
    page_state_key = "_page"
    initial_page = 1

    @on.message.enter()
    async def _on_message_enter(self, message: Message) -> None:
        page = await self.current_page(default=self.initial_page)
        await self.render_page(message, page=page)

    @on.callback_query.enter()
    async def _on_callback_enter(self, call: CallbackQuery) -> None:
        await call.answer()
        page = await self.current_page(default=self.initial_page)
        await self.render_page(call, page=page)

    @on.callback_query(PageNav.filter())
    async def _switch_page(self, call: CallbackQuery, callback_data: PageNav) -> None:
        await call.answer()
        await self.remember_page(callback_data.page)
        await self.render_page(call, page=callback_data.page)

    async def render_page(self, event: Message | CallbackQuery, *, page: int = 1) -> Any:
        raise NotImplementedError

    async def current_page(self, default: int = 1) -> int:
        page = await self.data.get(self.page_state_key, default)
        if not isinstance(page, int) or page < 1:
            return default
        return page

    async def remember_page(self, page: int) -> None:
        await self.data.update({self.page_state_key: max(page, 1)})


def paginate[ItemT](items: Sequence[ItemT], page: int, *, per_page: int = 8) -> PageWindow[ItemT]:
    if per_page < 1:
        raise ValueError("per_page must be greater than zero")
    pages = max(1, ceil(len(items) / per_page))
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    end = start + per_page

    prev_page = page - 1 if page > 1 else pages
    next_page = page + 1 if page < pages else 1

    return PageWindow(
        items=items[start:end],
        page=page,
        pages=pages,
        total=len(items),
        per_page=per_page,
        prev_page=prev_page,
        next_page=next_page,
    )


def pager_rows(
    window: PageWindow[Any],
    *,
    back: bool = True,
    home: bool = True,
    cancel: bool = False,
    home_target: str = "",
) -> list[list[Button]]:
    rows: list[list[Button]] = []

    if window.pages > 1:
        rows.append(
            [
                Button(text="◀️", callback_data=PageNav(page=window.prev_page)),
                noop_button(f"{window.page}/{window.pages}"),
                Button(text="▶️", callback_data=PageNav(page=window.next_page)),
            ]
        )

    navigation = nav_row(back=back, home=home, cancel=cancel, home_target=home_target)
    if navigation:
        rows.append(navigation)

    return rows
