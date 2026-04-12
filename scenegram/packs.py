from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from aiogram import F
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.scene import on
from aiogram.types import CallbackQuery, Message
from aiogram.utils.formatting import Bold, as_key_value, as_list, as_marked_list

from .base import BACK_TARGET_HOME, AppScene
from .contracts import CrudAdapter, CrudListItem, CrudPage, MenuContribution, SceneModule
from .patterns import ConfirmScene
from .ui import Button, inline_menu
from .ui.pagination import PageWindow, pager_rows


class CrudAction(CallbackData, prefix="crud"):
    action: str
    item_id: str = ""


class CrudListScene(AppScene):
    __abstract__ = True

    page_size = 10
    page_state_key = "_crud_page"
    crud_adapter_key = "crud"
    crud_adapter: CrudAdapter | None = None
    detail_scene: str | None = None
    empty_text = "Записи не найдены."
    title = "Список"
    navigation_home = True

    async def resolve_crud_adapter(self) -> CrudAdapter:
        if self.crud_adapter is not None:
            return self.crud_adapter
        return await self.require_service(self.crud_adapter_key)

    async def current_page(self) -> int:
        page = await self.data.get(self.page_state_key, 1)
        if not isinstance(page, int) or page < 1:
            return 1
        return page

    async def remember_page(self, page: int) -> None:
        await self.data.update({self.page_state_key: max(page, 1)})

    async def render_page(self, event: Message | CallbackQuery, *, page: int = 1) -> Any:
        adapter = await self.resolve_crud_adapter()
        crud_page = await self.run_operation(
            "list_items",
            event,
            adapter.list_items,
            self,
            page,
            self.page_size,
        )
        await self.remember_page(crud_page.page)
        rows = self.build_item_rows(crud_page.items)

        if not rows:
            rows = []

        rows.extend(self.pagination_rows(crud_page))
        content = await self.page_content(crud_page)
        return await self.show(event, content, reply_markup=inline_menu(rows))

    async def page_content(self, page: CrudPage) -> Any:
        if not page.items:
            return as_list(Bold(self.title), self.empty_text, sep="\n\n")
        return as_list(
            Bold(self.title),
            as_marked_list(*(item.title for item in page.items)),
            sep="\n\n",
        )

    def build_item_rows(self, items: Sequence[CrudListItem]) -> list[list[Button]]:
        return [
            [
                Button(
                    text=self.item_button_text(item),
                    callback_data=CrudAction(action="open", item_id=str(item.id)),
                )
            ]
            for item in items
        ]

    def item_button_text(self, item: CrudListItem) -> str:
        parts = [item.title]
        if item.badge:
            parts.append(item.badge)
        if item.description:
            parts.append(f"({item.description})")
        return " ".join(parts)

    def pagination_rows(self, page: CrudPage) -> list[list[Button]]:
        window = PageWindow(
            items=page.items,
            page=page.page,
            pages=page.pages,
            total=page.total,
            per_page=self.page_size,
            prev_page=page.page - 1 if page.page > 1 else page.pages,
            next_page=page.page + 1 if page.page < page.pages else 1,
        )
        return pager_rows(
            window,
            back=True,
            home=self.navigation_home,
            home_target=self.home_scene or "",
        )

    @on.message.enter()
    async def _on_message_enter(self, message: Message) -> None:
        await self.render_page(message, page=await self.current_page())

    @on.callback_query.enter()
    async def _on_callback_enter(self, call: CallbackQuery) -> None:
        await call.answer()
        await self.render_page(call, page=await self.current_page())

    @on.callback_query(CrudAction.filter(F.action == "open"))
    async def _open_item(self, call: CallbackQuery, callback_data: CrudAction) -> None:
        await call.answer()
        if not self.detail_scene:
            raise RuntimeError(f"{self.__class__.__name__} requires detail_scene")
        await self.nav.to(self.detail_scene, item_id=callback_data.item_id)


class CrudDetailScene(AppScene):
    __abstract__ = True

    crud_adapter_key = "crud"
    crud_adapter: CrudAdapter | None = None
    list_scene: str | None = None
    edit_scene: str | None = None
    delete_scene: str | None = None
    title = "Карточка"
    missing_item_notice = "Запись больше не найдена."

    async def resolve_crud_adapter(self) -> CrudAdapter:
        if self.crud_adapter is not None:
            return self.crud_adapter
        return await self.require_service(self.crud_adapter_key)

    async def current_item_id(self) -> str:
        return str(await self.data.require("item_id"))

    async def remember_item_id(self, item_id: str | None = None) -> str:
        if item_id is None:
            stored_item_id = await self.data.get("item_id")
            if stored_item_id is None:
                raise LookupError("Missing item_id")
            return str(stored_item_id)
        await self.data.update(item_id=str(item_id))
        return str(item_id)

    async def load_item(self, event: Message | CallbackQuery) -> Any:
        adapter = await self.resolve_crud_adapter()
        item_id = await self.current_item_id()
        try:
            return await self.run_operation("get_item", event, adapter.get_item, self, item_id)
        except LookupError:
            raise
        except RuntimeError as exc:
            if "StopIteration" in str(exc):
                raise LookupError(item_id) from exc
            raise

    async def handle_missing_item(self, event: Message | CallbackQuery) -> None:
        await self.data.discard("item_id")
        if isinstance(event, CallbackQuery):
            await event.answer(self.missing_item_notice)
        if self.list_scene:
            await self.nav.to(self.list_scene)
            return
        await self.nav.home()

    async def detail_rows(self, item_id: str) -> list[list[Button]]:
        rows: list[list[Button]] = []
        if self.edit_scene:
            rows.append(
                [
                    Button(
                        text="✏️ Редактировать",
                        callback_data=CrudAction(action="edit", item_id=item_id),
                    )
                ]
            )
        if self.delete_scene:
            rows.append(
                [
                    Button(
                        text="🗑 Удалить",
                        callback_data=CrudAction(action="delete", item_id=item_id),
                    )
                ]
            )
        rows.append(
            [Button(text="⬅️ Назад", callback_data=CrudAction(action="back", item_id=item_id))]
        )
        return rows

    async def detail_content(self, event: Message | CallbackQuery, item: Any) -> Any:
        adapter = await self.resolve_crud_adapter()
        title = await self.run_operation(
            "get_item_title",
            event,
            adapter.get_item_title,
            self,
            item,
        )
        fields = await self.run_operation(
            "get_item_fields",
            event,
            adapter.get_item_fields,
            self,
            item,
        )
        return as_list(
            Bold(title or self.title),
            *(as_key_value(field.label, field.value) for field in fields),
            sep="\n\n",
        )

    async def render_detail(self, event: Message | CallbackQuery) -> Any:
        item = await self.load_item(event)
        item_id = await self.current_item_id()
        return await self.show(
            event,
            await self.detail_content(event, item),
            reply_markup=inline_menu(await self.detail_rows(item_id)),
        )

    @on.message.enter()
    async def _on_message_enter(self, message: Message, item_id: str | None = None) -> None:
        try:
            await self.remember_item_id(item_id)
            await self.render_detail(message)
        except LookupError:
            await self.handle_missing_item(message)

    @on.callback_query.enter()
    async def _on_callback_enter(self, call: CallbackQuery, item_id: str | None = None) -> None:
        await call.answer()
        try:
            await self.remember_item_id(item_id)
            await self.render_detail(call)
        except LookupError:
            await self.handle_missing_item(call)

    @on.callback_query(CrudAction.filter(F.action == "back"))
    async def _go_back(self, call: CallbackQuery) -> None:
        await call.answer()
        if self.list_scene:
            await self.nav.to(self.list_scene)
            return
        await self.nav.back()

    @on.callback_query(CrudAction.filter(F.action == "edit"))
    async def _go_edit(self, call: CallbackQuery, callback_data: CrudAction) -> None:
        await call.answer()
        if not self.edit_scene:
            return
        await self.nav.to(self.edit_scene, item_id=callback_data.item_id)

    @on.callback_query(CrudAction.filter(F.action == "delete"))
    async def _go_delete(self, call: CallbackQuery, callback_data: CrudAction) -> None:
        await call.answer()
        if not self.delete_scene:
            return
        await self.nav.to(self.delete_scene, item_id=callback_data.item_id)


class CrudDeleteScene(ConfirmScene):
    __abstract__ = True

    crud_adapter_key = "crud"
    crud_adapter: CrudAdapter | None = None
    list_scene: str | None = None
    success_notice = "Запись удалена"
    missing_item_notice = "Запись уже удалена или недоступна."

    async def resolve_crud_adapter(self) -> CrudAdapter:
        if self.crud_adapter is not None:
            return self.crud_adapter
        return await self.require_service(self.crud_adapter_key)

    async def current_item_id(self) -> str:
        return str(await self.data.require("item_id"))

    async def remember_item_id(self, item_id: str | None = None) -> str:
        if item_id is None:
            stored_item_id = await self.data.get("item_id")
            if stored_item_id is None:
                raise LookupError("Missing item_id")
            return str(stored_item_id)
        await self.data.update(item_id=str(item_id))
        return str(item_id)

    async def current_item(self, event: Message | CallbackQuery) -> Any:
        adapter = await self.resolve_crud_adapter()
        item_id = await self.current_item_id()
        try:
            return await self.run_operation(
                "get_item",
                event,
                adapter.get_item,
                self,
                item_id,
            )
        except LookupError:
            raise
        except RuntimeError as exc:
            if "StopIteration" in str(exc):
                raise LookupError(item_id) from exc
            raise

    async def handle_missing_item(self, event: Message | CallbackQuery) -> None:
        await self.data.discard("item_id")
        if isinstance(event, CallbackQuery):
            await event.answer(self.missing_item_notice)
        if self.list_scene:
            await self.nav.to(self.list_scene)
            return
        await self.nav.home()

    async def confirm_content(self, event: Message | CallbackQuery):
        adapter = await self.resolve_crud_adapter()
        item = await self.current_item(event)
        title = await self.run_operation(
            "get_item_title",
            event,
            adapter.get_item_title,
            self,
            item,
        )
        return as_list(Bold("Подтверждение удаления"), f"Удалить {title}?", sep="\n\n")

    async def on_confirm(self, event: CallbackQuery) -> Any:
        adapter = await self.resolve_crud_adapter()
        try:
            item = await self.current_item(event)
        except LookupError:
            await self.handle_missing_item(event)
            return
        await self.run_operation("delete_item", event, adapter.delete_item, self, item)
        await event.answer(self.success_notice)
        await self.after_delete(event, item)
        if self.list_scene:
            await self.data.update(_back_target=BACK_TARGET_HOME)
            await self.nav.to(self.list_scene)
            return
        await self.nav.exit()

    async def after_delete(self, event: CallbackQuery, item: Any) -> None:
        return None

    @on.message.enter()
    async def _on_message_enter(self, message: Message, item_id: str | None = None) -> None:
        try:
            await self.remember_item_id(item_id)
            await super()._on_message_enter(message)
        except LookupError:
            await self.handle_missing_item(message)

    @on.callback_query.enter()
    async def _on_callback_enter(self, call: CallbackQuery, item_id: str | None = None) -> None:
        try:
            await self.remember_item_id(item_id)
            await super()._on_callback_enter(call)
        except LookupError:
            await self.handle_missing_item(call)


def crud_module(
    *,
    name: str,
    package_name: str,
    list_state: str,
    menu_target: str,
    menu_text: str = "📚 Список",
    menu_row: int | None = None,
    menu_order: int = 100,
    **services: Any,
) -> SceneModule:
    return SceneModule(
        name=name,
        package_name=package_name,
        title="CRUD",
        description="Portable CRUD scene pack",
        services=services,
        menu_entries=(
            MenuContribution(
                target_state=menu_target,
                text=menu_text,
                target_scene=list_state,
                row=menu_row,
                order=menu_order,
            ),
        ),
        tags=frozenset({"crud", "list", "detail"}),
        metadata={"list_state": list_state},
    )


__all__ = [
    "CrudAction",
    "CrudDeleteScene",
    "CrudDetailScene",
    "CrudListScene",
    "crud_module",
]
