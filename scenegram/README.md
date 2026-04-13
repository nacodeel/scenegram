# Package Notes

Папка `scenegram/` содержит framework-level код, который должен оставаться переносимым между ботами и не тянуть в себя бизнес-логику конкретного проекта.

## Содержимое пакета

- `base.py` — `AppScene`, data/services/history/navigation proxies, render pipeline, cleanup, chat actions.
- `bootstrap.py` — discovery, descriptors, role-aware router assembly, scene registry bootstrap.
- `cli.py` — CLI для `check` и генерации шаблонов сцен/модулей.
- `contracts.py` — typed contracts для scene modules, middleware bindings, menu contributions, cleanup, CRUD и broadcast adapters.
- `deep_links.py` — deep-link runtime, secure/stored token strategies, route helpers и start-scene integration.
- `di.py` — mapping/composite/null containers и service resolution helpers.
- `runtime.py` — shared runtime, cleanup defaults, module registry, menu contribution routing, task runner.
- `history.py` — breadcrumbs proxy и отдельный screen-stack proxy поверх scene data.
- `security.py` — role guards и secure scenes manager proxy.
- `state.py` — typed state accessors поверх scene data.
- `namespaces.py` — callback namespace helpers.
- `tasks.py` — in-process background task runner для модульных сцен.
- `patterns.py` — `MenuScene`, `ConfirmScene`, `StepScene`, `FormScene`.
- `packs.py` — built-in CRUD scene pack и `crud_module(...)`.
- `background.py` — `BroadcastScene` и `broadcast_module(...)`.
- `ui/` — inline/reply keyboard builders, callback payloads, pagination helpers.

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
- typed state descriptors и mutation contexts поверх raw scene data;
- deep-link entry scenes, scene-attached routes и stored/signed deep-link execution;
- cleanup policies и breadcrumbs/history;
- screen-stack navigation только по главным экранам сцен;
- global/module/scene middlewares;
- secure role guards на внутренних `enter/goto` переходах;
- callback prefix validation и namespaced helpers для portable modules;
- runtime observer hooks на transitions/render/operations/tasks;
- declarative chat actions;
- step/forms с typed result model, auto reply-keyboards и optional step-carousel внутри анкет;
- portable CRUD and broadcast packs;
- top-level public API и CLI через `scenegram.__init__` / `scenegram` script.

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
- middleware применяются через wrapper-router на сцену, чтобы entrypoints и scene handlers шли через единый pipeline.
- внутренние переходы дополнительно проверяются на роли через secure manager proxy, а не только через router filters.
- deep links используют официальный Telegram/aiogram стартовый механизм, но route registry, one-time/ttl semantics и scene opening остаются внутри framework runtime.
- reply keyboard на form/step сценах остаётся opt-out и удаляется на cancel через `ReplyKeyboardRemove`, а не через неявное поведение клиента.
- глобальный `back` идёт по собственному scene screen stack, а не по промежуточным step/page/confirm состояниям.
- `cancel` возвращает к `home_scene` текущей сцены без потери родительского back-stack, а `home`/`/start` выполняют root reset.
- `FormScene` по умолчанию возвращает `edit` на первый вопрос, а carousel/skip поведение включается декларативно на уровне сцены и отдельного `FormField`.
- background task runner хранит lifecycle/status в памяти процесса и даёт bounded-concurrency базу для `BroadcastScene`.

## Правила расширения

- не добавлять сюда доменные сущности конкретных ботов;
- не хардкодить infra adapters под один стек;
- новые packs должны быть самодостаточными и переносимыми;
- scene-level middlewares должны объявляться через typed bindings, а не через ручную регистрацию снаружи;
- middleware/update context должен быть доступен и в aiogram handlers, и во framework-level scene hooks через именованные параметры или `self.context`;
- любой новый runtime hook обязан иметь тесты;
- при значимых изменениях обновлять этот README и корневой README.

## Ближайшие планы

- расширить declarative form layer полями/виджетами beyond text input;
- добавить scene packs для selection/filter/detail workflows;
- усилить observability hooks;
- подготовить отдельные adapters для популярных service containers.
