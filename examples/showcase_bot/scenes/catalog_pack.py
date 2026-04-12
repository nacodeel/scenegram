from __future__ import annotations

from examples.showcase_bot.services import PRODUCTS, ProductCrudAdapter
from scenegram import (
    CrudDeleteScene,
    CrudDetailScene,
    CrudListScene,
    crud_module,
)

SCENEGRAM_MODULE = crud_module(
    name="showcase.catalog",
    package_name=__name__,
    list_state="catalog.list",
    menu_target="common.start",
    menu_text="🧩 CRUD pack",
    menu_row=0,
    menu_order=20,
    crud=ProductCrudAdapter(PRODUCTS),
)


class CatalogListScene(CrudListScene, state="catalog.list"):
    __abstract__ = False
    home_scene = "common.start"
    detail_scene = "catalog.detail"
    title = "Portable CRUD module"


class CatalogDetailScene(CrudDetailScene, state="catalog.detail"):
    __abstract__ = False
    home_scene = "common.start"
    list_scene = "catalog.list"
    delete_scene = "catalog.delete"
    title = "Product detail"


class CatalogDeleteScene(CrudDeleteScene, state="catalog.delete"):
    __abstract__ = False
    home_scene = "common.start"
    list_scene = "catalog.list"

    async def after_delete(self, event, item) -> None:
        await self.services.call("audit_logger", f"catalog.delete item={item.id}")
