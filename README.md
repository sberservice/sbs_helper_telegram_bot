# SBS Archie 🤖

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/) [![Лицензия](https://img.shields.io/badge/license-CC--BY--NC--SA--4.0-red.svg)](LICENSE)

> *Ваш AI-напарник в полях — потому что даже герои заслуживают умного помощника.*

## О проекте

**SBS Archie** (Archie = Architect) — модульная AI-платформа для инженеров **СберСервис**. Проект включает Telegram-бота, веб-инструменты и CLI-утилиты — объединённые общим AI-ядром.

Построен на архитектуре плагинов с AI-маршрутизатором в центре. Каждый модуль независим, включается/отключается через админку, а AI-роутер связывает их в единое целое — как мозг.

Демо: [@vyezdbyl_bot](https://t.me/vyezdbyl_bot) *(может не отражать текущую стадию разработки)*

## Архитектура

```
SBS Archie
├── src/core/ai/           ← Общее AI-ядро (LLM, RAG, vector search)
├── src/sbs_helper_telegram_bot/  ← Telegram-бот (модули)
├── prompt_tester/         ← Веб-приложение (FastAPI + React)
├── scripts/               ← CLI-утилиты
└── config/                ← Настройки (.env)
    ├── ai_settings.py     ← AI/RAG/LLM параметры
    ├── database_settings.py ← MySQL credentials
    └── settings.py        ← Telegram и сетевые настройки
```

## Компоненты

### Telegram-бот

Основной интерфейс. Просто напишите боту что угодно — AI поймёт, о чём вы, и направит в нужный модуль.

| | Модуль | Суть | Подробнее |
|---|--------|------|-----------|
| 🤖 | **AI-маршрутизатор** | Классификация текста через LLM, intent routing, RAG-база знаний, свободный чат | [README](src/sbs_helper_telegram_bot/ai_router/README.md) |
| 📝 | **Аттестация** | Тестирование, рейтинги, категории, режим обучения, динамические ранги | [README](src/sbs_helper_telegram_bot/certification/README.md) |
| 📸 | **Скриншоты** | Наложение маркеров локации на скриншоты Спринта (фоновая очередь) | [README](src/sbs_helper_telegram_bot/vyezd_byl/README.md) |
| 🧾 | **СООС** | Генерация чека «Сверка итогов» из текста тикета (фоновая очередь + рендер PNG) | [README](src/sbs_helper_telegram_bot/soos/README.md) |
| 🔢 | **UPOS Ошибки** | Поиск кодов ошибок UPOS с рекомендациями по устранению | [README](src/sbs_helper_telegram_bot/upos_error/README.md) |
| ✅ | **Валидация заявок** | Автоопределение типа + проверка по правилам + пакетная Excel-валидация | [README](src/sbs_helper_telegram_bot/ticket_validator/README.md) |
| ⏱️ | **КТР** | Коды трудозатрат с нормативным временем выполнения | [README](src/sbs_helper_telegram_bot/ktr/README.md) |
| 📬 | **Обратная связь** | Категоризированные обращения с анонимными ответами от поддержки | [README](src/sbs_helper_telegram_bot/feedback/README.md) |
| 📰 | **Новости** | Публикации, рассылки, обязательные объявления, реакции | [README](src/sbs_helper_telegram_bot/news/README.md) |
| 🏆 | **Геймификация** | Очки, достижения (🥉🥈🥇), ранги, лидерборды | [README](src/sbs_helper_telegram_bot/gamification/README.md) |
| 🛠️ | **Админ бота** | Пользователи, инвайты, модули, настройки, плановые работы | [README](src/sbs_helper_telegram_bot/bot_admin/README.md) |

### Prompt Tester (веб-приложение)

Веб-инструмент для слепого попарного сравнения промптов summary в RAG:
- сравнение комбинаций `(system_prompt + user_message + model + temperature)`;
- режимы оценки `human`, `llm`, `both`;
- корректные этапы выполнения `generating -> judging -> in_progress/completed`;
- итоговые рейтинги Elo + Win Rate.

```bash
python -m prompt_tester
```

Документация: [prompt_tester/README.md](prompt_tester/README.md)

### AI-ядро (`src/core/ai/`)

Переиспользуемый AI-движок, не зависящий от Telegram:
- **LLM Provider** — абстракция над DeepSeek API с circuit breaker и rate limiter
- **RAG Service** — полнотекстовый + векторный поиск, HyDE, spellcheck, summary-aware retrieval
- **Vector Search** — Qdrant (local/remote) с sentence-transformers
- **Prompts** — системные промпты для классификации и генерации

### CLI-утилиты (`scripts/`)

| Скрипт | Описание |
|--------|----------|
| `rag_ops.py` | Единый CLI для всех RAG-операций (health, status, setup, wizard) |
| `rag_directory_ingest.py` | Пакетная загрузка документов в RAG |
| `rag_certification_sync.py` | Синхронизация вопросов аттестации в RAG |
| `rag_vector_backfill.py` | Пакетная индексация в Qdrant |
| `rag_qdrant_sync_remote_to_local.py` | Синхронизация Qdrant remote→local |
| `rag_sentence_similarity.py` | Оценка похожести фраз для отладки RAG |
| `sync_chat_members.py` | Синхронизация участников Telegram-группы |
| `add_daily_scores.py` | Массовое начисление очков геймификации |

## Быстрый старт

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # Заполнить TELEGRAM_TOKEN, MYSQL_*, DEEPSEEK_API_KEY
mysql -u root -p < schema.sql
python run_bot.py
```

Подробная установка, настройка БД и конфигурация `.env` — см. [docs/SETUP.md](docs/SETUP.md).

## Навигация бота

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
| `fastapi`, `uvicorn` | Веб-сервер Prompt Tester |

## Документация

**Модули** — каждый модуль содержит свой README с полным описанием (см. таблицу модулей выше).

**Гайды:**
- [Установка и настройка](docs/SETUP.md)
- [Руководство по разработке модулей](docs/MODULE_GUIDE_RU.md)
- [Конфигурация модулей](docs/MODULE_CONFIG_GUIDE.md) · [Быстрый справочник](docs/MODULE_CONFIG_QUICK_REF.md)
- [AI RAG — база знаний](docs/AI_RAG_GUIDE.md)
- [RAG-операции (CLI)](docs/RAG_OPERATIONS_GUIDE.md)
- [Рекомендации по валидатору](docs/VALIDATOR_RECOMMENDATIONS.md)

## Лицензия

**CC BY-NC-SA 4.0** — см. [LICENSE](LICENSE).

> **Только для тестирования и образовательных целей.** Использование в рабочих целях может нарушить корпоративные политики. Автор не несёт ответственность за неправильное использование.

---

*Разработано с ❤️ и AI для инженеров СберСервис · Март 2026*

