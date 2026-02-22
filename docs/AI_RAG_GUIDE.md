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
- На Python `3.14+` импорт LangChain splitters отключается автоматически (ограничение `pydantic.v1`), поэтому всегда используется fallback chunking.
- Таблицы БД: `rag_documents`, `rag_chunks`, `rag_corpus_version`, `rag_query_log`.
- TTL-кэш ответов RAG в памяти процесса.
- UX-статус для RAG: после классификации запроса как `rag_qa` бот меняет плейсхолдер с «Обрабатываю ваш запрос» на «Ожидаю ответа ИИ» до получения финального ответа.

## Как загрузить документ

1. Администратор отправляет в чат бота документ.
2. В подписи к документу указывает `#rag` в начале подписи.
3. Бот подтверждает успешную загрузку, ID документа и число чанков.

## Как синхронизировать директорию документов

On-demand запуск:

```bash
python scripts/rag_directory_ingest.py --directory /path/to/docs
```

Daemon-режим (регулярная синхронизация):

```bash
python scripts/rag_directory_ingest.py --directory /path/to/docs --daemon --interval-seconds 900
```

Проверка без изменений в БД:

```bash
python scripts/rag_directory_ingest.py --directory /path/to/docs --dry-run
```

Поведение синхронизации:
- сканирует директорию рекурсивно (можно отключить флагом `--no-recursive`),
- загружает новые/изменённые документы,
- удалённые из директории документы удаляет из RAG через purge (`hard delete`),
- для одинакового `content_hash` использует существующий документ (дубликаты не плодятся).

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

## Переменные окружения

- `AI_RAG_ENABLED`
- `AI_RAG_MAX_FILE_SIZE_MB`
- `AI_RAG_MAX_CHUNKS_PER_DOC`
- `AI_RAG_CHUNK_SIZE`
- `AI_RAG_CHUNK_OVERLAP`
- `AI_RAG_TOP_K`
- `AI_RAG_MAX_CONTEXT_CHARS`
- `AI_RAG_CACHE_TTL_SECONDS`
- `AI_RAG_HTML_SPLITTER_ENABLED`

Runtime-ключ в `bot_settings`:
- `ai_rag_html_splitter_enabled` (`1` — включён, `0` — выключен)

## SQL-инициализация

```bash
mysql -u root -p sprint_db < scripts/ai_rag_setup.sql
```

## Ограничения текущего этапа

- Retrieval использует lexical scoring по чанкам (без векторной БД).
- Кэш хранится в памяти процесса и не шарится между инстансами.
- Нет UI для управления документами (архивация/удаление) — только загрузка.
- Metadata заголовков HTML сохраняется внутри текста чанка, так как текущая схема БД хранит только `chunk_text`.

## Рекомендуемый следующий шаг

- Добавить векторный индекс (FAISS/Qdrant) и эмбеддинги.
- Добавить админ-команды управления документами (`список`, `архив`, `удаление`).
- Добавить цитирование источников с точными ссылками на документ/чанк.
