from __future__ import annotations

import inspect
from collections.abc import Iterable, Mapping
from contextlib import asynccontextmanager
from dataclasses import fields, is_dataclass
from typing import Any, TypeVar

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.scene import Scene, on
from aiogram.types import CallbackQuery, Message

try:
    from aiogram.utils.chat_action import ChatActionSender
except ImportError:  # pragma: no cover
    ChatActionSender = None

from ._utils import call_with_optional_args
from .contracts import SceneActionConfig, SceneCleanup, SceneModule
from .di import UNSET, MissingServiceError, resolve_service_value
from .formatting import RenderableText, render_text
from .history import SceneHistoryProxy
from .roles import SceneRole, normalize_role, normalize_roles
from .runtime import RUNTIME
from .ui.callbacks import Navigate

ModelT = TypeVar("ModelT")
BACK_TARGET_HOME = "__scenegram_home__"


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


class SceneServicesProxy:
    def __init__(self, scene: AppScene) -> None:
        self.scene = scene

    async def get(self, key: str, default: Any | None = None) -> Any:
        return await self.scene.resolve_service(key, default=default)

    async def require(self, key: str) -> Any:
        return await self.scene.require_service(key)

    async def call(self, key: str, *args: Any) -> Any:
        binding = self.scene.service_binding(key)
        if callable(binding):
            result = await call_with_optional_args(binding, *args)
            if callable(result):
                return await call_with_optional_args(result, *args)
            return result

        raise TypeError(f"Service '{key}' is not callable")


class SceneNavigator:
    def __init__(self, scene: AppScene) -> None:
        self.scene = scene

    async def to(self, target: type[Scene] | str, **kwargs: Any) -> None:
        await self.scene.wizard.goto(target, **kwargs)

    async def replace(
        self,
        target: type[Scene] | str,
        *,
        reset_history: bool = False,
        **kwargs: Any,
    ) -> None:
        manager = getattr(self.scene.wizard, "manager", None)
        history = getattr(manager, "history", None)

        if history is not None and reset_history and hasattr(history, "clear"):
            await history.clear()

        await self.scene.wizard.leave(_with_history=False, **kwargs)
        if manager is None or not hasattr(manager, "enter"):
            await self.scene.wizard.goto(target, **kwargs)
            return
        await manager.enter(target, _check_active=False, **kwargs)

    async def back(self, **kwargs: Any) -> None:
        target = await self.scene.data.pop("_back_target", default=None)
        if target:
            if target == BACK_TARGET_HOME:
                await self.home(**kwargs)
                return
            await self.to(str(target), **kwargs)
            return
        await self.scene.history.pop()
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

    async def stack_states(self) -> list[str]:
        manager = getattr(self.scene.wizard, "manager", None)
        history = getattr(manager, "history", None)
        if history is None or not hasattr(history, "all"):
            return []

        records = await history.all()
        states: list[str] = []
        for record in records:
            state = getattr(record, "state", None)
            if isinstance(state, str):
                states.append(state)
        return states

    async def previous_scene_state(self, *, skip: int = 0) -> str | None:
        states = await self.stack_states()
        index = len(states) - 1 - skip
        if index < 0:
            return None
        return states[index]

    async def previous_before(self, target_state: str) -> str | None:
        states = await self.stack_states()
        for index in range(len(states) - 1, -1, -1):
            if states[index] != target_state:
                continue
            if index == 0:
                return None
            return states[index - 1]
        return None


class AppScene(Scene, reset_history_on_enter=False):
    __abstract__ = True
    entrypoints: tuple[Any, ...] = ()
    roles = frozenset({SceneRole.ANY.value})
    home_for_roles = frozenset()
    home_scene: str | None = None
    scene_module: str | None = None
    cleanup = SceneCleanup()
    breadcrumb: str | None = None
    default_chat_action: str | SceneActionConfig | None = None
    chat_actions: Mapping[str, str | SceneActionConfig] = {}

    def __init__(self, wizard: Any) -> None:
        super().__init__(wizard)
        self.data = SceneDataProxy(wizard)
        self.services = SceneServicesProxy(self)
        self.history = SceneHistoryProxy(self.data)
        self.nav = SceneNavigator(self)

    @property
    def state_id(self) -> str:
        scene_config = getattr(self, "__scene_config__", None)
        return getattr(scene_config, "state", self.__class__.__name__)

    @property
    def module(self) -> SceneModule | None:
        if self.scene_module:
            return RUNTIME.modules.get(self.scene_module)
        return RUNTIME.module_for_state(self.state_id)

    @property
    def runtime(self):
        return RUNTIME

    def cleanup_policy(self) -> SceneCleanup:
        return self.runtime.merge_cleanup(self.cleanup)

    def action_config_for(
        self,
        operation: str | None = None,
        override: str | SceneActionConfig | None = None,
    ) -> SceneActionConfig | None:
        value = override
        if value is None and operation is not None:
            value = self.chat_actions.get(operation)
        if value is None:
            value = self.default_chat_action
        if value is None:
            return None
        if isinstance(value, SceneActionConfig):
            return value
        return SceneActionConfig(action=str(value))

    @asynccontextmanager
    async def chat_action(
        self,
        event: Message | CallbackQuery | None,
        action: str | SceneActionConfig | None = None,
    ):
        config = self.action_config_for(override=action)
        message = event.message if isinstance(event, CallbackQuery) else event

        if (
            config is None
            or not config.enabled
            or message is None
            or ChatActionSender is None
            or getattr(message, "bot", None) is None
            or getattr(message, "chat", None) is None
        ):
            yield
            return

        sender_kwargs = {
            "bot": message.bot,
            "chat_id": message.chat.id,
            "action": config.action,
            "interval": config.interval,
            "initial_sleep": config.initial_sleep,
        }
        thread_id = getattr(message, "message_thread_id", None)
        if thread_id is not None:
            sender_kwargs["message_thread_id"] = thread_id

        async with ChatActionSender(**sender_kwargs):
            yield

    async def run_operation(
        self,
        operation: str,
        event: Message | CallbackQuery | None,
        callback: Any,
        *args: Any,
        action: str | SceneActionConfig | None = None,
    ) -> Any:
        config = self.action_config_for(operation=operation, override=action)
        async with self.chat_action(event, config):
            return await call_with_optional_args(callback, *args)

    async def resolve_service(self, key: str, default: Any = UNSET) -> Any:
        module = self.module
        value = self.service_binding(key, default=default)
        if value is UNSET:
            raise MissingServiceError(key)
        if value is default:
            return default
        return await resolve_service_value(value, scene=self, module=module)

    async def require_service(self, key: str) -> Any:
        return await self.resolve_service(key)

    def service_binding(self, key: str, default: Any = UNSET) -> Any:
        module = self.module

        if module and key in module.services:
            return module.services[key]

        return self.runtime.service_container.resolve(
            key,
            scene=self,
            module=module,
            default=default,
        )

    async def show(
        self,
        event: Message | CallbackQuery,
        content: RenderableText | None,
        *,
        reply_markup: Any | None = None,
        remember: bool = True,
        replace_parse_mode: bool = True,
        remember_history: bool | None = None,
        breadcrumb_label: str | None = None,
        **kwargs: Any,
    ) -> Any:
        payload = render_text(content, replace_parse_mode=replace_parse_mode)
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        payload.update(kwargs)

        if remember_history is None:
            remember_history = self.cleanup_policy().remember_history is not False
        if remember_history:
            await self.history.replace_current(
                self.state_id,
                breadcrumb_label or await self.breadcrumb_label(event, content),
            )

        if isinstance(event, CallbackQuery):
            return await self._show_callback(event, payload, remember=remember)

        await self._cleanup_previous_message(event)
        message = await event.answer(**payload)
        return await self._remember_screen(message, remember=remember)

    async def breadcrumb_label(
        self,
        event: Message | CallbackQuery,
        content: RenderableText | None,
    ) -> str:
        if self.breadcrumb:
            return self.breadcrumb
        payload = render_text(content, replace_parse_mode=False)
        text = payload.get("text", "") or self.state_id
        return text.splitlines()[0][:64] or self.state_id

    async def cleanup_screen(self, message: Message) -> None:
        previous_message_id = await self.data.get("_screen_message_id")
        if previous_message_id and getattr(message, "bot", None):
            try:
                await message.bot.delete_message(message.chat.id, previous_message_id)
            except TelegramBadRequest:
                pass

    async def cleanup_user_message(self, message: Message) -> None:
        if self.cleanup_policy().delete_user_messages is not True:
            return
        if getattr(message, "bot", None) is None:
            return
        if getattr(message, "message_id", None) is None:
            return
        try:
            await message.bot.delete_message(message.chat.id, message.message_id)
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
        if self.cleanup_policy().delete_previous_screen is not True:
            return
        previous_message_id = await self.data.get("_screen_message_id")
        if previous_message_id and getattr(message, "bot", None):
            try:
                await message.bot.delete_message(message.chat.id, previous_message_id)
            except TelegramBadRequest:
                pass

    async def _remember_screen(self, message: Any, *, remember: bool) -> Any:
        if remember and getattr(message, "message_id", None) is not None:
            await self.data.update(_screen_message_id=message.message_id)
        return message
