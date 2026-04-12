from __future__ import annotations

from typing import Any

from aiogram.utils.formatting import (
    BlockQuote,
    Bold,
    BotCommand,
    CashTag,
    Code,
    CustomEmoji,
    Email,
    ExpandableBlockQuote,
    HashTag,
    Italic,
    PhoneNumber,
    Pre,
    Spoiler,
    Strikethrough,
    Text,
    TextLink,
    TextMention,
    Underline,
    Url,
    as_key_value,
    as_line,
    as_list,
    as_marked_list,
    as_marked_section,
    as_numbered_list,
    as_numbered_section,
    as_section,
)

type RenderableText = Text | str | int | float | bool


def stringify(value: RenderableText | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def render_text(
    content: RenderableText | None,
    *,
    text_key: str = "text",
    entities_key: str = "entities",
    replace_parse_mode: bool = True,
    parse_mode_key: str = "parse_mode",
) -> dict[str, Any]:
    if isinstance(content, Text):
        return content.as_kwargs(
            text_key=text_key,
            entities_key=entities_key,
            replace_parse_mode=replace_parse_mode,
            parse_mode_key=parse_mode_key,
        )
    return {text_key: stringify(content)}


def render_caption(
    content: RenderableText | None,
    *,
    replace_parse_mode: bool = True,
) -> dict[str, Any]:
    if isinstance(content, Text):
        return content.as_caption_kwargs(replace_parse_mode=replace_parse_mode)
    return {"caption": stringify(content)}


def render_poll_question(
    content: RenderableText | None,
    *,
    replace_parse_mode: bool = True,
) -> dict[str, Any]:
    if isinstance(content, Text):
        return content.as_poll_question_kwargs(replace_parse_mode=replace_parse_mode)
    return {"question": stringify(content)}


def render_poll_explanation(
    content: RenderableText | None,
    *,
    replace_parse_mode: bool = True,
) -> dict[str, Any]:
    if isinstance(content, Text):
        return content.as_poll_explanation_kwargs(replace_parse_mode=replace_parse_mode)
    return {"explanation": stringify(content)}


def render_gift_text(
    content: RenderableText | None,
    *,
    replace_parse_mode: bool = True,
) -> dict[str, Any]:
    if isinstance(content, Text):
        return content.as_gift_text_kwargs(replace_parse_mode=replace_parse_mode)
    return {"text": stringify(content)}


__all__ = [
    "BlockQuote",
    "Bold",
    "BotCommand",
    "CashTag",
    "Code",
    "CustomEmoji",
    "Email",
    "ExpandableBlockQuote",
    "HashTag",
    "Italic",
    "PhoneNumber",
    "Pre",
    "RenderableText",
    "Spoiler",
    "Strikethrough",
    "Text",
    "TextLink",
    "TextMention",
    "Underline",
    "Url",
    "as_key_value",
    "as_line",
    "as_list",
    "as_marked_list",
    "as_marked_section",
    "as_numbered_list",
    "as_numbered_section",
    "as_section",
    "render_caption",
    "render_gift_text",
    "render_poll_explanation",
    "render_poll_question",
    "render_text",
    "stringify",
]
