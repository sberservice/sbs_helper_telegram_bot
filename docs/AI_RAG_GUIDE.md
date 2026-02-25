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
- Поддерживаемые форматы: `PDF`, `DOCX`, `TXT`, `MD`, `HTML`.
- Для `HTML` используется `HTMLHeaderTextSplitter` (если доступен в окружении), чтобы учитывать структуру заголовков `h1-h6`.
- Для `HTML` предусмотрен безопасный fallback на очищенный plain-text chunking, если header-splitter недоступен или не вернул чанков.
- Для `HTML` доступен runtime-переключатель `ai_rag_html_splitter_enabled` в админ-настройках AI (можно принудительно выключить header-splitter).
- На Python `3.14+` LangChain splitters работают корректно (предупреждения `pydantic.v1` подавляются); fallback chunking включается только если импорт splitter-а завершился ошибкой.
- Таблицы БД: `rag_documents`, `rag_chunks`, `rag_corpus_version`, `rag_query_log`.
- Таблица полного AI I/O логирования: `ai_model_io_log` (prompt/response всех LLM-вызовов, включая RAG).
- TTL-кэш ответов RAG в памяти процесса.
- Summary-aware retrieval: prefilter документов по `rag_document_summaries`, hybrid rerank чанков с учётом релевантности summary и prompt enrichment top-summary блоками.
- Опциональный локальный векторный retrieval (Qdrant local mode + локальная embedding-модель) с hybrid-слиянием lexical/vector кандидатов.
- UX-статус для RAG: после классификации запроса как `rag_qa` бот меняет плейсхолдер с «Обрабатываю ваш запрос» на «Ожидаю ответа ИИ» до получения финального ответа.
- Форматирование ответа `rag_qa` для Telegram MarkdownV2: сохраняются списки, `inline code`, жирный текст (`**...**` → Telegram-совместимый `*...*`), неподдерживаемая markdown-разметка экранируется.
- Длинные RAG-ответы автоматически делятся на несколько сообщений, чтобы не упираться в лимит длины Telegram-сообщения.

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
python scripts/rag_vector_backfill.py --batch-size 100
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
- для DB-операций (`delete`, `set_status`, `ingest`) при временных блокировках (`1205`/`1213`) автоматически выполняет retry с коротким backoff; Qdrant I/O вынесен за пределы MySQL-транзакций для минимизации времени удержания блокировок,
- для каждой директории синхронизации разрешён только один активный процесс `rag_directory_ingest.py` (PID lock-файл в системной temp-директории), повторный запуск для той же директории завершается с ошибкой,
- не выполняет vector upsert во время ingest; для обновления локального векторного индекса после синхронизации запускайте `rag_vector_backfill.py`,
- при загрузке формирует/обновляет `rag_document_summaries` для каждого документа,
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
- Это упрощает диагностику маршрутизации и проверку активной модели после переключения в админ-панели.
- Ошибки в `ai_router` и RAG-обработчике логируются с traceback и явным типом исключения (`error_type`/`error_repr`), поэтому даже при пустом тексте исключения причина не теряется.
- Для каждого retrieval-цикла RAG пишется диагностическая строка `RAG retrieval:` с полями `mode`, `tokens`, `prefilter_docs`, `lexical_hits`, `vector_hits`, `selected`, `top_source`.
- Для технической записи `rag_chunk_embeddings` при временных DB-блокировках пишется предупреждение о retry c `errno`, номером попытки и размером батча.
- Если `deepseek-reasoner` вернул пустой `content` для chat/RAG-ответа, провайдер автоматически делает один повтор на `deepseek-chat` и пишет предупреждение в лог (это снижает риск «немого» ответа пользователю).
- Полный текст `prompt/response` также сохраняется в `ai_model_io_log` с маскировкой чувствительных данных (`email`, `телефон`, `ИНН`, `СНИЛС`).
- Для очистки логов старше 30 дней используйте `scripts/ai_model_io_log_retention.sql` (подходит для запуска по cron).

## Переменные окружения

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
- `AI_RAG_PROMPT_SUMMARY_DOCS`
- `AI_RAG_CACHE_TTL_SECONDS`
- `AI_RAG_HTML_SPLITTER_ENABLED`
- `AI_RAG_VECTOR_ENABLED`
- `AI_RAG_HYBRID_ENABLED`
- `AI_RAG_VECTOR_LOCAL_MODE`
- `AI_RAG_VECTOR_DB_PATH`
- `AI_RAG_VECTOR_COLLECTION`
- `AI_RAG_VECTOR_DISTANCE`
- `AI_RAG_VECTOR_TOP_K`
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
- `AI_RAG_VECTOR_LEXICAL_WEIGHT=0.40`
- `AI_RAG_VECTOR_SEMANTIC_WEIGHT=0.60`

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

Runtime-ключ в `bot_settings`:
- `ai_rag_html_splitter_enabled` (`1` — включён, `0` — выключен)

## SQL-инициализация

```bash
mysql -u root -p sprint_db < scripts/ai_rag_setup.sql
mysql -u root -p sprint_db < scripts/ai_rag_document_summaries_setup.sql
mysql -u root -p sprint_db < scripts/ai_rag_vector_setup.sql
# Для существующих БД без FULLTEXT-индекса summary_text:
mysql -u root -p sprint_db < scripts/rag_document_summaries_fulltext_index.sql
```

## Ограничения текущего этапа

- Retrieval использует lexical scoring по summary+чанкам (без векторной БД): сначала prefilter документов по summary, затем rerank чанков с бонусом от summary-релевантности.
- Векторный режим требует локально установленные пакеты `qdrant-client` и `sentence-transformers`, а также доступность embedding-модели на текущем хосте.
- Кэш хранится в памяти процесса и не шарится между инстансами.
- Нет UI для управления документами (архивация/удаление) — только загрузка.
- Metadata заголовков HTML сохраняется внутри текста чанка, так как текущая схема БД хранит только `chunk_text`.

## Рекомендуемый следующий шаг

- Добавить векторный индекс (FAISS/Qdrant) и эмбеддинги.
- Добавить админ-команды управления документами (`список`, `архив`, `удаление`).
- Добавить цитирование источников с точными ссылками на документ/чанк.
