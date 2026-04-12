from __future__ import annotations

from aiogram.utils.formatting import Bold, as_list

from scenegram import Button, ConfirmScene, Navigate, inline_menu


class DeleteDraftScene(ConfirmScene, state="common.delete"):
    __abstract__ = False
    home_scene = "common.start"
    confirm_text = as_list(
        Bold("Очистить локальный черновик?"),
        "Пример built-in ConfirmScene: остаётся переопределить текст и действие подтверждения.",
        sep="\n\n",
    )

    async def on_confirm(self, event) -> None:
        await self.data.clear()
        await self.show(
            event,
            as_list(
                Bold("Черновик очищен"),
                "State data сцены сброшены, экран перерендерен тем же helper-методом.",
                sep="\n\n",
            ),
            reply_markup=inline_menu(
                [[Button(text="🏠 Вернуться в меню", callback_data=Navigate.home("common.start"))]]
            ),
        )
