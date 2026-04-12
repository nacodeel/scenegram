# Package Notes

Пакет `scenegram/` содержит framework-level код, который должен оставаться переносимым между ботами.

## Что лежит внутри

- `base.py` — базовая сцена, state proxy, navigation helpers;
- `bootstrap.py` — discovery, descriptors, entrypoints, scene router assembly;
- `formatting.py` — внутренний render helper, который обеспечивает поддержку `aiogram.utils.formatting` в `show(...)`;
- `patterns.py` — built-in scene patterns (`MenuScene`, `ConfirmScene`, `StepScene`, `FormScene`);
- `ui/` — callback data, keyboard builders, pagination helpers;
- `roles.py`, `runtime.py` — role-scoped routing runtime.

## Правила расширения

- не тащить в пакет бизнес-логику конкретного бота;
- не хардкодить сервисы, репозитории или доменные модели;
- новые built-in scenes должны быть переиспользуемыми и автономными;
- formatting support должен оставаться совместимым с прямым использованием `aiogram.utils.formatting`;
- discovery/bootstrap не должны требовать ручного реестра сцен.

## Что уже реализовано

- auto-discovery сцен по пакету;
- role-aware bootstrap;
- top-level imports из `scenegram`;
- built-in menu/confirm/pagination/step/form patterns;
- typed helpers для state, navigation и formatting;
- тестовое покрытие ключевых слоев.

## Следующий этап

- дополнительные reusable scenes для list/detail/selection flows;
- richer step/form widgets;
- больше observability hooks для production integration.
