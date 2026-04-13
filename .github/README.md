# GitHub Automation

Папка `.github/` содержит automation- и quality-артефакты репозитория.

## Что здесь находится

- `workflows/` — CI workflow для проверки quality gates на push/pull request.

## Архитектурная роль

Этот слой фиксирует минимальный CI-контур библиотеки:

- проверка `ruff`;
- прогон `pytest`;
- smoke-проверка того, что проект синхронизируется через `uv`.

## Статус

- базовый CI workflow реализован;
- release automation и publish pipeline ещё не добавлены.

## Правила расширения

- новые workflow не должны дублировать уже существующие quality checks;
- любые изменения в CI должны отражать реальные локальные команды из README;
- если добавляется publish/release pipeline, нужно обновить этот README и корневой README.
