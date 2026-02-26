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

Загрузка через Telegram (`#rag`) не выполняет немедленный vector upsert: эмбеддинги формируются отдельным запуском `scripts/rag_vector_backfill.py`.

**HTML-документы**: приоритетный semantic-preserving chunking через `HTMLSemanticPreservingSplitter` (h1–h6); при недоступности используется `HTMLHeaderTextSplitter`, затем fallback на plain-text.

**Python 3.14+**: LangChain splitters поддерживаются; встроенный fallback используется только при ошибке импорта/инициализации splitter-а.

### Retrieval

- Двухэтапный hybrid retrieval:
    - prefilter документов по `rag_document_summaries` (гибрид: word-boundary phrase match + token overlap + semantic vector similarity) с fallback-пулом документов для сохранения recall,
    - ранжирование чанков с учётом lexical score чанка + бонуса от summary-релевантности документа + post-merge summary-бонуса в hybrid fusion.
- Опционально: локальный векторный retrieval (Qdrant local mode + локальная embedding-модель) с fusion lexical/vector score.
- Top-summary документы добавляются в системный RAG-промпт как дополнительный контекст.
- In-memory TTL-кэш с инвалидацией по `rag_corpus_version`
- Логирование запросов в `rag_query_log`

### Vector backfill

```bash
python scripts/rag_vector_backfill.py --batch-size 100
python scripts/rag_vector_backfill.py --dry-run --max-documents 200
```

### Qdrant remote→local sync

```bash
python scripts/rag_qdrant_sync_remote_to_local.py --batch-size 200
python scripts/rag_qdrant_sync_remote_to_local.py --dry-run --max-points 500
```

По умолчанию используется коллекция из `AI_RAG_VECTOR_SYNC_COLLECTION` (fallback на `AI_RAG_VECTOR_COLLECTION`).

Периодический запуск через cron (каждые 30 минут):

```bash
*/30 * * * * cd /path/to/sbs_helper_telegram_bot && /path/to/venv/bin/python scripts/rag_qdrant_sync_remote_to_local.py --batch-size 200 >> /var/log/rag_qdrant_sync.log 2>&1
```

Пример systemd (Linux): unit + timer

```ini
# rag-qdrant-sync.service
[Unit]
Description=RAG Qdrant remote-to-local sync
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/sbs_helper_telegram_bot
EnvironmentFile=/path/to/sbs_helper_telegram_bot/.env
ExecStart=/path/to/venv/bin/python scripts/rag_qdrant_sync_remote_to_local.py --batch-size 200
```

```ini
# rag-qdrant-sync.timer
[Unit]
Description=Run RAG Qdrant sync every 30 minutes

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
```

`rag_directory_ingest.py` не выполняет генерацию эмбеддингов: обновление локального векторного индекса выполняется только через `rag_vector_backfill.py`.

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
Перед каждым циклом синхронизации пишется строка `Chunking конфигурация:` с активной стратегией (`html_strategy`, `plain_text_strategy`), выбранным `slicer`, параметрами `chunk_size`/`chunk_overlap` и флагами доступности splitter-ов.
При временных DB-блокировках (`1205`/`1213`) DB-операции (`delete`, `set_status`, `ingest`) автоматически повторяются с коротким backoff. Qdrant I/O вынесен за пределы MySQL-транзакций для минимизации времени удержания блокировок.
Для одной и той же директории синхронизации разрешён только один активный процесс `rag_directory_ingest.py` (PID lock-файл в системной temp-директории); второй запуск завершается с ошибкой, чтобы исключить конкуренцию транзакций.
Для обновления локального векторного индекса после синхронизации запускайте `rag_vector_backfill.py`.
При загрузке каждого документа синхронизация формирует/обновляет запись в `rag_document_summaries`.

## Безопасная отправка
- Для `rag_qa` поддерживается ограниченное форматирование ответа модели: нумерованные/маркированные списки, **жирный текст**, `inline code`; неподдерживаемая markdown-разметка экранируется
- Вложенная разметка вида `**\`code\`**` в `rag_qa` корректно восстанавливается и не выводит служебные плейсхолдеры в пользовательский текст
- Длинные ответы `rag_qa` автоматически разбиваются на несколько MarkdownV2-сообщений, чтобы избежать ошибки Telegram `Message is too long`
- Восстановление `ReplyKeyboardMarkup` после AI-ответа

## Прогресс плейсхолдера AI

- В AI-потоке используется поэтапный индикатор: базовая обработка → ожидание классификации/маршрутизации → RAG prefilter документов → отправка augmented payload в LLM.
- Для сценария `general_chat → reroute → rag_qa` этапы RAG также показываются пользователю.
- Для cache-hit RAG промежуточные этапы пропускаются и возвращается финальный ответ.
- Тексты этапов запрашиваются через единый резолвер сообщений по ключам (`get_ai_message_by_key`), что позволяет позже подключить источник из БД без изменений в бизнес-логике Telegram/Router.

## Логирование

- Результаты классификации → `ai_router_log` (intent, confidence, explain_code, response_time_ms)
- Профилирование маршрутизации: `classify_ms`, `db_log_ms`, `dispatch_ms`, `context_update_ms`
- RAG-запросы → `rag_query_log`
- Диагностика retrieval-канала RAG: строка `RAG retrieval:` с полями `mode`, `tokens`, `prefilter_docs`, `prefilter_scope_docs`, `fallback_docs`, `lexical_hits`, `vector_hits`, `selected`, `selected_unique_docs`, `selected_top_docs`, `top_source`; длинные `source` автоматически сокращаются
- `prefilter_docs` показывает только top-N summary-prefilter, а `prefilter_scope_docs` — итоговый размер области поиска после добавления fallback-документов
- `selected` показывает число финальных чанков, `selected_unique_docs` — число уникальных документов среди них, `selected_top_docs` — top уникальных `document_id` по порядку ранжирования
- Состояние удалённого векторного backend логируется отдельными переходами: `Состояние remote Qdrant: UP|DOWN|COOLDOWN|DISABLED`
- Доказательство summary-приоритизации: строка `RAG priority evidence:` в многострочном ранжированном формате с блоками `prefilter_top` и `selected_top` (до top-5; для `selected_top` добавлены `doc`, `chunk`, `origin`, разложение lexical-компоненты `lex_raw/lex_bonus/lex_total`, формула `hybrid=(lex_total*lexical_weight)+(vector_score*vector_weight)` и `summary_bonus`; `lex_bonus`/`summary_bonus` считаются по нормализованному summary-score документа в диапазоне `0..1` по относительной min-max схеме в текущем prefilter-пуле)
- Диагностика chunking при ingest: строка `RAG chunking strategy:` с полями `file`, `format`, `strategy`, `slicer`, `chunk_size`, `chunk_overlap`, `chunks`, `html_splitter_enabled`, `langchain_splitter_supported`
- Успешная векторная индексация чанков: строка `RAG vector upsert:` с полями `chunks` и `duration_ms` (время upsert в миллисекундах)
- Полный `prompt/response` всех LLM-вызовов (classification/chat/fallback_chat/rag_answer/rag_summary) → `ai_model_io_log`
- Для `deepseek-reasoner` добавлен runtime-fallback: при пустом `content` для chat/RAG выполняется один автоповтор на `deepseek-chat` с предупреждением в логах
- Перед записью в `ai_model_io_log` чувствительные данные маскируются (`email`, `телефон`, `ИНН`, `СНИЛС`)
- Очистка старых full-text логов выполняется скриптом `sql/ai_model_io_log_retention.sql` (30 дней)

## Конфигурация

### Переменные окружения

Важно: модуль `ai_router.settings` загружает `.env` с `load_dotenv(override=True)`, поэтому для AI-настроек значения из `.env` приоритетнее переменных, ранее выставленных в процессе.

| Переменная | По умолчанию | Описание |
| `AI_RAG_LEXICAL_SCORER` | `legacy` | Режим lexical scoring: `legacy` или `bm25` |
| `AI_RAG_BM25_K1` | `1.5` | Параметр `k1` для BM25 |
| `AI_RAG_BM25_B` | `0.75` | Параметр `b` для BM25 |
| `AI_RAG_RU_NORMALIZATION_ENABLED` | `1` | Включить RU-нормализацию токенов |
| `AI_RAG_RU_NORMALIZATION_MODE` | `lemma_then_stem` | Режим RU-нормализации: `lemma_then_stem`/`lemma_only`/`stem_only` |
|------------|-------------|----------|
| `AI_PROVIDER` | `deepseek` | Провайдер LLM |
| `DEEPSEEK_API_KEY` | — | API-ключ |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Базовый URL |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Модель по умолчанию |
| `AI_LLM_REQUEST_TIMEOUT` | `30` | Таймаут запроса (сек) |
| `AI_LLM_CLASSIFICATION_TEMPERATURE` | `0.1` | Температура для intent-классификации |
| `AI_LLM_CLASSIFICATION_MAX_TOKENS` | `1024` | Лимит токенов для intent-классификации |
| `AI_LLM_CHAT_TEMPERATURE` | `0.7` | Температура для chat/RAG-ответов |
| `AI_LLM_CHAT_MAX_TOKENS` | `1024` | Лимит токенов для chat/RAG-ответов |
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
| `AI_RAG_SUMMARY_MATCH_PHRASE_WEIGHT` | `1.6` | Вес exact phrase-совпадения вопроса с document summary |
| `AI_RAG_SUMMARY_MATCH_TOKEN_WEIGHT` | `1.0` | Вес token-overlap score для document summary |
| `AI_RAG_SUMMARY_SCORE_CAP` | `2.5` | Верхняя граница fallback-нормализации summary-score в диапазон `0..1` (основной retrieval использует min-max по prefilter-пулу) |
| `AI_RAG_SUMMARY_BONUS_WEIGHT` | `0.45` | Вес бонуса нормализованного summary-score в lexical scoring чанков |
| `AI_RAG_SUMMARY_POSTRANK_WEIGHT` | `0.20` | Вес пост-бонуса нормализованного summary-score после hybrid merge |
| `AI_RAG_SUMMARY_PREFILTER_FALLBACK_DOCS` | `0` | Число fallback-документов без summary-hit для сохранения recall |
| `AI_RAG_SUMMARY_VECTOR_WEIGHT` | `10` | Вес semantic vector similarity summary в prefilter scoring (`prefilter_score = lexical + vec * weight`) |
| `AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL` | — | Отдельная DeepSeek-модель для summary только в `rag_directory_ingest.py` (`deepseek-chat`/`deepseek-reasoner`) |
| `AI_RAG_CACHE_TTL_SECONDS` | `300` | TTL кэша |
| `AI_RAG_HTML_SPLITTER_ENABLED` | `1` | HTML semantic-preserving splitter |
| `AI_RAG_VECTOR_ENABLED` | `0` | Включить векторный retrieval |
| `AI_RAG_HYBRID_ENABLED` | `1` | Использовать hybrid-слияние lexical/vector |
| `AI_RAG_VECTOR_LOCAL_MODE` | `1` | Разрешить local fallback через Qdrant local mode |
| `AI_RAG_VECTOR_REMOTE_URL` | — | URL удалённого Qdrant (remote-first, если задан) |
| `AI_RAG_VECTOR_REMOTE_API_KEY` | — | API ключ удалённого Qdrant (опционально) |
| `AI_RAG_VECTOR_REMOTE_TIMEOUT_SECONDS` | `5` | Таймаут запросов к remote Qdrant |
| `AI_RAG_VECTOR_REMOTE_FAILURE_THRESHOLD` | `3` | Ошибок подряд до failover на local |
| `AI_RAG_VECTOR_REMOTE_COOLDOWN_SECONDS` | `120` | Cooldown remote после failover |
| `AI_RAG_VECTOR_DB_PATH` | `./data/qdrant` | Путь к локальному индексу |
| `AI_RAG_VECTOR_COLLECTION` | `rag_chunks_v1` | Имя коллекции вектора |
| `AI_RAG_VECTOR_SYNC_COLLECTION` | `rag_chunks_v1` | Имя коллекции для remote→local sync |
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

Поведение remote/local backend:
- Если задан `AI_RAG_VECTOR_REMOTE_URL`, индекс работает в режиме remote-first.
- При ошибках remote счётчик отказов увеличивается; после `AI_RAG_VECTOR_REMOTE_FAILURE_THRESHOLD` backend переключается на local.
- В течение `AI_RAG_VECTOR_REMOTE_COOLDOWN_SECONDS` remote не используется, затем сервис снова пытается подключиться к remote.
- Если local fallback отключён (`AI_RAG_VECTOR_LOCAL_MODE=0`) и remote недоступен, retrieval безопасно деградирует в lexical режим.

### Runtime-настройки (admin panel)

| Ключ `bot_settings` | Описание |
|---------------------|----------|
| `ai_deepseek_model_classification` | Модель для классификации |
| `ai_deepseek_model_response` | Модель для ответов |
| `ai_rag_html_splitter_enabled` | HTML splitter вкл/выкл |

## Установка

```bash
mysql -u root -p sprint_db < sql/ai_router_setup.sql
mysql -u root -p sprint_db < sql/ai_rag_setup.sql
mysql -u root -p sprint_db < sql/ai_rag_document_summaries_setup.sql
mysql -u root -p sprint_db < sql/ai_rag_vector_setup.sql
# Для существующих БД без FULLTEXT-индекса по summary_text:
mysql -u root -p sprint_db < sql/rag_document_summaries_fulltext_index.sql
# Периодическая очистка full-text AI логов (по умолчанию 30 дней):
mysql -u root -p sprint_db < sql/ai_model_io_log_retention.sql
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
