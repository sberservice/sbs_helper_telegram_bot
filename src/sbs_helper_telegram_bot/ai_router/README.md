# Модуль AI-маршрутизатора 🤖

Интеллектуальная маршрутизация произвольного текста к модулям бота через LLM с поддержкой RAG-базы знаний.

## Описание

AI-маршрутизатор — сердце бота. Каждое текстовое сообщение, не распознанное как команда меню, проходит через конвейер:

1. **Rate-limit** — скользящее окно (10 запросов / 60 сек на пользователя)
2. **Circuit breaker** — автоматическая деградация при серии ошибок LLM
3. **Классификация** — LLM определяет intent, confidence и параметры
4. **Маршрутизация** — запрос направляется в нужный модуль или в свободный чат
5. **RAG** — если вопрос относится к базе знаний, ответ формируется по загруженным документам

## Поддерживаемые intent'ы

| Intent | Модуль | Описание |
|--------|--------|----------|
| `upos_error_lookup` | 🔢 UPOS Ошибки | Поиск кода ошибки |
| `ticket_validation` | ✅ Валидация заявок | Проверка текста заявки |
| `ktr_lookup` | ⏱️ КТР | Поиск кода трудозатрат |
| `certification_info` | 📝 Аттестация | Сводка, статистика, категории |
| `news_search` | 📰 Новости | Поиск и отображение новостей |
| `rag_qa` | 📚 База знаний | Ответ по загруженным документам |
| `general_chat` | 💬 Чат | Свободный диалог с LLM |
| `unknown` | — | Неопознанный ввод |

## Архитектура

```
Пользователь
    │
    ▼
IntentRouter
    ├── RateLimiter          ── скользящее окно (in-memory deque)
    ├── CircuitBreaker       ── CLOSED → OPEN → HALF_OPEN
    ├── LLMProvider          ── DeepSeek (OpenAI-совместимый)
    │   ├── classify()       ── JSON: intent + confidence + parameters
    │   └── chat()           ── свободный ответ
    ├── IntentHandlers       ── dispatch по модулям
    └── RagKnowledgeService  ── ingest + retrieve + answer
```

### Логика маршрутизации

| Confidence | Действие |
|------------|----------|
| ≥ 0.6 | Направление в модуль (если включён) |
| 0.3–0.6 | Свободный чат через LLM |
| < 0.3 | Fallback-ответ «Не смог разобраться» |

Если `general_chat` определён, но сообщение не является small-talk и RAG включён → автоматический reroute в `rag_qa`.

## LLM-провайдер

- **Абстракция**: `LLMProvider` — расширяемая фабрика через `register_provider()`
- **Реализация**: `DeepSeekProvider` (OpenAI-совместимый `/v1/chat/completions`)
- **Раздельные модели**: отдельная модель для классификации и для генерации ответов
- **Переключение runtime**: через админ-панель (`🧠 AI модель`) без перезапуска бота
- **Парсинг ответов**: JSON → partial-JSON fallback → direct-text fallback

## Защита от нагрузки

### Rate Limiter
- Скользящее окно (in-memory `deque`) по каждому пользователю
- По умолчанию: 10 запросов за 60 секунд
- Возвращает оставшееся время до сброса окна

### Circuit Breaker
```
CLOSED ──(5 ошибок)──► OPEN ──(300с)──► HALF_OPEN
   ▲                                         │
   └────────(успех)──────────────────────────┘
                     (ошибка) ──► OPEN
```
- При серии из 5 ошибок LLM → все AI-запросы блокируются
- Через 300 секунд — пробный запрос (HALF_OPEN)
- Успех → возврат в работу; неудача → снова OPEN

### Контекст диалога
- Хранение последних 6 сообщений с TTL 10 минут (in-memory)
- Обеспечивает связность коротких диалогов
- Автоматическая очистка при навигации по меню

## RAG — база знаний

### Загрузка документов

Администраторы загружают документы в Telegram: файл + подпись `#rag`.

**Поддерживаемые форматы**: PDF, DOCX, TXT, MD, HTML

**Обработка**:
1. Извлечение текста из документа
2. Разбиение на чанки (1000 символов, overlap 150)
3. SHA-256 дедупликация (повторная загрузка реактивирует запись)
4. Сохранение в БД с FULLTEXT-индексом

**HTML-документы**: приоритетный header-aware chunking через `HTMLHeaderTextSplitter` (h1–h6); при недоступности — fallback на plain-text.

**Python 3.14+**: LangChain splitters поддерживаются; встроенный fallback используется только при ошибке импорта/инициализации splitter-а.

### Retrieval

- Двухэтапный hybrid retrieval:
    - prefilter документов по `rag_document_summaries` (релевантность summary к вопросу),
    - ранжирование чанков с учётом lexical score чанка + бонуса от summary-релевантности документа.
- Опционально: локальный векторный retrieval (Qdrant local mode + локальная embedding-модель) с fusion lexical/vector score.
- Top-summary документы добавляются в системный RAG-промпт как дополнительный контекст.
- In-memory TTL-кэш с инвалидацией по `rag_corpus_version`
- Логирование запросов в `rag_query_log`

### Vector backfill

```bash
python scripts/rag_vector_backfill.py --batch-size 100
python scripts/rag_vector_backfill.py --dry-run --max-documents 200
```

При сохранении метаданных в `rag_chunk_embeddings` используется batched upsert и автоматический retry для временных ошибок MySQL (`1205`/`1213`) с коротким backoff.

### Суммаризация документов

- AI-генерируемые саммари (4–8 предложений) для top-K документов
- Кэширование в `rag_document_summaries`
- Используются для prefilter документов и для prompt enrichment RAG-ответа

### Жизненный цикл документа

```
active → archived → deleted (soft) → purged (hard delete)
```

### CRUD-команды (Telegram)

| Команда | Описание |
|---------|----------|
| `#rag help` | Справка по командам |
| `#rag list [status] [limit]` | Список документов |
| `#rag info <id>` | Подробная карточка |
| `#rag archive <id>` | Архивация |
| `#rag restore <id>` | Восстановление |
| `#rag delete <id>` | Мягкое удаление |
| `#rag purge <id>` | Физическое удаление |

### Пакетная синхронизация директории

```bash
# On-demand
python scripts/rag_directory_ingest.py --directory <path>

# Принудительное переобновление даже без изменений
python scripts/rag_directory_ingest.py --directory <path> --force-update

# Daemon-режим
python scripts/rag_directory_ingest.py --directory <path> --daemon --interval-seconds 900

# Dry-run
python scripts/rag_directory_ingest.py --directory <path> --dry-run
```

Скрипт можно запускать и из любой текущей директории, если указать к нему абсолютный путь.

Удалённые из директории файлы purge-ятся из RAG; изменённые — перезагружаются.
С флагом `--force-update` перезагружаются также и неизменённые файлы.
При временных DB-блокировках (`1205`/`1213`) DB-операции (`delete`, `set_status`, `ingest`) автоматически повторяются с коротким backoff. Qdrant I/O вынесен за пределы MySQL-транзакций для минимизации времени удержания блокировок.
Для одной и той же директории синхронизации разрешён только один активный процесс `rag_directory_ingest.py` (PID lock-файл в системной temp-директории); второй запуск завершается с ошибкой, чтобы исключить конкуренцию транзакций.
Если локальный Qdrant-путь (`AI_RAG_VECTOR_DB_PATH`) уже занят другим процессом, векторная индексация автоматически отключается для текущего процесса синхронизации, а загрузка документов продолжается в lexical fallback.
При загрузке каждого документа синхронизация формирует/обновляет запись в `rag_document_summaries`.

## Безопасная отправка

- Экранирование MarkdownV2 с fallback на plain text
- Плейсхолдер «⏳ Обрабатываю ваш запрос...» → edit → fallback новым сообщением
- Для RAG-запросов плейсхолдер обновляется на «⏳ Ожидаю ответа ИИ»
- Для `rag_qa` поддерживается ограниченное форматирование ответа модели: нумерованные/маркированные списки, **жирный текст**, `inline code`; неподдерживаемая markdown-разметка экранируется
- Длинные ответы `rag_qa` автоматически разбиваются на несколько MarkdownV2-сообщений, чтобы избежать ошибки Telegram `Message is too long`
- Восстановление `ReplyKeyboardMarkup` после AI-ответа

## Логирование

- Результаты классификации → `ai_router_log` (intent, confidence, explain_code, response_time_ms)
- Профилирование маршрутизации: `classify_ms`, `db_log_ms`, `dispatch_ms`, `context_update_ms`
- RAG-запросы → `rag_query_log`
- Диагностика retrieval-канала RAG: строка `RAG retrieval:` с полями `mode`, `tokens`, `prefilter_docs`, `lexical_hits`, `vector_hits`, `selected`, `top_source`
- Полный `prompt/response` всех LLM-вызовов (classification/chat/fallback_chat/rag_answer/rag_summary) → `ai_model_io_log`
- Для `deepseek-reasoner` добавлен runtime-fallback: при пустом `content` для chat/RAG выполняется один автоповтор на `deepseek-chat` с предупреждением в логах
- Перед записью в `ai_model_io_log` чувствительные данные маскируются (`email`, `телефон`, `ИНН`, `СНИЛС`)
- Очистка старых full-text логов выполняется скриптом `scripts/ai_model_io_log_retention.sql` (30 дней)

## Конфигурация

### Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|-------------|----------|
| `AI_PROVIDER` | `deepseek` | Провайдер LLM |
| `DEEPSEEK_API_KEY` | — | API-ключ |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Базовый URL |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Модель по умолчанию |
| `AI_LLM_REQUEST_TIMEOUT` | `30` | Таймаут запроса (сек) |
| `AI_LOG_MODEL_IO` | `1` | Логировать payload prompt и raw response модели |
| `AI_LOG_MODEL_IO_MAX_CHARS` | `8000` | Лимит символов для prompt/response в логах |
| `AI_MODEL_IO_DB_LOG_ENABLED` | `1` | Сохранять полный prompt/response в таблицу `ai_model_io_log` |
| `AI_MODEL_IO_DB_RETENTION_DAYS` | `30` | Целевой retention full-text логов (для cron/cleanup) |
| `AI_CONFIDENCE_THRESHOLD` | `0.6` | Порог маршрутизации в модуль |
| `AI_CHAT_CONFIDENCE_THRESHOLD` | `0.3` | Порог свободного чата |
| `AI_RATE_LIMIT_MAX` | `10` | Макс. запросов в окне |
| `AI_RATE_LIMIT_WINDOW` | `60` | Окно rate-limit (сек) |
| `AI_MAX_CONTEXT_MESSAGES` | `6` | Размер контекста |
| `AI_CONTEXT_TTL_SECONDS` | `600` | TTL контекста (сек) |
| `AI_CIRCUIT_BREAKER_FAILURES` | `5` | Ошибок до OPEN |
| `AI_CIRCUIT_BREAKER_RECOVERY` | `300` | Время восстановления (сек) |
| `AI_MAX_INPUT_LENGTH` | `4000` | Макс. длина входа |

### RAG-конфигурация

| Переменная | По умолчанию | Описание |
|------------|-------------|----------|
| `AI_RAG_ENABLED` | `1` | RAG включён |
| `AI_RAG_MAX_FILE_SIZE_MB` | `20` | Макс. размер файла |
| `AI_RAG_CHUNK_SIZE` | `1000` | Размер чанка |
| `AI_RAG_CHUNK_OVERLAP` | `150` | Перекрытие чанков |
| `AI_RAG_TOP_K` | `8` | Top-K чанков для ответа |
| `AI_RAG_MAX_CONTEXT_CHARS` | `14000` | Макс. контекст |
| `AI_RAG_SUMMARY_ENABLED` | `1` | Включить AI/fallback summary |
| `AI_RAG_SUMMARY_INPUT_MAX_CHARS` | `12000` | Макс. объём входа для summary |
| `AI_RAG_SUMMARY_MAX_CHARS` | `1200` | Макс. длина summary |
| `AI_RAG_PREFILTER_TOP_DOCS` | `12` | Число документов в summary-prefilter |
| `AI_RAG_PROMPT_SUMMARY_DOCS` | `3` | Число summary в RAG-промпте |
| `AI_RAG_CACHE_TTL_SECONDS` | `300` | TTL кэша |
| `AI_RAG_HTML_SPLITTER_ENABLED` | `1` | HTML header-aware splitter |
| `AI_RAG_VECTOR_ENABLED` | `0` | Включить локальный векторный retrieval |
| `AI_RAG_HYBRID_ENABLED` | `1` | Использовать hybrid-слияние lexical/vector |
| `AI_RAG_VECTOR_LOCAL_MODE` | `1` | Использовать Qdrant local mode |
| `AI_RAG_VECTOR_DB_PATH` | `./data/qdrant` | Путь к локальному индексу |
| `AI_RAG_VECTOR_COLLECTION` | `rag_chunks_v1` | Имя коллекции вектора |
| `AI_RAG_VECTOR_DISTANCE` | `cosine` | Метрика (`cosine`/`dot`/`euclid`) |
| `AI_RAG_VECTOR_TOP_K` | `12` | Top-K векторных кандидатов |
| `AI_RAG_VECTOR_PREFETCH_K` | `40` | Глубина первичного поиска в индексе |
| `AI_RAG_VECTOR_EMBEDDING_MODEL` | `BAAI/bge-m3` | Локальная embedding-модель |
| `AI_RAG_VECTOR_DEVICE` | `auto` | Устройство embedding-модели (`auto`/`cuda`/`cpu`) |
| `AI_RAG_VECTOR_EMBEDDING_FP16` | `0` | Включить FP16 для локальных эмбеддингов на CUDA (`1`/`0`) |
| `AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE` | `8` | Batch size при вычислении эмбеддингов |
| `AI_RAG_VECTOR_EMBEDDING_MAX_CHARS` | `6000` | Ограничение длины текста на embedding |
| `AI_RAG_VECTOR_LEXICAL_WEIGHT` | `0.45` | Вес lexical score в hybrid |
| `AI_RAG_VECTOR_SEMANTIC_WEIGHT` | `0.55` | Вес vector score в hybrid |

### Практические пресеты

**macOS (сбалансированный)**
- `AI_RAG_VECTOR_EMBEDDING_MODEL=BAAI/bge-m3`
- `AI_RAG_VECTOR_EMBEDDING_FP16=0`
- `AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE=6`
- `AI_RAG_VECTOR_TOP_K=14`
- `AI_RAG_VECTOR_PREFETCH_K=42`
- `AI_RAG_VECTOR_LEXICAL_WEIGHT=0.40`
- `AI_RAG_VECTOR_SEMANTIC_WEIGHT=0.60`

**Windows (i5-3550 + NVIDIA T400, стабильный профиль)**
- `AI_RAG_VECTOR_EMBEDDING_MODEL=intfloat/multilingual-e5-small`
- `AI_RAG_VECTOR_DEVICE=auto`
- `AI_RAG_VECTOR_EMBEDDING_FP16=1`
- `AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE=2`
- `AI_RAG_VECTOR_TOP_K=10`
- `AI_RAG_VECTOR_PREFETCH_K=24`
- `AI_RAG_VECTOR_LEXICAL_WEIGHT=0.55`
- `AI_RAG_VECTOR_SEMANTIC_WEIGHT=0.45`

Пояснение для T400:
- `AI_RAG_VECTOR_DEVICE=auto` автоматически выбирает `cuda` при доступном GPU и переключается на `cpu`, если CUDA недоступен.
- `AI_RAG_VECTOR_EMBEDDING_FP16=1` применяется только при `cuda`; при `cpu` инициализация продолжится в FP32 без падения.
- Для строгого GPU-режима можно использовать `AI_RAG_VECTOR_DEVICE=cuda`.

### Runtime-настройки (admin panel)

| Ключ `bot_settings` | Описание |
|---------------------|----------|
| `ai_deepseek_model_classification` | Модель для классификации |
| `ai_deepseek_model_response` | Модель для ответов |
| `ai_rag_html_splitter_enabled` | HTML splitter вкл/выкл |

## Установка

```bash
mysql -u root -p sprint_db < scripts/ai_router_setup.sql
mysql -u root -p sprint_db < scripts/ai_rag_setup.sql
mysql -u root -p sprint_db < scripts/ai_rag_document_summaries_setup.sql
mysql -u root -p sprint_db < scripts/ai_rag_vector_setup.sql
# Для существующих БД без FULLTEXT-индекса по summary_text:
mysql -u root -p sprint_db < scripts/rag_document_summaries_fulltext_index.sql
# Периодическая очистка full-text AI логов (по умолчанию 30 дней):
mysql -u root -p sprint_db < scripts/ai_model_io_log_retention.sql
```

## База данных

### Таблицы

| Таблица | Описание |
|---------|----------|
| `ai_router_log` | Лог классификации (intent, confidence, response_time) |
| `ai_model_io_log` | Полный prompt/response AI-вызовов (с маскировкой PII) |
| `rag_documents` | Метаданные документов (статус, хеш, источник) |
| `rag_chunks` | Чанки документов (FULLTEXT индекс) |
| `rag_document_summaries` | AI-генерируемые саммари |
| `rag_corpus_version` | Версия корпуса для инвалидации кэша |
| `rag_query_log` | Лог RAG-запросов |

## Структура модуля

```
ai_router/
├── __init__.py              # Экспорт модуля
├── intent_router.py         # Оркестратор: rate-limit → classify → dispatch
├── llm_provider.py          # Абстракция LLM + DeepSeekProvider
├── intent_handlers.py       # Обработчики по модулям
├── prompts.py               # Системные промпты (classification, chat, RAG)
├── circuit_breaker.py       # Circuit Breaker (CLOSED/OPEN/HALF_OPEN)
├── rate_limiter.py          # Sliding-window rate limiter
├── context_manager.py       # Контекст диалога с TTL
├── rag_service.py           # RAG: ingest, chunk, retrieve, answer, cache
├── rag_admin_bot_part.py    # Админ-хендлеры загрузки и CRUD документов
├── ai_router_bot_part.py    # Регистрация хендлеров в Telegram
├── settings.py              # Конфигурация из .env
├── messages.py              # Сообщения (MarkdownV2)
├── keyboards.py             # Клавиатуры
└── README.md                # Документация
```

---

**Версия:** 1.0.0
**Обновлено:** Февраль 2026
