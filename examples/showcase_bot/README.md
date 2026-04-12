# Showcase Bot

Этот пример показывает канонический способ использования `scenegram` в реальном боте.

## Что внутри

- `main.py` — bootstrap `Dispatcher`, storage, event isolation, role resolver;
- `scenes/common/start.py` — меню на `MenuScene`;
- `scenes/common/catalog.py` — каталог на `PaginatedScene`;
- `scenes/common/delete.py` — подтверждение действия на `ConfirmScene`;
- `scenes/common/onboarding.py` — декларативная форма на `FormScene`;
- `scenes/admin.py` — role-scoped admin scene.

## Что смотреть в первую очередь

1. как `create_scenes_router(package_name="examples.showcase_bot.scenes")` подключает весь пакет сцен;
2. как каждая сцена импортирует только framework-классы из `scenegram`;
3. как текст экранов собирается напрямую через `aiogram.utils.formatting`;
4. как callbacks и pagination остаются локальными для своих модулей.
