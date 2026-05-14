from __future__ import annotations

import pytest

from scenegram import (
    Button,
    Navigate,
    PageNav,
    ReplyButton,
    inline_menu,
    nav_row,
    noop_button,
    pager_rows,
    paginate,
    reply_menu,
    reply_nav_row,
)


def test_inline_menu_packs_callback_data() -> None:
    markup = inline_menu([[Button(text="Catalog", callback_data=Navigate.open("common.catalog"))]])

    assert markup.inline_keyboard[0][0].callback_data == Navigate.open("common.catalog").pack()


def test_inline_menu_forwards_api_kwargs() -> None:
    markup = inline_menu(
        [[Button(text="Search", api_kwargs={"switch_inline_query_current_chat": "catalog"})]]
    )

    assert markup.inline_keyboard[0][0].switch_inline_query_current_chat == "catalog"


def test_reply_menu_forwards_api_kwargs() -> None:
    markup = reply_menu([[ReplyButton(text="Contact", api_kwargs={"request_contact": True})]])

    assert markup.keyboard[0][0].request_contact is True


def test_reply_menu_forwards_keyboard_level_kwargs() -> None:
    markup = reply_menu(
        [[ReplyButton(text="Cancel")]],
        one_time_keyboard=True,
        input_field_placeholder="Введите ответ",
        is_persistent=False,
    )

    assert markup.one_time_keyboard is True
    assert markup.input_field_placeholder == "Введите ответ"
    assert markup.is_persistent is False


def test_nav_row_respects_flags() -> None:
    buttons = nav_row(back=True, home=True, cancel=False, home_target="common.home")

    assert [button.text for button in buttons] == ["⬅️ Назад", "🏠 Домой"]
    assert buttons[1].callback_data == Navigate.home("common.home")


def test_reply_nav_row_respects_flags() -> None:
    buttons = reply_nav_row(back=True, home=False, cancel=True)

    assert [button.text for button in buttons] == ["Назад", "Отмена"]


def test_noop_button_uses_noop_callback() -> None:
    button = noop_button("1/5")

    assert button.callback_data == "noop"


def test_paginate_returns_expected_first_window() -> None:
    window = paginate(list(range(1, 11)), 1, per_page=4)

    assert window.items == [1, 2, 3, 4]
    assert window.page == 1
    assert window.pages == 3
    assert window.prev_page == 3
    assert window.next_page == 2


def test_paginate_clamps_page_to_last() -> None:
    window = paginate(list(range(1, 6)), 99, per_page=2)

    assert window.page == 3
    assert window.items == [5]


def test_paginate_rejects_zero_page_size() -> None:
    with pytest.raises(ValueError):
        paginate([1, 2, 3], 1, per_page=0)


def test_pager_rows_include_indicator_and_navigation() -> None:
    window = paginate(list(range(1, 11)), 2, per_page=4)
    rows = pager_rows(window, back=True, home=True, home_target="common.home")

    assert rows[0][0].callback_data == PageNav(page=window.prev_page)
    assert rows[0][1].callback_data == "noop"
    assert rows[1][1].callback_data == Navigate.home("common.home")


def test_pager_rows_omit_indicator_for_single_page() -> None:
    window = paginate([1, 2], 1, per_page=10)
    rows = pager_rows(window, back=False, home=True, cancel=True, home_target="common.home")

    assert len(rows) == 1
    assert [button.text for button in rows[0]] == ["🏠 Домой", "✖️ Отмена"]
