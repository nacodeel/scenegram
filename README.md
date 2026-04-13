# Scenegram

`scenegram` — framework-обёртка над `aiogram` scenes для production-разработки Telegram-ботов.

Библиотека решает не задачу “сделать ещё один FSM helper”, а задачу собрать устойчивый scene-layer:

- auto-discovery и auto-registration сцен без ручного реестра;
- роли, домашние сцены и модульные menu contributions;
- portable scene modules, которые можно переносить между ботами вместе с логикой;
- встроенные patterns для menu, pagination, confirm, step, forms, CRUD и background broadcast;
- нативная поддержка `aiogram.utils.formatting` без собственного markup DSL;
- service container, module-local adapters, cleanup policies, breadcrumbs/history, scene middlewares и chat actions.

## Что теперь умеет framework

### 1. Автоподключение сцен

`create_scenes_router(...)` сканирует ваш пакет сцен, находит классы на базе `AppScene`, регистрирует их в `SceneRegistry` и собирает `Router`.

### 2. Переносимые scene modules

Любой модуль сцены может объявить `SCENEGRAM_MODULE = SceneModule(...)` или использовать helper вроде `crud_module(...)` / `broadcast_module(...)`.

Модуль может нести:

- локальные сервисы и адаптеры;
- auto-added пункты меню;
- metadata/tags;
- собственный package prefix для automatic binding.

Это делает сцену или набор сцен самодостаточными: подключили пакет к боту, пробросили нужные сервисы, и модуль сразу работает.

### 3. Service injection

Есть два уровня DI:

- глобальный `service_container` при bootstrap;
- локальные сервисы внутри `SceneModule`.

В сцене сервисы доступны через:

```python
await self.services.get("name")
await self.services.require("name")
await self.services.call("audit_logger", "message")
```

Приоритет такой:

1. `SceneModule.services`
2. глобальный `service_container`

### 4. Cleanup policies

Глобально и локально можно управлять:

- удалением предыдущего screen message;
- удалением пользовательских сообщений;
- сохранением breadcrumbs/history.

Глобально:

```python
from scenegram import SceneCleanup

create_scenes_router(
    package_name="bot.scenes",
    cleanup=SceneCleanup(
        delete_previous_screen=True,
        delete_user_messages=False,
        remember_history=True,
    ),
)
```

На уровне сцены:

```python
class SurveyScene(FormScene, state="survey.start"):
    __abstract__ = False
    cleanup = SceneCleanup(
        delete_previous_screen=True,
        delete_user_messages=True,
    )
```

### 5. Scene middlewares

`scenegram` умеет вешать middleware:

- глобально на весь scenes router через `create_scenes_router(..., middlewares=...)`;
- локально на конкретную сцену через `Scene.middlewares`;
- локально на переносимый `SceneModule`, чтобы middleware ехала вместе с модулем.

Под капотом это собирается через обычные aiogram router middlewares (`middleware(...)` / `outer_middleware(...)`), но framework сам создаёт wrapper-router на каждую сцену, поэтому entrypoints и scene handlers проходят через один и тот же pipeline.

```python
from aiogram import BaseMiddleware
from scenegram import SceneModule, create_scenes_router, scene_middleware


class AuditMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        data["audit_enabled"] = True
        return await handler(event, data)


class SurveyScene(FormScene, state="survey.start"):
    __abstract__ = False
    middlewares = (
        scene_middleware(AuditMiddleware, "message", "callback_query", factory=True),
    )


SCENEGRAM_MODULE = SceneModule(
    name="survey.module",
    package_name=__name__,
    middlewares=(
        scene_middleware(AuditMiddleware, "message", factory=True),
    ),
)


create_scenes_router(
    package_name="bot.scenes",
    middlewares=(
        scene_middleware(AuditMiddleware, "message", factory=True),
    ),
)
```

### 6. Reply keyboard на шагах ввода

`StepScene` и `FormScene` теперь умеют автоматически показывать standard reply keyboard на шагах, где у пользователя нет inline-кнопок.

По умолчанию:

- на input screen появляется reply-кнопка `Отмена`;
- кнопка ловится built-in handler-ом сцены;
- на cancel framework отправляет `message.reply("Отменено", reply_markup=ReplyKeyboardRemove())`;
- после этого делает `nav.home()`.

Можно настраивать:

```python
from scenegram import FormField, FormScene, ReplyButton


class SurveyScene(FormScene, state="survey.start"):
    __abstract__ = False
    home_scene = "common.start"
    reply_rows = (
        (ReplyButton(text="Помощь"),),
    )
    reply_navigation_cancel = True
    fields = (
        FormField(name="name", prompt="Как вас зовут?"),
    )
```

Если scene-level prompt должен полностью отключить auto reply keyboard, можно передать `reply_markup=None` в `self.show(...)` или выставить `use_reply_keyboard = False`.

### 7. Chat actions

Для долгих операций можно декларативно включать `sendChatAction` через `default_chat_action` и `chat_actions`.

```python
from scenegram import SceneActionConfig

class HeavyScene(AppScene, state="heavy.run"):
    __abstract__ = False
    default_chat_action = SceneActionConfig(action="typing")
    chat_actions = {
        "generate_report": SceneActionConfig(action="upload_document"),
    }
```

Framework сам оборачивает `run_operation(...)` в `async with ChatActionSender(...)`, если для операции задан action.
По официальному aiogram sender крутит action, пока не завершится операция, без ручной длительности на стороне вашей сцены.

### 8. Нативный aiogram formatting

`scenegram` не подменяет `aiogram.utils.formatting`.

Правильный путь:

- в сценах вы импортируете `Text`, `Bold`, `as_list`, `as_section`, `as_key_value` напрямую из `aiogram`;
- `AppScene.show(...)` и built-in scenes принимают эти объекты нативно;
- framework лишь правильно рендерит `text + entities`, не заставляя вас работать через HTML/Markdown-строки.

Пример:

```python
from aiogram.utils.formatting import Bold, as_key_value, as_list

await self.show(
    message,
    as_list(
        Bold("Profile"),
        as_key_value("Name", "Alice"),
        as_key_value("Plan", "Pro"),
        sep="\n\n",
    ),
)
```

## Архитектура библиотеки

```text
scenegram/
├── __init__.py          # top-level API
├── base.py              # AppScene, data/services/history/navigation
├── bootstrap.py         # discovery, descriptors, router assembly
├── contracts.py         # typed contracts и module manifests
├── di.py                # containers/adapters
├── runtime.py           # runtime state и defaults
├── history.py           # breadcrumbs/history proxy
├── tasks.py             # background task runner
├── patterns.py          # MenuScene / ConfirmScene / StepScene / FormScene
├── packs.py             # CrudListScene / CrudDetailScene / CrudDeleteScene
├── background.py        # BroadcastScene
└── ui/                  # keyboards, pagination, callbacks
```

## Установка

```bash
uv add scenegram
```

Для разработки этого репозитория:

```bash
uv sync --group dev
```

## Быстрый старт в своём боте

### 1. Структура проекта

```text
bot/
├── app.py
├── services.py
└── scenes/
    ├── __init__.py
    ├── common/
    │   ├── __init__.py
    │   ├── start.py
    │   └── onboarding.py
    ├── catalog_pack.py
    └── admin_broadcast.py
```

### 2. Bootstrap dispatcher

```python
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation

from scenegram import SceneCleanup, SceneRole, create_scenes_router

from .services import build_service_container


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
        package_name="bot.scenes",
        role_resolver=resolve_roles,
        default_home="common.start",
        service_container=build_service_container(),
        cleanup=SceneCleanup(
            delete_previous_screen=True,
            delete_user_messages=False,
            remember_history=True,
        ),
    )
    dispatcher.include_router(scenes.router)
    return dispatcher
```

### 3. Базовая menu scene

```python
from aiogram.utils.formatting import Bold, as_list, as_marked_list

from scenegram import Button, MenuScene, Navigate, SceneRole, command_entry


class StartScene(MenuScene, state="common.start"):
    __abstract__ = False
    entrypoints = (command_entry("start"),)
    home_for_roles = frozenset({SceneRole.USER.value, SceneRole.ADMIN.value})

    async def menu_content(self, event):
        return as_list(
            Bold("Главное меню"),
            as_marked_list(
                "сцена подключается автоматически",
                "вкладки модулей добавляются сами",
                "entities-first formatting идёт напрямую через aiogram",
            ),
            sep="\n\n",
        )

    async def menu_rows(self, event):
        return [
            [Button(text="🧭 Анкета", callback_data=Navigate.open("common.onboarding"))],
            [Button(text="🗑 Очистить черновик", callback_data=Navigate.open("common.delete"))],
        ]
```

### 4. FormScene с cleanup policy и DI

```python
from dataclasses import dataclass

from aiogram.utils.formatting import Bold, as_key_value, as_list

from scenegram import Button, FormField, FormScene, Navigate, SceneCleanup, inline_menu


@dataclass(slots=True)
class OnboardingResult:
    name: str
    email: str


class OnboardingScene(FormScene, state="common.onboarding"):
    __abstract__ = False
    home_scene = "common.start"
    cleanup = SceneCleanup(delete_previous_screen=True, delete_user_messages=True)
    result_model = OnboardingResult
    use_confirm_step = True
    fields = (
        FormField(name="name", prompt="Как вас зовут?"),
        FormField(name="email", prompt="Какой e-mail использовать?", validator="validate_email"),
    )

    async def validate_email(self, value: str) -> str | None:
        if "@" not in value:
            return "Нужен корректный e-mail."
        return None

    async def on_form_submit(self, event, result: OnboardingResult) -> None:
        await self.services.call("audit_logger", f"onboarding.submit email={result.email}")
        await self.show(
            event,
            as_list(
                Bold("Анкета заполнена"),
                as_key_value("Name", result.name),
                as_key_value("Email", result.email),
                sep="\n\n",
            ),
            reply_markup=inline_menu(
                [[Button(text="🏠 В меню", callback_data=Navigate.home("common.start"))]]
            ),
        )
```

## Portable scene modules

### CRUD pack

Встроенные CRUD сцены можно собрать как переносимый модуль:

```python
from scenegram import CrudDeleteScene, CrudDetailScene, CrudListScene, crud_module

SCENEGRAM_MODULE = crud_module(
    name="catalog",
    package_name=__name__,
    list_state="catalog.list",
    menu_target="common.start",
    menu_text="🧩 CRUD pack",
    crud=ProductCrudAdapter(products),
)


class CatalogListScene(CrudListScene, state="catalog.list"):
    __abstract__ = False
    detail_scene = "catalog.detail"
    home_scene = "common.start"


class CatalogDetailScene(CrudDetailScene, state="catalog.detail"):
    __abstract__ = False
    list_scene = "catalog.list"
    delete_scene = "catalog.delete"


class CatalogDeleteScene(CrudDeleteScene, state="catalog.delete"):
    __abstract__ = False
    list_scene = "catalog.list"
```

Что это даёт:

- модуль сам регистрируется при discovery;
- в целевое меню автоматически добавляется кнопка;
- CRUD adapter живёт рядом со сценами, а не размазан по приложению;
- модуль можно перенести в другой бот почти без изменений.

### Background broadcast pack

`BroadcastScene` делает background-задачу через runtime task runner и вызывает adapter callbacks после завершения.

```python
from scenegram import BroadcastScene, FormField, SceneCleanup, broadcast_module

SCENEGRAM_MODULE = broadcast_module(
    name="broadcast",
    package_name=__name__,
    scene_state="admin.broadcast",
    menu_target="admin.dashboard",
    menu_text="📣 Рассылка",
    broadcast=AudienceBroadcastAdapter(),
)


class AdminBroadcastScene(BroadcastScene, state="admin.broadcast"):
    __abstract__ = False
    home_scene = "admin.dashboard"
    cleanup = SceneCleanup(delete_previous_screen=True, delete_user_messages=True)
    fields = (
        FormField(name="content", prompt="Какой текст нужно отправить аудитории?"),
    )
```

По умолчанию сцена:

- собирает форму текста рассылки;
- запускает background task;
- ограничивает скорость отправки (`broadcast_rate_limit`);
- ограничивает параллелизм (`broadcast_concurrency`);
- применяет timeout (`broadcast_timeout`);
- собирает `BroadcastReport`;
- вызывает `adapter.on_complete(...)` и `scene.on_broadcast_complete(...)`.

## Built-in classes

### Core

- `AppScene`
- `SceneDataProxy`
- `SceneServicesProxy`
- `SceneHistoryProxy`
- `SceneNavigator`
- `SceneModule`
- `SceneMiddleware`
- `SceneCleanup`
- `SceneActionConfig`
- `create_scenes_router(...)`

### Patterns

- `MenuScene`
- `PaginatedScene`
- `ConfirmScene`
- `StepScene`
- `FormScene`
- `CrudListScene`
- `CrudDetailScene`
- `CrudDeleteScene`
- `BroadcastScene`

### UI / helpers

- `Button`, `ReplyButton`
- `Navigate`, `PageNav`
- `inline_menu`, `reply_menu`, `nav_row`, `reply_nav_row`
- `scene_middleware(...)`
- `paginate`, `pager_rows`

## Showcase examples

Полноценный reference bot лежит в [examples/showcase_bot](./examples/showcase_bot/README.md).

Что там показано:

- `main.py` — bootstrap с `service_container` и глобальным cleanup;
- `services.py` — глобальные сервисы, CRUD adapter и broadcast adapter;
- `scenes/common/start.py` — главное меню;
- `scenes/common/onboarding.py` — форма с cleanup и DI;
- `scenes/common/catalog.py` — базовая пагинация;
- `scenes/catalog_pack.py` — portable CRUD module;
- `scenes/admin_broadcast.py` — portable background broadcast module;
- `scenes/admin.py` — admin menu с auto-added вкладкой рассылки.

## Команды разработки

```bash
uv run --cache-dir .uv-cache ruff check
uv run --cache-dir .uv-cache pytest
```

## Текущий статус

Реализовано:

- runtime-aware scene layer;
- module manifests и auto menu contributions;
- service container + module-local services;
- cleanup/history/chat action policies;
- built-in CRUD и background broadcast packs;
- flat package layout без `src/`;
- тестовое покрытие core/runtime/examples-level contracts.

Ближайшие шаги:

- richer declarative form widgets;
- selection/list-picker packs;
- больше observability hooks и trace points;
- adapters для популярных DI контейнеров.
