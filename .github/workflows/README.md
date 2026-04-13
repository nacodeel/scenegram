# Workflows

Папка `.github/workflows/` хранит CI workflows для `scenegram`.

## Что реализовано

- `ci.yml` — синхронизирует dev-окружение через `uv`, запускает `ruff` и `pytest`.

## Ограничения

- workflow пока не публикует wheel/sdist;
- typecheck и release tagging пока не автоматизированы отдельными jobs.

## Ближайшие планы

- добавить build/publish smoke;
- при необходимости вынести release workflow отдельно от CI.
