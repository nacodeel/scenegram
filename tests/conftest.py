from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from scenegram.runtime import RUNTIME


class HistoryRecordStub:
    def __init__(self, state: str) -> None:
        self.state = state


class HistoryManagerStub:
    def __init__(self) -> None:
        self.records: list[HistoryRecordStub] = []
        self.cleared = False

    async def all(self) -> list[HistoryRecordStub]:
        return list(self.records)

    async def clear(self) -> None:
        self.cleared = True
        self.records.clear()


class ManagerStub:
    def __init__(self) -> None:
        self.history = HistoryManagerStub()
        self.enter_calls: list[tuple[Any, bool, dict[str, Any]]] = []

    async def enter(self, scene: Any, _check_active: bool = True, **kwargs: Any) -> None:
        self.enter_calls.append((scene, _check_active, kwargs))


class WizardStub:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = dict(data or {})
        self.scene = None
        self.manager = ManagerStub()
        self.goto_calls: list[tuple[Any, dict[str, Any]]] = []
        self.back_calls: list[dict[str, Any]] = []
        self.retake_calls: list[dict[str, Any]] = []
        self.exit_calls: list[dict[str, Any]] = []
        self.leave_calls: list[tuple[bool, dict[str, Any]]] = []

    async def goto(self, target: Any, **kwargs: Any) -> None:
        self.goto_calls.append((target, kwargs))

    async def back(self, **kwargs: Any) -> None:
        self.back_calls.append(kwargs)

    async def retake(self, **kwargs: Any) -> None:
        self.retake_calls.append(kwargs)

    async def exit(self, **kwargs: Any) -> None:
        self.exit_calls.append(kwargs)

    async def leave(self, _with_history: bool = True, **kwargs: Any) -> None:
        self.leave_calls.append((_with_history, kwargs))

    async def get_data(self) -> dict[str, Any]:
        return dict(self.data)

    async def get_value(self, key: str, default: Any | None = None) -> Any | None:
        return self.data.get(key, default)

    async def update_data(
        self,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = dict(data or {})
        payload.update(kwargs)
        self.data.update(payload)
        return dict(self.data)

    async def set_data(self, data: dict[str, Any]) -> None:
        self.data = dict(data)

    async def clear_data(self) -> None:
        self.data.clear()


class FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))


class FakeResultMessage:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class FakeMessage:
    def __init__(
        self,
        *,
        bot: FakeBot | None = None,
        chat_id: int = 100,
        text: str = "",
        answer_message_id: int = 501,
        edit_message_id: int = 502,
        edit_exception: Exception | None = None,
    ) -> None:
        self.bot = bot or FakeBot()
        self.chat = SimpleNamespace(id=chat_id)
        self.text = text
        self.answer_message_id = answer_message_id
        self.edit_message_id = edit_message_id
        self.edit_exception = edit_exception
        self.answer_calls: list[dict[str, Any]] = []
        self.edit_calls: list[dict[str, Any]] = []

    async def answer(self, **kwargs: Any) -> FakeResultMessage:
        self.answer_calls.append(kwargs)
        return FakeResultMessage(self.answer_message_id)

    async def edit_text(self, **kwargs: Any) -> FakeResultMessage:
        self.edit_calls.append(kwargs)
        if self.edit_exception is not None:
            raise self.edit_exception
        return FakeResultMessage(self.edit_message_id)


class FakeCallbackQuery:
    def __init__(self, message: FakeMessage | None = None) -> None:
        self.message = message or FakeMessage()
        self.answer_calls: list[str | None] = []

    async def answer(self, text: str | None = None) -> None:
        self.answer_calls.append(text)


@pytest.fixture
def wizard() -> WizardStub:
    return WizardStub()


@pytest.fixture(autouse=True)
def reset_runtime() -> None:
    RUNTIME.reset()
    yield
    RUNTIME.reset()
