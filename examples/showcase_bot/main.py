from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation

from scenegram import SceneRole, create_scenes_router


async def resolve_roles(event):
    user = getattr(event, "from_user", None)
    if user is None:
        user = getattr(getattr(event, "message", None), "from_user", None)

    if user and user.id == 1:
        return {SceneRole.USER.value, SceneRole.ADMIN.value}
    return {SceneRole.USER.value}


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(
        storage=MemoryStorage(),
        events_isolation=SimpleEventIsolation(),
    )

    scenes = create_scenes_router(
        package_name="examples.showcase_bot.scenes",
        role_resolver=resolve_roles,
        default_home="common.start",
    )
    dispatcher.include_router(scenes.router)
    return dispatcher


async def main() -> None:
    token = os.environ["BOT_TOKEN"]
    bot = Bot(token)
    dispatcher = create_dispatcher()
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
