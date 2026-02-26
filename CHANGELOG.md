# Changelog

Все заметные изменения проекта фиксируются в этом файле.

Формат основан на Keep a Changelog,
а версияция следует Semantic Versioning.

## [0.1.75] - 2026-02-25

### Added
- Добавлен поэтапный прогресс-плейсхолдер для RAG-запросов: после общего статуса ожидания теперь отображаются промежуточные этапы prefilter документов и отправки augmented payload в LLM.
- Добавлен единый резолвер AI-сообщений по ключам (`get_ai_message_by_key`) с безопасным fallback, чтобы подготовить переход на динамические тексты из БД без изменения бизнес-логики.
- Добавлены тесты `tests/test_ai_messages.py` и расширены проверки в `tests/test_ai_placeholder.py`, `tests/test_ai_router.py`, `tests/test_rag_service.py` для новых этапов прогресса и поведения cache-hit.

### Changed
- В `src/sbs_helper_telegram_bot/telegram_bot/telegram_bot.py` логика плейсхолдера переведена на ключи сообщений и callback прогресса, включая сценарий `general_chat -> reroute -> rag_qa`.
- В `src/sbs_helper_telegram_bot/ai_router/intent_router.py`, `intent_handlers.py` и `rag_service.py` добавлен опциональный канал `on_progress` для сквозной передачи этапов RAG до Telegram-слоя.
- Обновлена документация модуля AI в `src/sbs_helper_telegram_bot/ai_router/README.md` с описанием поэтапного UX плейсхолдера и модели резолва текстов.

## [0.1.74] - 2026-02-25

### Added
- Добавлена helper CLI-утилита `scripts/rag_sentence_similarity.py` (ядро в `src/sbs_helper_telegram_bot/ai_router/rag_similarity.py`) для сравнения двух предложений при ручном тестировании RAG: считает semantic (embeddings/cosine), lexical (Jaccard), sequence similarity и итоговый `combined_similarity`, поддерживает `--threshold` и `--json`.
- Добавлены тесты `tests/test_rag_sentence_similarity.py` на расчёт метрик, fallback без эмбеддингов и JSON/валидацию CLI-ввода.

### Changed
- Обновлена документация по утилитам в `README.md` и RAG-гайд в `docs/AI_RAG_GUIDE.md` с примерами запуска `rag_sentence_similarity.py`.

## [0.1.73] - 2026-02-25

### Added
- Добавлены новые env-настройки в `src/sbs_helper_telegram_bot/ai_router/settings.py` для параметров генерации LLM: `AI_LLM_CLASSIFICATION_TEMPERATURE`, `AI_LLM_CLASSIFICATION_MAX_TOKENS`, `AI_LLM_CHAT_TEMPERATURE`, `AI_LLM_CHAT_MAX_TOKENS`.
- Добавлены регрессионные тесты в `tests/test_llm_provider.py`, проверяющие, что `classify` и `chat` используют `temperature/max_tokens` из `ai_router.settings`.

### Changed
- В `src/sbs_helper_telegram_bot/ai_router/llm_provider.py` убраны захардкоженные значения `temperature/max_tokens` для `classify` и `chat`; теперь используются конфигурируемые параметры из `settings`.
- Обновлена таблица конфигурации в `src/sbs_helper_telegram_bot/ai_router/README.md` с описанием новых переменных окружения.

## [0.1.72] - 2026-02-25

### Added
- Добавлен регрессионный тест в `tests/test_rag_service.py`, проверяющий, что лог `RAG vector upsert:` включает длительность операции в поле `duration_ms`.

### Changed
- В `src/sbs_helper_telegram_bot/ai_router/rag_service.py` расширено логирование успешного vector upsert: теперь строка `RAG vector upsert:` содержит не только `chunks`, но и `duration_ms`.
- Обновлена документация по RAG-логированию в `docs/AI_RAG_GUIDE.md` и `src/sbs_helper_telegram_bot/ai_router/README.md` с описанием поля `duration_ms`.

## [0.1.71] - 2026-02-25

### Changed
- В `src/sbs_helper_telegram_bot/ai_router/rag_service.py` HTML-чанкинг в RAG переведён на приоритетный `HTMLSemanticPreservingSplitter` с совместимым fallback на `HTMLHeaderTextSplitter`, а при недоступности splitter-ов сохраняется безопасный fallback на plain-text chunking.
- Обновлены диагностические названия стратегий HTML-чанкинга (`html_semantic_preserving_splitter_with_fallback` / `html_semantic_preserving_splitter`) для более точного runtime-логирования.
- Актуализирована документация в `docs/AI_RAG_GUIDE.md` и `src/sbs_helper_telegram_bot/ai_router/README.md` под новую стратегию HTML-обработки.

### Added
- Добавлен регрессионный тест в `tests/test_rag_service.py`, проверяющий совместимость инициализации HTML splitter-а со старой сигнатурой конструктора (без `max_chunk_size/chunk_overlap`).

## [0.1.66] - 2026-02-25

## [0.1.70] - 2026-02-25

### Changed
- В диагностическую строку `RAG retrieval:` в `src/sbs_helper_telegram_bot/ai_router/rag_service.py` добавлено поле `lexical_scorer`, показывающее активный режим lexical ранжирования (`legacy` или `bm25`) для каждого retrieval-цикла.

### Added
- Добавлена регрессионная проверка в `tests/test_rag_service.py`, фиксирующая наличие `lexical_scorer` в формате retrieval-лога.

## [0.1.69] - 2026-02-25

### Added
- В `.env.example` добавлен готовый профиль `lexical BM25 для русского языка` с параметрами `AI_RAG_LEXICAL_SCORER`, `AI_RAG_BM25_K1`, `AI_RAG_BM25_B`, `AI_RAG_RU_NORMALIZATION_ENABLED`, `AI_RAG_RU_NORMALIZATION_MODE`.

### Changed
- Упрощён старт BM25-конфигурации: теперь достаточно раскомментировать блок пресета в `.env.example` и перезапустить бота.

## [0.1.68] - 2026-02-25

### Added
- Добавлены новые env/runtime-настройки lexical retrieval в `src/sbs_helper_telegram_bot/ai_router/settings.py`: `AI_RAG_LEXICAL_SCORER` (`legacy|bm25`), `AI_RAG_BM25_K1`, `AI_RAG_BM25_B`, `AI_RAG_RU_NORMALIZATION_ENABLED`, `AI_RAG_RU_NORMALIZATION_MODE` и безопасные getter-функции для feature-flag переключения.
- Добавлены регрессионные тесты в `tests/test_rag_service.py` для BM25-ранжирования чанков, BM25-prefilter по summary, RU-нормализации токенов и базовой проверки BM25-score.

### Changed
- В `src/sbs_helper_telegram_bot/ai_router/rag_service.py` lexical retrieval для чанков и summary-prefilter теперь поддерживает режим `bm25` (Python BM25) с fallback на `legacy`-скoring.
- Для русского lexical-пайплайна добавлена опциональная нормализация токенов (лемматизация + стемминг) с in-memory кэшированием нормализованных форм.
- Обновлена документация по retrieval-конфигурации в `docs/AI_RAG_GUIDE.md` и `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Устранена ограниченность lexical-поиска на русских словоформах: при включённой RU-нормализации повышается recall для морфологических вариантов запроса/документа.

## [0.1.67] - 2026-02-25

### Added
- Добавлен регрессионный тест в `tests/test_rag_service.py`, проверяющий min-max нормализацию `summary_score` в prefilter-пуле и передачу `normalized_summary_scores` в lexical retrieval.

### Changed
- В `src/sbs_helper_telegram_bot/ai_router/rag_service.py` summary-бонусы для чанков и postrank теперь используют относительную нормализацию `summary_score` в диапазон `0..1` по текущему prefilter-пулу (`min-max`) перед применением весов.
- Диагностический блок `RAG priority evidence -> selected_top` синхронизирован с новой схемой расчёта `lex_bonus`/`summary_bonus`.
- Обновлены пояснения в `src/sbs_helper_telegram_bot/ai_router/settings.py`, `docs/AI_RAG_GUIDE.md` и `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Устранена ситуация, когда документы с разными high `summary_score` получали одинаковый бонус из-за cap-clamp; теперь бонус дифференцируется в пределах текущего retrieval-пула.

## [0.1.66] - 2026-02-25

### Added
- Добавлен регрессионный тест в `tests/test_rag_service.py`, проверяющий нормализацию `summary_score` документа в диапазон `0..1` перед применением `lexical` и `postrank` бонусов.

### Changed
- В `src/sbs_helper_telegram_bot/ai_router/rag_service.py` формулы `_summary_score_bonus()` и `_summary_postrank_bonus()` переведены на нормализованный `summary_score`: теперь бонусы рассчитываются как `normalize(summary_score, cap) * weight`, где `normalize = min(score, cap) / cap`.
- Уточнены описания конфигурации и лог-диагностики в `src/sbs_helper_telegram_bot/ai_router/settings.py`, `docs/AI_RAG_GUIDE.md` и `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Снижено доминирование document-level summary в chunk ranking: теперь вклад summary-бонуса ограничен диапазоном `0..weight`, что делает итоговый `fused` более сопоставимым с lexical/vector компонентами.

## [0.1.65] - 2026-02-25

### Added
- Добавлены регрессионные проверки в `tests/test_rag_service.py` для поля `chunk` в `selected_top` и для передачи `chunk_index` из lexical retrieval.

### Changed
- Расширено логирование `RAG priority evidence` в `src/sbs_helper_telegram_bot/ai_router/rag_service.py`: в строках `selected_top` после `doc` теперь выводится индекс чанка `chunk`.
- Обновлены описания диагностического формата в `docs/AI_RAG_GUIDE.md` и `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Устранена неоднозначность при разборе retrieval-логов: теперь видно, какой именно чанк документа попал в финальный top.

## [0.1.63] - 2026-02-25

## [0.1.64] - 2026-02-25

### Added
- Добавлен регрессионный тест в `tests/test_rag_service.py`, проверяющий детализацию lexical-компоненты в `selected_top` (`lex_raw`, `lex_bonus`, `lex_total`) и формулу `hybrid=(lex_total*lexical_weight)+(vector_score*vector_weight)`.

### Changed
- Улучшено логирование `RAG priority evidence` в `src/sbs_helper_telegram_bot/ai_router/rag_service.py`: в `selected_top` lexical-часть теперь декомпозируется на `lex_raw` (базовый chunk lexical), `lex_bonus` (summary bonus на lexical-этапе) и `lex_total` (итог lexical-компоненты до hybrid-взвешивания).
- Обновлена документация по форматам retrieval-логов: `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Устранена неоднозначность интерпретации `lexical_score` в `selected_top`: теперь явно видно, почему lexical-компонента может превышать диапазон `0..1`.

## [0.1.63] - 2026-02-25

### Added
- Добавлены регрессионные тесты в `tests/test_rag_service.py` для проверки разложения `selected_top` на weighted-компоненты (`hybrid=(lexical_score*lexical_weight)+(vector_score*vector_weight)`) и для проверки сборки lexical/vector-компонент по dedup-ключу merge.

### Changed
- Расширено логирование `RAG priority evidence` в `src/sbs_helper_telegram_bot/ai_router/rag_service.py`: в `selected_top` теперь выводится не только `fused`, но и детальный вклад lexical/vector в формате `hybrid=(lexical_score*lexical_weight)+(vector_score*vector_weight)` плюс `summary_bonus`.
- Обновлена документация по диагностике retrieval: `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Устранена непрозрачность расчёта `fused` в runtime-логах RAG: теперь по каждой строке `selected_top` видно, как сформирован базовый hybrid-score до добавления summary-бонуса.

## [0.1.62] - 2026-02-25

### Added
- Добавлен регрессионный тест в `tests/test_rag_service.py`, проверяющий новые retrieval-диагностики `selected_unique_docs` и `selected_top_docs`, а также helper для снимка top уникальных `document_id`.

### Changed
- Расширена строка `RAG retrieval:` в `src/sbs_helper_telegram_bot/ai_router/rag_service.py`: добавлены поля `selected_unique_docs` (количество уникальных документов в финальных чанках) и `selected_top_docs` (top уникальных `document_id` по порядку ранжирования).
- Обновлена документация по диагностике retrieval: `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Устранена неоднозначность интерпретации `selected_top` в runtime-логах RAG: теперь явно видно различие между количеством выбранных чанков и количеством документов, из которых эти чанки получены.

## [0.1.61] - 2026-02-25

### Added
- Добавлен регрессионный тест в `tests/test_rag_service.py`, проверяющий маркировку происхождения `selected_top` (`origin=prefilter|fallback|global`) и наличие поля `prefilter_scope_docs` в строке `RAG retrieval:`.

### Changed
- Улучшена диагностика retrieval в `src/sbs_helper_telegram_bot/ai_router/rag_service.py`: в `RAG retrieval:` добавлено поле `prefilter_scope_docs` (фактический размер области поиска после fallback), а в `RAG priority evidence -> selected_top` добавлено поле `origin` для каждого выбранного чанка.
- Обновлена документация по логированию RAG: `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Устранена неоднозначность в runtime-логах RAG, из-за которой документ мог появляться в `selected_top`, но визуально «отсутствовать» в `prefilter_top` без явного объяснения роли fallback/глобального поиска.

## [0.1.60] - 2026-02-25

### Added
- Добавлена env-настройка `AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL` для выбора модели генерации summary только в сценарии `scripts/rag_directory_ingest.py` (поддерживаются `deepseek-chat` и `deepseek-reasoner`).
- Добавлены регрессионные тесты в `tests/test_rag_service.py`, `tests/test_llm_provider.py`, `tests/test_rag_directory_ingest.py` и `tests/test_ai_model_switch.py`, покрывающие ingest-only override модели summary и безопасный fallback.

### Changed
- Расширен ingest-поток в `src/sbs_helper_telegram_bot/ai_router/rag_service.py`: `ingest_document_from_bytes()` принимает `summary_model_scope`, а `rag_directory_ingest.py` передаёт scope `directory_ingest` для точечного переключения модели summary без влияния на остальные `rag_summary`/chat-вызовы.
- Расширен API `DeepSeekProvider.chat()` в `src/sbs_helper_telegram_bot/ai_router/llm_provider.py`: добавлен параметр `model_override` для одноразового override модели в конкретном вызове.
- Обновлена документация по RAG-конфигурации и directory-ingest: `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Устранено ограничение, при котором directory-ingest summary всегда использовал response-модель; теперь возможен отдельный выбор summary-модели без глобального переключения AI-ответов.

## [0.1.59] - 2026-02-25

### Added
- Добавлен регрессионный тест в `tests/test_rag_service.py`, подтверждающий отображение взвешенного векторного вклада (`vec_w`) в `prefilter_top` и его изменение при смене `AI_RAG_SUMMARY_VECTOR_WEIGHT`.

### Changed
- Улучшена диагностическая строка `RAG priority evidence: prefilter_top` в `src/sbs_helper_telegram_bot/ai_router/rag_service.py`: теперь для каждого документа логируется разложение итогового score (`summary`, `lexical`, `vec`, `vec_w`), где `vec_w = vec * AI_RAG_SUMMARY_VECTOR_WEIGHT`.
- Уточнены комментарии в `src/sbs_helper_telegram_bot/ai_router/settings.py` о разграничении ролей `AI_RAG_SUMMARY_BONUS_WEIGHT` (chunk scoring) и `AI_RAG_SUMMARY_VECTOR_WEIGHT` (prefilter docs).
- Обновлена документация RAG по prefilter-диагностике и формуле в `docs/AI_RAG_GUIDE.md` и `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Устранена неоднозначность интерпретации prefilter-логов: теперь влияние `AI_RAG_SUMMARY_VECTOR_WEIGHT` на ранжирование документов видно напрямую, без ручных вычислений.

## [0.1.58] - 2026-02-25

### Fixed
- Исправлено форматирование RAG-ответов с вложенной разметкой вида `**\`code\`**`: внутренние служебные токены больше не попадают в сообщения пользователю (устранены артефакты `RAGTOKENCODE...`).

## [0.1.57] - 2026-02-25

### Added
- Добавлены регрессионные тесты в `tests/test_rag_service.py` для нового человекочитаемого форматирования retrieval-логов: сокращение длинного `source` и многострочный ранжированный snapshot для `prefilter_top/selected_top`.

### Changed
- Улучшено логирование в `src/sbs_helper_telegram_bot/ai_router/rag_service.py`: `RAG priority evidence:` теперь выводится в многострочном ранжированном формате, а `top_source` в `RAG retrieval:` автоматически сокращается при длинных путях/URL.
- Обновлена документация по RAG-диагностике: `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Устранена низкая читаемость эксплуатационных логов retrieval при длинных именах источников и плотном однострочном выводе evidence.

## [0.1.56] - 2026-02-25

### Added
- Семантический векторный поиск по summary документов: при доступном embedding-провайдере `_prefilter_documents_by_summary` дополнительно вычисляет cosine similarity между вопросом и каждым summary, что позволяет отличать «X5» от «VX520» на уровне смысла.
- Новая переменная окружения `AI_RAG_SUMMARY_VECTOR_WEIGHT` (по умолчанию `0.6`) — вес векторного сходства summary в prefilter scoring.
- Кэширование summary-эмбеддингов в памяти с автоматической инвалидацией при изменении corpus version.
- Диагностическая строка `RAG priority evidence: prefilter_top` теперь показывает отдельный `vec=` компонент для каждого документа.

### Changed
- Фразовый match в `_score_summary_text` заменён с substring (`in`) на word-boundary regex (`\b`), чтобы «X5» не совпадало внутри «VX520».
- Минимальная длина фразы для phrase-match снижена с 3 до 2 символов для поддержки коротких терминов (X5, D2 и т.д.).

### Changed
- Обновлена документация по RAG-диагностике: `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Упрощена оперативная верификация сценариев типа `X5 shop group`: теперь в runtime-логах явно видно, какие документы получили summary-приоритет и как это отразилось в финальном топе чанков.

### Added
- Добавлены новые env-настройки приоритизации summary retrieval в `src/sbs_helper_telegram_bot/ai_router/settings.py`: `AI_RAG_SUMMARY_MATCH_PHRASE_WEIGHT`, `AI_RAG_SUMMARY_MATCH_TOKEN_WEIGHT`, `AI_RAG_SUMMARY_SCORE_CAP`, `AI_RAG_SUMMARY_BONUS_WEIGHT`, `AI_RAG_SUMMARY_POSTRANK_WEIGHT`, `AI_RAG_SUMMARY_PREFILTER_FALLBACK_DOCS`.
- Добавлены регрессионные тесты в `tests/test_rag_service.py` на фразовый приоритет summary, controlled fallback документов и post-merge summary-bonus в hybrid retrieval.

### Changed
- Усилен summary-aware retrieval в `src/sbs_helper_telegram_bot/ai_router/rag_service.py`: prefilter документов теперь использует гибридный scoring (`exact phrase + token overlap`), а при наличии summary-hit добавляет fallback-пул активных документов для сохранения recall.
- В hybrid fusion добавлен дополнительный document-level summary-bonus после merge lexical/vector кандидатов для более стабильного приоритета документов с релевантным summary.
- Обновлена документация: `README.md`, `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Снижен риск ситуации, когда документ с релевантным фразовым summary (например, `X5 shop group`) недостаточно приоритизируется при равных vector/lexical сигналах.

## [0.1.55] - 2026-02-25

### Added
- Добавлена диагностическая строка `RAG priority evidence:` в `src/sbs_helper_telegram_bot/ai_router/rag_service.py` с top-5 prefilter-документами и top-5 финально выбранными чанками (`doc`, `source`, `fused`, `summary`) для наглядной проверки эффекта summary-приоритизации.
- Добавлен регрессионный тест в `tests/test_rag_service.py`, проверяющий наличие `RAG priority evidence:` в логах retrieval-цикла.

## [0.1.54] - 2026-02-25

## [0.1.53] - 2026-02-25

### Added
- Добавлено диагностическое логирование стратегии чанкинга в `scripts/rag_directory_ingest.py`: перед каждым циклом синхронизации пишется строка `Chunking конфигурация:` с активными `html/plain_text` стратегиями, выбранным `slicer`, `chunk_size`/`chunk_overlap` и флагами доступности splitter-ов.
- Добавлен регрессионный тест в `tests/test_rag_directory_ingest.py`, проверяющий наличие chunking-диагностики в runtime-логах ingest-скрипта.

### Changed
- В `src/sbs_helper_telegram_bot/ai_router/rag_service.py` расширено runtime-логирование ingest: теперь для каждого документа пишется строка `RAG chunking strategy:` с фактически выбранной стратегией (`html_header_splitter` или fallback), используемым slicer-ом и числом сформированных чанков.
- Обновлена документация по RAG-логированию: `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

## [0.1.52] - 2026-02-25

### Added
- Добавлен регрессионный тест в `tests/test_rag_admin_bot_part.py`, проверяющий, что загрузка документа через `#rag` вызывает ingest с `upsert_vectors=False`.

### Changed
- Изменён Telegram ingestion-поток (`src/sbs_helper_telegram_bot/ai_router/rag_admin_bot_part.py`): админ-загрузка `#rag` теперь сохраняет документ и чанки без немедленной генерации эмбеддингов.
- Обновлена документация (`docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`): для Telegram-загрузки явно зафиксирован backfill-only процесс векторной индексации через `scripts/rag_vector_backfill.py`.

### Fixed
- Устранено расхождение между путями ingest: и directory-sync, и Telegram `#rag` теперь используют единый подход без inline vector upsert, исключая частичную дубликацию индексации.

## [0.1.51] - 2026-02-25

### Added
- Добавлен регрессионный тест в `tests/test_rag_directory_ingest.py`, проверяющий, что `scripts/rag_directory_ingest.py` отключает немедленный vector upsert при ingest документов.

### Changed
- Изменён ingestion-поток `scripts/rag_directory_ingest.py`: синхронизация директории теперь загружает документы и чанки без генерации эмбеддингов, а обновление локального векторного индекса выполняется только через `scripts/rag_vector_backfill.py`.
- Обновлена документация по RAG-процессу (`docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`) с явным разделением этапов ingest и vector backfill.

### Fixed
- Устранена избыточная векторная обработка при directory ingest, которая могла дублировать/ускорять конкурирующие операции локальной индексации при отдельном запуске backfill.

## [0.1.50] - 2026-02-25

### Added
- Добавлен env-параметр `AI_RAG_VECTOR_EMBEDDING_FP16` для управления FP16-режимом локальной embedding-модели в vector RAG.
- Добавлены регрессионные тесты в `tests/test_vector_search.py` на корректное включение `half()` при CUDA и безопасное игнорирование FP16 на CPU.

### Changed
- `LocalEmbeddingProvider` в `src/sbs_helper_telegram_bot/ai_router/vector_search.py` теперь поддерживает FP16 для CUDA: при включённом флаге модель переводится в half precision и encode выполняется под `torch.cuda.amp.autocast`.
- Обновлены конфигурационные примеры и документация по настройке vector retrieval (`.env.example`, `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`) с примерами профилей для `AI_RAG_VECTOR_EMBEDDING_FP16`.

### Fixed
- Добавлен безопасный fallback на FP32 при недоступности CUDA, отсутствии поддержки `half()` у модели или ошибке инициализации autocast, чтобы исключить падения embedding-пайплайна.

## [0.1.49] - 2026-02-25

### Added
- Добавлен регрессионный тест в `tests/test_vector_search.py`, проверяющий, что при lock-конфликте локального Qdrant клиент не переинициализируется повторно в рамках одного процесса.

### Changed
- Обновлена документация по RAG (`docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`) с пояснением поведения при конкурентном доступе к `AI_RAG_VECTOR_DB_PATH`.

### Fixed
- Исправлен шумный сценарий при конкурирующем доступе к Qdrant local mode: `LocalVectorIndex` теперь распознаёт ошибку блокировки storage (`already accessed by another instance`), отключает векторную индексацию для текущего процесса и не выполняет повторные попытки инициализации клиента.

## [0.1.48] - 2026-02-25

### Fixed
- Исправлен кроссплатформенный дефект `scripts/rag_directory_ingest.py` на Windows: lock-файл single-instance теперь создаётся в системной temp-директории (`tempfile.gettempdir()`), а не в жёстко заданном `/tmp`, из-за чего ранее возникал `FileNotFoundError`.
- Добавлен тест в `tests/test_rag_directory_ingest.py`, проверяющий построение lock-пути через системный temp-dir.

## [0.1.47] - 2026-02-25

### Added
- Добавлена single-instance защита в `scripts/rag_directory_ingest.py`: для каждой директории синхронизации создаётся PID lock-файл в `/tmp`, повторный параллельный запуск завершается с понятной ошибкой.
- Добавлены тесты в `tests/test_rag_directory_ingest.py` для проверки блокировки второго запуска и очистки stale lock-файла.

### Fixed
- Устранён практический источник длительных lock wait при `rag_directory_ingest.py`: предотвращён параллельный запуск нескольких процессов синхронизации по одной директории, который приводил к конкурирующим транзакциям в `rag_documents`/`rag_chunks`.

## [0.1.46] - 2026-02-25

### Fixed
- Устранена основная причина `Lock wait timeout exceeded` при массовой синхронизации RAG: операции с Qdrant (`delete_document_points`, `set_payload`) вынесены за пределы открытых MySQL-транзакций в `delete_document()`, `set_document_status()` и `ingest_document_from_bytes()` (реактивация). Ранее Qdrant I/O (`wait=True`) выполнялся внутри транзакции, удерживая эксклюзивные блокировки строк на время дисковых операций.
- Добавлен retry с backoff для `delete_document()` и `set_document_status()` при временных InnoDB-ошибках (`1205`/`1213`).

## [0.1.45] - 2026-02-24

### Added
- Добавлен регрессионный тест в `tests/test_rag_service.py`, проверяющий retry ingest при временной MySQL-ошибке `1205` во время вставки в `rag_documents`.

### Changed
- Обновлена документация (`docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`): зафиксировано автоматическое повторение ingest-транзакций при временных блокировках БД.

### Fixed
- Исправлено аварийное завершение `scripts/rag_directory_ingest.py --force-update` при `Lock wait timeout exceeded`: в `RagKnowledgeService.ingest_document_from_bytes()` добавлен retry с backoff для временных InnoDB-ошибок (`1205`, `1213`) на критичных DB-этапах (`find/reactivate`, `insert document + chunks`).

## [0.1.44] - 2026-02-24

### Added
- Добавлены регрессионные тесты в `tests/test_rag_service.py` на поведение retry при временной ошибке MySQL `1205` и на отсутствие retry для неретраибельных SQL-ошибок при записи `rag_chunk_embeddings`.

### Changed
- Обновлена документация по vector RAG (`docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`): зафиксировано batched-сохранение и автоматический retry для временных блокировок БД.

### Fixed
- Исправлены сбои сохранения метаданных `rag_chunk_embeddings` при конкурирующих транзакциях: запись переведена на `executemany` батчами и дополняется автоматическим retry с backoff для временных ошибок InnoDB (`1205 lock wait timeout`, `1213 deadlock`).

## [0.1.43] - 2026-02-24

### Added
- Добавлен новый env-параметр `AI_RAG_VECTOR_DEVICE` (`auto|cuda|cpu`) для управления устройством локальной embedding-модели в vector RAG.
- Добавлены тесты `tests/test_vector_search.py` для проверки выбора устройства (`auto/cuda`) и передачи `device` в `SentenceTransformer`.

### Changed
- `LocalEmbeddingProvider` в `src/sbs_helper_telegram_bot/ai_router/vector_search.py` теперь явно выбирает устройство (`cuda` при доступности GPU, иначе `cpu`) и логирует выбранный `device` при загрузке модели.
- Обновлены конфигурационные примеры и документация для Windows-профиля с NVIDIA T400: `.env.example`, `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Снижен риск «тихого» запуска embedding-инференса на CPU без явной диагностики: выбор устройства стал контролируемым через конфиг и прозрачным в логах.

## [0.1.42] - 2026-02-24

### Added
- Добавлены регрессионные тесты для RAG-форматирования и доставки длинных MarkdownV2-ответов: `tests/test_ai_router_escape.py`, `tests/test_intent_handlers.py`, `tests/test_telegram_bot_markdown_safe.py`.

### Changed
- Для ответов `rag_qa` включено ограниченное сохранение форматирования в Telegram MarkdownV2: поддерживаются списки, жирный текст и `inline code`, а неподдерживаемая markdown-разметка безопасно экранируется.
- Обновлена документация по RAG UX и безопасной отправке: `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Устранён UX-дефект, при котором форматированный RAG-ответ (например, `**жирный**`, `код`, структурированные пункты) отображался как «сырой» текст из-за полного экранирования.
- Снижен риск ошибки Telegram `Message is too long`: длинные ответы `rag_qa` теперь автоматически разбиваются на несколько сообщений.

## [0.1.41] - 2026-02-24

### Added
- Добавлены регрессионные тесты в `tests/test_llm_provider.py`: автоповтор на `deepseek-chat` при пустом ответе `deepseek-reasoner` и извлечение текста из structured `content` (list-формат).

### Changed
- Обновлена документация (`docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`) с описанием runtime-fallback при пустом `content` у `deepseek-reasoner`.

### Fixed
- Исправлен сценарий «тихого» ответа модели: `DeepSeekProvider` теперь автоматически повторяет chat/RAG-запрос один раз на `deepseek-chat`, если `deepseek-reasoner` вернул пустой финальный `content`.

## [0.1.40] - 2026-02-24

### Added
- Добавлен диагностический лог `RAG retrieval:` в `RagKnowledgeService` с полями `mode`, `tokens`, `prefilter_docs`, `lexical_hits`, `vector_hits`, `selected`, `top_source` для прозрачной отладки retrieval-канала.
- Добавлен регрессионный тест в `tests/test_rag_service.py`, проверяющий наличие и формат лога `RAG retrieval:` с режимом `lexical_only`.

### Changed
- Обновлена документация по логированию в `docs/AI_RAG_GUIDE.md` и `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Нет изменений.

## [0.1.39] - 2026-02-24

### Added
- Добавлен регрессионный тест `tests/test_vector_search.py`, проверяющий корректную сборку Qdrant-фильтра по списку `document_id` без ошибки валидации.

### Changed
- Нет изменений.

### Fixed
- Исправлена ошибка `ValidationError` в локальном vector retrieval: фильтр Qdrant больше не использует `min_should=1` в `models.Filter` и формирует ограничение по документам через `MatchAny`.

## [0.1.38] - 2026-02-24

### Added
- Добавлены готовые пресеты локального vector RAG для двух классов окружений: macOS (сбалансированный BGE-M3) и Windows-машины с i5-3550 + NVIDIA T400 (стабильный профиль с `intfloat/multilingual-e5-small`).

### Changed
- Обновлены конфигурационные примеры и документация по запуску/тюнингу vector retrieval: `.env.example`, `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`.

### Fixed
- Нет изменений.

## [0.1.37] - 2026-02-24

### Added
- Добавлен опциональный локальный векторный слой RAG: модуль `src/sbs_helper_telegram_bot/ai_router/vector_search.py` (Qdrant local mode + локальные эмбеддинги) с безопасным fallback на lexical retrieval.
- Добавлен SQL-скрипт `scripts/ai_rag_vector_setup.sql` для хранения метаданных векторной индексации чанков (`rag_chunk_embeddings`).
- Добавлен CLI-скрипт `scripts/rag_vector_backfill.py` для пакетной индексации уже загруженных RAG-документов.
- Добавлены тесты: hybrid merge/vector-only merge в `tests/test_rag_service.py`, fallback вопроса `rag_qa` в `tests/test_ai_router.py`, dry-run backfill в `tests/test_rag_service.py`.

### Changed
- В `RagKnowledgeService` реализован hybrid retrieval: объединение lexical и vector кандидатов с конфигурируемыми весами и сохранением summary-enrichment.
- Ingest/CRUD документы теперь синхронизируют состояние локального векторного индекса (upsert при загрузке, статус при archive/restore/delete, удаление точек при hard-delete).
- В `IntentRouter` добавлен fallback: для intent `rag_qa` автоматически используется `original_text`, если классификатор не передал параметр `question`.
- Обновлена документация (`README.md`, `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`) и `.env.example` по локальному vector/hybrid режиму.

### Fixed
- Снижена вероятность пропуска релевантных шагов в RAG-ответах для переформулированных запросов за счёт добавления семантического (vector) канала retrieval.

## [0.1.36] - 2026-02-24

### Added
- Добавлено полное хранение `prompt/response` всех LLM-вызовов (включая классификацию, chat и RAG) в новой таблице `ai_model_io_log`.
- Добавлен SQL-скрипт `scripts/ai_model_io_log_retention.sql` для очистки full-text AI логов старше 30 дней.
- Добавлена маскировка чувствительных данных перед записью AI логов в БД (`email`, `телефон`, `ИНН`, `СНИЛС`).
- Добавлены тесты `tests/test_pii_masking.py` и расширены `tests/test_llm_provider.py` сценариями сохранения full-text логов и отказоустойчивости при ошибке БД.

### Changed
- `DeepSeekProvider` теперь записывает полный model I/O в БД через `ai_model_io_log` без влияния на основной ответ пользователю при ошибках логирования.
- В RAG и chat-путях пробрасываются `purpose` и `user_id` для корректной категоризации full-text логов.
- Обновлена документация (`README.md`, `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`) по новой схеме логирования и retention.

### Fixed
- Нет изменений.

## [0.1.35] - 2026-02-24

### Fixed
- Снято ограничение на использование `HTMLHeaderTextSplitter` на Python 3.14+: `_is_langchain_splitter_supported` теперь определяет доступность LangChain splitters пробным импортом, а не проверкой версии Python. Предупреждения `pydantic.v1` подавляются через `warnings.catch_warnings`.

## [0.1.34] - 2026-02-24

### Added
- В `scripts/rag_directory_ingest.py` добавлен CLI-флаг `--force-update` для принудительной перезагрузки файлов, даже если `content_hash` не изменился.
- Добавлен тест `tests/test_rag_directory_ingest.py`, проверяющий принудительный re-ingest неизменённого файла.

### Changed
- `run_ingest_cycle()` и daemon-режим ingest-скрипта теперь поддерживают параметр `force_update`, влияющий на логику пропуска неизменённых файлов.
- Обновлена документация по RAG-синхронизации (`docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`) с примером использования `--force-update`.

### Fixed
- Нет изменений.

## [0.1.33] - 2026-02-23

### Added
- Добавлено логирование prompt payload, отправляемого в LLM, и raw response модели в `DeepSeekProvider` (`llm_provider.py`).
- Добавлен env-переключатель `AI_LOG_MODEL_IO` и лимит `AI_LOG_MODEL_IO_MAX_CHARS` для контроля объёма логов.
- Добавлен тест `tests/test_llm_provider.py`, проверяющий логирование request/response при вызове `_call_api()`.

### Changed
- При HTTP-ошибке DeepSeek в лог теперь добавляется trimmed body ответа для упрощения диагностики.
- Обновлена документация (`README.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`) по новым параметрам логирования AI I/O.

### Fixed
- Нет изменений.

## [0.1.32] - 2026-02-23

### Added
- Добавлен SQL-скрипт `scripts/rag_document_summaries_fulltext_index.sql` для безопасного добавления FULLTEXT-индекса по `rag_document_summaries.summary_text` в существующих БД.
- Добавлены тесты в `tests/test_rag_service.py` для summary-aware prefilter, hybrid rerank чанков и передачи summary-блоков в RAG-промпт.

### Changed
- Обновлён retrieval в `RagKnowledgeService`: сначала выполняется prefilter активных документов по `rag_document_summaries`, затем ранжирование чанков усиливается бонусом релевантности summary документа.
- В `answer_question()` summary top-документов теперь передаются в `build_rag_prompt(..., summary_blocks=...)` для enrichment системного контекста.
- Обновлён `scripts/ai_rag_document_summaries_setup.sql`: добавлен FULLTEXT-индекс `ft_rag_doc_summary_text`.
- Обновлена документация (`README.md`, `docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`) по summary-aware retrieval и SQL-инициализации.

### Fixed
- Устранён разрыв между ingest и retrieval: `rag_document_summaries` больше не только заполняется при загрузке документов, но и реально используется для повышения релевантности RAG-ответов.

## [0.1.31] - 2026-02-23

### Added
- Добавлен регрессионный тест `tests/test_rag_service.py`, проверяющий создание записи в `rag_document_summaries` при ingestion документа.

### Changed
- Обновлена документация (`docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`): уточнено, что пакетная синхронизация директории формирует/обновляет summary документов.

### Fixed
- Исправлен `RagKnowledgeService.ingest_document_from_bytes()`: теперь при on-demand/daemon ingest обязательно выполняется upsert в `rag_document_summaries`.
- Добавлен безопасный fallback-summary, чтобы сбой AI-суммаризации не прерывал загрузку документа.

## [0.1.30] - 2026-02-23

### Added
- Добавлен регрессионный тест `tests/test_rag_directory_ingest.py` на прямой запуск `scripts/rag_directory_ingest.py` из любой текущей директории.

### Changed
- Обновлена документация по пакетной синхронизации RAG (`docs/AI_RAG_GUIDE.md`, `src/sbs_helper_telegram_bot/ai_router/README.md`): уточнено, что скрипт можно запускать по абсолютному пути из любого `cwd`.

### Fixed
- Исправлен запуск `scripts/rag_directory_ingest.py` как standalone-скрипта: добавлен bootstrap корня проекта в `sys.path`, чтобы исключить `ModuleNotFoundError: No module named 'src'`.

## [0.1.29] - 2026-02-22

### Added
- Добавлен README.md для модуля AI-маршрутизатора (`src/sbs_helper_telegram_bot/ai_router/README.md`).

### Changed
- Проект переименован в «SBS Helper AI Telegram Bot» с акцентом на AI-возможности.
- Главный README.md полностью переработан: компактная структура, таблица модулей со ссылками на отдельные README.
- Обновлены ссылки на проект в README модулей (ticket\_validator, gamification) и в `docs/MODULE_GUIDE_RU.md`.

## [0.1.28] - 2026-02-22

### Added
- Добавлен helper-скрипт `scripts/rag_directory_ingest.py` для синхронизации файловой директории с RAG-базой знаний в двух режимах: on-demand и daemon (`--interval-seconds`).
- Добавлены тесты `tests/test_rag_directory_ingest.py` для сценариев загрузки, purge удалённых файлов, обновления изменённых файлов и dry-run.

### Changed
- `RagKnowledgeService.ingest_document_from_bytes()` теперь корректно обрабатывает совпадающий `content_hash` для неактивных документов: выполняется реактивация существующей записи вместо ошибки вставки из-за `UNIQUE(content_hash)`.
- В `RagKnowledgeService` добавлен метод `list_documents_by_source()` для выборки документов по типу источника и префиксу `source_url`.
- Обновлена документация (`README.md`, `docs/AI_RAG_GUIDE.md`) по пакетной синхронизации документов из директории.

### Fixed
- Исправлен сценарий повторной загрузки документа с уже существующим `content_hash` в статусе `archived/deleted`: ingestion больше не падает на конфликте уникального индекса.

## [0.1.27] - 2026-02-22

### Added
- В `🧠 AI модель` (админ-настройки бота) добавлен отдельный runtime-тумблер `HTML splitter` для RAG HTML-документов.
- В `bot_settings` добавлен ключ `ai_rag_html_splitter_enabled` (инициализация по умолчанию в `scripts/ai_router_setup.sql`).

### Changed
- `RagKnowledgeService` теперь учитывает настройку `ai_rag_html_splitter_enabled`: при `0` header-aware HTML splitter пропускается и используется fallback chunking по очищенному тексту.
- Обновлена документация по управлению HTML splitter в `README.md`, `docs/AI_RAG_GUIDE.md` и `src/sbs_helper_telegram_bot/bot_admin/README.md`.

### Fixed
- Нет изменений.

## [0.1.26] - 2026-02-22

### Added
- Добавлен регрессионный тест `tests/test_rag_service.py`, подтверждающий, что на Python `3.14+` RAG chunking работает через fallback без импорта `langchain`.

### Changed
- В `RagKnowledgeService` использование LangChain splitters автоматически отключается на Python `3.14+`, чтобы избежать несовместимого пути `pydantic.v1`.
- Обновлена документация (`README.md`, `docs/AI_RAG_GUIDE.md`) по поведению RAG chunking на Python `3.14+`.

### Fixed
- Убрано шумное предупреждение `Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater` в процессе RAG-обработки: теперь используется встроенный fallback splitter.

## [0.1.25] - 2026-02-22

### Added
- Для HTML-документов в RAG добавлен приоритетный header-aware chunking через `HTMLHeaderTextSplitter` с переносом контекста заголовков `h1-h6` в текст чанков.
- Добавлены тесты для HTML-ветки chunking в `tests/test_rag_service.py` (основной путь и fallback).

### Changed
- При загрузке HTML в `RagKnowledgeService` теперь сначала применяется HTML-сплиттер по заголовкам, а не только общий текстовый splitter.
- Обновлена документация по поведению HTML chunking в `README.md` и `docs/AI_RAG_GUIDE.md`.

### Fixed
- Повышена устойчивость загрузки HTML в RAG: при недоступном/неуспешном `HTMLHeaderTextSplitter` автоматически используется fallback на plain-text chunking без отказа загрузки документа.

## [0.1.24] - 2026-02-22

### Added
- В настройках бота добавлено раздельное переключение DeepSeek-моделей: отдельно для классификации intent и отдельно для ответов (`chat`/`RAG`).
- В `bot_settings` добавлены ключи `ai_deepseek_model_classification` и `ai_deepseek_model_response` (инициализация в `scripts/ai_router_setup.sql`).
- Добавлены/обновлены тесты на новую схему выбора моделей (`tests/test_ai_model_switch.py`, `tests/test_llm_provider.py`).

### Changed
- `DeepSeekProvider` теперь использует отдельную модель для этапа классификации и отдельную — для генерации ответов.
- Обновлены пользовательские гайды (`README.md`, `docs/AI_RAG_GUIDE.md`) по настройке AI-моделей.

### Fixed
- Нет изменений.

## [0.1.23] - 2026-02-22

### Added
- Добавлен callback `on_classified` в `IntentRouter.route()`, позволяющий реагировать на результат классификации до получения финального ответа обработчика.
- Добавлены тесты на вызов callback после классификации (`tests/test_ai_router.py`) и на смену RAG-плейсхолдера (`tests/test_ai_placeholder.py`).

### Changed
- Для запросов, классифицированных как `rag_qa`, промежуточное сообщение обновляется с «⏳ Обрабатываю ваш запрос...» на «⏳ Ожидаю ответа ИИ» в ожидании финального ответа RAG.

### Fixed
- Нет изменений.

## [0.1.18] - 2026-02-22

## [0.1.19] - 2026-02-22

## [0.1.20] - 2026-02-22

## [0.1.21] - 2026-02-22

## [0.1.22] - 2026-02-22

### Added
- Добавлен `direct-text fallback` в парсер классификации AI: если модель возвращает длинный готовый текст вместо JSON, ответ маршрутизируется пользователю как chat-ответ.
- Добавлены тесты на fallback не-JSON ответа в `tests/test_llm_provider.py` и `tests/test_ai_router.py`.

### Changed
- `IntentRouter` теперь умеет использовать `classification.parameters.direct_answer` без повторного запроса в `provider.chat`.

### Fixed
- Исправлен кейс, когда вопрос по RAG получал ответ от модели в не-JSON формате, но бот показывал "Не понял вашу команду" из-за `NO_JSON_IN_RESPONSE`.

## [0.1.21] - 2026-02-22

### Added
- В админ-интерфейс добавлено переключение режима модели DeepSeek: `deepseek-chat` / `deepseek-reasoner`.
- В `scripts/ai_router_setup.sql` добавлена настройка по умолчанию `ai_deepseek_model=deepseek-chat`.
- Добавлены тесты переключения модели: `tests/test_ai_model_switch.py`.

### Changed
- `DeepSeekProvider` теперь определяет активную модель динамически через `bot_settings`, что позволяет применять переключение без перезапуска бота.
- Раздел настроек бота расширен кнопкой `🧠 AI модель` и inline-переключателем режимов.
- Обновлена документация (`README.md`, `docs/AI_RAG_GUIDE.md`) по управлению моделью из админ-панели.

### Fixed
- Нет изменений.

## [0.1.20] - 2026-02-22

### Added
- Поддержка загрузки HTML-документов в RAG (`.html`, `.htm`) с извлечением текста из HTML-контента.

### Changed
- Уточнён порядок регистрации хендлеров: RAG-обработчики теперь срабатывают до общего обработчика пакетной загрузки файлов.
- Обновлена документация по поддерживаемым форматам RAG-документов (`README.md`, `docs/AI_RAG_GUIDE.md`).

### Fixed
- Исправлены regex-фильтры для `#rag` команд и загрузок: убрано некорректное экранирование, из-за которого хендлер загрузки мог не срабатывать.

## [0.1.19] - 2026-02-22

### Added
- Реализован CRUD для RAG-документов через админ-команды в Telegram: `#rag list/info/archive/restore/delete/purge/help`.
- Добавлен обработчик текстовых RAG-команд в `rag_admin_bot_part.py` с проверкой admin-прав и валидацией параметров.
- Добавлены тесты `tests/test_rag_admin_bot_part.py` для сценариев команд управления документами.

### Changed
- `RagKnowledgeService` расширен методами управления документами: `list_documents`, `get_document`, `set_document_status`, `delete_document`.
- При изменении статуса/удалении документов автоматически обновляется `rag_corpus_version` для корректной инвалидации кэша и retrieval-состояния.
- Обновлена документация по админскому управлению RAG-документами в `README.md` и `docs/AI_RAG_GUIDE.md`.

### Fixed
- Нет изменений.

## [0.1.18] - 2026-02-22

### Added
- Начат MVP RAG для AI-роутера: добавлен новый intent `rag_qa` и обработчик ответов по базе знаний документов.
- Добавлена админ-загрузка документов в RAG через Telegram: отправка `PDF/DOCX/TXT/MD` с подписью `#rag`.
- Добавлен сервис `RagKnowledgeService` с извлечением текста, разбиением на чанки (LangChain `RecursiveCharacterTextSplitter` с fallback), retrieval и TTL-кэшем ответов.
- Добавлен SQL-скрипт `scripts/ai_rag_setup.sql` для таблиц `rag_documents`, `rag_chunks`, `rag_corpus_version`, `rag_query_log`.
- Добавлены настройки окружения для RAG (`AI_RAG_*`) и тесты `tests/test_rag_service.py`.

### Changed
- Обновлён AI классификационный промпт: добавлен сценарий маршрутизации вопросов по внутренним документам в `rag_qa`.
- Обновлена документация в `README.md` по настройке/запуску RAG и процессу загрузки документов администратором.

### Fixed
- Нет изменений.

## [0.1.17] - 2026-02-22

### Fixed
- Исправлена логика возврата меню после AI-ответа: теперь бот восстанавливает последнюю активную `ReplyKeyboardMarkup`, которая была показана пользователю до ввода произвольного AI-запроса, вместо принудительного переключения на главное меню.
- Добавлено сохранение последней reply-клавиатуры в ключевых точках навигации (`/start`, `/menu`, `/reset`, `/help`, переходы по основным меню и подменю), чтобы корректно возвращать именно текущий контекст пользователя.

### Added
- Тест восстановления предыдущей клавиатуры после AI-ответа и обновление тестовых моков контекста для `user_data`.

## [0.1.16] - 2026-02-22

### Fixed
- После успешного AI-ответа (`chat`/`routed` и fallback `unrecognized`) бот теперь автоматически отправляет отдельное сообщение с `ReplyKeyboardMarkup`, чтобы нижние кнопки меню снова отображались в Telegram-клиенте.
- Исправлен UX-сценарий, когда после редактирования AI-плейсхолдера кнопки меню могли оставаться скрытыми до следующего ручного действия пользователя.

### Added
- Регрессионные тесты AI-потока: проверка, что после успешного редактирования плейсхолдера отправляется отдельное сообщение для восстановления клавиатуры главного меню.

## [0.1.11] - 2026-02-22

### Added
- Детальное профилирование AI-маршрутизации в `IntentRouter`: лог `AI route profiling` теперь показывает разбиение `total_ms` на `classify_ms`, `db_log_ms`, `dispatch_ms`, `context_update_ms`, а также внутренние метрики `chat_ms`/`handler_ms` и путь `path`.

### Changed
- `_dispatch()` теперь возвращает метаданные этапа маршрутизации для прозрачной диагностики задержек.

## [0.1.9] - 2026-02-22

## [0.1.10] - 2026-02-22

### Fixed
- Убраны лишние обратные слэши в plain-text fallback AI-ответов (например, `режиме\.`): `_strip_markdown_v2_escaping()` теперь снимает все подряд слэши перед MarkdownV2-спецсимволом (`\\+`), а не только один.

### Added
- Регрессионные тесты для кейсов `\\.` и `\\\.` в `_strip_markdown_v2_escaping()`.

### Fixed
- Плейсхолдер AI теперь отправляется без `reply_markup`, чтобы `edit_text` был редактируемым: ранее плейсхолдер отправлялся с `ReplyKeyboardMarkup`, что на части клиентов/сценариев приводило к `BadRequest: Message can't be edited`.

### Added
- Диагностическое логирование стратегии отправки плейсхолдера: в лог пишется тип клавиатуры и явная пометка о риске `ReplyKeyboardMarkup` для `edit_text`.

## [0.1.8] - 2026-02-22

### Fixed
- Ответы AI с обратными слэшами (pre-escaped от LLM) вызывали ошибку `Can't parse entities` в Telegram: `escape_markdown_v2()` не экранировала `\`, из-за чего `\!` превращалось в `\\!` (экранированный бэкслеш + неэкранированный спецсимвол). Теперь обратные слэши экранируются первыми во всех 5 копиях функции (`ai_router`, `common`, `news`, `ktr`, `upos_error`).
- Fallback в `_reply_markdown_safe()` применял `escape_markdown_v2()` к уже экранированному тексту (двойное экранирование), что приводило к повторному `Can't parse entities`. Теперь fallback отправляет plain text без parse_mode, аналогично `_edit_markdown_safe()`.

### Added
- Тесты экранирования обратных слэшей в AI-ответах (`test_ai_router_escape.py`).
- Расширенное диагностическое логирование при ошибке `Message can't be edited`: теперь в лог записываются `message_id`, `chat_id`, `date` плейсхолдера, тип исключения, длина и превью ответа — для отладки причин невозможности редактирования.

## [0.1.7] - 2026-02-22

### Fixed
- Плейсхолдер «⏳ Обрабатываю ваш запрос...» оставался в чате при ошибке редактирования: теперь плейсхолдер удаляется перед отправкой нового сообщения.
- Двойное экранирование в `_edit_markdown_safe()`: при ошибке парсинга MarkdownV2 fallback вызывал `escape_markdown_v2()` на уже экранированном тексте, что приводило к видимым обратным слэшам и ошибке «Message can't be edited». Теперь fallback отправляет plain text без форматирования.

### Added
- Вспомогательная функция `_strip_markdown_v2_escaping()` для удаления MarkdownV2-экранирования при plain-text fallback.

## [0.1.6] - 2026-02-22

### Added
- Индикатор загрузки при AI-маршрутизации: при отправке произвольного текста в бот пользователь видит `ChatAction.TYPING` и плейсхолдер-сообщение «⏳ Обрабатываю ваш запрос...», которое заменяется ответом AI. При ошибке редактирования — fallback на новое сообщение.
- Вспомогательная функция `_edit_markdown_safe()` для безопасного редактирования сообщений с MarkdownV2-fallback.
- Тесты потока typing → плейсхолдер → edit/fallback (`test_ai_placeholder.py`).

## [0.1.5] - 2026-02-21

### Fixed
- Кнопка «Главное меню» в модуле аттестации (режим обучения/тест) требовала двойного нажатия: первый клик лишь завершал ConversationHandler без отображения главного меню, второй — фактически показывал меню. Теперь `cancel_on_menu` сразу отправляет главное меню при выходе из диалога.

## [0.1.4] - 2026-02-21

### Fixed
- Ошибка парсинга MarkdownV2 при отправке новостей через AI-маршрутизатор: символы `(` и `)` в заголовках `NewsHandler` не были экранированы, что приводило к падению Telegram API и каскадному двойному экранированию в fallback-режиме (ломало символ `.`).

## [0.1.3] - 2026-02-21

### Added
- Пул соединений MySQL (`MySQLConnectionPool`) в `database.py` — вместо создания нового TCP-соединения на каждый запрос (~100-200мс) используется пул из 5 готовых соединений (~1-2мс). Размер настраивается через `DB_POOL_SIZE`.
- TTL-кеш настроек (`_SETTINGS_CACHE_TTL=60с`) в `bot_settings.py` — повторные вызовы `get_setting()` берут значение из памяти, а не из БД. Кеш сбрасывается автоматически при `set_setting()`.
- Консолидированная проверка авторизации `get_user_auth_status()` в `telegram_user.py` — все проверки (chat_members, manual_users, invites, is_admin) выполняются за одно подключение к БД вместо 6-9 отдельных.
- Кеш статуса здоровья налоговой (`_HEALTH_CACHE_TTL=60с`) в `health_check.py` — `get_tax_health_status_lines()` кеширует результат, сбрасывается при `record_health_status()`.
- Тесты `tests/test_performance_optimizations.py` — 20 тестов для пула соединений, кеша настроек, пакетной загрузки модулей, консолидированной авторизации и кеша здоровья.

### Changed
- `get_all_module_states()` и `get_modules_config()` загружают настройки всех модулей одним SQL-запросом `WHERE IN (...)` вместо 8 отдельных запросов.
- `get_user_categories_this_month()` в `certification_logic.py` — устранён N+1 паттерн: ранги по категориям вычисляются в одном соединении к БД, а не N отдельных.
- Обработчик `text_entered` в `telegram_bot.py` использует `get_user_auth_status()` вместо разрозненных проверок.

### Fixed
- Время отклика обработчиков `reply_main_menu` (~3.8с→<0.5с), `reply_modules_menu` (~5с→<0.2с), `reply_ticket_validator_submenu` (~7.5с→<0.5с), `certification_my_ranking` (~2.4с→<0.5с) за счёт устранения избыточных TCP-соединений к MySQL.

## [0.1.2] - 2026-02-21

### Added
- Логирование профиля обработки входящего текста в `text_entered`: `total_ms` от получения сообщения до завершения действия и поэтапные тайминги в миллисекундах (`steps=[...]`).
- Тесты `tests/test_telegram_bot_markdown_safe.py` для проверки форматирования шагов профилирования и наличия сводного профилирующего лога при обработке сообщения.

### Changed
- Оптимизирована ветка авторизации по инвайту: статус инвайта теперь вычисляется один раз и переиспользуется в проверках.

### Fixed
- Нет изменений.

## [0.1.1] - 2026-02-21

### Added
- Регрессионные тесты: `tests/test_telegram_bot_markdown_safe.py` для fallback-отправки MarkdownV2 и новые кейсы в `tests/test_llm_provider.py` для частично обрезанного JSON-ответа LLM.

### Changed
- В `DeepSeekProvider.classify()` увеличен `max_tokens` для классификации (`512` → `1024`), чтобы снизить риск обрезки JSON при длинных заявках.
- Промпт классификации обновлён: для `ticket_validation` модель должна передавать в `parameters.ticket_text` только информативный фрагмент, а не дублировать весь длинный текст.

### Fixed
- Исправлен сценарий `Can't parse entities` при отправке AI-ответов: добавлен безопасный fallback повторной отправки с полным экранированием MarkdownV2.
- Исправлен парсинг частично обрезанного JSON от LLM: добавлен fallback-извлекатель `intent/confidence/explain_code`, чтобы не проваливаться в `NO_JSON_IN_RESPONSE` при длинных ответах.

## [0.1.0] - 2026-02-21

### Added
- **AI-маршрутизатор**: новый модуль `ai_router` для интеллектуальной обработки произвольного текста через DeepSeek API (OpenAI-совместимый). Поддерживает маршрутизацию к 5 модулям (UPOS-ошибки, Валидация заявок, КТР, Аттестация, Новости) и свободный диалог с LLM.
- Абстракция `LLMProvider` с реализацией `DeepSeekProvider`; расширяемая фабрика через `register_provider()`.
- Circuit breaker: автоматический переход в degrade-режим при серии ошибок LLM-провайдера (CLOSED → OPEN → HALF_OPEN).
- Per-user sliding-window rate limiter для защиты от спама и контроля стоимости API.
- Менеджер контекста диалога: хранение 3–5 последних сообщений с TTL для поддержки коротких диалогов.
- Повторная проверка admin-прав в callback-ветках `handle_callback` (`admin_bot_part.py`) для защиты от stale inline-клавиатур.
- Hard-disable модулей в runtime: при выключении модуля через админку AI не маршрутизирует к нему, а кнопки меню показывают сообщение о деактивации.
- Логирование результатов AI-классификации в таблицу `ai_router_log` (intent, confidence, explain_code, response_time_ms).
- SQL-скрипт `scripts/ai_router_setup.sql` для создания таблицы логов и настройки модуля.
- `MODULE_CONFIG` для `ai_router` и `news` в `bot_settings.py`.
- Тесты: `test_circuit_breaker.py`, `test_rate_limiter.py`, `test_context_manager.py`, `test_llm_provider.py`, `test_intent_handlers.py`, `test_ai_router.py`, `test_admin_callback_auth.py`.

### Changed
- `text_entered` в `telegram_bot.py`: нераспознанный текст теперь маршрутизируется через AI-роутер перед показом стандартного сообщения об ошибке; при нажатии кнопок меню контекст AI-диалога очищается.
- Конфигурация env-переменных расширена: `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`, `AI_CONFIDENCE_THRESHOLD`, `AI_RATE_LIMIT_*`, `AI_CIRCUIT_BREAKER_*`, и др.

## [0.0.13] - 2026-02-20

### Fixed
- При нажатии кнопки меню во время нестабильного соединения (`httpx.ConnectError`, `httpx.RemoteProtocolError` и другие сетевые ошибки) бот теперь отвечает пользователю всплывающим уведомлением «Нет связи с сервером» вместо молчания. Добавлен вспомогательный `_answer_callback_silent` для ответа на callback-запрос без риска зацикливания обработки.

## [0.0.12] - 2026-02-20

### Changed
- Формат отображения плановых работ `OUTAGE_TYPE_RED` изменён на `с ЧЧ:ММ ДД.ММ по ЧЧ:ММ ДД.ММ.ГГГГ МСК`.

## [0.0.11] - 2026-02-19

### Changed
- Формат отображения плановых работ `OUTAGE_TYPE_RED` изменён на `ЧЧ:ММ ДД.ММ.ГГГГ - ЧЧ:ММ ДД.ММ.ГГГГ`.

## [0.0.10] - 2026-02-19

### Added
- Добавлен регрессионный тест `tests/test_health_check.py` для проверки отображения дат начала и окончания в `OUTAGE_TYPE_RED`.

### Changed
- В отображении плановых работ типа `OUTAGE_TYPE_RED` теперь показываются обе даты окна: начало и окончание \(вместо формулировки `до ...`\).

### Fixed
- Уточнено информирование пользователей о будущих двухдневных работах налоговой: из сообщения сразу видны точные даты начала и завершения.

## [0.0.9] - 2026-02-18

### Added
- Добавлен регрессионный async-тест на обработчик `show_my_ranking`, чтобы исключить повторный `NameError` по `expiry_lines`.

### Changed
- Нет изменений.

### Fixed
- Исправлена инициализация `expiry_lines` в `show_my_ranking` \(модуль аттестации\).

## [0.0.8] - 2026-02-18

### Added
- В тесты модуля аттестации добавлены проверки порядка сложностей вопросов: `easy` → `medium` → `hard`.

### Changed
- В генерации тестов сохранена случайность внутри каждой сложности, но итоговый порядок выдачи вопросов фиксирован: сначала лёгкие, затем средние, затем сложные.

### Fixed
- Нет изменений.

## [0.0.7] - 2026-02-18

### Added
- В сообщение подменю аттестации добавлены текущий аттестационный ранг и строка прогресса в формате `Прогресс аттестации : [бар] XX% current/max`.

### Changed
- Нет изменений.

### Fixed
- Нет изменений.

## [0.0.6] - 2026-02-18

### Added
- Нет изменений.

### Changed
- Блок аттестации в главном меню упрощён: удалены отдельные строки про баллы, максимум, число тестов, срок результата по категории и последний успешный тест.
- Добавлена единая строка прогресса формата `Прогресс аттестации : [бар] XX% current/max`.

### Fixed
- Нет изменений.

## [0.0.5] - 2026-02-18

### Added
- Нет изменений.

### Changed
- Формула `certification_points` изменена: теперь очки считаются как сумма лучших процентов тестов по категориям за последние 30 дней \(100% в категории = 100 очков\).
- Максимально достижимые очки пересчитаны как `active_categories * 100`.

### Fixed
- Нет изменений.

## [0.0.4] - 2026-02-18

### Added
- Добавлены тесты фильтрации событий геймификации для временного режима только аттестации.

### Changed
- Временно отключена обработка событий геймификации для всех модулей, кроме `certification.*`.

### Fixed
- Нет изменений.

## [0.0.3] - 2026-02-18

### Added
- В главное меню добавлен прогресс аттестации к максимуму очков и визуальный прогресс-бар.

### Changed
- Нет изменений.

### Fixed
- Нет изменений.

## [0.0.2] - 2026-02-18

### Added
- На экране «Мой рейтинг» добавлен прогресс-бар аттестации с отображением очков относительно динамического максимума и следующей ступени.

### Changed
- Ступень «Мастер аттестации» перенесена на 90% от максимума очков.
- Добавлена новая ultimate-ступень «Абсолют» на 100%.

### Fixed
- Нет изменений.

## [0.0.1] - 2024-06-12 

### Added
- В интерфейс аттестации добавлен полный список рангов с порогами баллов на экране «Мой рейтинг».

### Changed
- Для пользователей с истекшими результатами категорий добавлено явное предупреждение о возможном снижении аттестационного ранга.
- Пороги аттестационных рангов переведены с фиксированных значений на проценты от динамически рассчитываемого максимума очков.

### Fixed
- Нет изменений.
