from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from .callbacks import Navigate


@dataclass(slots=True)
class Button:
    text: str
    callback_data: CallbackData | str | None = None
    url: str | None = None
    api_kwargs: Mapping[str, Any] | None = None


@dataclass(slots=True)
class ReplyButton:
    text: str
    api_kwargs: Mapping[str, Any] | None = None


def _pack_callback(callback_data: CallbackData | str | None) -> str | None:
    if callback_data is None:
        return None
    if isinstance(callback_data, str):
        return callback_data
    return callback_data.pack()


def inline_menu(rows: Sequence[Sequence[Button]]) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for row in rows:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=button.text,
                    callback_data=_pack_callback(button.callback_data),
                    url=button.url,
                    **dict(button.api_kwargs or {}),
                )
                for button in row
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def nav_row(
    *,
    back: bool = True,
    home: bool = False,
    cancel: bool = False,
    home_target: str = "",
) -> list[Button]:
    buttons: list[Button] = []
    if back:
        buttons.append(Button(text="⬅️ Назад", callback_data=Navigate.back()))
    if home:
        buttons.append(Button(text="🏠 Домой", callback_data=Navigate.home(home_target)))
    if cancel:
        buttons.append(Button(text="✖️ Отмена", callback_data=Navigate.cancel(home_target)))
    return buttons


def noop_button(text: str) -> Button:
    return Button(text=text, callback_data="noop")


def reply_menu(
    rows: Sequence[Sequence[ReplyButton]],
    *,
    resize_keyboard: bool = True,
) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=button.text, **dict(button.api_kwargs or {})) for button in row]
        for row in rows
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=resize_keyboard)
