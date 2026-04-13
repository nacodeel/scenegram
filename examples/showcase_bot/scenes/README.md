# Scenes Package

Пакет `examples.showcase_bot.scenes` демонстрирует, как должен выглядеть scene-layer прикладного бота поверх `scenegram`.

## Что здесь находится

- обычные сцены в `common/`;
- role-scoped admin сцены;
- portable modules с `SCENEGRAM_MODULE`;
- mix ручных и reusable scene packs в одном пакете discovery.

## Архитектурная роль

Этот пакет принадлежит приложению, а не библиотеке. Здесь допустимы:

- доменные adapters конкретного бота;
- layout меню и пользовательские тексты;
- привязка reusable framework-паков к вашему домену.

## Что уже реализовано

- главное меню и onboarding flow;
- deep-link start scene и scene-attached route на catalog detail;
- простая пагинация;
- portable CRUD module;
- portable background broadcast module;
- admin dashboard с role gating.

## Как расширять

- новый reusable pack оформлять отдельным модулем с `SCENEGRAM_MODULE`;
- scene-local логику держать рядом со сценой;
- внешние сервисы пробрасывать через `service_container` или module services;
- для новых подкаталогов добавлять свой README.
