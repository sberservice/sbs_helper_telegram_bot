# SBS Archie 🤖

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/) [![Лицензия](https://img.shields.io/badge/license-CC--BY--NC--SA--4.0-red.svg)](LICENSE)

> *Ваш AI-напарник в полях — потому что даже герои заслуживают умного помощника.*

## О проекте

**SBS Archie** (Archie = Architect) — модульная AI-платформа для инженеров **СберСервис**. Объединяет Telegram-бота, веб-админку, систему добычи знаний из групп техподдержки, AI-помощника для чатов и набор CLI-утилит — общим AI-ядром.

Построен на архитектуре плагинов с AI-маршрутизатором в центре. Каждый модуль независим, включается/отключается через админку, а AI-роутер связывает их в единое целое — как мозг.

Демо: [@vyezdbyl_bot](https://t.me/vyezdbyl_bot) *(может не отражать текущую стадию разработки)*

## Архитектура

```
SBS Archie
├── src/core/ai/                  ← Общее AI-ядро (LLM, RAG, vector search)
├── src/sbs_helper_telegram_bot/  ← Telegram-бот (модули-плагины)
├── src/group_knowledge/          ← Добыча знаний из групп техподдержки
├── admin_web/                    ← Веб-админка (FastAPI + React)
├── prompt_tester/                ← A/B-тестер промптов RAG (FastAPI + React)
├── scripts/                      ← CLI-утилиты и демоны
└── config/                       ← Настройки (.env)
    ├── ai_settings.py            ← AI/RAG/LLM/GigaChat/GK параметры (~700 строк)
    ├── database_settings.py      ← MySQL credentials
    └── settings.py               ← Telegram и сетевые настройки
```

## Компоненты

### 1. Telegram-бот

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
| 🩺 | **Health Check** | Мониторинг доступности сервиса налоговой + календарь плановых работ | — |
| 🛠️ | **Админ бота** | Пользователи, инвайты, модули, настройки, плановые работы | [README](src/sbs_helper_telegram_bot/bot_admin/README.md) |

### 2. Group Knowledge — добыча знаний из групп

Standalone-подсистема на Telethon для автоматического извлечения знаний из переписок в Telegram-группах техподдержки. 4-стадийный пайплайн:

1. **Коллектор** — слушает сообщения через Telethon, сохраняет в MySQL, классифицирует как вопрос/не вопрос через LLM.
2. **Обработчик изображений** — описывает скриншоты через GigaChat Vision API.
3. **Анализатор** — извлекает Q&A-пары из reply-цепочек (thread-based) и через LLM-анализ контекста (LLM-inferred), индексирует в Qdrant.
4. **Автоответчик** — daemon, встроенный в коллектор: обнаруживает вопросы, ищет ответы через гибридный BM25 + Vector + RRF, отвечает с ссылкой на исходное обсуждение. Dry-run по умолчанию.

Ключевые возможности:
- Гибридный поиск с Russian NLP (pymorphy3 + snowballstemmer), защищёнными доменными терминами, корпусной коррекцией опечаток (SymSpellPy + LLM-fallback)
- Склейка соседних сообщений одного пользователя (текст + изображение) в единый контекст
- Кросс-дневное обогащение цепочек для ответов, приходящих на следующий день
- Per-user и per-group rate limiting, test-mode с redirect в тестовую группу
- Подсказки релевантности для LLM (уровень + нормализованные BM25/vector оценки)
- Q&A-пары, отклонённые экспертами, исключаются из поиска и индексации

Подробнее: [src/group_knowledge/README.md](src/group_knowledge/README.md)

### 3. The Helper — AI-помощник для групп

Telethon-скрипт, слушающий команду `/helpme` в настроенных Telegram-группах. Маршрутизирует запрос через AI-пайплайн (RAG / UPOS) и отвечает reply-сообщением с прогрессом по этапам.

- Голый `/helpme` в ответ на сообщение — отправляет текст оригинала в RAG
- `/helpme <вопрос>` — полная AI-маршрутизация
- Двухуровневый rate-limit (per-user + per-group)
- Ограничен intent-ами: `upos_error_lookup`, `rag_qa`, `general_chat`

Подробнее: [scripts/THE_HELPER_README.md](scripts/THE_HELPER_README.md)

### 4. Admin Web — веб-админка

Единая веб-платформа администрирования (FastAPI + React SPA) с аутентификацией и RBAC.

**Аутентификация:**
- Telegram Login Widget
- Password-вход (параллельно) с policy сложности, rate-limit и lockout

**Роли:** `super_admin`, `admin`, `expert`, `viewer` — права настраиваются в БД.

**Модули:**

| Модуль | Возможности |
|--------|-------------|
| 🧠 **Group Knowledge** | 9 вкладок: статистика, каталог Q&A-пар, экспертная валидация с hotkeys и двойным подтверждением, A/B-тестер промптов (Elo + Win Rate + агрегированная статистика), группы, лог автоответчика, очередь изображений (ручная загрузка + превью), отдельный Image Prompt Tester (blind A/B + Elo + выбор модели + кастомные промпты + полная статистика), песочница гибридного поиска с предпросмотром ответа |
| ⚙️ **Менеджер процессов** | Управление 18 процессами по 5 категориям: запуск/остановка/перезапуск из веба, пресеты режимов, формы выбора параметров, WebSocket-логи, история запусков, персистентное состояние (авто-восстановление демонов после рестарта), компактный обзор карточек процессов |
| 🧪 **Prompt Tester** | Встроенный тестер промптов RAG (монтируется как sub-application) |

```bash
python -m admin_web
```

Подробнее: [admin_web/README.md](admin_web/README.md)

### 5. Prompt Tester — A/B-тестирование промптов

Веб-инструмент для слепого попарного сравнения промптов summary в RAG:
- сравнение комбинаций `(system_prompt + user_message + model + temperature)`;
- режимы оценки: `human`, `llm` (LLM-as-Judge), `both`;
- этапы: `generating → judging → in_progress → completed`;
- стратифицированная выборка документов;
- итоговые рейтинги Elo + Win Rate.

```bash
python -m prompt_tester
```

Подробнее: [prompt_tester/README.md](prompt_tester/README.md)

### 6. AI-ядро (`src/core/ai/`)

Переиспользуемый AI-движок, не зависящий от Telegram:

| Файл | Назначение |
|------|------------|
| `llm_provider.py` | LLM-абстракция: `DeepSeekProvider` (classification + chat + RAG) и `GigaChatProvider` (vision/image description) |
| `rag_service.py` | Полный RAG-пайплайн (~5200 строк): ingestion (PDF/TXT/DOCX/MD/HTML), BM25 с Russian NLP, HyDE, spellcheck (SymSpellPy + LLM), summary-prefilter/fallback, response caching |
| `vector_search.py` | `LocalEmbeddingProvider` (BAAI/bge-m3, fp16) + `LocalVectorIndex` (Qdrant local/remote) |
| `qdrant_sync.py` | Синхронизация Qdrant remote → local |
| `circuit_breaker.py` | CLOSED → OPEN → HALF\_OPEN с настраиваемыми порогами |
| `rate_limiter.py` | Sliding window per-user rate limiter |
| `context_manager.py` | In-memory TTL-deque контекста диалога |
| `prompts.py` | Динамические системные промпты (classification, chat, RAG, HyDE, spellcheck) |
| `formatters.py` | MarkdownV2-форматирование, прогресс-этапы |
| `rag_similarity.py` | Оценка похожести: semantic + lexical + sequence, CLI-режим |
| `rag_similarity_interactive.py` | Интерактивный REPL для similarity с историей, diff, JSON/CSV-экспортом |

### 7. CLI-утилиты и демоны (`scripts/`)

| Скрипт | Описание |
|--------|----------|
| `gk_collector.py` | Daemon: сбор сообщений GK + обработка изображений + автоответчик |
| `gk_analyze.py` | Извлечение Q&A-пар + Qdrant-индексация |
| `gk_responder.py` | Legacy standalone-автоответчик GK |
| `gk_delete_group_data.py` | Безопасное удаление данных группы с dry-run |
| `the_helper.py` | Daemon: `/helpme` listener для Telegram-групп |
| `rag_ops.py` | Единый CLI для RAG (health, status, setup, update, preload-embeddings, sync-remote, wizard) |
| `rag_directory_ingest.py` | Пакетная загрузка документов в RAG (one-shot / daemon) |
| `rag_certification_sync.py` | Синхронизация вопросов аттестации в RAG |
| `rag_vector_backfill.py` | Пакетная индексация в Qdrant |
| `rag_qdrant_sync_remote_to_local.py` | Синхронизация Qdrant remote → local |
| `rag_sentence_similarity.py` | Оценка похожести фраз (one-shot / интерактивный REPL) |
| `sync_chat_members.py` | Синхронизация участников Telegram-группы |
| `add_daily_scores.py` | Массовое начисление очков геймификации |
| `release.py` | Bump VERSION, обновление CHANGELOG, создание git-тега |

## Точки входа

| Процесс | Команда | Назначение |
|---------|---------|------------|
| Telegram-бот + воркеры | `python run_bot.py` | 4 подпроцесса: бот, фоновые очереди скриншотов и СООС, health check |
| Admin Web | `python -m admin_web` | Веб-админка на порту 8090 |
| GK Collector | `python scripts/gk_collector.py` | Сбор + автоответчик (standalone) |
| GK Analyzer | `python scripts/gk_analyze.py` | Q&A-извлечение (standalone) |
| The Helper | `python scripts/the_helper.py` | `/helpme` listener (standalone) |
| Prompt Tester | `python -m prompt_tester` | A/B-тестер промптов (standalone или через Admin Web) |

## Быстрый старт

```bash
# 1. Виртуальное окружение
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Конфигурация
cp .env.example .env   # Заполнить TELEGRAM_TOKEN, MYSQL_*, DEEPSEEK_API_KEY

# 3. База данных
mysql -u root -p < schema.sql
# Далее sql/*_setup.sql по необходимости (см. docs/SETUP.md)

# 4. Запуск бота
python run_bot.py

# 5. (опционально) Веб-админка
python -m admin_web

# 6. (опционально) Group Knowledge
python scripts/gk_collector.py --manage-groups  # настройка групп
python scripts/gk_collector.py                  # старт коллектора (dry-run)
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

## Основные зависимости

| Категория | Пакеты |
|-----------|--------|
| Telegram | `python-telegram-bot`, `Telethon` |
| AI/ML | `torch`, `transformers`, `sentence-transformers`, `tokenizers` |
| LLM | `httpx` (DeepSeek), `gigachat` (GigaChat Vision) |
| NLP | `pymorphy3`, `snowballstemmer`, `rank-bm25`, `symspellpy` |
| LangChain | `langchain`, `langchain-text-splitters`, `langchain-community` |
| Vector DB | `qdrant-client` |
| Database | `mysql-connector-python`, `PyMySQL`, `SQLAlchemy` |
| Web | `fastapi`, `uvicorn`, `beautifulsoup4`, `Jinja2` |
| Обработка файлов | `pillow`, `openpyxl`, `xlrd`, `pdfplumber` |
| Validation | `pydantic`, `pydantic-settings` |
| Config | `python-dotenv` |
| Testing | `pytest`, `pytest-asyncio` |

## Документация

**По модулям** — каждый модуль содержит свой README (см. таблицу модулей выше).

**Подсистемы:**
- [Group Knowledge](src/group_knowledge/README.md)
- [Admin Web](admin_web/README.md)
- [Prompt Tester](prompt_tester/README.md)
- [The Helper](scripts/THE_HELPER_README.md)

**Гайды:**
- [Установка и настройка](docs/SETUP.md)
- [Руководство по разработке модулей](docs/MODULE_GUIDE_RU.md)
- [Конфигурация модулей](docs/MODULE_CONFIG_GUIDE.md) · [Быстрый справочник](docs/MODULE_CONFIG_QUICK_REF.md)
- [RAG-операции (CLI)](docs/RAG_OPERATIONS_GUIDE.md)
- [Ingestion пайплайн](docs/ingestion.md)
- [Рекомендации по валидатору](docs/VALIDATOR_RECOMMENDATIONS.md)

## Лицензия

**CC BY-NC-SA 4.0** — см. [LICENSE](LICENSE).

> **Только для тестирования и образовательных целей.** Использование в рабочих целях может нарушить корпоративные политики. Автор не несёт ответственность за неправильное использование.

---

*Разработано с ❤️ и AI для инженеров СберСервис · v0.9.8 · Март 2026*

