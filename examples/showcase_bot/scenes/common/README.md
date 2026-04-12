# Common Scenes

Папка `common/` содержит пользовательские сцены, доступные обычному пользователю.

## Что внутри

- `start.py` — главное меню;
- `catalog.py` — ручной пример `PaginatedScene`;
- `delete.py` — ручной пример `ConfirmScene`;
- `onboarding.py` — форма на `FormScene`.

## Роль в системе

Это пример обычных экранов бота, которые не оформлены как переносимый модуль и принадлежат конкретному приложению.

## Что уже реализовано

- menu hub;
- pagination flow;
- confirm flow;
- cleanup-aware onboarding form с auto reply-кнопкой `Отмена`;
- использование глобальных сервисов контейнера.

## Ограничения

- здесь не лежат reusable portable modules;
- тяжёлые сценарии вынесены в соседние модули `catalog_pack.py` и `admin_broadcast.py`.

## Правила расширения

- сохранять локальность: scene-specific callbacks и тексты держать рядом;
- если сцена становится reusable между ботами, выносить её в отдельный модуль с `SCENEGRAM_MODULE`;
- при добавлении новой группы common-сцен обновлять этот README.
