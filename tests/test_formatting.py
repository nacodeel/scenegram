from __future__ import annotations

import pytest
from aiogram.enums import MessageEntityType

from scenegram.formatting import (
    Bold,
    Text,
    render_caption,
    render_gift_text,
    render_poll_explanation,
    render_poll_question,
    render_text,
    stringify,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("hello", "hello"),
        (42, "42"),
        (True, "True"),
    ],
)
def test_stringify_handles_supported_values(value, expected) -> None:
    assert stringify(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("hello", {"text": "hello"}),
        (42, {"text": "42"}),
        (False, {"text": "False"}),
    ],
)
def test_render_text_with_plain_values(value, expected) -> None:
    assert render_text(value) == expected


def test_render_text_with_entities() -> None:
    payload = render_text(Text("Hello, ", Bold("Alex"), "!"))

    assert payload["text"] == "Hello, Alex!"
    assert payload["parse_mode"] is None
    assert len(payload["entities"]) == 1
    assert payload["entities"][0].type == MessageEntityType.BOLD


def test_render_caption_with_plain_value() -> None:
    assert render_caption("caption") == {"caption": "caption"}


def test_render_caption_with_entities() -> None:
    payload = render_caption(Text(Bold("Caption")))

    assert payload["caption"] == "Caption"
    assert payload["parse_mode"] is None
    assert payload["caption_entities"][0].type == MessageEntityType.BOLD


def test_render_poll_question_with_plain_value() -> None:
    assert render_poll_question("Question?") == {"question": "Question?"}


def test_render_poll_question_with_entities() -> None:
    payload = render_poll_question(Text(Bold("Question")))

    assert payload["question"] == "Question"
    assert payload["question_entities"][0].type == MessageEntityType.BOLD


def test_render_poll_explanation_with_plain_value() -> None:
    assert render_poll_explanation("Because") == {"explanation": "Because"}


def test_render_poll_explanation_with_entities() -> None:
    payload = render_poll_explanation(Text(Bold("Because")))

    assert payload["explanation"] == "Because"
    assert payload["explanation_entities"][0].type == MessageEntityType.BOLD


def test_render_gift_text_with_plain_value() -> None:
    assert render_gift_text("Gift") == {"text": "Gift"}


def test_render_gift_text_with_entities() -> None:
    payload = render_gift_text(Text(Bold("Gift")))

    assert payload["text"] == "Gift"
    assert payload["text_entities"][0].type == MessageEntityType.BOLD
