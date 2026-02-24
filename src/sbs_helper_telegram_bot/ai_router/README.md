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

**Python 3.14+**: LangChain-splitters автоматически отключаются из-за несовместимости `pydantic.v1`; используется встроенный fallback.

### Retrieval

- Лексический scoring: покрытие токенов + бонус за плотность
- In-memory TTL-кэш с инвалидацией по `rag_corpus_version`
- Логирование запросов в `rag_query_log`

### Суммаризация документов

- AI-генерируемые саммари (4–8 предложений) для top-K документов
- Кэширование в `rag_document_summaries`
- Используются при формировании контекста RAG-ответа

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

# Daemon-режим
python scripts/rag_directory_ingest.py --directory <path> --daemon --interval-seconds 900

# Dry-run
python scripts/rag_directory_ingest.py --directory <path> --dry-run
```

Удалённые из директории файлы purge-ятся из RAG; изменённые — перезагружаются.

## Безопасная отправка

- Экранирование MarkdownV2 с fallback на plain text
- Плейсхолдер «⏳ Обрабатываю ваш запрос...» → edit → fallback новым сообщением
- Для RAG-запросов плейсхолдер обновляется на «⏳ Ожидаю ответа ИИ»
- Восстановление `ReplyKeyboardMarkup` после AI-ответа

## Логирование

- Результаты классификации → `ai_router_log` (intent, confidence, explain_code, response_time_ms)
- Профилирование маршрутизации: `classify_ms`, `db_log_ms`, `dispatch_ms`, `context_update_ms`
- RAG-запросы → `rag_query_log`

## Конфигурация

### Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|-------------|----------|
| `AI_PROVIDER` | `deepseek` | Провайдер LLM |
| `DEEPSEEK_API_KEY` | — | API-ключ |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | Базовый URL |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Модель по умолчанию |
| `AI_LLM_REQUEST_TIMEOUT` | `30` | Таймаут запроса (сек) |
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
| `AI_RAG_TOP_K` | `5` | Top-K чанков для ответа |
| `AI_RAG_MAX_CONTEXT_CHARS` | `7000` | Макс. контекст |
| `AI_RAG_CACHE_TTL_SECONDS` | `300` | TTL кэша |
| `AI_RAG_HTML_SPLITTER_ENABLED` | `1` | HTML header-aware splitter |

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
```

## База данных

### Таблицы

| Таблица | Описание |
|---------|----------|
| `ai_router_log` | Лог классификации (intent, confidence, response_time) |
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
