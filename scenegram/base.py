from __future__ import annotations

import inspect
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass
from typing import Any, TypeVar

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.scene import Scene, on
from aiogram.types import CallbackQuery, Message

from .formatting import RenderableText, render_text
from .roles import SceneRole, normalize_role, normalize_roles
from .runtime import RUNTIME
from .ui.callbacks import Navigate

ModelT = TypeVar("ModelT")


class SceneDataProxy:
    def __init__(self, wizard: Any) -> None:
        self._wizard = wizard

    async def all(self) -> dict[str, Any]:
        return await self._wizard.get_data()

    async def get(self, key: str, default: Any | None = None) -> Any | None:
        return await self._wizard.get_value(key, default)

    async def pick(self, *keys: str) -> tuple[Any, ...]:
        data = await self.all()
        return tuple(data.get(key) for key in keys)

    async def require(self, key: str) -> Any:
        value = await self.get(key)
        if value is None:
            raise KeyError(f"Missing required scene data key: {key}")
        return value

    async def require_many(self, *keys: str) -> tuple[Any, ...]:
        values = []
        for key in keys:
            values.append(await self.require(key))
        return tuple(values)

    async def update(
        self,
        data: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if data is not None:
            return await self._wizard.update_data(data=dict(data), **kwargs)
        return await self._wizard.update_data(**kwargs)

    async def set(
        self,
        data: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        payload = dict(data or {})
        payload.update(kwargs)
        await self._wizard.set_data(payload)

    async def clear(self) -> None:
        await self._wizard.clear_data()

    async def pop(self, *keys: str, default: Any | None = None) -> Any:
        current = await self.all()
        values = tuple(current.pop(key, default) for key in keys)
        await self._wizard.set_data(current)
        if len(values) == 1:
            return values[0]
        return values

    async def discard(self, *keys: str) -> None:
        current = await self.all()
        for key in keys:
            current.pop(key, None)
        await self._wizard.set_data(current)

    async def model(self, model_cls: type[ModelT]) -> ModelT:
        data = await self.all()

        if hasattr(model_cls, "model_validate"):
            return model_cls.model_validate(data)

        if is_dataclass(model_cls):
            allowed = {field.name for field in fields(model_cls)}
            return model_cls(**{key: value for key, value in data.items() if key in allowed})

        return model_cls(**data)


class SceneNavigator:
    def __init__(self, scene: AppScene) -> None:
        self.scene = scene

    async def to(self, target: type[Scene] | str, **kwargs: Any) -> None:
        await self.scene.wizard.goto(target, **kwargs)

    async def back(self, **kwargs: Any) -> None:
        await self.scene.wizard.back(**kwargs)

    async def retake(self, **kwargs: Any) -> None:
        await self.scene.wizard.retake(**kwargs)

    async def exit(self, **kwargs: Any) -> None:
        await self.scene.wizard.exit(**kwargs)

    async def home(self, **kwargs: Any) -> None:
        target = self.scene.home_scene or RUNTIME.default_home
        if target:
            await self.to(target, **kwargs)
            return
        await self.exit(**kwargs)

    async def role_home(self, role: SceneRole | str, **kwargs: Any) -> None:
        target = (
            RUNTIME.home_by_role.get(normalize_role(role))
            or self.scene.home_scene
            or RUNTIME.default_home
        )
        if target:
            await self.to(target, **kwargs)
            return
        await self.exit(**kwargs)


class AppScene(Scene, reset_history_on_enter=False):
    __abstract__ = True
    entrypoints: tuple[Any, ...] = ()
    roles = frozenset({SceneRole.ANY.value})
    home_for_roles = frozenset()
    home_scene: str | None = None

    def __init__(self, wizard: Any) -> None:
        super().__init__(wizard)
        self.data = SceneDataProxy(wizard)
        self.nav = SceneNavigator(self)

    async def show(
        self,
        event: Message | CallbackQuery,
        content: RenderableText | None,
        *,
        reply_markup: Any | None = None,
        remember: bool = True,
        replace_parse_mode: bool = True,
        **kwargs: Any,
    ) -> Any:
        payload = render_text(content, replace_parse_mode=replace_parse_mode)
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        payload.update(kwargs)

        if isinstance(event, CallbackQuery):
            return await self._show_callback(event, payload, remember=remember)

        await self._cleanup_previous_message(event)
        message = await event.answer(**payload)
        return await self._remember_screen(message, remember=remember)

    async def cleanup_screen(self, message: Message) -> None:
        previous_message_id = await self.data.get("_screen_message_id")
        if previous_message_id and getattr(message, "bot", None):
            try:
                await message.bot.delete_message(message.chat.id, previous_message_id)
            except TelegramBadRequest:
                pass

    async def resolve_roles(self, event: Any) -> set[str]:
        if RUNTIME.role_resolver is None:
            return {SceneRole.USER.value}

        resolved = RUNTIME.role_resolver(event)
        if inspect.isawaitable(resolved):
            resolved = await resolved

        if resolved is None:
            return set()
        if isinstance(resolved, str):
            return {normalize_role(resolved)}
        return {normalize_role(role) for role in resolved}

    async def has_any_role(self, event: Any, roles: Iterable[SceneRole | str]) -> bool:
        allowed = normalize_roles(roles)
        resolved = await self.resolve_roles(event)
        return bool(resolved & allowed)

    @on.callback_query(Navigate.filter(F.action == "open"))
    async def _navigate_open(self, call: CallbackQuery, callback_data: Navigate) -> None:
        await call.answer()
        await self.nav.to(callback_data.target)

    @on.callback_query(Navigate.filter(F.action == "back"))
    async def _navigate_back(self, call: CallbackQuery, callback_data: Navigate) -> None:
        await call.answer()
        if callback_data.target:
            await self.nav.to(callback_data.target)
            return
        await self.nav.back()

    @on.callback_query(Navigate.filter(F.action == "home"))
    async def _navigate_home(self, call: CallbackQuery, callback_data: Navigate) -> None:
        await call.answer()
        if callback_data.target:
            await self.nav.to(callback_data.target)
            return
        await self.nav.home()

    @on.callback_query(Navigate.filter(F.action == "cancel"))
    async def _navigate_cancel(self, call: CallbackQuery, callback_data: Navigate) -> None:
        await call.answer("Отменено")
        if callback_data.target:
            await self.nav.to(callback_data.target)
            return
        await self.nav.home()

    @on.callback_query(F.data == "noop")
    async def _noop(self, call: CallbackQuery) -> None:
        await call.answer()

    @on.message(Command("cancel"))
    async def _cancel_command(self, message: Message) -> None:
        await self.nav.home()

    @on.message(F.text == "Отмена")
    async def _cancel_text(self, message: Message) -> None:
        await self.nav.home()

    @on.message(F.text == "Назад")
    async def _back_text(self, message: Message) -> None:
        await self.nav.back()

    async def _show_callback(
        self,
        call: CallbackQuery,
        payload: dict[str, Any],
        *,
        remember: bool,
    ) -> Any:
        if call.message is None:
            raise RuntimeError("CallbackQuery without message is not supported by AppScene.show")

        try:
            message = await call.message.edit_text(**payload)
        except TelegramBadRequest:
            message = await call.message.answer(**payload)

        return await self._remember_screen(message, remember=remember)

    async def _cleanup_previous_message(self, message: Message) -> None:
        previous_message_id = await self.data.get("_screen_message_id")
        if previous_message_id and getattr(message, "bot", None):
            try:
                await message.bot.delete_message(message.chat.id, previous_message_id)
            except TelegramBadRequest:
                pass

    async def _remember_screen(self, message: Any, *, remember: bool) -> Any:
        if remember and hasattr(message, "message_id"):
            await self.data.update(_screen_message_id=message.message_id)
        return message
