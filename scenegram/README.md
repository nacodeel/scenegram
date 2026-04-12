# Package Notes

Папка `scenegram/` содержит framework-level код, который должен оставаться переносимым между ботами и не тянуть в себя бизнес-логику конкретного проекта.

## Содержимое пакета

- `base.py` — `AppScene`, data/services/history/navigation proxies, render pipeline, cleanup, chat actions.
- `bootstrap.py` — discovery, descriptors, role-aware router assembly, scene registry bootstrap.
- `contracts.py` — typed contracts для scene modules, menu contributions, cleanup, CRUD и broadcast adapters.
- `di.py` — mapping/composite/null containers и service resolution helpers.
- `runtime.py` — shared runtime, cleanup defaults, module registry, menu contribution routing, task runner.
- `history.py` — breadcrumbs/history proxy поверх scene data.
- `tasks.py` — in-process background task runner для модульных сцен.
- `patterns.py` — `MenuScene`, `ConfirmScene`, `StepScene`, `FormScene`.
- `packs.py` — built-in CRUD scene pack и `crud_module(...)`.
- `background.py` — `BroadcastScene` и `broadcast_module(...)`.
- `ui/` — keyboard builders, callback payloads, pagination helpers.

## Архитектурная роль

Пакет является reusable scene framework-слоем. Его задача:

- дать устойчивую абстракцию поверх aiogram scenes;
- не дублировать официальный API aiogram без необходимости;
- поддерживать нативный `aiogram.utils.formatting`;
- предоставлять переносимые building blocks для меню, форм, CRUD и background сценариев;
- оставаться совместимым с разными ботами через DI и module manifests.

## Что уже реализовано

- auto-discovery и auto-registration сцен;
- role-aware routing и home scenes;
- service container + module-local services;
- cleanup policies и breadcrumbs/history;
- declarative chat actions;
- step/forms с typed result model;
- portable CRUD and broadcast packs;
- top-level public API через `scenegram.__init__`.

## Что ещё не реализовано

- adapters для внешних DI frameworks;
- declarative field widgets beyond text input;
- selection/list picker packs;
- built-in persistence/queue backends для background jobs.

## Важные технические решения

- formatting не оборачивается в новый публичный DSL; поддерживается нативный aiogram `Text`.
- runtime остаётся process-local и лёгким; тяжёлые очереди пользователь подключает через свои adapters.
- scene packs не зависят от ORM/БД; всё доменное поведение идёт через adapters/services.
- module manifests завязаны на package prefix, чтобы сцены автоматически связывались со своим модулем.

## Правила расширения

- не добавлять сюда доменные сущности конкретных ботов;
- не хардкодить infra adapters под один стек;
- новые packs должны быть самодостаточными и переносимыми;
- любой новый runtime hook обязан иметь тесты;
- при значимых изменениях обновлять этот README и корневой README.

## Ближайшие планы

- расширить declarative form layer;
- добавить scene packs для selection/filter/detail workflows;
- усилить observability hooks;
- подготовить отдельные adapters для популярных service containers.
