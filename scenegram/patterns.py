from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from aiogram import F
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.scene import on
from aiogram.types import CallbackQuery, Message
from aiogram.utils.formatting import Bold, Text, as_key_value, as_list

from .base import AppScene
from .formatting import RenderableText
from .ui import Button, inline_menu, nav_row

type FormHook = str | Callable[..., Any]


def _positional_arity(callback: Callable[..., Any]) -> int | None:
    signature = inspect.signature(callback)
    parameters = list(signature.parameters.values())

    if any(parameter.kind == inspect.Parameter.VAR_POSITIONAL for parameter in parameters):
        return None

    return len(
        [
            parameter
            for parameter in parameters
            if parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
    )


async def _call_hook(callback: Callable[..., Any], *args: Any) -> Any:
    arity = _positional_arity(callback)
    call_args = args if arity is None else args[:arity]
    result = callback(*call_args)
    if inspect.isawaitable(result):
        return await result
    return result


class MenuScene(AppScene):
    __abstract__ = True

    menu_text: RenderableText | None = None
    static_rows: Sequence[Sequence[Button]] = ()
    navigation_back = False
    navigation_home = False
    navigation_cancel = False
    navigation_home_target = ""

    async def menu_content(self, event: Message | CallbackQuery) -> RenderableText | None:
        return self.menu_text

    async def menu_rows(self, event: Message | CallbackQuery) -> list[list[Button]]:
        return [list(row) for row in self.static_rows]

    async def menu_markup(self, event: Message | CallbackQuery):
        rows = await self.menu_rows(event)
        navigation = nav_row(
            back=self.navigation_back,
            home=self.navigation_home,
            cancel=self.navigation_cancel,
            home_target=self.navigation_home_target,
        )
        if navigation:
            rows.append(navigation)
        return inline_menu(rows)

    async def render_menu(self, event: Message | CallbackQuery) -> Any:
        return await self.show(
            event,
            await self.menu_content(event),
            reply_markup=await self.menu_markup(event),
        )

    @on.message.enter()
    async def _on_message_enter(self, message: Message) -> None:
        await self.render_menu(message)

    @on.callback_query.enter()
    async def _on_callback_enter(self, call: CallbackQuery) -> None:
        await call.answer()
        await self.render_menu(call)


class ConfirmAction(CallbackData, prefix="confirm"):
    action: str


class ConfirmScene(AppScene):
    __abstract__ = True

    confirm_text: RenderableText | None = "Подтвердите действие"
    confirm_button_text = "✅ Подтвердить"
    reject_button_text = "✖️ Отмена"
    reject_notice = "Отменено"

    async def confirm_content(self, event: Message | CallbackQuery) -> RenderableText | None:
        return self.confirm_text

    async def confirm_rows(self, event: Message | CallbackQuery) -> list[list[Button]]:
        return [
            [Button(text=self.confirm_button_text, callback_data=ConfirmAction(action="confirm"))],
            [Button(text=self.reject_button_text, callback_data=ConfirmAction(action="cancel"))],
        ]

    async def render_confirm(self, event: Message | CallbackQuery) -> Any:
        return await self.show(
            event,
            await self.confirm_content(event),
            reply_markup=inline_menu(await self.confirm_rows(event)),
        )

    async def on_confirm(self, event: CallbackQuery) -> Any:
        raise NotImplementedError

    async def on_reject(self, event: CallbackQuery) -> Any:
        await self.nav.back()

    @on.message.enter()
    async def _on_message_enter(self, message: Message) -> None:
        await self.render_confirm(message)

    @on.callback_query.enter()
    async def _on_callback_enter(self, call: CallbackQuery) -> None:
        await call.answer()
        await self.render_confirm(call)

    @on.callback_query(ConfirmAction.filter(F.action == "confirm"))
    async def _confirm_action(self, call: CallbackQuery) -> None:
        await call.answer()
        await self.on_confirm(call)

    @on.callback_query(ConfirmAction.filter(F.action == "cancel"))
    async def _reject_action(self, call: CallbackQuery) -> None:
        await call.answer(self.reject_notice)
        await self.on_reject(call)


class StepAction(CallbackData, prefix="step"):
    action: str


def step_nav_row(
    *,
    next_step: bool = False,
    back: bool = True,
    exit_scene: bool = False,
) -> list[Button]:
    buttons: list[Button] = []
    if back:
        buttons.append(Button(text="⬅️ Назад", callback_data=StepAction(action="back")))
    if next_step:
        buttons.append(Button(text="➡️ Дальше", callback_data=StepAction(action="next")))
    if exit_scene:
        buttons.append(Button(text="✖️ Выйти", callback_data=StepAction(action="exit")))
    return buttons


class StepScene(AppScene):
    __abstract__ = True

    step_key = "_step"

    @classmethod
    def declared_steps(cls) -> tuple[str, ...]:
        discovered: dict[str, str] = {}
        for base in reversed(cls.mro()):
            for name, value in base.__dict__.items():
                if name == "step_storage_key":
                    continue
                if name.startswith("step_") and callable(value):
                    discovered[name] = name

        def sort_key(name: str) -> tuple[int, int | str]:
            suffix = name.removeprefix("step_")
            if suffix.isdigit():
                return (0, int(suffix))
            return (1, suffix)

        return tuple(sorted(discovered, key=sort_key))

    @classmethod
    def initial_step_name(cls) -> str:
        steps = cls.declared_steps()
        if not steps:
            raise RuntimeError(f"{cls.__name__} must define at least one step_<name> method")
        return steps[0]

    def step_storage_key(self, step_name: str) -> str:
        return step_name

    async def current_step(self) -> str:
        step_name = await self.data.get(self.step_key, self.initial_step_name())
        if step_name not in self.declared_steps():
            return self.initial_step_name()
        return step_name

    async def set_step(self, step_name: str, **data: Any) -> None:
        if step_name not in self.declared_steps():
            raise KeyError(f"Unknown step: {step_name}")
        await self.data.update({self.step_key: step_name}, **data)

    async def go_to_step(self, event: Message | CallbackQuery, step_name: str) -> Any:
        await self.set_step(step_name)
        return await self.render_current_step(event)

    async def render_current_step(self, event: Message | CallbackQuery) -> Any:
        step_name = await self.current_step()
        renderer = getattr(self, step_name)
        return await renderer(event)

    async def next_step(self, event: Message | CallbackQuery, **data: Any) -> Any:
        steps = self.declared_steps()
        current = await self.current_step()
        index = steps.index(current)
        if data:
            await self.data.update(data)
        if index + 1 >= len(steps):
            return await self.on_complete(event)

        next_step_name = steps[index + 1]
        await self.set_step(next_step_name)
        return await self.render_current_step(event)

    async def prev_step(self, event: Message | CallbackQuery, **data: Any) -> Any:
        steps = self.declared_steps()
        current = await self.current_step()
        index = steps.index(current)
        if data:
            await self.data.update(data)
        if index == 0:
            return await self.nav.back()

        previous_step_name = steps[index - 1]
        await self.set_step(previous_step_name)
        return await self.render_current_step(event)

    async def on_complete(self, event: Message | CallbackQuery) -> Any:
        await self.nav.exit()

    async def save_step_input(self, message: Message) -> dict[str, Any]:
        step_name = await self.current_step()
        return await self.data.update({self.step_storage_key(step_name): message.text})

    async def handle_step_input(self, message: Message, step_name: str) -> None:
        await self.save_step_input(message)
        await self.next_step(message)

    @on.message.enter()
    async def _on_message_enter(self, message: Message) -> None:
        await self.set_step(await self.current_step())
        await self.render_current_step(message)

    @on.callback_query.enter()
    async def _on_callback_enter(self, call: CallbackQuery) -> None:
        await call.answer()
        await self.set_step(await self.current_step())
        await self.render_current_step(call)

    @on.message(F.text)
    async def _on_step_input(self, message: Message) -> None:
        step_name = await self.current_step()
        handler = getattr(self, f"handle_{step_name}", None)

        if handler is not None:
            await handler(message)
            return

        await self.handle_step_input(message, step_name)

    @on.message()
    async def _on_unsupported_input(self, message: Message) -> None:
        await self.show(message, "Для этого шага ожидается текстовый ответ.")

    @on.callback_query(StepAction.filter(F.action == "next"))
    async def _next_action(self, call: CallbackQuery) -> None:
        await call.answer()
        await self.next_step(call)

    @on.callback_query(StepAction.filter(F.action == "back"))
    async def _back_action(self, call: CallbackQuery) -> None:
        await call.answer()
        await self.prev_step(call)

    @on.callback_query(StepAction.filter(F.action == "exit"))
    async def _exit_action(self, call: CallbackQuery) -> None:
        await call.answer()
        await self.nav.exit()


@dataclass(slots=True, frozen=True)
class FormField:
    name: str
    prompt: RenderableText
    parser: FormHook | None = None
    validator: FormHook | None = None
    formatter: FormHook | None = None
    storage_key: str | None = None
    summary_label: str | None = None


class FormAction(CallbackData, prefix="form"):
    action: str


class FormScene(StepScene):
    __abstract__ = True

    fields: Sequence[FormField] = ()
    result_model: type[Any] | None = None
    use_confirm_step = False
    confirm_step_name = "__confirm__"
    confirm_title: RenderableText = "Проверьте данные"
    submit_button_text = "✅ Сохранить"
    edit_button_text = "✏️ Исправить"
    invalid_input_text = "Проверьте введённое значение и повторите ввод."

    @classmethod
    def field_definitions(cls) -> tuple[FormField, ...]:
        if not cls.fields:
            raise RuntimeError(f"{cls.__name__} must declare at least one FormField")

        normalized = tuple(cls.fields)
        names = [field.name for field in normalized]
        if len(set(names)) != len(names):
            raise RuntimeError(f"{cls.__name__} contains duplicate form field names")
        return normalized

    @classmethod
    def declared_steps(cls) -> tuple[str, ...]:
        steps = tuple(cls.field_step_name(field.name) for field in cls.field_definitions())
        if cls.use_confirm_step:
            return (*steps, cls.confirm_step_name)
        return steps

    @classmethod
    def field_step_name(cls, field_name: str) -> str:
        return f"field__{field_name}"

    @classmethod
    def field_by_step(cls, step_name: str) -> FormField:
        for field in cls.field_definitions():
            if cls.field_step_name(field.name) == step_name:
                return field
        raise KeyError(f"Unknown form step: {step_name}")

    def field_data_key(self, field: FormField) -> str:
        return field.storage_key or field.name

    async def render_current_step(self, event: Message | CallbackQuery) -> Any:
        step_name = await self.current_step()
        if step_name == self.confirm_step_name:
            return await self.render_confirmation(event)

        field = self.field_by_step(step_name)
        return await self.show(
            event,
            await self.field_content(field, event),
            reply_markup=await self.field_markup(field, event),
        )

    async def field_content(
        self,
        field: FormField,
        event: Message | CallbackQuery,
    ) -> RenderableText:
        field_index = self.field_definitions().index(field) + 1
        total_fields = len(self.field_definitions())
        return Text(Bold(f"Шаг {field_index}/{total_fields}"), "\n\n", field.prompt)

    async def field_markup(
        self,
        field: FormField,
        event: Message | CallbackQuery,
    ) -> Any | None:
        return None

    async def field_error_content(self, field: FormField, error: str) -> RenderableText:
        return Text(Bold("Ошибка"), "\n\n", error, "\n\n", field.prompt)

    async def parse_field_value(
        self,
        field: FormField,
        raw_value: str,
        message: Message,
    ) -> Any:
        if field.parser is None:
            return raw_value

        hook = self._resolve_form_hook(field.parser)
        return await _call_hook(hook, raw_value, message, field)

    async def validate_field_value(
        self,
        field: FormField,
        value: Any,
        message: Message,
    ) -> str | None:
        if field.validator is None:
            return None

        hook = self._resolve_form_hook(field.validator)
        result = await _call_hook(hook, value, message, field)

        if result in (None, True):
            return None
        if result is False:
            return self.invalid_input_text
        return str(result)

    async def format_summary_value(self, field: FormField, value: Any) -> str:
        if field.formatter is None:
            return "" if value is None else str(value)

        hook = self._resolve_form_hook(field.formatter)
        result = await _call_hook(hook, value, field)
        return "" if result is None else str(result)

    async def form_values(self) -> dict[str, Any]:
        data = await self.data.all()
        return {
            field.name: data.get(self.field_data_key(field))
            for field in self.field_definitions()
        }

    async def form_result(self) -> Any:
        values = await self.form_values()
        if self.result_model is None:
            return values

        model_cls = self.result_model
        if hasattr(model_cls, "model_validate"):
            return model_cls.model_validate(values)
        if is_dataclass(model_cls):
            allowed = {field.name for field in fields(model_cls)}
            return model_cls(**{key: value for key, value in values.items() if key in allowed})
        return model_cls(**values)

    async def confirm_content(self, event: Message | CallbackQuery) -> RenderableText:
        rows: list[Any] = [self.confirm_title]
        values = await self.form_values()

        for field in self.field_definitions():
            label = field.summary_label or field.name
            value = await self.format_summary_value(field, values.get(field.name))
            rows.append(as_key_value(label, value))

        return as_list(*rows, sep="\n\n")

    async def confirm_rows(self, event: Message | CallbackQuery) -> list[list[Button]]:
        rows = [
            [Button(text=self.submit_button_text, callback_data=FormAction(action="submit"))],
            [Button(text=self.edit_button_text, callback_data=FormAction(action="edit"))],
        ]
        return rows

    async def render_confirmation(self, event: Message | CallbackQuery) -> Any:
        return await self.show(
            event,
            await self.confirm_content(event),
            reply_markup=inline_menu(await self.confirm_rows(event)),
        )

    async def submit_form(self, event: Message | CallbackQuery) -> Any:
        result = await self.form_result()
        return await self.on_form_submit(event, result)

    async def on_form_submit(self, event: Message | CallbackQuery, result: Any) -> Any:
        await self.nav.exit()

    async def on_complete(self, event: Message | CallbackQuery) -> Any:
        return await self.submit_form(event)

    async def handle_step_input(self, message: Message, step_name: str) -> None:
        field = self.field_by_step(step_name)

        try:
            value = await self.parse_field_value(field, message.text or "", message)
        except ValueError as exc:
            await self.show(message, await self.field_error_content(field, str(exc)))
            return

        error = await self.validate_field_value(field, value, message)
        if error:
            await self.show(message, await self.field_error_content(field, error))
            return

        await self.data.update({self.field_data_key(field): value})
        await self.next_step(message)

    def _resolve_form_hook(self, hook: FormHook) -> Callable[..., Any]:
        if isinstance(hook, str):
            return getattr(self, hook)
        return hook

    def edit_step_name(self) -> str:
        return self.field_step_name(self.field_definitions()[-1].name)

    @on.callback_query(FormAction.filter(F.action == "submit"))
    async def _submit_action(self, call: CallbackQuery) -> None:
        await call.answer()
        await self.submit_form(call)

    @on.callback_query(FormAction.filter(F.action == "edit"))
    async def _edit_action(self, call: CallbackQuery) -> None:
        await call.answer()
        await self.go_to_step(call, self.edit_step_name())


__all__ = [
    "ConfirmAction",
    "ConfirmScene",
    "FormAction",
    "FormField",
    "FormScene",
    "MenuScene",
    "StepAction",
    "StepScene",
    "step_nav_row",
]
