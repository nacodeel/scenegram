from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.scene import on
from aiogram.types import CallbackQuery
from aiogram.utils.formatting import Bold, as_key_value, as_list, as_section

from scenegram import Button, Navigate, PaginatedScene, inline_menu, pager_rows, paginate

PRODUCTS = [
    {"id": 1, "title": "Starter Pack", "price": "9.90"},
    {"id": 2, "title": "Growth Pack", "price": "19.90"},
    {"id": 3, "title": "Pro Pack", "price": "29.90"},
    {"id": 4, "title": "Enterprise Pack", "price": "49.90"},
    {"id": 5, "title": "Campaign Pack", "price": "59.90"},
    {"id": 6, "title": "Retention Pack", "price": "69.90"},
    {"id": 7, "title": "Loyalty Pack", "price": "79.90"},
]


class ProductAction(CallbackData, prefix="product"):
    product_id: int


class CatalogScene(PaginatedScene, state="common.catalog"):
    __abstract__ = False
    page_size = 3
    home_scene = "common.start"

    async def render_page(self, event, *, page: int = 1):
        window = paginate(PRODUCTS, page, per_page=self.page_size)
        await self.remember_page(window.page)

        rows = [
            [Button(text=item["title"], callback_data=ProductAction(product_id=item["id"]))]
            for item in window.items
        ]
        rows.extend(pager_rows(window, back=True, home=True, home_target="common.start"))

        content = as_list(
            Bold("Каталог"),
            as_section(
                Bold("Что показывает сцена"),
                as_key_value("Страница", f"{window.page}/{window.pages}"),
                as_key_value("Всего элементов", window.total),
            ),
            sep="\n\n",
        )
        await self.show(event, content, reply_markup=inline_menu(rows))

    @on.callback_query(ProductAction.filter())
    async def open_product(self, call: CallbackQuery, callback_data: ProductAction) -> None:
        product = next(item for item in PRODUCTS if item["id"] == callback_data.product_id)
        content = as_list(
            Bold(product["title"]),
            as_key_value("Price", product["price"]),
            "Тут можно открыть checkout, карточку товара или любое следующее действие.",
            sep="\n\n",
        )
        await self.show(
            call,
            content,
            reply_markup=inline_menu(
                [
                    [
                        Button(
                            text="⬅️ Назад к списку",
                            callback_data=Navigate.open("common.catalog"),
                        )
                    ],
                    [Button(text="🏠 Домой", callback_data=Navigate.home("common.start"))],
                ]
            ),
        )
