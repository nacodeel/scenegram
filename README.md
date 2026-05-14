# Scenegram

`scenegram` — production-oriented framework layer над `aiogram` scenes для Telegram-ботов. Он не заменяет `aiogram`, а собирает поверх него устойчивый scene runtime с навигацией, модульностью, deep links, reusable scene patterns и нормальным developer workflow.

## Для чего нужен framework

`scenegram` закрывает типичные проблемы больших Telegram-ботов:

- ручной реестр сцен и хрупкий bootstrap;
- размазанная навигация между экранами;
- отсутствие переносимых модулей сцен;
- смешение transport-слоя, DI и бизнес-логики;
- ad-hoc формы, пагинация и CRUD-flow без общего контракта;
- слабая обратная навигация и отсутствие screen stack;
- разрозненные deep links и отсутствие typed runtime hooks.

## Ключевые возможности

- auto-discovery и auto-registration сцен;
- `AppScene` с `data`, `services`, `context`, `nav`, `history`, `deep_links`;
- role-aware navigation и role-specific home scenes;
- portable `SceneModule` с menu contributions и локальными сервисами;
- built-in patterns: `MenuScene`, `ConfirmScene`, `StepScene`, `FormScene`, `PaginatedScene`;
- higher-level packs: CRUD и broadcast flows;
- deep links как часть scene runtime, а не отдельный ad-hoc `/start` handler;
- typed state model descriptors;
- cleanup policies, runtime observers и in-process task runner.

## Установка

### Runtime

```bash
uv add scenegram aiogram
```

### Development

```bash
uv sync --group dev
```

## Минимальный запуск

```python
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from scenegram import create_scenes_router


bot = Bot(
    token="TOKEN",
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

dp.include_router(
    create_scenes_router(
        package_name="bot.scenes",
        default_home="common.start",
    )
)
```

Требования к пакету сцен:

- сцены должны наследоваться от `AppScene` или framework patterns;
- каждая concrete scene должна иметь `state="module.scene"` и `__abstract__ = False`;
- пакет должен быть импортируемым Python package.

## Базовая сцена

```python
from aiogram.fsm.scene import on
from aiogram.types import Message

from scenegram import AppScene


class StartScene(AppScene, state="common.start"):
    __abstract__ = False

    @on.message.enter()
    async def _on_message_enter(self, message: Message) -> None:
        await self.show(message, "Главное меню")
```

`AppScene` даёт:

- `self.show(...)` — единый render pipeline для message/callback events;
- `self.data` — typed proxy для scene data;
- `self.services` — DI access к модульным и глобальным сервисам;
- `self.nav` — transitions `to/back/replace/home/cancel/start`;
- `self.history` — breadcrumbs/history helpers;
- `self.context` — runtime context, собранный во время update processing;
- `self.deep_links` — генерация и открытие deep links.

## Навигация

### Простая навигация

```python
from scenegram import Button, Navigate, inline_menu


rows = [
    [Button(text="Каталог", callback_data=Navigate.open("common.catalog"))],
    [Button(text="Домой", callback_data=Navigate.home("common.start"))],
]

markup = inline_menu(rows)
```

### Параметризованная навигация

Теперь `Navigate` принимает `**params`:

```python
Navigate.open("contact.notes", contact_id=123)
Navigate.open("crm.deals", contact_id=123, page=2)
Navigate.replace("report.view", year=2026, month=5)
Navigate.home("common.start", tab="stats")
```

Сцена получает параметры автоматически:

```python
from scenegram import PaginatedScene


class ContactNotesScene(PaginatedScene, state="contact.notes"):
    __abstract__ = False

    async def render_page(
        self,
        event,
        *,
        page: int = 1,
        contact_id: int | None = None,
    ):
        ...
```

Поддерживаемые типы:

- `str`
- `int`
- `float`
- `bool`
- `None`
- JSON-compatible `list` и `dict`

### Как это устроено

- старые callback payloads вида `nav:open:common.catalog` продолжают работать;
- если params отсутствуют, framework пакует старый формат без изменений;
- если params есть, они кодируются в компактный typed payload;
- `AppScene` автоматически раскладывает params в `self.nav.*(...)`;
- `PaginatedScene` сохраняет params в scene data и повторно использует их на page switch callbacks.

### Почему params не хранятся только в `wizard.state`

Потому что `Navigate.open(...)` — статический builder без доступа к текущему экземпляру сцены. Чтобы полностью прятать payload в state/store, нужен отдельный scene-aware packing layer, который при рендере клавиатуры создаёт opaque token и кладёт данные в storage. Это возможно как следующая эволюция, но для текущего API компактный transport даёт нужную high-level abstraction без слома public API.

## MenuScene

```python
from scenegram import Button, MenuScene, Navigate


class MainMenuScene(MenuScene, state="common.start"):
    __abstract__ = False
    menu_text = "Выберите раздел"
    static_rows = (
        (Button(text="Профиль", callback_data=Navigate.open("profile.view")),),
        (Button(text="Каталог", callback_data=Navigate.open("catalog.list")),),
    )
    navigation_home = False
```

`MenuScene` умеет:

- собирать `static_rows`;
- автоматически добавлять module menu contributions;
- добавлять стандартный navigation row;
- рендерить меню одинаково для message и callback entry.

## PaginatedScene

```python
from scenegram import Button, PaginatedScene, inline_menu, paginate, pager_rows


class CatalogScene(PaginatedScene, state="catalog.list"):
    __abstract__ = False

    async def render_page(self, event, *, page: int = 1, category: str | None = None):
        items = await self.services.call("catalog_items", category)
        window = paginate(items, page, per_page=self.page_size)
        rows = [[Button(text=item.title)] for item in window.items]
        rows.extend(pager_rows(window, back=True, home=True, home_target="common.start"))
        await self.show(event, f"Страница {window.page}", reply_markup=inline_menu(rows))
```

`PaginatedScene` из коробки:

- хранит номер текущей страницы в scene data;
- умеет `current_page()` и `remember_page(...)`;
- обрабатывает `PageNav`;
- сохраняет navigation params между входом в сцену и page switching.

## Формы и шаговые сценарии

Framework включает:

- `ConfirmScene` — подтверждение действия;
- `StepScene` — линейный или carousel-like пошаговый flow;
- `FormScene` — typed multi-step data collection поверх declarative `FormField`.

Подробности и ограничения этих слоёв зафиксированы в [scenegram/README.md](/Users/nikita/Projects/aioscene/scenegram/scenegram/README.md).

## CRUD и broadcast packs

Для типовых production-сценариев доступны готовые reusable packs:

- `CrudListScene`
- `CrudDetailScene`
- `CrudDeleteScene`
- `crud_module(...)`
- `BroadcastScene`
- `broadcast_module(...)`

Эти пакеты не завязаны на конкретную ORM или storage. Вы даёте адаптеры, framework строит transport flow, pagination, подтверждения и навигацию.

## Deep links

`scenegram` рассматривает deep links как часть scene runtime.

Поддерживаются:

- start scene с `DeepLinkScene` или `DeepLinkMenuScene`;
- route helpers `deep_link_handler(...)` и `deep_link_scene(...)`;
- signed payloads;
- temporary и one-time links;
- `back_target` для корректной обратной навигации после deep-link entry.

Пример:

```python
from scenegram import DeepLinkMenuScene, deep_link_handler


class StartScene(DeepLinkMenuScene, state="common.start"):
    __abstract__ = False
    deep_links = (
        deep_link_handler("app.referral", "handle_referral"),
    )

    async def handle_referral(self, event, context):
        await self.data.update(referrer_id=context.payload.get("referrer_id"))
        return await self.render_menu(event)
```

## Scene modules

`SceneModule` нужен, когда вы хотите переносить не одиночную сцену, а целый feature slice:

- набор сцен;
- menu contributions;
- локальные сервисы;
- module metadata;
- module-level middlewares.

Примерная схема:

```python
from scenegram import MenuContribution, SceneModule


SCENEGRAM_MODULE = SceneModule(
    name="catalog",
    package_name="bot.scenes.catalog",
    title="Catalog",
    services={"catalog_service": build_catalog_service},
    menu_entries=(
        MenuContribution(
            target_state="common.start",
            text="Каталог",
            target_scene="catalog.list",
            row=0,
            order=10,
        ),
    ),
)
```

## Typed state

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
```

Это помогает не работать руками с сырой `dict`, а держать state contract явно.

## Архитектура проекта

```text
scenegram/
  base.py
  bootstrap.py
  contracts.py
  deep_links.py
  patterns.py
  packs.py
  runtime.py
  state.py
  tasks.py
  ui/
tests/
examples/
```

- `scenegram/` — reusable framework code;
- `tests/` — unit/integration-style coverage public contracts;
- `examples/` — showcase bot и reference usage.

## Локальная разработка

### Установка зависимостей

```bash
uv sync --group dev
```

### Тесты

```bash
uv run pytest
```

### Линтинг

```bash
uv run ruff check .
```

### Type checking

```bash
uv run pyright
```

## Качество и совместимость

- Python `>=3.12`
- `aiogram >=3.24,<4.0`
- backward compatibility для legacy `Navigate` callbacks без params
- тестами покрыты navigation, deep links, forms, pagination, bootstrap и runtime modules

## Ограничения и практические рекомендации

- Telegram callback data ограничен 64 байтами; не пытайтесь передавать большие структуры через `Navigate`.
- Для тяжёлых payload используйте scene data, service-backed lookup, deep links или отдельный callback handler.
- Runtime task runner и deep-link store по умолчанию process-local; для production persistence подключайте свои adapters.

## Roadmap

- opaque token mode для параметризованной navigation при scene-aware keyboard packing;
- новые reusable packs для selection/filter/detail workflows;
- richer observability hooks;
- больше reference examples и расширенная docs-site структура, если проект продолжит расти.

## Документация по пакетам

- [scenegram/README.md](/Users/nikita/Projects/aioscene/scenegram/scenegram/README.md) — внутренняя карта framework package, contracts и правила расширения.
- [examples/README.md](/Users/nikita/Projects/aioscene/scenegram/examples/README.md) — примеры и showcase bot.
