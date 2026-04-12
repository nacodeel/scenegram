# Scenegram

`scenegram` — это framework-обертка над `aiogram` scenes для production-разработки Telegram-ботов.

Идея простая:

- вы не пишете ручную регистрацию сцен;
- вы не держите гигантский `scenes/__init__.py`;
- вы не размазываете навигацию, pagination, confirm-flows и formatting по всему проекту;
- вы создаёте в своем боте собственную папку `scenes/`, а `scenegram` даёт базовые классы, bootstrap и готовые scene-patterns.

## Что решает framework

`scenegram` закрывает основные боли scene/FSM-слоя:

- автообнаружение сцен по пакету `scenes`;
- автоматическое подключение сцен в `SceneRegistry`;
- role-aware routing без ручной склейки routers;
- нормальная навигация `open / back / home / cancel`;
- нативная поддержка `aiogram.utils.formatting` в `show(...)`, без собственной обязательной DSL;
- переиспользуемые базовые классы для меню, confirm-flow, step-flow и форм;
- единый `SceneDataProxy` для работы с `SceneWizard.get_value/update_data`;
- удобный top-level API, чтобы импортировать нужные классы прямо из `scenegram`.

## Базовая модель использования

Вы ставите библиотеку и в своем боте заводите структуру вроде:

```text
bot/
├── app.py
├── services/
├── config/
└── scenes/
    ├── __init__.py
    ├── common/
    │   ├── __init__.py
    │   ├── start.py
    │   ├── catalog.py
    │   └── support.py
    └── admin.py
```

Внутри `scenes/` вы импортируете строительные блоки из `scenegram`:

```python
from scenegram import (
    AppScene,
    MenuScene,
    PaginatedScene,
    ConfirmScene,
    Button,
    Navigate,
    command_entry,
)
```

Дальше `scenegram` сам сканирует ваш пакет сцен и подключает найденные классы.

## Установка

```bash
uv add scenegram
```

Или для локальной разработки этого репозитория:

```bash
cd scenegram
uv sync --group dev
```

## Быстрый старт

### 1. Подключите bootstrap

```python
from aiogram import Dispatcher
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
        package_name="scenes",
        role_resolver=resolve_roles,
        default_home="common.start",
    )
    dispatcher.include_router(scenes.router)
    return dispatcher
```

### 2. Создайте первую сцену

```python
from aiogram.utils.formatting import Bold, as_list, as_marked_list

from scenegram import Button, MenuScene, Navigate, SceneRole, command_entry


class StartScene(MenuScene, state="common.start"):
    __abstract__ = False
    entrypoints = (command_entry("start"),)
    home_for_roles = frozenset({SceneRole.USER.value})

    async def menu_content(self, event):
        return as_list(
            Bold("Главное меню"),
            as_marked_list(
                "сцена нашлась автоматически",
                "screen rendering использует aiogram entities",
                "кнопки и навигация собираются декларативно",
            ),
            sep="\n\n",
        )

    async def menu_rows(self, event):
        return [
            [Button(text="Каталог", callback_data=Navigate.open("common.catalog"))],
        ]
```

Больше ничего вручную регистрировать не нужно.

## Что экспортируется из framework

### Core

- `AppScene` — минимальная базовая сцена;
- `SceneDataProxy` — обертка над `SceneWizard` data API;
- `SceneNavigator` — переходы `to/back/home/role_home/retake/exit`;
- `create_scenes_router()` — discovery + registry + router assembly;
- `command_entry()`, `message_entry()`, `callback_entry()` — entrypoint helpers.

### Built-in scene patterns

- `MenuScene` — декларативное меню с `menu_content()` и `menu_rows()`;
- `PaginatedScene` — built-in scene для списков и каталогов;
- `ConfirmScene` — подтверждение действия с готовыми callback handlers;
- `StepScene` — generic multi-step flow с `step_1()`, `step_2()`, ...;
- `FormScene` — декларативные формы на `FormField`, parser/validator hooks и typed result model.

### UI helpers

- `Button`, `ReplyButton`;
- `inline_menu()`, `reply_menu()`, `nav_row()`;
- `Navigate`, `PageNav`;
- `paginate()`, `pager_rows()`, `PageWindow`.

## Formatting

`scenegram` не требует отдельного formatting-слоя поверх aiogram. Правильный путь такой:

- вы импортируете `Text`, `Bold`, `as_list`, `as_section` и прочие элементы напрямую из `aiogram.utils.formatting`;
- `AppScene.show(...)` и built-in scenes принимают эти объекты нативно;
- scenegram лишь гарантирует, что entities корректно проходят через render/send/edit pipeline.

Почему это важно:

- отсутствие проблем с экранированием пользовательского ввода;
- отсутствие необходимости следить за парностью тегов;
- единый объект `Text`, который можно безопасно передавать в `message.answer`, `edit_text`, caption/poll/gift методы;
- более стабильную и предсказуемую сборку UI-текста.

Пример:

```python
from aiogram.utils.formatting import Bold, HashTag, as_key_value, as_list, as_section

content = as_list(
    Bold("Profile"),
    as_section(
        Bold("Summary"),
        as_key_value("Name", "Alice"),
        as_key_value("Status", "active"),
    ),
    HashTag("#scenegram"),
    sep="\n\n",
)

await self.show(message, content)
```

`AppScene.show(...)` принимает и обычную строку, и `Text`.

## Built-in patterns

### `MenuScene`

Подходит для главных меню, dashboards, hubs, action menus.

Что нужно переопределить:

- `menu_content(self, event)` — текст экрана;
- `menu_rows(self, event)` — список кнопок.

Опционально:

- `navigation_back = True`
- `navigation_home = True`
- `navigation_cancel = True`
- `navigation_home_target = "common.start"`

### `PaginatedScene`

Подходит для каталогов, списков заявок, списков пользователей, карточек сущностей.

Что нужно переопределить:

- `render_page(self, event, *, page: int = 1)`

Что уже есть из коробки:

- enter-handlers для message/callback;
- хранение текущей страницы;
- `current_page()` / `remember_page()`;
- `paginate()` и `pager_rows()`.

Пример:

```python
class CatalogScene(PaginatedScene, state="common.catalog"):
    __abstract__ = False
    page_size = 10

    async def render_page(self, event, *, page: int = 1):
        window = paginate(products, page, per_page=self.page_size)
        await self.remember_page(window.page)

        rows = [
            [Button(text=item.title, callback_data=ProductAction(product_id=item.id))]
            for item in window.items
        ]
        rows.extend(pager_rows(window, back=True, home=True, home_target="common.start"))
        await self.show(event, "Каталог", reply_markup=inline_menu(rows))
```

### `ConfirmScene`

Подходит для delete/reset/approve/reject flows.

Что нужно переопределить:

- `confirm_text` или `confirm_content(...)`;
- `on_confirm(...)`.

Опционально:

- `confirm_rows(...)`, если нужен кастомный layout;
- `on_reject(...)`, если нужно не просто `back()`.

### `StepScene`

Подходит для onboarding-flow, опросников, multi-step form wizard, анкет, checkout-цепочек.

Что даёт базовый класс:

- автоматически находит `step_1`, `step_2`, `step_3`, ...;
- хранит текущий шаг в state data;
- по умолчанию сохраняет текстовый ввод и переходит на следующий шаг;
- умеет переходить `next/back/exit` как из кода, так и через built-in callback handlers;
- позволяет переопределить `step_storage_key(...)`, чтобы ключи в state были доменными;
- вызывает `on_complete(...)` после последнего шага.

Минимальный пример:

```python
from aiogram.utils.formatting import Bold, as_list

from scenegram import StepScene, step_nav_row, inline_menu


class OnboardingScene(StepScene, state="common.onboarding"):
    __abstract__ = False

    def step_storage_key(self, step_name: str) -> str:
        return {
            "step_1": "name",
            "step_2": "email",
            "step_3": "goal",
        }[step_name]

    async def step_1(self, event):
        await self.show(
            event,
            as_list(Bold("Шаг 1/3"), "Как вас зовут?", sep="\n\n"),
            reply_markup=inline_menu([step_nav_row(exit_scene=True)]),
        )

    async def step_2(self, event):
        await self.show(event, as_list(Bold("Шаг 2/3"), "Какой у вас e-mail?", sep="\n\n"))

    async def step_3(self, event):
        await self.show(event, as_list(Bold("Шаг 3/3"), "Что хотите автоматизировать?", sep="\n\n"))

    async def on_complete(self, event):
        await self.show(event, "Анкета заполнена")
```

Если на конкретном шаге нужна своя логика валидации, можно добавить `handle_step_2(...)`, `handle_step_3(...)` и самостоятельно вызвать `await self.next_step(message, ...)`.

### `FormScene`

Подходит для декларативных form flows, где вы хотите описывать не методы `step_1/step_2`, а набор полей.

Что даёт базовый класс:

- `fields = (FormField(...), ...)`;
- parsers через `parser="parse_age"` или callable hook;
- validators через `validator="validate_email"` или callable hook;
- optional confirm-step;
- typed result model через `result_model = MyDataclass | MyPydanticModel`;
- submit/edit callbacks из коробки.

Пример:

```python
from dataclasses import dataclass

from aiogram.utils.formatting import Bold, as_key_value, as_list

from scenegram import Button, FormField, FormScene, Navigate, inline_menu


@dataclass(slots=True)
class SignupResult:
    age: int
    email: str


class SignupScene(FormScene, state="common.signup"):
    __abstract__ = False
    result_model = SignupResult
    use_confirm_step = True
    fields = (
        FormField(name="age", prompt="Сколько вам лет?", parser="parse_age", validator="validate_age"),
        FormField(name="email", prompt="Какой e-mail использовать?", validator="validate_email"),
    )

    async def parse_age(self, raw_value: str) -> int:
        return int(raw_value)

    async def validate_age(self, value: int) -> str | None:
        if value < 18:
            return "Возраст должен быть не меньше 18."
        return None

    async def validate_email(self, value: str) -> str | None:
        if "@" not in value:
            return "Некорректный e-mail."
        return None

    async def on_form_submit(self, event, result: SignupResult) -> None:
        await self.show(
            event,
            as_list(
                Bold("Готово"),
                as_key_value("Age", result.age),
                as_key_value("Email", result.email),
                sep="\n\n",
            ),
            reply_markup=inline_menu(
                [[Button(text="🏠 В меню", callback_data=Navigate.home("common.start"))]]
            ),
        )
```

## Работа с scene data

Вместо постоянного:

```python
data = await self.wizard.get_data()
name = data.get("name")
```

используйте:

```python
name = await self.data.get("name")
name, email = await self.data.pick("name", "email")
await self.data.update(name="Alice", step="confirm")
await self.data.set(name="Alice", age=30)
await self.data.discard("obsolete_key")
draft = await self.data.model(MyDataclassOrPydanticModel)
```

Методы `SceneDataProxy`:

- `all()`
- `get()`
- `pick()`
- `require()`
- `require_many()`
- `update()`
- `set()`
- `clear()`
- `pop()`
- `discard()`
- `model()`

## Навигация

### Через готовые callback data

```python
Button(text="Открыть каталог", callback_data=Navigate.open("common.catalog"))
Button(text="Домой", callback_data=Navigate.home("common.start"))
```

### Изнутри сцены

```python
await self.nav.to("common.catalog")
await self.nav.back()
await self.nav.home()
await self.nav.role_home(SceneRole.ADMIN)
await self.nav.retake(step="confirm")
await self.nav.exit()
```

## Role-aware routing

У сцены можно ограничить роли:

```python
class AdminScene(MenuScene, state="admin.dashboard"):
    __abstract__ = False
    roles = frozenset({SceneRole.ADMIN.value})
    home_for_roles = frozenset({SceneRole.ADMIN.value})
```

Если вы передали `role_resolver`, то `scenegram`:

- сгруппирует scene routers по ролям;
- добавит фильтр доступа;
- зарегистрирует role home в runtime.

## Discovery и bootstrap

`create_scenes_router()` умеет принимать один пакет или несколько:

```python
create_scenes_router(package_name="scenes")
create_scenes_router(package_name=("scenes.common", "scenes.admin"))
```

Также доступны служебные функции:

- `discover_scene_descriptors()`
- `discover_scene_classes()`

Они полезны для тестов, introspection, healthchecks и tooling.

## Примеры

Смотрите каталог [examples](examples/README.md):

- `examples/showcase_bot/` — reference project с настоящим пакетом `scenes/`;
- в нём показаны `MenuScene`, `PaginatedScene`, `ConfirmScene`, `FormScene`, `StepScene`, `role_resolver` и нативный `aiogram.utils.formatting`.

## Тестирование

```bash
uv run pytest
uv run ruff check
```

Тесты покрывают:

- formatting layer;
- scene discovery и bootstrap;
- state proxy;
- keyboard/pagination helpers;
- base scene rendering;
- built-in scene patterns.

## Ограничения текущей версии

Пакет уже пригоден как foundation для production bot development, но в roadmap ещё входят:

- built-in CRUD/list/detail scene packs;
- breadcrumbs/history helpers;
- более богатые typed contracts для scene modules;
- adapters для DI/service containers.

## Статус

`scenegram` уже оформлен как библиотека, которую можно встраивать в ботов через собственную папку `scenes/`.

Ключевой принцип проекта:

> framework поставляет абстракции и готовые patterns, а пользовательский бот хранит свои доменные сцены у себя и просто импортирует нужные базовые классы из `scenegram`.
