# RAG Operations Guide

Руководство охватывает полный жизненный цикл RAG-корпуса: первичную настройку, регулярные
обновления, восстановление после сбоев и рекомендации по улучшению.

---

## Оглавление

1. [Архитектура RAG-подсистемы](#1-архитектура)
2. [Первичная настройка](#2-первичная-настройка)
3. [Workflow: что делать когда что-то меняется](#3-workflow-обновлений)
4. [Сценарии восстановления](#4-восстановление)
5. [Справочник CLI (`rag_ops.py`)](#5-cli-rag_opspy)
6. [Справочник отдельных скриптов](#6-отдельные-скрипты)
7. [Рекомендации по улучшению](#7-рекомендации)

---

## 1. Архитектура

```
┌─────────────────────────────────────────────────────┐
│                   Источники данных                   │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │  Файлы/HTML/ │  │ Аттестацион- │  │ Telegram  │  │
│  │  PDF/MD/DOCX │  │ ные вопросы  │  │ (#rag)    │  │
│  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘  │
└─────────┼─────────────────┼────────────────┼─────────┘
          │                 │                │
          ▼                 ▼                ▼
┌─────────────────────────────────────────────────────┐
│               MySQL RAG-таблицы                     │
│                                                     │
│  rag_documents        — метаданные документов       │
│  rag_chunks           — текстовые чанки             │
│  rag_document_summaries — LLM/детерм. summary       │
│  rag_chunk_embeddings — метаданные embedding        │
│  rag_summary_embeddings — метаданные summary-embed  │
│  rag_document_signals — category/freshness сигналы  │
│  rag_corpus_version   — версия корпуса (инвалидация кэша)│
│  rag_query_log        — лог запросов                │
└─────────────────────────────────────────────────────┘
          │                                │
      MySQL                            MySQL
          │                                │
          ▼                                ▼
┌─────────────────┐               ┌────────────────────┐
│  Qdrant chunks  │               │  Qdrant summaries  │
│  (rag_chunks_v1)│               │  (rag_document_    │
│                 │               │   summaries_v1)    │
└────────┬────────┘               └────────┬───────────┘
         │                                 │
         └──────────────┬──────────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │  Retrieval      │
              │  (RagKnowledge  │
              │   Service)      │
              ├─────────────────┤
              │ Prefilter docs  │ ← lexical + summary vector
              │ Retrieve chunks │ ← hybrid lexical/vector
              │ Postrank        │ ← category/freshness signals
              └─────────────────┘
```

### Компоненты индексации

| Компонент | Где | Назначение |
|---|---|---|
| MySQL `rag_documents` | БД | Метаданные, статус, content\_hash |
| MySQL `rag_chunks` | БД | Сырые текстовые чанки |
| MySQL `rag_document_summaries` | БД | Summary документа (для prefilter) |
| Qdrant `rag_chunks_v1` | Qdrant | Векторы чанков (semantic search) |
| Qdrant `rag_document_summaries_v1` | Qdrant | Векторы summary (быстрый prefilter) |
| MySQL `rag_chunk_embeddings` | БД | Метаданные chunk-векторов (stale-flag) |
| MySQL `rag_summary_embeddings` | БД | Метаданные summary-векторов (stale-flag) |

### Правило: MySQL — источник истины; Qdrant — производный индекс

MySQL всегда обновляется первым. Qdrant можно полностью перестроить из MySQL через `backfill`.

---

## 2. Первичная настройка

### 2.1 Требования

- Python ≥ 3.12 (рекомендуется 3.12–3.14)
- MySQL 8.0+
- (опционально) Qdrant (local embedded или server)
- Зависимости: `pip install -r requirements.txt`

### 2.2 Шаги первичной настройки

#### Шаг 1 — Конфигурация

```bash
cp .env.example .env
# Заполните MYSQL_*, DEEPSEEK_API_KEY и (если нужно) AI_RAG_VECTOR_ENABLED=1
```

Минимальный набор RAG-переменных в `.env`:

```dotenv
# Базовый RAG (только lexical)
AI_RAG_ENABLED=1
AI_RAG_SUMMARY_ENABLED=1

# Добавить для векторного retrieval:
AI_RAG_VECTOR_ENABLED=1
AI_RAG_VECTOR_LOCAL_MODE=1           # локальный Qdrant (без сервера)
AI_RAG_VECTOR_DB_PATH=./data/qdrant

# Profiled настройки для быстрого старта (русский язык):
AI_RAG_LEXICAL_SCORER=bm25
AI_RAG_RU_NORMALIZATION_ENABLED=1
AI_RAG_RU_NORMALIZATION_MODE=lemma_then_stem
```

#### Шаг 2 — Применение SQL-миграций

```bash
# Интерактивно:
python scripts/rag_ops.py wizard
# → выбрать "3. Первичная настройка"

# Или non-interactive:
python scripts/rag_ops.py setup --apply-sql --yes
```

Применяются следующие SQL-файлы (в таком порядке):

| Файл | Назначение |
|---|---|
| `sql/ai_rag_setup.sql` | Основные RAG-таблицы (`rag_documents`, `rag_chunks`, `rag_corpus_version`, `rag_query_log`) |
| `sql/ai_rag_document_summaries_setup.sql` | Таблица `rag_document_summaries` |
| `sql/ai_rag_vector_setup.sql` | Таблица `rag_chunk_embeddings` |
| `sql/ai_rag_summary_vector_setup.sql` | Таблица `rag_summary_embeddings` |
| `sql/ai_rag_certification_signals_setup.sql` | Таблица `rag_document_signals` |
| `sql/rag_document_summaries_fulltext_index.sql` | FULLTEXT-индекс по `rag_document_summaries.summary_text` |
| `sql/ai_router_setup.sql` | Настройки модуля `ai_router` в `bot_settings` |
| `sql/ai_model_io_log_retention.sql` | Retention-задача для `ai_model_io_log` |

Если `mysql` CLI недоступен, примените файлы вручную:

```bash
mysql -u root -p sprint_db < sql/ai_rag_setup.sql
mysql -u root -p sprint_db < sql/ai_rag_document_summaries_setup.sql
# ... и т.д. по списку выше
```

#### Шаг 3 — Загрузка документов

```bash
# Загрузить директорию с документами:
python scripts/rag_ops.py update docs --directory /path/to/docs

# Загрузить вопросы аттестации:
python scripts/rag_ops.py update cert --upsert-vectors
```

#### Шаг 4 — Построение векторного индекса

```bash
# Перестроить оба индекса (чанки + summary):
python scripts/rag_ops.py update vectors --target both --batch-size 100
```

#### Шаг 4.1 — Предзагрузка embedding-модели для offline-старта

```bash
# При доступной сети: скачать/прогреть модель в локальный кэш
python scripts/rag_ops.py preload-embeddings

# Проверить, что модель доступна только из локального кэша (без сети)
python scripts/rag_ops.py preload-embeddings --offline-check
```

Рекомендуется задать постоянную директорию кэша через `AI_RAG_VECTOR_EMBEDDING_CACHE_DIR` (например, volume в контейнере), чтобы модель не перекачивалась после рестартов.
Для strict-режима офлайн-запуска используйте:
- `AI_RAG_VECTOR_EMBEDDING_OFFLINE=1`
- `AI_RAG_VECTOR_EMBEDDING_FAIL_FAST=1`

В таком режиме процесс завершится с ошибкой на старте, если модель отсутствует в локальном кэше.

На первом запуске embedding-модель загружается локально (модели `BAAI/bge-m3` ~2.5GB). Для Windows с NVIDIA T400 рекомендуется профиль `intfloat/multilingual-e5-small` (быстрее, меньше памяти).

#### Шаг 5 — Проверка

```bash
python scripts/rag_ops.py health
python scripts/rag_ops.py status
```

**Ожидаемый вывод `status` после первичной настройки:**

```
rag_documents (active)                   : 680
rag_documents (total)                    : 680
rag_chunks (total)                       : 980
rag_document_summaries                   : 680
rag_chunk_embeddings (indexed)           : 980   ← должен совпадать с chunks
rag_summary_embeddings (indexed)         : 680   ← должен совпадать с docs active
```

---

## 3. Workflow обновлений

### 3.1 Добавились / изменились документы в директории

```bash
python scripts/rag_ops.py update docs --directory /path/to/docs
```

Скрипт автоматически:
- определяет **новые файлы** (ingest)
- определяет **изменённые** (по `content_hash`) и переингестирует их
- **удаляет** из корпуса файлы, которых больше нет в директории

После ingest обновите векторный индекс:

```bash
python scripts/rag_ops.py update vectors --target both
```

| Ситуация | Флаги |
|---|---|
| Норма (только изменённые) | (без флагов) |
| Принудительно переиндексировать всё | `--force` |
| Изменился промпт summary | `--regenerate-summaries` |
| Сканировать только top-level | `--no-recursive` |
| Проверить без записи | `--dry-run` |

---

### 3.2 Изменились вопросы аттестации

```bash
# Только обновить изменившиеся (по content_hash):
python scripts/rag_ops.py update cert --upsert-vectors

# Принудительно переиндексировать все 275+ вопросов:
python scripts/rag_ops.py update cert --force --upsert-vectors
```

После `--upsert-vectors` дополнительно обновите summary-коллекцию:

```bash
python scripts/rag_ops.py update vectors --target summaries
```

---

### 3.3 Добавились новые вопросы аттестации (в БД `certification_questions`)

```bash
# Инкрементальный sync: инжестируются только новые + изменённые
python scripts/rag_ops.py update cert --upsert-vectors
```

Удалённые из `certification_questions` вопросы **автоматически purge-удаляются** из `rag_documents`.

---

### 3.4 Изменился промпт LLM-суммаризации

```bash
# Перегенерировать summary для документов директории:
python scripts/rag_ops.py update docs --directory /path --regenerate-summaries

# Перестроить summary-векторы:
python scripts/rag_ops.py update vectors --target summaries
```

---

### 3.5 Сменилась embedding-модель (`AI_RAG_VECTOR_EMBEDDING_MODEL`)

При смене модели все существующие векторы несовместимы. Требуется **полная пересборка**.

```bash
# 1. Удалить Qdrant-коллекции (если local mode):
rm -rf ./data/qdrant/collection/rag_chunks_v1
rm -rf ./data/qdrant/collection/rag_document_summaries_v1

# 2. Сбросить метаданные embedding в MySQL:
#    (вручную, или через скрипт — см. п. 4.2)

# 3. Перестроить оба индекса:
python scripts/rag_ops.py update vectors --target both --batch-size 50
```

---

### 3.6 Регулярное обслуживание (рекомендации)

| Частота | Действие |
|---|---|
| При каждом изменении вопросов | `update cert --upsert-vectors` |
| При изменении документов | `update docs -d PATH` + `update vectors` |
| Ежедневно или по расписанию | `update all -d PATH` |
| При проблемах с retrieval | `update vectors --target both --batch-size 100` (полный backfill) |
| После обновления нод Qdrant | `sync-remote` (remote→local) |

---

### 3.7 Полный update за один запуск

```bash
# Docs + certification + summary backfill:
python scripts/rag_ops.py update all --directory /path/to/docs

# С принудительным переоbновлением:
python scripts/rag_ops.py update all --directory /path/to/docs --force
```

---

## 4. Восстановление

### 4.1 Векторы устарели (vec=0 в prefilter-логах)

**Симптом:** в логах `RAG priority evidence: prefilter_top` видно `vec=0.000 vec_w=0.000`.

**Причина:** документы не проиндексированы в Qdrant (не запускался backfill или был запущен без `--upsert-vectors`).

**Решение:**

```bash
python scripts/rag_ops.py update vectors --target both
```

---

### 4.2 Qdrant-коллекция повреждена или потеряна (local mode)

```bash
# 1. Удалить локальные данные Qdrant:
rm -rf ./data/qdrant

# 2. Сбросить stale-флаги в MySQL:
mysql -u root -p sprint_db -e "DELETE FROM rag_chunk_embeddings;"
mysql -u root -p sprint_db -e "DELETE FROM rag_summary_embeddings;"

# 3. Пересоздать все векторы:
python scripts/rag_ops.py update vectors --target both --batch-size 50
```

---

### 4.3 Дублирование документов после interrupted sync

```bash
# Проверить дубликаты:
mysql -u root -p sprint_db -e \
  "SELECT source_url, COUNT(*) c FROM rag_documents GROUP BY source_url HAVING c > 1;"

# Purge конкретного документа через #rag-команды в Telegram:
#rag purge <document_id>
```

---

### 4.4 Certification Q/A полностью перезагрузить с нуля

```bash
# Hard-delete всех существующих certification документов и переингест:
python scripts/rag_ops.py update cert --force --upsert-vectors
python scripts/rag_ops.py update vectors --target summaries
```

---

### 4.5 Qdrant remote недоступен, бот работает на local fallback

```bash
# Проверить состояние:
python scripts/rag_ops.py health

# Принудительная синхронизация remote→local, когда remote снова доступен:
python scripts/rag_ops.py sync-remote --batch-size 200
```

---

### 4.6 Lock-файл заблокировал директорию (завис rag_directory_ingest.py)

```bash
# Найти и удалить stale lock-файл:
ls /tmp/rag_directory_ingest_*.lock
rm /tmp/rag_directory_ingest_<hash>.lock
```

---

## 5. CLI `rag_ops.py`

### Запуск

```bash
python scripts/rag_ops.py <command> [options]
# Или в интерактивном режиме:
python scripts/rag_ops.py wizard
```

### Команды

#### `health`

```bash
python scripts/rag_ops.py health
```

Проверяет:
- подключение к MySQL и наличие RAG-таблиц
- доступность Qdrant (если `AI_RAG_VECTOR_ENABLED=1`)

#### `status`

```bash
python scripts/rag_ops.py status
```

Выводит счётчики документов, чанков, эмбеддингов и разбивку по `source_type`.

#### `setup`

```bash
python scripts/rag_ops.py setup [--apply-sql] [--yes]
```

| Флаг | Описание |
|---|---|
| `--apply-sql` | Применить SQL без вопросов |
| `--yes` / `-y` | Подтверждать все шаги автоматически |

Примечание: команда читает MySQL-параметры из переменных окружения `MYSQL_*`
через `src.common.constants.database`.

#### `update docs`

```bash
python scripts/rag_ops.py update docs -d PATH [options]
```

| Флаг | Описание |
|---|---|
| `-d`, `--directory` | Путь к директории документов (обязательный) |
| `--force` | Переиндексировать все файлы, даже с одинаковым hash |
| `--daemon` | Запустить в режиме непрерывной синхронизации |
| `--interval-seconds N` | Интервал daemon-цикла (по умолчанию 900 с) |
| `--dry-run` | Показать изменения без записи |
| `--regenerate-summaries` | Перегенерировать summary (при смене промпта) |
| `--no-recursive` | Не сканировать поддиректории |

#### `update cert`

```bash
python scripts/rag_ops.py update cert [options]
```

| Флаг | Описание |
|---|---|
| `--force` | Переиндексировать все вопросы (даже с одинаковым hash) |
| `--upsert-vectors` | Сразу записать эмбеддинги в Qdrant |
| `--uploaded-by ID` | ID пользователя для аудит-лога |

#### `update vectors`

```bash
python scripts/rag_ops.py update vectors [options]
```

| Флаг | Описание |
|---|---|
| `--target` | `chunks`, `summaries` или `both` (по умолчанию `both`) |
| `--batch-size N` | Документов за батч (по умолчанию 100) |
| `--dry-run` | Только подсчитать — без записи в индекс |
| `--max-documents N` | Ограничить число документов |

#### `update all`

```bash
python scripts/rag_ops.py update all [-d PATH] [--force] [--batch-size N]
```

Выполняет последовательно: sync docs → sync cert → backfill summaries.

#### `sync-remote`

```bash
python scripts/rag_ops.py sync-remote [options]
```

| Флаг | Описание |
|---|---|
| `--dry-run` | Без записи/удаления |
| `--batch-size N` | Размер батча (по умолчанию 200) |
| `--max-points N` | Ограничить число точек |
| `--delete-missing` | Удалять точки, отсутствующие в remote |

#### `wizard`

```bash
python scripts/rag_ops.py wizard
```

Интерактивное меню из 8 пунктов. Работает в любом терминале. Нажмите **Ctrl+C** для выхода.

---

## 6. Отдельные скрипты

### `scripts/rag_directory_ingest.py`

Синхронизация директории файлов (PDF, DOCX, TXT, MD, HTML).

```bash
python scripts/rag_directory_ingest.py -d PATH [--force-update] [--daemon] \
  [--interval-seconds N] [--dry-run] [--regenerate-summaries] [--no-recursive] [--info] [-v]
```

**Флаг `--info`** — выводит подробную информацию о текущем режиме ingestion (версии LangChain, активный сплиттер, сепараторы, параметры чанкинга, статистика файлов в директории) и завершает работу без выполнения ingestion.

**Важно:** не выполняет inline vector upsert — после запуска необходим `rag_vector_backfill.py`.

---

### `scripts/rag_certification_sync.py`

Синхронизация вопросов аттестации (из `certification_questions` → `rag_documents`).

```bash
python scripts/rag_certification_sync.py \
  [--uploaded-by ID] [--upsert-vectors] [--force-update]
```

---

### `scripts/rag_vector_backfill.py`

Пакетная векторная индексация.

```bash
python scripts/rag_vector_backfill.py \
  --target [chunks|summaries|both] \
  --batch-size N \
  [--dry-run] [--max-documents N]
```

---

### `scripts/rag_qdrant_sync_remote_to_local.py`

Синхронизация Qdrant remote → local (best-effort).

```bash
python scripts/rag_qdrant_sync_remote_to_local.py \
  [--dry-run] [--batch-size N] [--max-points N] [--delete-missing]
```

---

### `scripts/rag_sentence_similarity.py`

Сравнение семантической/лексической близости двух фраз (для ручной проверки RAG).

**Одноразовый режим** (legacy):

```bash
python scripts/rag_sentence_similarity.py \
  --sentence-a "Ошибка UPOS: не проходит оплата" \
  --sentence-b "Оплата по карте не проходит на UPOS" \
  --threshold 0.70 [--json]
```

**Интерактивный REPL** (`-i` / `--interactive`):

```bash
# Запуск пустого REPL
python scripts/rag_sentence_similarity.py -i

# С предустановленными предложениями
python scripts/rag_sentence_similarity.py -i \
  --sentence-a "Ошибка UPOS" --sentence-b "Сбой терминала"
```

Основные возможности REPL:

| Команда | Описание |
|---------|----------|
| `a <текст>` / `b <текст>` | Задать/изменить одно предложение |
| `compare` / `c` | Сравнить текущие предложения |
| `swap` | Поменять A и B местами |
| `threshold <0‥1>` | Изменить порог без повторного ввода |
| `metrics [semantic lexical sequence \| all]` | Выбрать метрики для combined score |
| `history` / `diff N M` | Просмотреть историю / сравнить два результата |
| `export json <файл>` / `export csv <файл>` | Экспортировать историю |
| `status` | Проверить статус embedding-модели |

---

## 7. Рекомендации

### 7.1 Отделить backfill от ingest (уже реализовано ✓)

Текущий дизайн правильный: ingest записывает в MySQL, backfill строит Qdrant. Это исключает конкурирующий I/O при массовой синхронизации.

---

### 7.2 Daemon-режим + автоматический backfill

Сейчас `rag_directory_ingest.py --daemon` не запускает backfill автоматически после каждого цикла. Вариант — добавить флаг `--auto-backfill`, который запускает `rag_vector_backfill.py` по завершении каждого ingest-цикла.

```bash
# В ожидаемом виде (не реализовано):
python scripts/rag_directory_ingest.py -d PATH --daemon --auto-backfill
```

---

### 7.3 Автоматический `certification sync` по расписанию

К текущему cron-примеру для Qdrant sync стоит добавить аналогичную запись для cert sync:

```cron
# Каждую ночь в 02:00 — пересинхронизировать вопросы аттестации
0 2 * * * cd /path/to/bot && .venv/bin/python scripts/rag_ops.py update cert --upsert-vectors >> /var/log/rag_cert_sync.log 2>&1
```

---

### 7.4 Мониторинг состояния индекса

Добавить Telegram-команду `#rag health` для администраторов (аналог `rag_ops.py status`), выводящую текущие счётчики прямо в чат.

---

### 7.5 Версионирование embedding-коллекций

Имена коллекций `rag_chunks_v1` и `rag_document_summaries_v1` содержат версию. При смене модели достаточно указать новое имя коллекции в `.env` (`AI_RAG_VECTOR_COLLECTION`, `AI_RAG_SUMMARY_VECTOR_COLLECTION`) и запустить backfill — без удаления старой коллекции (rollback возможен).

---

### 7.6 stale-флаги в `rag_chunk_embeddings` и `rag_summary_embeddings`

Эти таблицы хранят статус `stale` для точек, которые нужно переиндексировать. Запускать backfill только по stale-записям快 быстрее полного backfill:

```bash
# Не реализовано, но логика стоит добавить:
python scripts/rag_ops.py update vectors --stale-only
```

---

### 7.7 Snapshotting Qdrant для DR

Если используется Qdrant server, настройте периодическое создание snapshot:

```bash
# REST API Qdrant
curl -X POST "http://localhost:6333/collections/rag_chunks_v1/snapshots"
```

Для local mode достаточно резервного копирования директории `AI_RAG_VECTOR_DB_PATH`.

---

### 7.8 Тестирование качества retrieval

Используйте `rag_sentence_similarity.py` для baseline-проверок перед и после обновления корпуса:

```bash
# Создать CSV со строками: sentence_a, sentence_b, expected_similarity
# И прогнать по паре фраз:
python scripts/rag_sentence_similarity.py \
  --sentence-a "Что делать при ошибке E_TIMEOUT?" \
  --sentence-b "Превышение времени ожидания на терминале" \
  --threshold 0.65 --json
```

---

### 7.9 Многопоточный backfill

Текущий backfill однопоточный (sequential батчи). При большом корпусе (>5000 документов) можно ускорить через параллельный enqueue батчей в `ThreadPoolExecutor`. Это поле для будущего улучшения.

---

*Документ обновлён: 2026-02-27. Соответствует версии 0.2.22.*
