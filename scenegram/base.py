from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from contextlib import asynccontextmanager
from dataclasses import fields, is_dataclass
from typing import Any, TypeVar, cast

from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.scene import Scene, on
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

try:
    from aiogram.utils.chat_action import ChatActionSender
except ImportError:  # pragma: no cover
    ChatActionSender = None

from ._utils import call_with_optional_args
from .contracts import SceneActionConfig, SceneCleanup, SceneModule
from .deep_links import SceneDeepLinksProxy
from .di import UNSET, MissingServiceError, resolve_service_value
from .formatting import RenderableText, render_text
from .history import SceneHistoryProxy, SceneStackProxy
from .roles import SceneRole, normalize_role, normalize_roles
from .runtime import RUNTIME
from .security import (
    ACCESS_DENIED_TEXT,
    SecureScenesManagerProxy,
    is_state_allowed,
    notify_access_denied,
    resolve_event_roles,
    resolve_target_state,
)
from .ui.callbacks import Navigate
from .ui.keyboards import uses_message_reply_markup

ModelT = TypeVar("ModelT")
BACK_TARGET_HOME = "__scenegram_home__"
HIDDEN_REPLY_TEXT = "\u2060"
LOGGER = logging.getLogger("scenegram")
FRAMEWORK_DATA_KEYS = frozenset(
    {
        "_back_target",
        "_history",
        "_scene_stack",
        "_screen_message_id",
    }
)


class _SceneDataMutation(dict[str, Any]):
    def __init__(self, data: Mapping[str, Any], *, protected_keys: set[str]) -> None:
        super().__init__(data)
        self._protected_keys = protected_keys

    def _ensure_mutable(self, key: str) -> None:
        if key in self._protected_keys:
            raise KeyError(f"Protected scene data key cannot be mutated: {key}")

    def __setitem__(self, key: str, value: Any) -> None:
        self._ensure_mutable(key)
        super().__setitem__(key, value)

    def __delitem__(self, key: str) -> None:
        self._ensure_mutable(key)
        super().__delitem__(key)

    def pop(self, key: str, default: Any | None = None) -> Any:
        self._ensure_mutable(key)
        return super().pop(key, default)

    def update(self, *args: Any, **kwargs: Any) -> None:
        candidate = dict(*args, **kwargs)
        for key in candidate:
            self._ensure_mutable(key)
        super().update(candidate)

    def clear(self) -> None:
        protected = self._protected_keys & set(self.keys())
        if protected:
            joined = ", ".join(sorted(protected))
            raise KeyError(f"Protected scene data keys cannot be cleared: {joined}")
        super().clear()


class SceneDataProxy:
    def __init__(self, wizard: Any) -> None:
        self._wizard = wizard

    def framework_keys(self) -> frozenset[str]:
        return FRAMEWORK_DATA_KEYS

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

    @asynccontextmanager
    async def mutate(
        self,
        *,
        protect_reserved: bool = False,
        protected_keys: Iterable[str] | None = None,
    ):
        current = await self.all()
        keys = set(protected_keys or ())
        if protect_reserved:
            keys.update(self.framework_keys())
        data = _SceneDataMutation(current, protected_keys=keys)
        yield data
        await self._wizard.set_data(dict(data))

    async def pop(self, *keys: str, default: Any | None = None) -> Any:
        async with self.mutate() as current:
            values = tuple(current.pop(key, default) for key in keys)
        if len(values) == 1:
            return values[0]
        return values

    async def discard(self, *keys: str) -> None:
        async with self.mutate() as current:
            for key in keys:
                current.pop(key, None)

    async def model(self, model_cls: type[ModelT]) -> ModelT:
        data = await self.all()

        validator = getattr(model_cls, "model_validate", None)
        if callable(validator):
            return cast(ModelT, validator(data))

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

    def _target_state(self, target: type[Scene] | str) -> str | None:
        return resolve_target_state(target)

    async def to(self, target: type[Scene] | str, **kwargs: Any) -> None:
        target_state = self._target_state(target)
        if not await self.scene.ensure_scene_access(target_state):
            return
        if target_state is not None:
            await self.scene.stack.push(target_state)
        await self.scene.runtime.emit(
            "scene.transition",
            scene=self.scene,
            target_state=target_state,
            event=self.scene.current_event(),
            action="to",
        )
        await self.scene.wizard.goto(target, **kwargs)

    async def back_to(self, target: type[Scene] | str, **kwargs: Any) -> None:
        target_state = self._target_state(target)
        if target_state is not None and not await self.scene.ensure_scene_access(target_state):
            return
        if target_state is None:
            await self.replace(target, sync_stack=False, **kwargs)
            return

        await self.scene.stack.pop()
        current = await self.scene.stack.current()
        if current != target_state:
            if current is None:
                await self.scene.stack.reset(target_state)
            else:
                await self.scene.stack.replace_current(target_state)
        await self.scene.history.pop()
        await self.scene.runtime.emit(
            "scene.transition",
            scene=self.scene,
            target_state=target_state,
            event=self.scene.current_event(),
            action="back_to",
        )
        await self.replace(target, sync_stack=False, **kwargs)

    async def cancel(self, **kwargs: Any) -> None:
        target = self.scene.home_scene or RUNTIME.default_home
        if target:
            await self.back_to(target, **kwargs)
            return
        await self.exit(**kwargs)

    async def replace(
        self,
        target: type[Scene] | str,
        *,
        reset_history: bool = False,
        sync_stack: bool = True,
        **kwargs: Any,
    ) -> None:
        manager = getattr(self.scene.wizard, "manager", None)
        history = getattr(manager, "history", None)
        target_state = self._target_state(target)
        if target_state is not None and not await self.scene.ensure_scene_access(target_state):
            return

        if history is not None and reset_history and hasattr(history, "clear"):
            await history.clear()
        if reset_history:
            await self.scene.history.clear()

        if sync_stack and target_state is not None:
            if reset_history:
                await self.scene.stack.reset(target_state)
            else:
                await self.scene.stack.replace_current(target_state)

        await self.scene.runtime.emit(
            "scene.transition",
            scene=self.scene,
            target_state=target_state,
            event=self.scene.current_event(),
            action="replace",
            reset_history=reset_history,
        )
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
            await self.back_to(str(target), **kwargs)
            return

        target_state = await self.scene.stack.back_target(self.scene.state_id)
        if target_state is not None:
            if not await self.scene.ensure_scene_access(target_state):
                await self.scene.stack.pop()
                await self.scene.history.pop()
                return await self.back(**kwargs)
            await self.scene.stack.pop()
            await self.scene.history.pop()
            await self.scene.runtime.emit(
                "scene.transition",
                scene=self.scene,
                target_state=target_state,
                event=self.scene.current_event(),
                action="back",
            )
            await self.replace(target_state, sync_stack=False, **kwargs)
            return

        await self.scene.history.pop()
        await self.scene.wizard.back(**kwargs)

    async def retake(self, **kwargs: Any) -> None:
        await self.scene.wizard.retake(**kwargs)

    async def exit(self, **kwargs: Any) -> None:
        await self.scene.stack.pop()
        await self.scene.history.pop()
        await self.scene.runtime.emit(
            "scene.transition",
            scene=self.scene,
            target_state=None,
            event=self.scene.current_event(),
            action="exit",
        )
        await self.scene.wizard.exit(**kwargs)

    async def home(self, **kwargs: Any) -> None:
        target = self.scene.home_scene or RUNTIME.default_home
        if target:
            await self.replace(target, reset_history=True, **kwargs)
            return
        await self.exit(**kwargs)

    async def start(self, **kwargs: Any) -> None:
        target = RUNTIME.default_home or self.scene.home_scene
        if target:
            await self.replace(target, reset_history=True, **kwargs)
            return
        await self.exit(**kwargs)

    async def role_home(self, role: SceneRole | str, **kwargs: Any) -> None:
        target = (
            RUNTIME.home_by_role.get(normalize_role(role))
            or self.scene.home_scene
            or RUNTIME.default_home
        )
        if target:
            await self.replace(target, reset_history=True, **kwargs)
            return
        await self.exit(**kwargs)

    async def stack_states(self) -> list[str]:
        states = await self.scene.stack.states()
        if states:
            return states

        manager = getattr(self.scene.wizard, "manager", None)
        history = getattr(manager, "history", None)
        if history is None or not hasattr(history, "all"):
            return []

        records = await history.all()
        states = []
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
    middlewares: tuple[Any, ...] = ()
    roles = frozenset({SceneRole.ANY.value})
    home_for_roles = frozenset()
    home_scene: str | None = None
    scene_module: str | None = None
    cleanup = SceneCleanup()
    breadcrumb: str | None = None
    default_chat_action: str | SceneActionConfig | None = None
    chat_actions: Mapping[str, str | SceneActionConfig] = {}
    cancel_notice_text = "Отменено"
    home_notice_text = "Открываю меню"
    access_denied_text = ACCESS_DENIED_TEXT

    def __init__(self, wizard: Any) -> None:
        super().__init__(wizard)
        manager = getattr(wizard, "manager", None)
        if manager is not None:
            if isinstance(manager, SecureScenesManagerProxy):
                manager.scene = self
            else:
                wizard.manager = SecureScenesManagerProxy(manager, scene=self)
        self.data = SceneDataProxy(wizard)
        self.services = SceneServicesProxy(self)
        self.history = SceneHistoryProxy(self.data)
        self.stack = SceneStackProxy(self.data)
        self.nav = SceneNavigator(self)
        self.deep_links = SceneDeepLinksProxy(self)

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

    def current_event(self) -> Any | None:
        manager = getattr(self.wizard, "manager", None)
        return getattr(manager, "event", None)

    async def current_roles(self, event: Any | None = None) -> set[str]:
        return await resolve_event_roles(event or self.current_event())

    async def can_access_state(self, target_state: str | None, event: Any | None = None) -> bool:
        roles = await self.current_roles(event)
        return is_state_allowed(target_state, roles)

    async def ensure_scene_access(self, target_state: str | None, event: Any | None = None) -> bool:
        if target_state is None:
            return True

        current_event = event or self.current_event()
        roles = await self.current_roles(current_event)
        if is_state_allowed(target_state, roles):
            return True

        await self.runtime.emit(
            "scene.access_denied",
            scene=self,
            target_state=target_state,
            event=current_event,
            roles=sorted(roles),
        )
        if current_event is not None:
            await notify_access_denied(current_event, self.access_denied_text)
        return False

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
        await self.runtime.emit(
            "scene.operation.start",
            scene=self,
            event=event,
            operation=operation,
        )
        try:
            async with self.chat_action(event, config):
                result = await call_with_optional_args(callback, *args)
        except Exception as exc:
            await self.runtime.emit(
                "scene.operation.error",
                scene=self,
                event=event,
                operation=operation,
                error=repr(exc),
            )
            raise
        await self.runtime.emit(
            "scene.operation.success",
            scene=self,
            event=event,
            operation=operation,
        )
        return result

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
        await self.stack.ensure(self.state_id)
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
        await self.runtime.emit(
            "scene.render",
            scene=self,
            event=event,
            remember=remember,
            remember_history=remember_history,
            reply_markup=type(reply_markup).__name__ if reply_markup is not None else None,
        )

        if isinstance(event, CallbackQuery):
            if uses_message_reply_markup(reply_markup):
                if event.message is None:
                    raise RuntimeError(
                        "CallbackQuery without message is not supported by AppScene.show"
                    )
                if not hasattr(event.message, "answer"):
                    raise RuntimeError("CallbackQuery message is not editable/answerable")
                callback_message = cast(Message, event.message)
                await self._cleanup_previous_message(callback_message)
                message = await callback_message.answer(**payload)
                return await self._remember_screen(message, remember=remember)
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
        bot = getattr(message, "bot", None)
        if previous_message_id and bot is not None:
            try:
                await bot.delete_message(message.chat.id, previous_message_id)
            except TelegramBadRequest:
                pass

    async def cleanup_user_message(self, message: Message) -> None:
        if self.cleanup_policy().delete_user_messages is not True:
            return
        if getattr(message, "bot", None) is None:
            return
        if getattr(message, "message_id", None) is None:
            return
        bot = getattr(message, "bot", None)
        if bot is None:
            return
        try:
            await bot.delete_message(message.chat.id, message.message_id)
        except TelegramBadRequest:
            pass

    async def reply_notice(
        self,
        message: Message,
        content: RenderableText | None,
        *,
        remove_reply_keyboard: bool = False,
        transient: bool = False,
        replace_parse_mode: bool = True,
        **kwargs: Any,
    ) -> Any:
        payload = render_text(
            HIDDEN_REPLY_TEXT if content is None and remove_reply_keyboard else content,
            replace_parse_mode=replace_parse_mode,
        )
        if remove_reply_keyboard:
            payload["reply_markup"] = ReplyKeyboardRemove()
        payload.update(kwargs)

        sent = await message.answer(**payload)

        bot = getattr(message, "bot", None)
        if transient and bot is not None:
            sent_message_id = getattr(sent, "message_id", None)
            if sent_message_id is not None:
                try:
                    await bot.delete_message(message.chat.id, sent_message_id)
                except TelegramBadRequest:
                    pass
        return sent

    async def resolve_roles(self, event: Any) -> set[str]:
        return await resolve_event_roles(event)

    async def has_any_role(self, event: Any, roles: Iterable[SceneRole | str]) -> bool:
        allowed = normalize_roles(roles)
        resolved = await self.resolve_roles(event)
        return bool(resolved & allowed)

    @on.callback_query(Navigate.filter(F.action == "open"))
    async def _navigate_open(self, call: CallbackQuery, callback_data: Navigate) -> None:
        await call.answer()
        if callback_data.target == self.state_id:
            await self.nav.replace(callback_data.target)
            return
        await self.nav.to(callback_data.target)

    @on.callback_query(Navigate.filter(F.action == "back"))
    async def _navigate_back(self, call: CallbackQuery, callback_data: Navigate) -> None:
        await call.answer()
        if callback_data.target:
            await self.nav.back_to(callback_data.target)
            return
        await self.nav.back()

    @on.callback_query(Navigate.filter(F.action == "home"))
    async def _navigate_home(self, call: CallbackQuery, callback_data: Navigate) -> None:
        await call.answer()
        if callback_data.target:
            await self.nav.replace(callback_data.target, reset_history=True)
            return
        await self.nav.home()

    @on.callback_query(Navigate.filter(F.action == "cancel"))
    async def _navigate_cancel(self, call: CallbackQuery, callback_data: Navigate) -> None:
        await call.answer("Отменено")
        if callback_data.target:
            await self.nav.back_to(callback_data.target)
            return
        await self.nav.cancel()

    @on.callback_query(F.data == "noop")
    async def _noop(self, call: CallbackQuery) -> None:
        await call.answer()

    @on.message(Command("cancel"))
    async def _cancel_command(self, message: Message) -> None:
        await self.reply_notice(
            message,
            None,
            remove_reply_keyboard=True,
            transient=True,
        )
        await self.nav.cancel()

    @on.message(Command("start"))
    async def _start_command(self, message: Message) -> None:
        await self.reply_notice(
            message,
            None,
            remove_reply_keyboard=True,
            transient=True,
        )
        await self.nav.start()

    @on.message(F.text == "Отмена")
    async def _cancel_text(self, message: Message) -> None:
        await self.reply_notice(
            message,
            self.cancel_notice_text,
            remove_reply_keyboard=True,
        )
        await self.nav.cancel()

    @on.message(F.text == "Назад")
    async def _back_text(self, message: Message) -> None:
        await self.nav.back()

    @on.message(F.text == "Домой")
    async def _home_text(self, message: Message) -> None:
        await self.reply_notice(
            message,
            self.home_notice_text,
            remove_reply_keyboard=True,
        )
        await self.nav.home()

    async def _show_callback(
        self,
        call: CallbackQuery,
        payload: dict[str, Any],
        *,
        remember: bool,
    ) -> Any:
        if call.message is None:
            raise RuntimeError("CallbackQuery without message is not supported by AppScene.show")
        if not hasattr(call.message, "edit_text"):
            raise RuntimeError("CallbackQuery message is not editable")
        callback_message = cast(Message, call.message)

        try:
            message = await callback_message.edit_text(**payload)
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                message = callback_message
                return await self._remember_screen(message, remember=remember)
            LOGGER.warning(
                "Callback render failed for state %s: %s",
                self.state_id,
                exc,
            )
            message = await callback_message.answer(**payload)

        return await self._remember_screen(message, remember=remember)

    async def _cleanup_previous_message(self, message: Message) -> None:
        if self.cleanup_policy().delete_previous_screen is not True:
            return
        previous_message_id = await self.data.get("_screen_message_id")
        bot = getattr(message, "bot", None)
        if previous_message_id and bot is not None:
            try:
                await bot.delete_message(message.chat.id, previous_message_id)
            except TelegramBadRequest:
                pass

    async def _remember_screen(self, message: Any, *, remember: bool) -> Any:
        if remember and getattr(message, "message_id", None) is not None:
            await self.data.update(_screen_message_id=message.message_id)
        return message
