# Scenegram

`scenegram` — framework-обёртка над `aiogram` scenes для production-разработки Telegram-ботов.

Библиотека решает не задачу “сделать ещё один FSM helper”, а задачу собрать устойчивый scene-layer:

- auto-discovery и auto-registration сцен без ручного реестра;
- роли, домашние сцены и модульные menu contributions;
- безопасные внутренние переходы между сценами с role-guard не только на entrypoints, но и на `goto/enter`;
- portable scene modules, которые можно переносить между ботами вместе с логикой;
- встроенные patterns для menu, pagination, confirm, step, forms, CRUD и background broadcast;
- нативная поддержка `aiogram.utils.formatting` без собственного markup DSL;
- service container, typed state accessors, cleanup policies, scene-level screen history, middlewares, chat actions и runtime hooks.

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

### 3.1. Typed scene state

Помимо raw `self.data`, framework теперь поддерживает typed state model через descriptor `state_model(...)`.

```python
from dataclasses import dataclass

from scenegram import AppScene, state_model


@dataclass(slots=True)
class ProfileDraft:
    name: str | None = None
    email: str | None = None


class ProfileScene(AppScene, state="profile.edit"):
    __abstract__ = False
    draft = state_model(ProfileDraft, key="_draft", default_factory=ProfileDraft)

    async def save_name(self, message):
        await self.draft.patch(name=message.text)
```

Для low-level сценариев `SceneDataProxy` теперь даёт `async with self.data.mutate(): ...`, чтобы собрать несколько изменений в один `set_data(...)` и при необходимости защитить framework keys.

### 3.2. Secure scene access

Role-фильтры теперь применяются не только на entrypoints, но и на внутренних переходах сцен.

Это означает:

- `Navigate.open("admin.dashboard")` не откроет закрытую сцену пользователю без роли;
- `self.nav.to(...)`, `self.nav.replace(...)`, `wizard.goto(...)` и `ScenesManager.enter(...)` проходят через guard;
- при запрете перехода пользователь получает короткий notice, а framework не кладёт forbidden scene в stack.

### 3.3. Deep links как часть scene-layer

Scenegram теперь работает с deep links не как с ручным `/start ...`, а как с частью scene framework.

Поддерживаются два паттерна одновременно:

- `DeepLinkMenuScene` / `DeepLinkScene` — стартовая сцена, которая ловит `/start`, разбирает payload и открывает нужный flow;
- `deep_link_scene(...)` / `deep_link_handler(...)` — декларативные deep-link routes, которые можно объявлять на start scene, на portable `SceneModule` или прямо на target scene.

Bootstrap:

```python
create_scenes_router(
    package_name="bot.scenes",
    default_home="common.start",
    deep_link_secret="stable-secret",
)
```

- `deep_link_secret` включает signed inline deep links;
- если payload большой, ссылка временная или one-time, scenegram автоматически использует opaque stored token;
- для production можно передать свой `deep_link_store`, если нужна Redis/DB-backed реализация.

Стартовая сцена:

```python
from scenegram import DeepLinkMenuScene, deep_link_handler


class StartScene(DeepLinkMenuScene, state="common.start"):
    __abstract__ = False
    deep_links = (
        deep_link_handler("app.referral", "handle_referral"),
    )

    async def handle_referral(self, event, context):
        payload = dict(context.payload or {})
        await self.data.update(referrer_id=payload.get("referrer_id"))
        return await self.render_menu(event)
```

Deep link прямо на target scene:

```python
from scenegram import CrudDetailScene, deep_link_scene


class CatalogDetailScene(CrudDetailScene, state="catalog.detail"):
    __abstract__ = False
    deep_links = (
        deep_link_scene(
            "catalog.product",
            payload_key="item_id",
            back_target="catalog.list",
        ),
    )
```

Route автоматически привяжется к `catalog.detail`, даже если state не указан в helper-е.

Генерация ссылок внутри сцены:

```python
# постоянная ссылка на сцену
scene_link = await self.deep_links.scene(
    "catalog.detail",
    payload={"item_id": "starter"},
    back_target="catalog.list",
)

# временная ссылка
temporary = await self.deep_links.temporary_scene(
    "catalog.detail",
    ttl_seconds=300,
    payload={"item_id": "starter"},
)

# one-time ссылка
one_time = await self.deep_links.one_time_scene(
    "admin.broadcast",
    ttl_seconds=300,
    roles={"admin"},
)

# реферальная ссылка
referral = await self.deep_links.referral(
    referrer_id=message.from_user.id,
    campaign="spring",
    target_scene="common.start",
)

# кастомный route
promo = await self.deep_links.create(
    "app.referral",
    {"referrer_id": message.from_user.id},
)
```

Что это даёт:

- deep link может открыть меню, сцену, товар, админскую функцию или отдельный form flow;
- есть signed, temporary, permanent и one-time режимы;
- back-навигация остаётся логичной через `back_target`;
- доступ проверяется и на уровне route, и на уровне target scene.

### 4. Cleanup policies

Глобально и локально можно управлять:

- удалением предыдущего screen message;
- удалением пользовательских сообщений;
- сохранением breadcrumbs/history.

При этом back-навигация хранит именно стек главных экранов сцен:

- `main -> admin -> broadcast` вернёт `broadcast -> admin -> main`;
- пагинация, form steps, confirm-step и другие внутренние рендеры не засоряют back-stack;
- same-scene refresh/update не создаёт новых history entries.
- `cancel` закрывает текущую сцену к её `home_scene`, сохраняя родительский back-stack;
- `home` и `/start` считаются root-navigation и сбрасывают стек до целевого root screen.

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

Встроенно на каждый scene router также ставятся:

- security middleware, который оборачивает `data["scenes"]` в secure manager proxy;
- error middleware, который эмитит runtime event на необработанные ошибки scene-layer.

### 6. Reply keyboard на шагах ввода

`StepScene` и `FormScene` теперь умеют автоматически показывать standard reply keyboard на шагах, где у пользователя нет inline-кнопок.

По умолчанию:

- на input screen появляется reply-кнопка `Отмена`;
- кнопка ловится built-in handler-ом сцены;
- на cancel framework отправляет `message.answer(..., reply_markup=ReplyKeyboardRemove())`;
- после этого делает `nav.cancel()` к `home_scene` текущей сцены, не ломая родительский scene stack.

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

### 6.1. Карусель вопросов внутри формы

`FormScene` умеет работать в двух режимах:

- строгая форма: пользователь обязан отвечать последовательно, шаги переключаются только после ввода;
- carousel-форма: сцена показывает кнопки `Предыдущий вопрос` / `Следующий вопрос` / `Пропустить`, и пользователь может перелистывать уже заполненные поля.

Включается это на уровне конкретной сцены:

```python
from scenegram import FormField, FormScene


class SurveyScene(FormScene, state="survey.start"):
    __abstract__ = False
    home_scene = "common.start"
    step_pagination = True
    use_confirm_step = True
    fields = (
        FormField(name="name", prompt="Как вас зовут?"),
        FormField(
            name="telegram",
            prompt="Какой Telegram указать для связи?",
            required=False,
        ),
        FormField(name="email", prompt="Какой e-mail использовать?"),
    )
```

Правила:

- `edit` из confirm screen по умолчанию возвращает на первый вопрос;
- `step_pagination = True` добавляет question-level navigation в reply keyboard;
- `required=False` делает поле пропускаемым;
- если поле обязательное и ещё не заполнено, `Следующий вопрос` не перелистнёт форму молча.

Если нужно старое поведение с возвратом к последнему вопросу, можно явно задать:

```python
class LegacyEditScene(FormScene, state="legacy.edit"):
    __abstract__ = False
    edit_restart_from = "last"
```

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

### 8. Callback namespaces и observability hooks

Для portable modules можно использовать namespaced callback prefixes, чтобы не ловить коллизии между модулями:

```python
from aiogram.filters.callback_data import CallbackData

from scenegram import cb_namespace

catalog_cb = cb_namespace("catalog.module")


class CatalogItemCb(CallbackData, prefix=catalog_cb.callback_prefix("item")):
    action: str
    item_id: str
```

`create_scenes_router(...)` теперь fail-fast валидирует callback prefix collisions на старте.

Runtime также поддерживает observer hooks:

```python
from scenegram import RUNTIME


async def log_scene_events(event):
    print(event.name, event.state, event.target_state, event.metadata)


RUNTIME.observe(log_scene_events)
```

Framework эмитит события на render, transition, operation start/success/error, unhandled errors и background task lifecycle.

### 9. Нативный aiogram formatting

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
├── cli.py               # scenegram CLI (check / generate)
├── contracts.py         # typed contracts и module manifests
├── deep_links.py        # deep-link runtime, tokens, route helpers
├── di.py                # containers/adapters
├── runtime.py           # runtime state и defaults
├── history.py           # breadcrumbs/history proxy
├── security.py          # secure scene access / manager proxy
├── state.py             # typed state descriptors
├── namespaces.py        # callback namespace helpers
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

После подключения можно проверить пакет сцен и сгенерировать шаблоны:

```bash
scenegram check bot.scenes
scenegram generate scene --state common.start --class-name StartScene
scenegram generate module --name catalog --package-name bot.scenes.catalog --target-state catalog.list --menu-target common.start
```

Для разработки этого репозитория:

```bash
uv sync --group dev
pre-commit install
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
        deep_link_secret="stable-secret",
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

from scenegram import Button, DeepLinkMenuScene, Navigate, SceneRole, deep_link_handler


class StartScene(DeepLinkMenuScene, state="common.start"):
    __abstract__ = False
    home_for_roles = frozenset({SceneRole.USER.value, SceneRole.ADMIN.value})
    deep_links = (
        deep_link_handler("app.referral", "handle_referral"),
    )

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

    async def handle_referral(self, event, context):
        payload = dict(context.payload or {})
        await self.data.update(referrer_id=payload.get("referrer_id"))
        return await self.render_menu(event)
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
    step_pagination = True
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
- `state_model(...)`
- `SceneModule`
- `SceneMiddleware`
- `SceneCleanup`
- `SceneActionConfig`
- `create_scenes_router(...)`
- `DeepLinkManager`
- `deep_link_scene(...)`
- `deep_link_handler(...)`

### Patterns

- `MenuScene`
- `DeepLinkMenuScene`
- `DeepLinkScene`
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
- `cb_namespace(...)`
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
