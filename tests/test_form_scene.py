from __future__ import annotations

from dataclasses import dataclass

import pytest

import scenegram.base as base_module
from scenegram import FormAction, FormField, FormScene, StepAction, step_nav_row


@dataclass(slots=True)
class SignupResult:
    age: int
    email: str


class DemoFormScene(FormScene, state="tests.form"):
    __abstract__ = False
    result_model = SignupResult
    use_confirm_step = True
    fields = (
        FormField(
            name="age",
            prompt="Сколько вам лет?",
            parser="parse_age",
            validator="validate_age",
            summary_label="Age",
        ),
        FormField(
            name="email",
            prompt="Какой e-mail использовать?",
            validator="validate_email",
            summary_label="Email",
        ),
    )

    def __init__(self, wizard):
        super().__init__(wizard)
        self.submitted = None

    async def parse_age(self, raw_value: str) -> int:
        return int(raw_value)

    async def validate_age(self, value: int) -> str | None:
        if value < 18:
            return "Возраст должен быть не меньше 18."
        return None

    async def validate_email(self, value: str) -> str | None:
        if "@" not in value:
            return "Некорректный e-mail."
        return None

    async def on_form_submit(self, event, result) -> None:
        self.submitted = result


def test_form_scene_declares_generated_steps() -> None:
    assert DemoFormScene.declared_steps() == ("field__age", "field__email", "__confirm__")


def test_step_nav_row_builds_requested_actions() -> None:
    buttons = step_nav_row(next_step=True, back=True, exit_scene=True)

    assert [button.text for button in buttons] == ["⬅️ Предыдущий шаг", "➡️ Дальше", "✖️ Выйти"]
    assert buttons[0].callback_data == StepAction(action="back")
    assert buttons[1].callback_data == StepAction(action="next")
    assert buttons[2].callback_data == StepAction(action="exit")


@pytest.mark.asyncio
async def test_form_scene_parser_and_validator_move_to_next_field(wizard) -> None:
    from tests.conftest import FakeMessage

    scene = DemoFormScene(wizard)
    message = FakeMessage(text="25")

    await scene._on_step_input(message)

    assert wizard.data["age"] == 25
    assert wizard.data["_step"] == "field__email"
    assert message.answer_calls[-1]["text"] == "Шаг 2/2\n\nКакой e-mail использовать?"


@pytest.mark.asyncio
async def test_form_scene_validation_error_keeps_current_step(wizard) -> None:
    from tests.conftest import FakeMessage

    scene = DemoFormScene(wizard)
    message = FakeMessage(text="15")

    await scene._on_step_input(message)

    assert wizard.data.get("_step") is None
    assert "Возраст должен быть не меньше 18." in message.answer_calls[-1]["text"]


@pytest.mark.asyncio
async def test_form_scene_parser_error_keeps_current_step(wizard) -> None:
    from tests.conftest import FakeMessage

    scene = DemoFormScene(wizard)
    message = FakeMessage(text="abc")

    await scene._on_step_input(message)

    assert wizard.data.get("_step") is None
    assert "invalid literal for int()" in message.answer_calls[-1]["text"]


@pytest.mark.asyncio
async def test_form_scene_renders_confirm_step_after_last_field(wizard) -> None:
    from tests.conftest import FakeMessage

    wizard.data = {"_step": "field__email", "age": 25}
    scene = DemoFormScene(wizard)
    message = FakeMessage(text="user@example.com")

    await scene._on_step_input(message)

    assert wizard.data["_step"] == "__confirm__"
    assert "Проверьте данные" in message.answer_calls[-1]["text"]
    assert "Age" in message.answer_calls[-1]["text"]


@pytest.mark.asyncio
async def test_form_scene_submit_action_builds_typed_result(wizard) -> None:
    from tests.conftest import FakeCallbackQuery

    wizard.data = {"_step": "__confirm__", "age": 25, "email": "user@example.com"}
    scene = DemoFormScene(wizard)
    call = FakeCallbackQuery()

    await scene._submit_action(call)

    assert scene.submitted == SignupResult(age=25, email="user@example.com")
    assert call.answer_calls == [None]


@pytest.mark.asyncio
async def test_form_scene_edit_action_returns_to_last_field(wizard, monkeypatch) -> None:
    from tests.conftest import FakeCallbackQuery

    monkeypatch.setattr(base_module, "CallbackQuery", FakeCallbackQuery)
    wizard.data = {"_step": "__confirm__", "age": 25, "email": "user@example.com"}
    scene = DemoFormScene(wizard)
    call = FakeCallbackQuery()

    await scene._edit_action(call)

    assert wizard.data["_step"] == "field__email"
    assert "Шаг 2/2" in call.message.edit_calls[-1]["text"]


@pytest.mark.asyncio
async def test_form_scene_confirm_rows_use_form_actions(wizard) -> None:
    scene = DemoFormScene(wizard)

    rows = await scene.confirm_rows(None)

    assert rows[0][0].callback_data == FormAction(action="submit")
    assert rows[1][0].callback_data == FormAction(action="edit")
