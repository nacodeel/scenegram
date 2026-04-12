from __future__ import annotations

from aiogram.utils.formatting import Bold, HashTag, as_list, as_marked_list, as_section

from scenegram import Button, MenuScene, Navigate, SceneRole, command_entry


class StartScene(MenuScene, state="common.start"):
    __abstract__ = False
    entrypoints = (command_entry("start"),)
    home_for_roles = frozenset({SceneRole.USER.value, SceneRole.ADMIN.value})

    async def menu_content(self, event):
        return as_list(
            Bold("Scenegram Showcase"),
            as_section(
                Bold("Внутри этой сцены"),
                as_marked_list(
                    "авто-discovery по вашему пакету scenes",
                    "menu contributions от portable scene modules",
                    "service container и module-local adapters",
                    "форматирование через aiogram entities вместо HTML/Markdown",
                    "готовые MenuScene / PaginatedScene / CRUD / Broadcast / FormScene",
                ),
            ),
            HashTag("#scenegram"),
            sep="\n\n",
        )

    async def menu_rows(self, event):
        rows = [
            [Button(text="🧭 Анкета", callback_data=Navigate.open("common.onboarding"))],
            [Button(text="📄 Пагинация", callback_data=Navigate.open("common.catalog"))],
            [Button(text="🗑 Очистить черновик", callback_data=Navigate.open("common.delete"))],
        ]

        roles = await self.resolve_roles(event)
        if SceneRole.ADMIN.value in roles:
            rows.append(
                [Button(text="🛠 Админ-панель", callback_data=Navigate.open("admin.dashboard"))]
            )

        return rows
