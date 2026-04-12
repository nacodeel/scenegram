# Examples

`scenegram` предполагает, что в вашем боте есть собственный пакет `scenes/`, а сама библиотека только поставляет базовые классы, helpers и bootstrap.

В этом каталоге лежит один полноформатный пример:

- `showcase_bot/` — реальная структура бота с `main.py`, пакетом `scenes/`, автоматическим discovery, ролями, `MenuScene`, `PaginatedScene`, `ConfirmScene`, `FormScene`, `StepScene` и нативным форматированием через `aiogram.utils.formatting`.

Запускать пример удобнее так:

```bash
cd scenegram
BOT_TOKEN=... python -m examples.showcase_bot.main
```

Он предназначен не как demo-игрушка, а как reference implementation того, как должен выглядеть проект, где пользователь просто добавляет свою папку `scenes/` и наполняет ее модулями.
