# SBS Helper AI Telegram Bot 🤖

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/) [![Лицензия](https://img.shields.io/badge/license-CC--BY--NC--SA--4.0-red.svg)](LICENSE)

> *Ваш AI-напарник в полях — потому что даже герои заслуживают умного помощника.*

## О проекте

**SBS Helper AI Telegram Bot** — модульный AI-powered Telegram-бот для инженеров **СберСервис**. Просто напишите боту что угодно — AI поймёт, о чём вы, и направит в нужный модуль. Никаких лишних кнопок, никаких инструкций на 20 страниц. Пишите как человеку — бот разберётся. Ну, почти всегда. 😉

Построен на архитектуре плагинов с AI-маршрутизатором в центре. Каждый модуль независим, включается/отключается через админку, а AI-роутер связывает их в единое целое — как мозг.

Демо: [@vyezdbyl_bot](https://t.me/vyezdbyl_bot) *(может не отражать текущую стадию разработки)*

## Что умеет

| | Модуль | Суть | Подробнее |
|---|--------|------|-----------|
| 🤖 | **AI-маршрутизатор** | Классификация текста через LLM, intent routing, RAG-база знаний, свободный чат | [README](src/sbs_helper_telegram_bot/ai_router/README.md) |
| 📝 | **Аттестация** | Тестирование, рейтинги, категории, режим обучения, динамические ранги | [README](src/sbs_helper_telegram_bot/certification/README.md) |
| 📸 | **Скриншоты** | Наложение маркеров локации на скриншоты Спринта (фоновая очередь) | [README](src/sbs_helper_telegram_bot/vyezd_byl/README.md) |
| 🔢 | **UPOS Ошибки** | Поиск кодов ошибок UPOS с рекомендациями по устранению | [README](src/sbs_helper_telegram_bot/upos_error/README.md) |
| ✅ | **Валидация заявок** | Автоопределение типа + проверка по правилам + пакетная Excel-валидация | [README](src/sbs_helper_telegram_bot/ticket_validator/README.md) |
| ⏱️ | **КТР** | Коды трудозатрат с нормативным временем выполнения | [README](src/sbs_helper_telegram_bot/ktr/README.md) |
| 📬 | **Обратная связь** | Категоризированные обращения с анонимными ответами от поддержки | [README](src/sbs_helper_telegram_bot/feedback/README.md) |
| 📰 | **Новости** | Публикации, рассылки, обязательные объявления, реакции | [README](src/sbs_helper_telegram_bot/news/README.md) |
| 🏆 | **Геймификация** | Очки, достижения (🥉🥈🥇), ранги, лидерборды | [README](src/sbs_helper_telegram_bot/gamification/README.md) |
| 🛠️ | **Админ бота** | Пользователи, инвайты, модули, настройки, плановые работы | [README](src/sbs_helper_telegram_bot/bot_admin/README.md) |

**AI-маршрутизатор** работает в фоне — просто пишите боту текст, и он сам разберётся куда его направить. Circuit breaker, rate limiter и RAG-база знаний документов — всё включено.

## Быстрый старт

### Требования

- Python 3.10+ · MySQL 8.0+ · [Telegram Bot Token](https://t.me/botfather)

### Установка

```bash
git clone https://github.com/sberservice/sbs_helper_telegram_bot.git
cd sbs_helper_telegram_bot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Заполнить TELEGRAM_TOKEN, MYSQL_*, DEEPSEEK_API_KEY
```

### База данных

```bash
mysql -u root -p < schema.sql
# Модули (все скрипты в sql/*_setup.sql):
for f in bot_settings_setup initial_ticket_types initial_validation_rules \
         map_rules_to_ticket_types certification_setup ktr_setup upos_error_setup \
         gamification_setup feedback_setup news_setup ai_router_setup ai_rag_setup \
         ai_rag_document_summaries_setup ai_rag_vector_setup chat_members_setup health_check_setup \
         health_outage_calendar_setup; do
  mysql -u root -p sprint_db < "sql/${f}.sql"
done
# Для существующих БД без FULLTEXT-индекса summary_text:
mysql -u root -p sprint_db < sql/rag_document_summaries_fulltext_index.sql
```

### Запуск

```bash
python run_bot.py
```

Стартуют два процесса: **Telegram Bot** + **Image Queue Processor**. Автоперезапуск при сбоях (до 3 раз). `Ctrl+C` для остановки.

## Конфигурация

Все настройки — через `.env` (см. `.env.example`). Ключевые группы:

| Группа | Переменные | Описание |
|--------|-----------|----------|
| **Telegram** | `TELEGRAM_TOKEN` | Токен бота |
| **MySQL** | `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` | Подключение к БД |
| **AI** | `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `AI_CONFIDENCE_THRESHOLD`, `AI_LOG_MODEL_IO`, `AI_MODEL_IO_DB_LOG_ENABLED` | LLM-провайдер, пороги и логирование prompt/response |
| **RAG** | `AI_RAG_ENABLED`, `AI_RAG_CHUNK_SIZE`, `AI_RAG_TOP_K`, `AI_RAG_PREFILTER_TOP_DOCS`, `AI_RAG_SUMMARY_MATCH_PHRASE_WEIGHT`, `AI_RAG_SUMMARY_VECTOR_WEIGHT`, `AI_RAG_VECTOR_ENABLED` | База знаний документов |
| **Сеть** | `TELEGRAM_HTTP_MAX_RETRIES`, `TELEGRAM_SEND_MSG_READ_TIMEOUT_SECONDS` | Сетевые профили |

Для хранения полных AI/RAG логов (`prompt/response`) используется таблица `ai_model_io_log` (создаётся в `sql/ai_router_setup.sql`).
Записи маскируют чувствительные данные (email/телефон/ИНН/СНИЛС) перед сохранением.
Очистка старых записей выполняется через `sql/ai_model_io_log_retention.sql` (по умолчанию старше 30 дней).

Полный список переменных — в `.env.example`. AI-модели переключаются в runtime через админ-панель (`🧠 AI модель`).

## Навигация

```
🏠 Главное меню
├── ⚡ Начать работу → [список модулей]
├── 🏆 Достижения
├── 📰 Новости
├── ⚙️ Настройки (инвайты, помощь)
└── 🛠️ Админ бота (только для админов)
```

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и регистрация |
| `/menu` | Главное меню |
| `/reset` | Сброс состояния |
| `/help` | Справка |
| `/cancel` | Отмена операции |
| `/invite` | Коды приглашений |

## Тестирование

```bash
pytest
```

Конфигурация: `pytest.ini`, таймаут 30 сек/тест.

## Зависимости

| Пакет | Зачем |
|-------|-------|
| `python-telegram-bot` | Telegram Bot API |
| `mysql-connector-python` | MySQL |
| `httpx` | HTTP-клиент для LLM (AI Router) |
| `pillow` | Обработка изображений |
| `openpyxl`, `xlrd` | Excel (.xlsx, .xls) |
| `python-dotenv` | Переменные окружения |
| `telethon` | Синхронизация участников группы |

## Документация

**Модули** — каждый модуль содержит свой README с полным описанием (см. таблицу «Что умеет» выше).

**Гайды:**
- [Руководство по разработке модулей](docs/MODULE_GUIDE_RU.md)
- [Конфигурация модулей](docs/MODULE_CONFIG_GUIDE.md) · [Быстрый справочник](docs/MODULE_CONFIG_QUICK_REF.md)
- [AI RAG — база знаний](docs/AI_RAG_GUIDE.md)
- [Рекомендации по валидатору](docs/VALIDATOR_RECOMMENDATIONS.md)

**Утилиты:** `scripts/sync_chat_members.py` (синхронизация Telegram-группы), `scripts/add_daily_scores.py` (массовое начисление очков), `scripts/rag_directory_ingest.py` (пакетная загрузка документов в RAG), `scripts/rag_vector_backfill.py` (пакетная индексация существующих RAG-чанков в локальный Qdrant).

## Лицензия

**CC BY-NC-SA 4.0** — см. [LICENSE](LICENSE).

> **Только для тестирования и образовательных целей.** Использование в рабочих целях может нарушить корпоративные политики. Автор не несёт ответственность за неправильное использование.

---

*Разработано с ❤️ и AI для инженеров СберСервис · Февраль 2026*

