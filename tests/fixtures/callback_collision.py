from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class FirstCollision(CallbackData, prefix="dup"):
    value: str


class SecondCollision(CallbackData, prefix="dup"):
    value: str
