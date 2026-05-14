from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class Navigate(CallbackData, prefix="nav"):
    action: str
    target: str

    @classmethod
    def open(cls, target: str) -> Navigate:
        return cls(action="open", target=target)

    @classmethod
    def back(cls, target: str = "") -> Navigate:
        return cls(action="back", target=target)

    @classmethod
    def home(cls, target: str = "") -> Navigate:
        return cls(action="home", target=target)

    @classmethod
    def cancel(cls, target: str = "") -> Navigate:
        return cls(action="cancel", target=target)


class PageNav(CallbackData, prefix="page"):
    page: int
