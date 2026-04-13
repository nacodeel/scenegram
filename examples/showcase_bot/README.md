# Showcase Bot

`examples/showcase_bot/` — reference bot, который показывает `scenegram` не в изоляции, а в нормальной bot-level интеграции.

## Структура

```text
showcase_bot/
├── main.py
├── services.py
└── scenes/
    ├── admin.py
    ├── admin_broadcast.py
    ├── catalog_pack.py
    └── common/
        ├── start.py
        ├── catalog.py
        ├── delete.py
        └── onboarding.py
```

## Что здесь реализовано

### `main.py`

- создаёт `Dispatcher`;
- включает `SimpleEventIsolation`;
- подключает `create_scenes_router(...)`;
- пробрасывает глобальный `service_container`;
- задаёт глобальную cleanup policy.

### `services.py`

- `build_service_container()` — глобальные сервисы бота;
- `ProductCrudAdapter` — adapter для portable CRUD pack;
- `AudienceBroadcastAdapter` — adapter для portable background broadcast.

### `scenes/common/start.py`

- обычное главное меню на `MenuScene`;
- manual actions плюс auto-added вкладки от portable modules;
- нативное formatting через `aiogram.utils.formatting`.

### `scenes/common/catalog.py`

- базовый `PaginatedScene`;
- пример локального pager-flow без module manifest.

### `scenes/common/onboarding.py`

- `FormScene` с typed result model;
- auto reply-кнопка `Отмена` на input-шагах;
- включённый step-carousel для возврата к предыдущим вопросам без засорения scene stack;
- cleanup policy `delete_user_messages=True`;
- вызов глобального сервиса через `self.services.call(...)`.

### `scenes/catalog_pack.py`

- reusable CRUD module;
- `SCENEGRAM_MODULE = crud_module(...)`;
- module-local adapter живёт рядом со сценами;
- пункт меню добавляется в `common.start` автоматически.

### `scenes/admin_broadcast.py`

- reusable background broadcast module;
- `SCENEGRAM_MODULE = broadcast_module(...)`;
- admin-only scene;
- background task + completion callback + cleanup/chat action policy.

### `scenes/admin.py`

- role-scoped admin dashboard;
- кнопка рассылки приходит автоматически через module contribution.

## Какие паттерны стоит копировать в свой бот

- держать adapters рядом с reusable scene modules;
- пробрасывать bot-wide сервисы через `service_container`;
- использовать `SCENEGRAM_MODULE` для самоописания модулей;
- полагаться на `aiogram.utils.formatting`, а не на HTML-строки;
- использовать auto reply-keyboards на `StepScene` / `FormScene` и удалять их через built-in cancel flow;
- включать `step_pagination = True` только там, где форма должна разрешать question-level navigation;
- задавать cleanup/chat action policies декларативно на уровне сцены.

## Запуск

```bash
cd /Users/nikita/Projects/aioscene/scenegram
BOT_TOKEN=... python -m examples.showcase_bot.main
```

## Ограничения примера

- adapters in-memory, без БД и брокера;
- background jobs живут в процессе бота;
- логирование сведено к простому `print`, чтобы не тащить лишнюю инфраструктуру в example.

Для production это означает: сами adapters можно заменить на PostgreSQL/Redis/Celery/S3 и оставить scene-layer без переписывания.
