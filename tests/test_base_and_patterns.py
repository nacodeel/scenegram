from __future__ import annotations

from types import SimpleNamespace

import pytest
from aiogram.enums import MessageEntityType
from aiogram.types import ReplyKeyboardRemove

import scenegram.base as base_module
from scenegram import (
    BACK_TARGET_HOME,
    AppScene,
    Button,
    ConfirmAction,
    ConfirmScene,
    MappingContainer,
    MenuContribution,
    MenuScene,
    Navigate,
    PaginatedScene,
    ReplyButton,
    SceneModule,
    SceneRole,
    StepScene,
    reply_menu,
)
from scenegram.formatting import Bold, Text
from scenegram.runtime import RUNTIME


class DemoScene(AppScene, state="tests.demo"):
    __abstract__ = False


class DemoMenuScene(MenuScene, state="tests.menu"):
    __abstract__ = False
    menu_text = "Menu"
    static_rows = ((Button(text="Open", callback_data=Navigate.open("tests.demo")),),)
    navigation_back = True
    navigation_home = True
    navigation_home_target = "tests.demo"


class DemoConfirmScene(ConfirmScene, state="tests.confirm"):
    __abstract__ = False

    def __init__(self, wizard):
        super().__init__(wizard)
        self.confirmed = False
        self.rejected = False

    async def on_confirm(self, event):
        self.confirmed = True

    async def on_reject(self, event):
        self.rejected = True


class DemoPaginatedScene(PaginatedScene, state="tests.page"):
    __abstract__ = False

    async def render_page(self, event, *, page: int = 1):
        return page


class DemoStepScene(StepScene, state="tests.steps"):
    __abstract__ = False

    def __init__(self, wizard):
        super().__init__(wizard)
        self.completed = False

    async def step_1(self, event):
        await self.show(event, "Step 1")

    async def step_2(self, event):
        await self.show(event, "Step 2")

    async def step_10(self, event):
        await self.show(event, "Step 10")

    async def on_complete(self, event):
        self.completed = True


@pytest.mark.asyncio
async def test_show_deletes_previous_message_and_remembers_new_one(wizard) -> None:
    scene = DemoScene(wizard)
    from tests.conftest import FakeBot, FakeMessage

    bot = FakeBot()
    wizard.data = {"_screen_message_id": 77}
    event = FakeMessage(bot=bot, answer_message_id=88)

    await scene.show(event, "Hello")

    assert bot.deleted == [(100, 77)]
    assert event.answer_calls[0]["text"] == "Hello"
    assert wizard.data["_screen_message_id"] == 88


def test_scene_cleanup_policy_inherits_runtime_defaults(wizard) -> None:
    scene = DemoScene(wizard)

    assert scene.cleanup_policy().delete_previous_screen is True
    assert scene.cleanup_policy().remember_history is True


@pytest.mark.asyncio
async def test_show_supports_aiogram_formatting_entities(wizard) -> None:
    from tests.conftest import FakeMessage

    scene = DemoScene(wizard)
    event = FakeMessage()

    await scene.show(event, Text("Hello, ", Bold("Alex"), "!"))

    payload = event.answer_calls[0]
    assert payload["text"] == "Hello, Alex!"
    assert payload["entities"][0].type == MessageEntityType.BOLD
    assert wizard.data["_scene_stack"] == ["tests.demo"]


@pytest.mark.asyncio
async def test_show_falls_back_to_answer_when_edit_fails(wizard, monkeypatch) -> None:
    from tests.conftest import FakeCallbackQuery, FakeMessage

    class DummyTelegramBadRequest(RuntimeError):
        pass

    monkeypatch.setattr(base_module, "TelegramBadRequest", DummyTelegramBadRequest)
    monkeypatch.setattr(base_module, "CallbackQuery", FakeCallbackQuery)
    scene = DemoScene(wizard)
    callback_message = FakeMessage(
        edit_exception=DummyTelegramBadRequest("boom"),
        answer_message_id=90,
    )
    call = FakeCallbackQuery(callback_message)

    await scene.show(call, "Fallback")

    assert callback_message.edit_calls[0]["text"] == "Fallback"
    assert callback_message.answer_calls[0]["text"] == "Fallback"
    assert wizard.data["_screen_message_id"] == 90


@pytest.mark.asyncio
async def test_show_uses_new_message_for_callback_reply_keyboard(wizard, monkeypatch) -> None:
    from tests.conftest import FakeCallbackQuery, FakeMessage

    monkeypatch.setattr(base_module, "CallbackQuery", FakeCallbackQuery)
    scene = DemoScene(wizard)
    callback_message = FakeMessage(answer_message_id=91)
    call = FakeCallbackQuery(callback_message)

    await scene.show(
        call,
        "Question",
        reply_markup=reply_menu([[ReplyButton(text="Отмена")]]),
    )

    assert callback_message.edit_calls == []
    assert callback_message.answer_calls[0]["text"] == "Question"
    assert callback_message.answer_calls[0]["reply_markup"].keyboard[0][0].text == "Отмена"
    assert wizard.data["_screen_message_id"] == 91


@pytest.mark.asyncio
async def test_show_does_not_send_new_message_when_callback_render_is_unchanged(
    wizard,
    monkeypatch,
) -> None:
    from tests.conftest import FakeCallbackQuery, FakeMessage

    class DummyTelegramBadRequest(RuntimeError):
        pass

    monkeypatch.setattr(base_module, "TelegramBadRequest", DummyTelegramBadRequest)
    monkeypatch.setattr(base_module, "CallbackQuery", FakeCallbackQuery)
    scene = DemoScene(wizard)
    callback_message = FakeMessage(
        edit_exception=DummyTelegramBadRequest("Bad Request: message is not modified"),
        edit_message_id=70,
    )
    call = FakeCallbackQuery(callback_message)

    result = await scene.show(call, "Same")

    assert result is callback_message
    assert callback_message.answer_calls == []


@pytest.mark.asyncio
async def test_menu_scene_combines_static_rows_and_navigation(wizard) -> None:
    scene = DemoMenuScene(wizard)
    markup = await scene.menu_markup(SimpleNamespace())

    assert markup.inline_keyboard[0][0].text == "Open"
    assert markup.inline_keyboard[1][0].callback_data == Navigate.back().pack()
    assert markup.inline_keyboard[1][1].callback_data == Navigate.home("tests.demo").pack()


@pytest.mark.asyncio
async def test_cancel_text_replies_with_keyboard_remove_and_navigates_home(wizard) -> None:
    from tests.conftest import FakeMessage

    scene = DemoScene(wizard)
    scene.home_scene = "tests.confirm"
    message = FakeMessage(text="Отмена")

    await scene._cancel_text(message)

    assert message.answer_calls[0]["text"] == "Отменено"
    assert isinstance(message.answer_calls[0]["reply_markup"], ReplyKeyboardRemove)
    assert wizard.goto_calls == []
    assert wizard.leave_calls == [(False, {})]
    assert wizard.manager.history.cleared is False
    assert wizard.manager.enter_calls == [("tests.confirm", False, {})]


@pytest.mark.asyncio
async def test_home_text_replies_with_keyboard_remove_and_navigates_home(wizard) -> None:
    from tests.conftest import FakeMessage

    scene = DemoScene(wizard)
    scene.home_scene = "tests.confirm"
    message = FakeMessage(text="Домой")

    await scene._home_text(message)

    assert message.answer_calls[0]["text"] == scene.home_notice_text
    assert isinstance(message.answer_calls[0]["reply_markup"], ReplyKeyboardRemove)
    assert wizard.goto_calls == []
    assert wizard.leave_calls == [(False, {})]
    assert wizard.manager.history.cleared is True
    assert wizard.manager.enter_calls == [("tests.confirm", False, {})]


@pytest.mark.asyncio
async def test_navigate_home_callback_resets_history_before_entering_target(
    wizard,
    monkeypatch,
) -> None:
    from tests.conftest import FakeCallbackQuery

    monkeypatch.setattr(base_module, "CallbackQuery", FakeCallbackQuery)
    scene = DemoScene(wizard)
    call = FakeCallbackQuery()

    await scene._navigate_home(call, Navigate.home("tests.confirm"))

    assert call.answer_calls == [None]
    assert wizard.goto_calls == []
    assert wizard.leave_calls == [(False, {})]
    assert wizard.manager.history.cleared is True
    assert wizard.manager.enter_calls == [("tests.confirm", False, {})]


@pytest.mark.asyncio
async def test_start_command_removes_keyboard_without_visible_notice(wizard) -> None:
    from tests.conftest import FakeMessage

    scene = DemoScene(wizard)
    scene.home_scene = "tests.confirm"
    RUNTIME.default_home = "tests.start"
    message = FakeMessage(text="/start")

    await scene._start_command(message)

    assert message.answer_calls[0]["text"] == base_module.HIDDEN_REPLY_TEXT
    assert isinstance(message.answer_calls[0]["reply_markup"], ReplyKeyboardRemove)
    assert message.bot.deleted == [(100, message.answer_message_id)]
    assert wizard.goto_calls == []
    assert wizard.leave_calls == [(False, {})]
    assert wizard.manager.history.cleared is True
    assert wizard.manager.enter_calls == [("tests.start", False, {})]


@pytest.mark.asyncio
async def test_menu_scene_includes_module_contributions_by_row_and_order(wizard) -> None:
    RUNTIME.reset()
    RUNTIME.role_resolver = lambda event: {SceneRole.ADMIN.value}
    RUNTIME.register_modules(
        [
            SceneModule(
                name="tests.menu.module",
                package_name="tests.fixtures.sample_scenes",
                menu_entries=(
                    MenuContribution(
                        target_state="tests.menu",
                        text="Reports",
                        target_scene="tests.reports",
                        row=1,
                        order=20,
                    ),
                    MenuContribution(
                        target_state="tests.menu",
                        text="Users",
                        target_scene="tests.users",
                        row=1,
                        order=10,
                    ),
                    MenuContribution(
                        target_state="tests.menu",
                        text="Settings",
                        target_scene="tests.settings",
                    ),
                    MenuContribution(
                        target_state="tests.menu",
                        text="Admin only",
                        target_scene="tests.admin",
                        roles=frozenset({SceneRole.ADMIN.value}),
                        row=0,
                        order=5,
                    ),
                ),
            )
        ]
    )
    scene = DemoMenuScene(wizard)

    markup = await scene.menu_markup(SimpleNamespace())

    assert [button.text for button in markup.inline_keyboard[0]] == ["Open"]
    assert [button.text for button in markup.inline_keyboard[1]] == ["Admin only"]
    assert [button.text for button in markup.inline_keyboard[2]] == ["Users", "Reports"]
    assert [button.text for button in markup.inline_keyboard[3]] == ["Settings"]


@pytest.mark.asyncio
async def test_scene_prefers_module_services_and_falls_back_to_container(wizard) -> None:
    RUNTIME.reset()
    RUNTIME.service_container = MappingContainer(
        {"sample_service": "global-value", "fallback_service": "fallback-value"}
    )
    RUNTIME.register_modules(
        [
            SceneModule(
                name="tests.module",
                package_name="tests.fixtures.sample_scenes",
                services={"sample_service": lambda: "module-value"},
            )
        ]
    )
    RUNTIME.bind_scene_module("tests.demo", "tests.module")
    scene = DemoScene(wizard)

    assert await scene.require_service("sample_service") == "module-value"
    assert await scene.require_service("fallback_service") == "fallback-value"


@pytest.mark.asyncio
async def test_services_call_supports_direct_callable_service_bindings(wizard) -> None:
    calls: list[str] = []

    async def audit_logger(message: str) -> None:
        calls.append(message)

    RUNTIME.reset()
    RUNTIME.service_container = MappingContainer({"audit_logger": audit_logger})
    scene = DemoScene(wizard)

    await scene.services.call("audit_logger", "hello")

    assert calls == ["hello"]


@pytest.mark.asyncio
async def test_services_call_supports_provider_returning_callable(wizard) -> None:
    calls: list[str] = []

    async def audit_logger(message: str) -> None:
        calls.append(message)

    RUNTIME.reset()
    RUNTIME.service_container = MappingContainer({"audit_logger": lambda: audit_logger})
    scene = DemoScene(wizard)

    await scene.services.call("audit_logger", "hello")

    assert calls == ["hello"]


@pytest.mark.asyncio
async def test_require_service_returns_direct_callable_without_invoking_it(wizard) -> None:
    async def collector(report: str) -> str:
        return report

    RUNTIME.reset()
    RUNTIME.service_container = MappingContainer({"collector": collector})
    scene = DemoScene(wizard)

    resolved = await scene.require_service("collector")

    assert resolved is collector


@pytest.mark.asyncio
async def test_confirm_scene_default_rows_are_built(wizard) -> None:
    scene = DemoConfirmScene(wizard)
    rows = await scene.confirm_rows(SimpleNamespace())

    assert rows[0][0].text == "✅ Подтвердить"
    assert rows[0][0].callback_data == ConfirmAction(action="confirm")
    assert rows[1][0].callback_data == ConfirmAction(action="cancel")
    assert rows[1][0].text == "✖️ Отмена"


@pytest.mark.asyncio
async def test_confirm_scene_confirm_handler_is_called(wizard) -> None:
    from tests.conftest import FakeCallbackQuery

    scene = DemoConfirmScene(wizard)
    call = FakeCallbackQuery()

    await scene._confirm_action(call)

    assert scene.confirmed is True
    assert call.answer_calls == [None]


@pytest.mark.asyncio
async def test_confirm_scene_reject_handler_is_called(wizard) -> None:
    from tests.conftest import FakeCallbackQuery

    scene = DemoConfirmScene(wizard)
    call = FakeCallbackQuery()

    await scene._reject_action(call)

    assert scene.rejected is True
    assert call.answer_calls == ["Отменено"]


@pytest.mark.asyncio
async def test_paginated_scene_remembers_page(wizard) -> None:
    scene = DemoPaginatedScene(wizard)

    await scene.remember_page(3)

    assert await scene.current_page() == 3


@pytest.mark.asyncio
async def test_paginated_scene_defaults_to_first_page_for_invalid_state(wizard) -> None:
    wizard.data = {"_page": "bad"}
    scene = DemoPaginatedScene(wizard)

    assert await scene.current_page() == 1


@pytest.mark.asyncio
async def test_navigator_home_uses_runtime_default_home(wizard) -> None:
    scene = DemoScene(wizard)
    RUNTIME.default_home = "tests.demo"

    await scene.nav.home(step=2)

    assert wizard.goto_calls == []
    assert wizard.leave_calls == [(False, {"step": 2})]
    assert wizard.manager.history.cleared is True
    assert wizard.manager.enter_calls == [("tests.demo", False, {"step": 2})]
    assert wizard.data["_scene_stack"] == ["tests.demo"]


@pytest.mark.asyncio
async def test_navigator_role_home_uses_role_specific_target(wizard) -> None:
    scene = DemoScene(wizard)
    RUNTIME.default_home = "tests.demo"
    RUNTIME.home_by_role = {SceneRole.ADMIN.value: "tests.confirm"}

    await scene.nav.role_home(SceneRole.ADMIN)

    assert wizard.goto_calls == []
    assert wizard.leave_calls == [(False, {})]
    assert wizard.manager.history.cleared is True
    assert wizard.manager.enter_calls == [("tests.confirm", False, {})]
    assert wizard.data["_scene_stack"] == ["tests.confirm"]


@pytest.mark.asyncio
async def test_navigator_back_uses_back_target_override(wizard) -> None:
    scene = DemoScene(wizard)
    wizard.data = {"_back_target": "tests.confirm", "_scene_stack": ["tests.menu", "tests.demo"]}

    await scene.nav.back()

    assert wizard.goto_calls == []
    assert wizard.leave_calls == [(False, {})]
    assert wizard.manager.enter_calls == [("tests.confirm", False, {})]
    assert wizard.data["_scene_stack"] == ["tests.confirm"]
    assert "_back_target" not in wizard.data
    assert wizard.back_calls == []


@pytest.mark.asyncio
async def test_navigator_back_can_route_home_via_back_target_override(wizard) -> None:
    scene = DemoScene(wizard)
    scene.home_scene = "tests.demo"
    wizard.data = {
        "_back_target": BACK_TARGET_HOME,
        "_scene_stack": ["tests.menu", "tests.confirm"],
    }

    await scene.nav.back(step=1)

    assert wizard.goto_calls == []
    assert wizard.leave_calls == [(False, {"step": 1})]
    assert wizard.manager.history.cleared is True
    assert wizard.manager.enter_calls == [("tests.demo", False, {"step": 1})]
    assert wizard.data["_scene_stack"] == ["tests.demo"]
    assert "_back_target" not in wizard.data
    assert wizard.back_calls == []


@pytest.mark.asyncio
async def test_navigator_replace_enters_target_without_snapshotting_current_scene(wizard) -> None:
    scene = DemoScene(wizard)

    await scene.nav.replace("tests.confirm", reset_history=True, page=2)

    assert wizard.manager.history.cleared is True
    assert wizard.leave_calls == [(False, {"page": 2})]
    assert wizard.manager.enter_calls == [("tests.confirm", False, {"page": 2})]
    assert wizard.data["_scene_stack"] == ["tests.confirm"]


@pytest.mark.asyncio
async def test_navigate_open_replaces_current_scene_without_duplicating_history(
    wizard,
    monkeypatch,
) -> None:
    from tests.conftest import FakeCallbackQuery

    monkeypatch.setattr(base_module, "CallbackQuery", FakeCallbackQuery)
    scene = DemoScene(wizard)
    call = FakeCallbackQuery()

    await scene._navigate_open(call, Navigate.open("tests.demo"))

    assert wizard.goto_calls == []
    assert wizard.leave_calls == [(False, {})]
    assert wizard.manager.enter_calls == [("tests.demo", False, {})]
    assert wizard.data["_scene_stack"] == ["tests.demo"]


@pytest.mark.asyncio
async def test_navigator_to_pushes_target_scene_to_screen_stack(wizard) -> None:
    scene = DemoScene(wizard)
    wizard.data = {"_scene_stack": ["tests.menu", "tests.demo"]}

    await scene.nav.to("tests.confirm")

    assert wizard.goto_calls == [("tests.confirm", {})]
    assert wizard.data["_scene_stack"] == ["tests.menu", "tests.demo", "tests.confirm"]


@pytest.mark.asyncio
async def test_navigator_back_uses_custom_scene_stack_before_aiogram_history(wizard) -> None:
    scene = DemoScene(wizard)
    wizard.data = {"_scene_stack": ["tests.menu", "tests.list", "tests.demo"]}

    await scene.nav.back()

    assert wizard.goto_calls == []
    assert wizard.back_calls == []
    assert wizard.leave_calls == [(False, {})]
    assert wizard.manager.enter_calls == [("tests.list", False, {})]
    assert wizard.data["_scene_stack"] == ["tests.menu", "tests.list"]


@pytest.mark.asyncio
async def test_navigator_previous_before_reads_scene_stack_history(wizard) -> None:
    scene = DemoScene(wizard)
    from tests.conftest import HistoryRecordStub

    wizard.manager.history.records = [
        HistoryRecordStub("tests.menu"),
        HistoryRecordStub("tests.list"),
        HistoryRecordStub("tests.detail"),
    ]

    assert await scene.nav.previous_scene_state() == "tests.detail"
    assert await scene.nav.previous_before("tests.list") == "tests.menu"


@pytest.mark.asyncio
async def test_resolve_roles_returns_default_user_role_when_resolver_missing(wizard) -> None:
    scene = DemoScene(wizard)
    RUNTIME.role_resolver = None

    assert await scene.resolve_roles(SimpleNamespace()) == {SceneRole.USER.value}


def test_step_scene_declared_steps_are_sorted_numerically() -> None:
    assert DemoStepScene.declared_steps() == ("step_1", "step_2", "step_10")


@pytest.mark.asyncio
async def test_step_scene_auto_saves_input_and_moves_forward(wizard) -> None:
    from tests.conftest import FakeMessage

    scene = DemoStepScene(wizard)
    message = FakeMessage(text="Alice")

    await scene._on_step_input(message)

    assert wizard.data["step_1"] == "Alice"
    assert wizard.data["_step"] == "step_2"
    assert message.answer_calls[-1]["text"] == "Step 2"


@pytest.mark.asyncio
async def test_step_scene_can_move_back(wizard) -> None:
    from tests.conftest import FakeMessage

    wizard.data = {"_step": "step_2"}
    scene = DemoStepScene(wizard)
    message = FakeMessage()

    await scene.prev_step(message)

    assert wizard.data["_step"] == "step_1"
    assert message.answer_calls[-1]["text"] == "Step 1"


@pytest.mark.asyncio
async def test_step_scene_calls_completion_hook_on_last_step(wizard) -> None:
    from tests.conftest import FakeMessage

    wizard.data = {"_step": "step_10"}
    scene = DemoStepScene(wizard)
    message = FakeMessage(text="done")

    await scene._on_step_input(message)

    assert wizard.data["step_10"] == "done"
    assert scene.completed is True


@pytest.mark.asyncio
async def test_step_scene_next_callback_moves_forward(wizard, monkeypatch) -> None:
    from tests.conftest import FakeCallbackQuery

    monkeypatch.setattr(base_module, "CallbackQuery", FakeCallbackQuery)
    scene = DemoStepScene(wizard)
    call = FakeCallbackQuery()

    await scene._next_action(call)

    assert wizard.data["_step"] == "step_2"
    assert call.answer_calls == [None]


@pytest.mark.asyncio
async def test_step_scene_back_callback_moves_backward(wizard, monkeypatch) -> None:
    from tests.conftest import FakeCallbackQuery

    monkeypatch.setattr(base_module, "CallbackQuery", FakeCallbackQuery)
    wizard.data = {"_step": "step_2"}
    scene = DemoStepScene(wizard)
    call = FakeCallbackQuery()

    await scene._back_action(call)

    assert wizard.data["_step"] == "step_1"
    assert call.answer_calls == [None]


@pytest.mark.asyncio
async def test_step_scene_exit_callback_exits_scene(wizard) -> None:
    from tests.conftest import FakeCallbackQuery

    scene = DemoStepScene(wizard)
    call = FakeCallbackQuery()

    await scene._exit_action(call)

    assert wizard.exit_calls == [{}]
    assert call.answer_calls == [None]
