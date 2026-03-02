# AI RAG Guide

## Назначение

Этот документ описывает первый этап внедрения RAG-подсистемы в модуль `ai_router`.

RAG-поток позволяет:
- администраторам загружать внутренние документы,
- использовать их как контекст для ответов AI,
- кешировать ответы для ускорения и снижения нагрузки на LLM.

## Что реализовано в MVP

- Новый intent: `rag_qa`.
- Новый обработчик: `RagQaHandler` в `src/sbs_helper_telegram_bot/ai_router/intent_handlers.py`.
- Сервис базы знаний: `RagKnowledgeService` в `src/sbs_helper_telegram_bot/ai_router/rag_service.py`.
- Админ-загрузка документов через Telegram: отправка файла с подписью `#rag`.
- Синхронизация директории документов через helper-скрипт `scripts/rag_directory_ingest.py` (on-demand и daemon-режим).
- Синхронизация вопросов/ответов аттестации через helper-скрипт `scripts/rag_certification_sync.py`.
- Поддерживаемые форматы: `PDF`, `DOCX`, `TXT`, `MD`, `HTML`.
- Для `HTML` используется `HTMLSemanticPreservingSplitter` (если доступен в окружении), чтобы учитывать структуру заголовков `h1-h6` и лучше сохранять семантику документа.
- Для `HTML` предусмотрен безопасный fallback на очищенный plain-text chunking, если semantic splitter (или его fallback `HTMLHeaderTextSplitter`) недоступен или не вернул чанков.
- Для `HTML` доступен runtime-переключатель `ai_rag_html_splitter_enabled` в админ-настройках AI (можно принудительно выключить HTML splitter).
- На Python `3.14+` LangChain splitters работают корректно (предупреждения `pydantic.v1` подавляются); fallback chunking включается только если импорт/инициализация splitter-а завершились ошибкой.
- Таблицы БД: `rag_documents`, `rag_chunks`, `rag_corpus_version`, `rag_query_log`, `rag_document_signals`.
- Таблица полного AI I/O логирования: `ai_model_io_log` (prompt/response всех LLM-вызовов, включая RAG).
- TTL-кэш ответов RAG в памяти процесса.
- Summary-aware retrieval: prefilter документов по `rag_document_summaries` с гибридным scoring (`BM25/legacy lexical + word-boundary phrase match + semantic vector similarity`), controlled fallback документов для recall, hybrid rerank чанков с учётом релевантности summary и prompt enrichment top-summary блоками.
- Query preprocessing для lexical retrieval: фильтрация русских стоп-слов (`AI_RAG_STOPWORDS_ENABLED`), снятие шаблонных вопросительных паттернов типа «что такое X» (`AI_RAG_QUERY_PATTERN_STRIP_ENABLED`) и IDF dampening часто встречающихся query-токенов в summary prefilter (`AI_RAG_PREFILTER_IDF_DAMPEN_RATIO`). Это улучшает ранжирование в корпусах с однородной структурой документов (например, сертификационные Q/A, все начинающиеся с «что такое»).
- В query tokenization сохраняются короткие доменные токены и числовые идентификаторы (`фн`, `36` и т.п.), а фиксированные налоговые термины (`осно`, `усн`, `псн`, `енвд`, `нпд`) защищены от агрессивного стемминга, чтобы не терять смысл в lexical retrieval.
- HyDE (Hypothetical Document Embeddings): LLM генерирует короткий гипотетический ответ на вопрос пользователя, и его эмбеддинг используется для vector search вместо эмбеддинга исходного вопроса (`AI_RAG_HYDE_ENABLED`). Это устраняет разрыв между пространством вопросов и ответов в embedding-модели и улучшает recall при векторном поиске.
- Опциональный векторный retrieval с режимом remote-first (Qdrant server) и автоматическим local fallback (Qdrant local mode + локальная embedding-модель) с hybrid-слиянием lexical/vector кандидатов.
- Для summary-prefilter добавлена отдельная векторная коллекция документов (`AI_RAG_SUMMARY_VECTOR_COLLECTION`) с fallback на in-memory summary embedding scoring, если коллекция недоступна или пуста.
- UX-статус для RAG: после классификации запроса как `rag_qa` бот меняет плейсхолдер с «Обрабатываю ваш запрос» на «Ожидаю ответа ИИ» до получения финального ответа.
- Форматирование ответа `rag_qa` для Telegram MarkdownV2: сохраняются списки, `inline code`, жирный текст (`**...**` → Telegram-совместимый `*...*`), неподдерживаемая markdown-разметка экранируется.
- Длинные RAG-ответы автоматически делятся на несколько сообщений, чтобы не упираться в лимит длины Telegram-сообщения.
- В retrieval добавлены category/freshness сигналы для `source_type=certification`: совпадение категории запроса даёт мягкий буст, неактуальные/неактивные вопросы получают штраф, но остаются в выдаче.
- Для `source_type=certification` в RAG-контент и summary попадают только: вопрос, правильный ответ, пояснение и категории; неверные варианты ответов не включаются.
- Summary для коротких сертификационных Q/A формируется детерминированно (без LLM), чтобы исключить попадание дистракторов и снизить шум в prefilter.
- Summary-fallback: если RAG-чанки не найдены или LLM сообщила `question_answered=false`, система автоматически пытается ответить пользователю на основе summary документов. RAG-ответ возвращается в JSON Mode (`{"answer": "...", "question_answered": true/false}`), а при fallback выполняется отдельный LLM-вызов с контекстом summary. Управляется настройками `AI_RAG_SUMMARY_FALLBACK_ENABLED`, `AI_RAG_SUMMARY_FALLBACK_TOP_DOCS`, `AI_RAG_SUMMARY_FALLBACK_MAX_CONTEXT_CHARS`.

## Как загрузить документ

1. Администратор отправляет в чат бота документ.
2. В подписи к документу указывает `#rag` в начале подписи.
3. Бот подтверждает успешную загрузку, ID документа и число чанков.

Важно: загрузка документа через Telegram (`#rag`) также не выполняет генерацию эмбеддингов. Для обновления локального векторного индекса используйте `scripts/rag_vector_backfill.py`.

## Как синхронизировать директорию документов

On-demand запуск:

```bash
python scripts/rag_directory_ingest.py --directory /path/to/docs
```

Принудительное переобновление файлов (даже без изменения `content_hash`):

```bash
python scripts/rag_directory_ingest.py --directory /path/to/docs --force-update
```

Daemon-режим (регулярная синхронизация):

```bash
python scripts/rag_directory_ingest.py --directory /path/to/docs --daemon --interval-seconds 900
```

Backfill локального векторного индекса по уже загруженным чанкам:

```bash
python scripts/rag_vector_backfill.py --target chunks --batch-size 100
```

Синхронизация сертификационных Q/A пар в RAG:

```bash
python scripts/rag_certification_sync.py --uploaded-by 0
```

С немедленным upsert эмбеддингов в Qdrant:

```bash
python scripts/rag_certification_sync.py --uploaded-by 0 --upsert-vectors
```

Принудительное переобновление всех certification-документов (включая неизменённые по `content_hash`) с немедленным upsert эмбеддингов:

```bash
python scripts/rag_certification_sync.py --uploaded-by 0 --force-update --upsert-vectors
```

Backfill summary-векторов документов (отдельная коллекция):

```bash
python scripts/rag_vector_backfill.py --target summaries --batch-size 100
```

Backfill обоих индексов за один проход:

```bash
python scripts/rag_vector_backfill.py --target both --batch-size 100
```

Best-effort синхронизация Qdrant remote→local (по умолчанию коллекция берётся из `AI_RAG_VECTOR_SYNC_COLLECTION`):

```bash
python scripts/rag_qdrant_sync_remote_to_local.py --batch-size 200
```

Dry-run без записи/удаления:

```bash
python scripts/rag_qdrant_sync_remote_to_local.py --dry-run --max-points 500
```

Периодический запуск через cron (каждые 30 минут):

```bash
*/30 * * * * cd /path/to/sbs_helper_telegram_bot && /path/to/venv/bin/python scripts/rag_qdrant_sync_remote_to_local.py --batch-size 200 >> /var/log/rag_qdrant_sync.log 2>&1
```

Пример systemd unit (Linux):

```ini
[Unit]
Description=RAG Qdrant remote-to-local sync
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/sbs_helper_telegram_bot
EnvironmentFile=/path/to/sbs_helper_telegram_bot/.env
ExecStart=/path/to/venv/bin/python scripts/rag_qdrant_sync_remote_to_local.py --batch-size 200
```

Пример systemd timer (каждые 30 минут):

```ini
[Unit]
Description=Run RAG Qdrant sync every 30 minutes

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
```

Для применения systemd-конфигурации:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rag-qdrant-sync.timer
sudo systemctl status rag-qdrant-sync.timer
```

Сравнение двух фраз для быстрой оценки семантической/лексической близости (helper для ручных RAG-тестов):

```bash
python scripts/rag_sentence_similarity.py \
	--sentence-a "Ошибка UPOS: не проходит оплата" \
	--sentence-b "Оплата по карте не проходит на UPOS" \
	--threshold 0.70
```

JSON-вывод для автопроверок/скриптов:

```bash
python scripts/rag_sentence_similarity.py \
	--sentence-a "Ошибка UPOS: не проходит оплата" \
	--sentence-b "Оплата по карте не проходит на UPOS" \
	--json
```

Важно: `rag_directory_ingest.py` больше не выполняет генерацию эмбеддингов и не пишет в локальный векторный индекс. Векторная индексация выполняется только через `rag_vector_backfill.py`.

При сохранении метаданных в `rag_chunk_embeddings` сервис использует batched upsert и автоматический retry для временных ошибок InnoDB (`1205 lock wait timeout`, `1213 deadlock`) с коротким backoff.

Оценка объёма backfill без записи в индекс:

```bash
python scripts/rag_vector_backfill.py --dry-run --max-documents 200
```

Проверка без изменений в БД:

```bash
python scripts/rag_directory_ingest.py --directory /path/to/docs --dry-run
```

Скрипт можно запускать и из любой другой текущей директории, если указать к нему абсолютный путь.

Поведение синхронизации:
- сканирует директорию рекурсивно (можно отключить флагом `--no-recursive`),
- загружает новые/изменённые документы,
- с флагом `--force-update` повторно загружает и неизменённые документы,
- перед началом цикла пишет `Chunking конфигурация:` с активной стратегией (`html_strategy`, `plain_text_strategy`), выбранным `slicer`, `chunk_size`/`chunk_overlap` и статусом доступности LangChain splitter,
- для DB-операций (`delete`, `set_status`, `ingest`) при временных блокировках (`1205`/`1213`) автоматически выполняет retry с коротким backoff; Qdrant I/O вынесен за пределы MySQL-транзакций для минимизации времени удержания блокировок,
- для каждой директории синхронизации разрешён только один активный процесс `rag_directory_ingest.py` (PID lock-файл в системной temp-директории), повторный запуск для той же директории завершается с ошибкой,
- не выполняет vector upsert во время ingest; для обновления локального векторного индекса после синхронизации запускайте `rag_vector_backfill.py`,
- при загрузке формирует/обновляет `rag_document_summaries` для каждого документа,
- для directory-ingest может использовать отдельную модель summary через env `AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL` (`deepseek-chat` или `deepseek-reasoner`),
- удалённые из директории документы удаляет из RAG через purge (`hard delete`),
- без `--force-update` для одинакового `content_hash` использует существующий документ (дубликаты не плодятся).

## CRUD-команды администратора

- `#rag help` — показать справку по командам.
- `#rag list [active|archived|deleted|all] [limit]` — список документов.
- `#rag info <id>` — карточка документа.
- `#rag archive <id>` — перевести документ в `archived`.
- `#rag restore <id>` — вернуть документ в `active`.
- `#rag delete <id>` — мягкое удаление (`status=deleted`).
- `#rag purge <id>` — физическое удаление из БД.

## Переключение моделей DeepSeek (админ-интерфейс)

- Путь: `🛠️ Админ бота` → `⚙️ Настройки бота` → `🧠 AI модель`.
- Режимы:
	- `deepseek-chat` — быстрый режим.
	- `deepseek-reasoner` — усиленный reasoning-режим.
- Настройки разделены по сценариям:
	- модель для *классификации intent*;
	- модель для *ответов chat/RAG*.
- Дополнительно доступен тумблер `HTML splitter` для RAG HTML-документов.
- Переключение применяется в runtime (без перезапуска процесса бота).

## Логирование модели AI

- В runtime-логах `ai_router` для каждого запроса фиксируются:
	- провайдер (`provider`),
	- модель классификации (`model` в `AI classification`),
	- модель генерации ответа (`model` в `AI chat request`, если сработал chat/fallback).
- Для intent-классификации включён DeepSeek JSON Mode (`response_format={"type":"json_object"}`): модель обязана вернуть JSON-объект, а не текстовый ответ.
- Если классификатор вернул невалидный/неполный/non-JSON ответ, роутер выполняет retry и затем безопасно деградирует в `unknown/low_confidence` (без прямой отправки текста классификатора пользователю).
- Это упрощает диагностику маршрутизации и проверку активной модели после переключения в админ-панели.
- Ошибки в `ai_router` и RAG-обработчике логируются с явным типом исключения (`error_type`/`error_repr`); для временных сетевых сбоев LLM (timeout/request error) используется warning-ветка без длинного traceback, чтобы уменьшить шум логов.
- Для каждого retrieval-цикла RAG пишется диагностический многострочный блок `RAG retrieval:` в табличном формате (`metric` / `value`) с полями `mode`, `tokens`, `retrieval_tokens`, `prefilter_docs`, `prefilter_scope_docs`, `fallback_docs`, `lexical_hits`, `vector_hits`, `selected`, `selected_unique_docs`, `selected_top_docs`, `top_source`, а также `timings_ms.total/prefilter/lexical/vector/merge/summary_blocks`; длинные `source` автоматически сокращаются для читаемости.
- Перед `RAG retrieval:` пишется диагностический многострочный блок `RAG query preprocessing:` в табличном формате (`metric` / `value`) с полями `original_tokens`, `retrieval_tokens`, `stopwords_removed`, `pattern_stripped`, `hyde`, `hyde_lexical_augmented`, `strip_result` (строка после pattern-strip; слова с префиксом `#` сохраняются) и `preprocess_result` (итоговая строка после stopwords-фильтрации).
- `prefilter_docs` отражает только top-N документов этапа summary-prefilter, а `prefilter_scope_docs` — фактический размер области поиска после добавления fallback-документов.
- `selected` отражает число выбранных чанков, `selected_unique_docs` — число уникальных документов среди этих чанков, `selected_top_docs` — top уникальных `document_id` по порядку ранжирования.
- Для каждого retrieval-цикла RAG пишется блок `RAG priority evidence:` с двумя табличными секциями (`prefilter_top` и `selected_top`). В `prefilter_top` отображаются `rank`, `doc`, `summary`, `lexical`, `vec`, `vec_w` (взвешенный вклад `vec * AI_RAG_SUMMARY_VECTOR_WEIGHT`), `excerpt` (краткий фрагмент summary ~80 символов) и `source`; в `selected_top` — `rank`, `doc`, `chunk`, `fused`, `summary`, `origin` (`prefilter`/`fallback`/`global`), разложение lexical-компоненты (`lex_raw`, `lex_bonus`, `lex_total`, `lex_norm`), формула `hybrid=(lex_norm*lexical_weight)+(vector_score*vector_weight)`, `summary_bonus` и `source`; `lex_total` — исходный raw lexical score (с учётом summary-bonus на lexical-этапе), `lex_norm` — нормализованный lexical score в диапазоне `0..1` (min-max по пулу lexical-кандидатов); hybrid-формула использует `lex_norm`, чтобы lexical- и vector-компоненты были на одной шкале; `lex_bonus`/`summary_bonus` считаются из нормализованного summary-score документа в диапазоне `0..1` по относительной min-max схеме в текущем prefilter-пуле.
- Для каждого ingest документа пишется диагностическая строка `RAG chunking strategy:` с полями `file`, `format`, `strategy`, `slicer`, `chunk_size`, `chunk_overlap`, `chunks`, `html_splitter_enabled`, `langchain_splitter_supported`.
- При успешном vector upsert пишется строка `RAG vector upsert:` с полями `chunks` и `duration_ms`, где `duration_ms` — длительность операции upsert в миллисекундах.
- На старте бота выполняется прогрев lazy-зависимостей RAG; процесс логируется строками `RAG preload: start` и `RAG preload: done ...` (со статусом и `duration_ms`).
- Для remote Qdrant пишутся логи состояния backend: `Состояние remote Qdrant: UP|DOWN|COOLDOWN|DISABLED`, что упрощает диагностику доступности удалённого индекса и момента failover на local.
- Для технической записи `rag_chunk_embeddings` при временных DB-блокировках пишется предупреждение о retry c `errno`, номером попытки и размером батча.
- Если `deepseek-reasoner` вернул пустой `content` для chat/RAG-ответа, провайдер автоматически делает один повтор на `deepseek-chat` и пишет предупреждение в лог (это снижает риск «немого» ответа пользователю).
- Полный текст `prompt/response` также сохраняется в `ai_model_io_log` с маскировкой чувствительных данных (`email`, `телефон`, `ИНН`, `СНИЛС`).
- Для очистки логов старше 30 дней используйте `sql/ai_model_io_log_retention.sql` (подходит для запуска по cron).

## Переменные окружения

Важно: настройки `ai_router.settings` загружают `.env` с `load_dotenv(override=True)`, поэтому значения из `.env` имеют приоритет над ранее выставленными переменными процесса для AI\-параметров.

- `AI_RAG_ENABLED`
- `AI_RAG_MAX_FILE_SIZE_MB`
- `AI_RAG_MAX_CHUNKS_PER_DOC`
- `AI_RAG_CHUNK_SIZE`
- `AI_RAG_CHUNK_OVERLAP`
- `AI_RAG_TOP_K`
- `AI_RAG_MAX_CONTEXT_CHARS`
- `AI_RAG_SUMMARY_ENABLED`
- `AI_RAG_SUMMARY_INPUT_MAX_CHARS`
- `AI_RAG_SUMMARY_MAX_CHARS`
- `AI_RAG_PREFILTER_TOP_DOCS`
- `AI_RAG_PREFILTER_EXCLUDE_CERTIFICATION_FROM_COUNT`
- `AI_RAG_PROMPT_SUMMARY_DOCS`
- `AI_RAG_PROMPT_SUMMARIES_EXCLUDE_CERTIFICATION`
- `AI_RAG_SUMMARY_MATCH_PHRASE_WEIGHT`
- `AI_RAG_SUMMARY_MATCH_TOKEN_WEIGHT`
- `AI_RAG_SUMMARY_SCORE_CAP`
- `AI_RAG_SUMMARY_BONUS_WEIGHT`
- `AI_RAG_SUMMARY_POSTRANK_WEIGHT`
- `AI_RAG_SUMMARY_PREFILTER_FALLBACK_DOCS`
- `AI_RAG_SUMMARY_VECTOR_WEIGHT`
- `AI_RAG_LEXICAL_SCORER`
- `AI_RAG_BM25_K1`
- `AI_RAG_BM25_B`
- `AI_RAG_RU_NORMALIZATION_ENABLED`
- `AI_RAG_RU_NORMALIZATION_MODE`
- `AI_RAG_STOPWORDS_ENABLED`
- `AI_RAG_QUERY_PATTERN_STRIP_ENABLED`
- `AI_RAG_PREFILTER_IDF_DAMPEN_RATIO`
- `AI_RAG_PREFILTER_IDF_DAMPEN_FACTOR`
- `AI_RAG_HYDE_ENABLED`
- `AI_RAG_HYDE_MAX_CHARS`
- `AI_RAG_HYDE_CACHE_TTL_SECONDS`
- `AI_RAG_HYDE_LEXICAL_ENABLED`
- `AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL`
- `AI_RAG_CACHE_TTL_SECONDS`
- `AI_RAG_HTML_SPLITTER_ENABLED`
- `AI_RAG_VECTOR_ENABLED`
- `AI_RAG_HYBRID_ENABLED`
- `AI_RAG_VECTOR_LOCAL_MODE`
- `AI_RAG_VECTOR_REMOTE_URL`
- `AI_RAG_VECTOR_REMOTE_API_KEY`
- `AI_RAG_VECTOR_REMOTE_TIMEOUT_SECONDS`
- `AI_RAG_VECTOR_REMOTE_FAILURE_THRESHOLD`
- `AI_RAG_VECTOR_REMOTE_COOLDOWN_SECONDS`
- `AI_RAG_VECTOR_DB_PATH`
- `AI_RAG_VECTOR_COLLECTION`
- `AI_RAG_SUMMARY_VECTOR_COLLECTION`
- `AI_RAG_VECTOR_SYNC_COLLECTION`
- `AI_RAG_VECTOR_DISTANCE`
- `AI_RAG_VECTOR_TOP_K`
- `AI_RAG_SUMMARY_VECTOR_TOP_K`
- `AI_RAG_VECTOR_PREFETCH_K`
- `AI_RAG_VECTOR_EMBEDDING_MODEL`
- `AI_RAG_VECTOR_DEVICE`
- `AI_RAG_VECTOR_EMBEDDING_FP16`
- `AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE`
- `AI_RAG_VECTOR_EMBEDDING_MAX_CHARS`
- `AI_RAG_VECTOR_LEXICAL_WEIGHT`
- `AI_RAG_VECTOR_SEMANTIC_WEIGHT`

## Рекомендуемые профили окружения

### Профиль A — macOS (сбалансированный)

- `AI_RAG_VECTOR_ENABLED=1`
- `AI_RAG_HYBRID_ENABLED=1`
- `AI_RAG_VECTOR_EMBEDDING_MODEL=BAAI/bge-m3`
- `AI_RAG_VECTOR_EMBEDDING_FP16=0`
- `AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE=6`
- `AI_RAG_VECTOR_EMBEDDING_MAX_CHARS=5000`
- `AI_RAG_VECTOR_TOP_K=14`
- `AI_RAG_VECTOR_PREFETCH_K=42`
- `AI_RAG_TOP_K=8`
- `AI_RAG_VECTOR_LEXICAL_WEIGHT=0.20`
- `AI_RAG_VECTOR_SEMANTIC_WEIGHT=0.80`

### Профиль B — Windows (i5-3550 + NVIDIA T400, стабильный)

- `AI_RAG_VECTOR_ENABLED=1`
- `AI_RAG_HYBRID_ENABLED=1`
- `AI_RAG_VECTOR_EMBEDDING_MODEL=intfloat/multilingual-e5-small`
- `AI_RAG_VECTOR_DEVICE=auto`
- `AI_RAG_VECTOR_EMBEDDING_FP16=1`
- `AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE=2`
- `AI_RAG_VECTOR_EMBEDDING_MAX_CHARS=3500`
- `AI_RAG_VECTOR_TOP_K=10`
- `AI_RAG_VECTOR_PREFETCH_K=24`
- `AI_RAG_TOP_K=7`
- `AI_RAG_VECTOR_LEXICAL_WEIGHT=0.55`
- `AI_RAG_VECTOR_SEMANTIC_WEIGHT=0.45`

Примечания по Windows-профилю:
- Профиль ориентирован на CPU-стабильность и умеренную память.
- `AI_RAG_VECTOR_DEVICE=auto` выбирает `cuda`, если GPU доступен, и безопасно переключается на `cpu`, если CUDA недоступен.
- `AI_RAG_VECTOR_EMBEDDING_FP16=1` применяется только на `cuda`; при `cpu` или при ошибке инициализации автоматически включается безопасный fallback на FP32.
- Для принудительного запуска эмбеддингов на GPU можно указать `AI_RAG_VECTOR_DEVICE=cuda`.
- Если локальный Qdrant-путь (`AI_RAG_VECTOR_DB_PATH`) уже удерживается другим процессом, векторная индексация автоматически отключается только для текущего процесса, а ingest продолжает работу в lexical-режиме.
- Если задан `AI_RAG_VECTOR_REMOTE_URL`, backend работает в режиме remote-first; после `AI_RAG_VECTOR_REMOTE_FAILURE_THRESHOLD` ошибок подряд включается local fallback на `AI_RAG_VECTOR_REMOTE_COOLDOWN_SECONDS`.
- Если remote недоступен и local fallback выключен (`AI_RAG_VECTOR_LOCAL_MODE=0`), retrieval продолжает работу в lexical-режиме без падения пользовательского потока.
- Если доступен CUDA и есть запас по памяти, можно увеличить `AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE` до `3-4`.
- Если latency высокая, сначала уменьшайте `AI_RAG_VECTOR_PREFETCH_K`, затем `AI_RAG_VECTOR_TOP_K`.

Проверка CUDA на Windows (T400):

```powershell
nvidia-smi
```

Проверка PyTorch CUDA в активном окружении:

```powershell
python -c "import torch; print('cuda=', torch.cuda.is_available()); print('cuda_version=', torch.version.cuda); print('device=', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
```

Runtime-ключи в `bot_settings`:
- `ai_rag_html_splitter_enabled` (`1` — включён, `0` — выключен)
- `ai_rag_stopwords_enabled` (`1` — фильтрация стоп-слов, `0` — выключена)
- `ai_rag_query_pattern_strip_enabled` (`1` — снятие паттернов, `0` — выключено)
- `ai_rag_hyde_enabled` (`1` — HyDE генерация включена, `0` — выключена)
- `ai_rag_hyde_lexical_enabled` (`1` — HyDE дополняет BM25 lexical scoring, `0` — только vector)

## SQL-инициализация

```bash
mysql -u root -p sprint_db < sql/ai_rag_setup.sql
mysql -u root -p sprint_db < sql/ai_rag_document_summaries_setup.sql
mysql -u root -p sprint_db < sql/ai_rag_vector_setup.sql
mysql -u root -p sprint_db < sql/ai_rag_summary_vector_setup.sql
mysql -u root -p sprint_db < sql/ai_rag_certification_signals_setup.sql
# Для существующих БД без FULLTEXT-индекса summary_text:
mysql -u root -p sprint_db < sql/rag_document_summaries_fulltext_index.sql
```

## Ограничения текущего этапа

- Retrieval использует lexical scoring по summary+чанкам: режим `legacy` (coverage+density) или `bm25` (Okapi BM25) задаётся через `AI_RAG_LEXICAL_SCORER`; сначала выполняется prefilter документов по summary, затем rerank чанков с бонусом от summary-релевантности.
- Перед lexical scoring запрос проходит query preprocessing: стоп-слова (`что`, `такое`, `это`, `как` и ~40 других) удаляются, шаблонные вопросительные конструкции (например, «что такое X», «как работает Y») разбираются для извлечения предметной части. В summary prefilter дополнительно подавляются query-токены с высокой document frequency через IDF dampening.
- Токенизация query использует порог длины `>=3`, но дополнительно сохраняет короткие alnum-токены формата `буква+цифра`/`цифра+буква` (например, `X5`, `K2`) для корректного поиска по брендам и моделям без существенного роста шумовых коротких слов.
- HyDE (Hypothetical Document Embeddings): при включении (`AI_RAG_HYDE_ENABLED=1`) перед vector search LLM генерирует короткий гипотетический ответ на вопрос пользователя. Эмбеддинг этого текста используется вместо эмбеддинга исходного вопроса для chunk vector search и summary vector prefilter. Это устраняет разрыв «вопрос vs ответ» в embedding-пространстве. Дополнительно, если включён `AI_RAG_HYDE_LEXICAL_ENABLED=1` (по умолчанию), уникальные токены из HyDE-текста (после фильтрации стоп-слов) добавляются к query-токенам для BM25 lexical scoring — это расширяет лексическое покрытие и помогает BM25 находить чанки, содержащие ответную лексику. HyDE-текст кэшируется на `AI_RAG_HYDE_CACHE_TTL_SECONDS` (по умолчанию 300с). При ошибке LLM retrieval продолжается без HyDE (graceful degradation). HyDE добавляет ~1-2с latency на первый запрос из-за дополнительного LLM-вызова.
- Для русского языка доступна опциональная нормализация токенов (`AI_RAG_RU_NORMALIZATION_ENABLED=1`) с режимами `lemma_then_stem`, `lemma_only`, `stem_only`.
- Векторный режим требует пакет `qdrant-client`; для локальных эмбеддингов также необходим `sentence-transformers` и доступность embedding-модели на текущем хосте.
- Кэш хранится в памяти процесса и не шарится между инстансами.
- Нет UI для управления документами (архивация/удаление) — только загрузка.
- Metadata заголовков HTML сохраняется внутри текста чанка, так как текущая схема БД хранит только `chunk_text`.

## Рекомендуемый следующий шаг

- Добавить векторный индекс (FAISS/Qdrant) и эмбеддинги.
- Добавить админ-команды управления документами (`список`, `архив`, `удаление`).
- Добавить цитирование источников с точными ссылками на документ/чанк.
