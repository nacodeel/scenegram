from __future__ import annotations

from aiogram.utils.formatting import Bold

from examples.showcase_bot.services import AudienceBroadcastAdapter
from scenegram import (
    BroadcastScene,
    FormField,
    SceneActionConfig,
    SceneCleanup,
    SceneRole,
    broadcast_module,
)

SCENEGRAM_MODULE = broadcast_module(
    name="showcase.broadcast",
    package_name=__name__,
    scene_state="admin.broadcast",
    menu_target="admin.dashboard",
    menu_text="📣 Рассылка",
    menu_row=0,
    menu_order=10,
    broadcast=AudienceBroadcastAdapter(),
)


class AdminBroadcastScene(BroadcastScene, state="admin.broadcast"):
    __abstract__ = False
    roles = frozenset({SceneRole.ADMIN.value})
    home_scene = "admin.dashboard"
    cleanup = SceneCleanup(delete_previous_screen=True, delete_user_messages=True)
    default_chat_action = SceneActionConfig(action="typing", interval=4.0)
    confirm_title = Bold("Проверьте текст перед запуском фоновой рассылки")
    fields = (
        FormField(
            name="content",
            prompt="Какой текст нужно отправить аудитории?",
            summary_label="Broadcast text",
        ),
    )

    async def on_broadcast_complete(self, report) -> None:
        await self.services.call(
            "audit_logger",
            f"broadcast.finished job={report.job_id} sent={report.sent}/{report.total}",
        )
