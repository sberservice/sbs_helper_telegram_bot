# Установка и настройка SBS Archie

## Требования

- Python 3.10+
- MySQL 8.0+
- [Telegram Bot Token](https://t.me/botfather)

## Установка

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Заполнить TELEGRAM_TOKEN, MYSQL_*, DEEPSEEK_API_KEY
```

## База данных

```bash
mysql -u root -p < schema.sql
# Модули (все скрипты в sql/*_setup.sql):
for f in bot_settings_setup initial_ticket_types initial_validation_rules \
         map_rules_to_ticket_types certification_setup ktr_setup upos_error_setup \
         soos_image_queue_setup \
         gamification_setup feedback_setup news_setup ai_router_setup ai_rag_setup \
         ai_rag_document_summaries_setup ai_rag_vector_setup ai_rag_certification_signals_setup chat_members_setup health_check_setup \
         health_outage_calendar_setup prompt_tester_setup; do
  mysql -u root -p sprint_db < "sql/${f}.sql"
done
# Для существующих БД без FULLTEXT-индекса summary_text:
mysql -u root -p sprint_db < sql/rag_document_summaries_fulltext_index.sql
```

## Запуск

```bash
python run_bot.py
```

Стартуют процессы: **Telegram Bot**, **Image Queue Processor**, **SOOS Queue Processor**, **Health Check**. Автоперезапуск при сбоях (до 3 раз). `Ctrl+C` для остановки.

## Конфигурация

Все настройки — через `.env` (см. `.env.example`). Ключевые группы:

| Группа | Переменные | Описание |
|--------|-----------|----------|
| **Telegram** | `TELEGRAM_TOKEN` | Токен бота |
| **MySQL** | `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` | Подключение к БД |
| **AI** | `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `AI_CONFIDENCE_THRESHOLD`, `AI_LOG_MODEL_IO`, `AI_MODEL_IO_DB_LOG_ENABLED` | LLM-провайдер, пороги и логирование prompt/response |
| **RAG** | `AI_RAG_ENABLED`, `AI_RAG_CHUNK_SIZE`, `AI_RAG_TOP_K`, `AI_RAG_PREFILTER_TOP_DOCS`, `AI_RAG_VECTOR_ENABLED`, ... | База знаний документов |
| **Сеть** | `TELEGRAM_HTTP_MAX_RETRIES`, `TELEGRAM_SEND_MSG_READ_TIMEOUT_SECONDS` | Сетевые профили |

Для Admin Web дополнительно доступны переменные password-аутентификации:
`ADMIN_WEB_TELEGRAM_BOT_USERNAME`, `ADMIN_WEB_PASSWORD_AUTH_ENABLED`,
`ADMIN_WEB_PASSWORD_MIN_LENGTH`, `ADMIN_WEB_PASSWORD_RATE_LIMIT_WINDOW_SECONDS`,
`ADMIN_WEB_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS`, `ADMIN_WEB_PASSWORD_LOCKOUT_THRESHOLD`,
`ADMIN_WEB_PASSWORD_LOCKOUT_MINUTES`.

Полный список переменных — в `.env.example`. AI-модели переключаются в runtime через админ-панель (`🧠 AI модель`).

### Логирование AI

Для хранения полных AI/RAG логов (`prompt/response`) используется таблица `ai_model_io_log` (создаётся в `sql/ai_router_setup.sql`).
Записи маскируют чувствительные данные (email/телефон/ИНН/СНИЛС) перед сохранением.
Очистка старых записей выполняется через `sql/ai_model_io_log_retention.sql` (по умолчанию старше 30 дней).

## Тестирование

```bash
pytest
```

Конфигурация: `pytest.ini`, таймаут 30 сек/тест.
