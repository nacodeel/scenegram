from __future__ import annotations

from aiogram.utils.formatting import Bold, as_list, as_marked_list

from scenegram import Button, MenuScene, Navigate, SceneRole, command_entry


class AdminDashboardScene(MenuScene, state="admin.dashboard"):
    __abstract__ = False
    entrypoints = (command_entry("admin"),)
    roles = frozenset({SceneRole.ADMIN.value})
    home_for_roles = frozenset({SceneRole.ADMIN.value})
    navigation_back = True
    navigation_home = True
    navigation_home_target = "common.start"

    async def menu_content(self, event):
        return as_list(
            Bold("Admin dashboard"),
            as_marked_list(
                "Роль ограничена через role_resolver",
                "Сцена нашлась автоматически по пакету scenes",
                "Навигация собирается базовым классом",
                "Рассылка ниже подключается как portable module через menu contribution",
            ),
            sep="\n\n",
        )

    async def menu_rows(self, event):
        return [
            [Button(text="📦 Каталог", callback_data=Navigate.open("common.catalog"))],
            [Button(text="🗑 Очистить черновик", callback_data=Navigate.open("common.delete"))],
        ]
