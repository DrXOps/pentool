# Шаблон промпта: Новый модуль

Копируй этот шаблон при создании нового модуля. Заполни все [ПОЛЯ].

---

```
Проект: PenTool (консольный аналог Burp Suite, Python 3.12, Textual TUI)
Архитектура: docs/architecture.md
Стайлгайд: docs/styleguide.md
Роль: Разработчик модуля [ИМЯ_МОДУЛЯ]

## Задача

Реализовать модуль [ИМЯ_МОДУЛЯ] согласно спецификации specs/[имя].md.

## Что нужно создать

1. `pentool/modules/[имя].py` — бизнес-логика (без TUI, без api/)
2. `pentool/api/[имя]_api.py` — тонкий фасад-обёртка
3. `pentool/tui/screens/[имя]/screen.py` — TUI-экран (Widget, не Screen)
4. `tests/unit/modules/test_[имя].py` — unit-тесты модуля
5. `tests/unit/api/test_[имя]_api.py` — unit-тесты API-обёртки

## Ограничения

- Изменять ТОЛЬКО файлы, перечисленные выше.
- НЕ трогать: proxy.py, repeater.py, intruder.py, app.py, другие экраны.
- TUI-экран импортирует только из `pentool.api.[имя]_api`, не из `pentool.modules`.
- Следовать стайлгайду: type hints, docstrings, get_logger(__name__), async/await для IO.
- Новые зависимости НЕ добавлять без явного разрешения.

## Спецификация

[Вставить содержимое или ссылку на specs/[имя].md]

## После выполнения

1. Запустить: `pytest tests/unit/modules/test_[имя].py tests/unit/api/test_[имя]_api.py -v`
2. Убедиться, что все тесты зелёные.
3. Резюмировать: какие файлы созданы, какие классы/методы добавлены, сколько тестов.
```
