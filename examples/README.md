# Examples

Каталог `examples/` содержит reference implementations того, как `scenegram` должен использоваться внутри реального бота.

## Что находится в примерах

- `showcase_bot/` — основной reference bot.

## Что показывает showcase bot

- bootstrap `Dispatcher` с `create_scenes_router(...)`;
- глобальный `service_container`;
- auto-discovery сцен по пакету `examples.showcase_bot.scenes`;
- mix ручных сцен и portable scene modules;
- cleanup policies и history-ready rendering;
- secure scene transitions with role guards;
- формы, question-level step carousel, пагинацию, CRUD pack и background broadcast.

## Быстрый запуск

```bash
cd /Users/nikita/Projects/aioscene/scenegram
BOT_TOKEN=... python -m examples.showcase_bot.main
```

## Для чего читать этот каталог

Это не toy demo. Пример собран так, чтобы разработчик мог:

- взять структуру папок как основу своего бота;
- скопировать portable module целиком;
- посмотреть, как пробрасывать adapters и глобальные сервисы;
- увидеть, как использовать `aiogram.utils.formatting` напрямую в сценах.
