# Переименование таблиц Ticket Validator - Сводка миграции

## Обзор
Все таблицы базы данных в модуле `ticket_validator` были переименованы с добавлением префикса `ticket_validator_` для избежания конфликтов имен с другими модулями и улучшения организации кода.

## Внесенные изменения

### 1. Схема базы данных (schema.sql)
Переименованы все 7 таблиц:
- `validation_rules` → `ticket_validator_validation_rules`
- `validation_history` → `ticket_validator_validation_history`
- `ticket_types` → `ticket_validator_ticket_types`
- `ticket_type_rules` → `ticket_validator_ticket_type_rules`
- `ticket_templates` → `ticket_validator_ticket_templates`
- `template_rule_tests` → `ticket_validator_template_rule_tests`
- `template_test_results` → `ticket_validator_template_test_results`

Обновлены все ограничения внешних ключей для ссылки на новые имена таблиц.

### 2. SQL скрипты настройки (scripts/)
Обновлены ссылки на таблицы в:
- `initial_validation_rules.sql` - Все операторы INSERT
- `initial_ticket_types.sql` - Все операторы INSERT
- `map_rules_to_ticket_types.sql` - Все операторы INSERT
- `sample_templates.sql` - Все операторы INSERT
- `sample_test_templates.sql` - Все операторы INSERT и DELETE
- `example_negative_keywords.sql` - Все операторы UPDATE и INSERT

### 3. Python код (src/sbs_helper_telegram_bot/ticket_validator/)
Обновлены все SQL запросы в:
- `validation_rules.py` - Все операторы SELECT, INSERT, UPDATE, DELETE и JOIN
- `messages.py` - Все операторы SELECT
- `admin_panel_bot_part.py` - Без прямого SQL (использует функции из validation_rules.py)
- `ticket_validator_bot_part.py` - Без прямого SQL (использует функции из validation_rules.py)
- `validators.py` - Без прямого SQL (использует классы данных)

### 4. Документация
Обновлены ссылки на таблицы в:
- `TEST_TEMPLATES.md` - Все ссылки на имена таблиц
- `TICKET_TYPES.md` - Все ссылки на имена таблиц
- `NEGATIVE_KEYWORDS.md` - Все примеры операторов UPDATE

### 5. Скрипты миграции
Созданы новые скрипты:
- `scripts/migrate_ticket_validator_tables.sql` - Переименовывает существующие таблицы в продакшене
- `scripts/rollback_ticket_validator_tables.sql` - Откатывает изменения при необходимости

## Инструкции по миграции

### Для новых установок
1. Используйте обновленный `schema.sql` для создания таблиц с новыми именами
2. Запустите скрипты настройки в порядке:
   - `initial_validation_rules.sql`
   - `initial_ticket_types.sql`
   - `map_rules_to_ticket_types.sql`
   - `sample_templates.sql` (опционально)
   - `sample_test_templates.sql` (опционально)

### Для существующих баз данных
1. **ВАЖНО**: Сделайте резервную копию базы данных перед продолжением
2. Разверните обновленный код на сервере (НЕ перезапускайте бота пока)
3. Остановите Telegram бота
4. Выполните `scripts/migrate_ticket_validator_tables.sql` для переименования таблиц
5. Проверьте, что миграция завершилась успешно (скрипт включает запросы проверки)
6. Запустите бота с новым кодом

### Процедура отката (при необходимости)
1. Остановите бота
2. Выполните `scripts/rollback_ticket_validator_tables.sql`
3. Разверните старую версию кода
4. Запустите бота

## Рекомендации по тестированию
1. После миграции протестируйте следующее:
   - Валидация заявки (пользовательский процесс)
   - Просмотр правил валидации в админ-панели
   - Создание/редактирование правила валидации
   - Создание/редактирование типа заявки
   - Запуск тестов шаблонов
   - Назначение правил типам заявок

2. Проверка целостности данных:
   - Проверьте, что все правила валидации присутствуют
   - Проверьте, что все типы заявок присутствуют
   - Проверьте, что сопоставления правил с типами не повреждены
   - Проверьте, что шаблоны и результаты тестов доступны

## Измененные файлы

### Схема и скрипты
- schema.sql
- scripts/initial_validation_rules.sql
- scripts/initial_ticket_types.sql
- scripts/map_rules_to_ticket_types.sql
- scripts/sample_templates.sql
- scripts/sample_test_templates.sql
- scripts/example_negative_keywords.sql

### Python код
- src/sbs_helper_telegram_bot/ticket_validator/validation_rules.py
- src/sbs_helper_telegram_bot/ticket_validator/messages.py

### Документация
- src/sbs_helper_telegram_bot/ticket_validator/TEST_TEMPLATES.md
- src/sbs_helper_telegram_bot/ticket_validator/TICKET_TYPES.md
- src/sbs_helper_telegram_bot/ticket_validator/NEGATIVE_KEYWORDS.md

### Новые файлы
- scripts/migrate_ticket_validator_tables.sql
- scripts/rollback_ticket_validator_tables.sql
- MIGRATION_SUMMARY.md (этот файл)

## Примечания
- Все ограничения внешних ключей остаются неизменными и ссылаются на новые имена таблиц
- Данные не теряются во время миграции - ALTER TABLE RENAME сохраняет все данные
- Скрипт отката предоставляется только для экстренного использования
- Все индексы и ограничения автоматически переименовываются MySQL во время переименования таблицы

## Запросы проверки

После миграции вы можете проверить изменения с помощью:

```sql
-- Показать все таблицы ticket_validator
SHOW TABLES LIKE 'ticket_validator_%';

-- Подсчитать записи в каждой таблице
SELECT 'ticket_validator_validation_rules' AS table_name, COUNT(*) AS records FROM ticket_validator_validation_rules
UNION ALL
SELECT 'ticket_validator_ticket_types', COUNT(*) FROM ticket_validator_ticket_types
UNION ALL
SELECT 'ticket_validator_ticket_type_rules', COUNT(*) FROM ticket_validator_ticket_type_rules
UNION ALL
SELECT 'ticket_validator_ticket_templates', COUNT(*) FROM ticket_validator_ticket_templates
UNION ALL
SELECT 'ticket_validator_template_rule_tests', COUNT(*) FROM ticket_validator_template_rule_tests
UNION ALL
SELECT 'ticket_validator_template_test_results', COUNT(*) FROM ticket_validator_template_test_results
UNION ALL
SELECT 'ticket_validator_validation_history', COUNT(*) FROM ticket_validator_validation_history;
```

## Контакты
По вопросам или проблемам обращайтесь к документации проекта или свяжитесь с командой разработки.

---
**Дата миграции**: 29 января 2026 г.
**Ветка**: certification_module
