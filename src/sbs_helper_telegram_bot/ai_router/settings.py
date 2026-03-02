"""
settings.py — настройки модуля AI-маршрутизации.

Содержит конфигурационные константы, ключи настроек, тексты кнопок
и пороговые значения для AI-классификации.
"""

from typing import Final
import os
from dotenv import load_dotenv


load_dotenv(override=True)


# =============================================
# Идентификаторы модуля
# =============================================

# Ключ модуля AI-роутера в общей конфигурации модулей.
AI_MODULE_KEY: Final[str] = "ai_router"
# Ключ флага включения/выключения AI-роутера в таблице bot_settings.
AI_SETTING_KEY: Final[str] = "module_ai_router_enabled"

# =============================================
# Настройки LLM-провайдера
# =============================================

# Имя активного LLM-провайдера (сейчас используется DeepSeek).
AI_PROVIDER: Final[str] = os.getenv("AI_PROVIDER", "deepseek")
# API-ключ доступа к DeepSeek.
DEEPSEEK_API_KEY: Final[str] = os.getenv("DEEPSEEK_API_KEY", "")
# Базовый URL DeepSeek API.
DEEPSEEK_BASE_URL: Final[str] = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
# Модель DeepSeek по умолчанию, если не переопределена через bot_settings.
DEEPSEEK_MODEL: Final[str] = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Ключи настроек модели в bot_settings (переключаются из админ-панели)
# Legacy-ключ модели (старый единый ключ для всех задач).
AI_DEEPSEEK_MODEL_SETTING_KEY_LEGACY: Final[str] = "ai_deepseek_model"
# Ключ модели для intent-классификации.
AI_DEEPSEEK_MODEL_CLASSIFICATION_SETTING_KEY: Final[str] = "ai_deepseek_model_classification"
# Ключ модели для генерации ответов (chat/RAG).
AI_DEEPSEEK_MODEL_RESPONSE_SETTING_KEY: Final[str] = "ai_deepseek_model_response"
# Модель для генерации summary только в сценарии directory-ingest (из env).
AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL: Final[str] = os.getenv(
    "AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL",
    "deepseek-reasoner",
)

# Поддерживаемые модели DeepSeek для runtime-переключения
# Название chat-модели DeepSeek.
DEEPSEEK_MODEL_CHAT: Final[str] = "deepseek-chat"
# Название reasoner-модели DeepSeek.
DEEPSEEK_MODEL_REASONER: Final[str] = "deepseek-reasoner"
# Белый список разрешённых имён моделей DeepSeek.
ALLOWED_DEEPSEEK_MODELS: Final[tuple[str, ...]] = (
    DEEPSEEK_MODEL_CHAT,
    DEEPSEEK_MODEL_REASONER,
)

# Таймаут HTTP-запросов к LLM (секунды)
# Максимальное время ожидания ответа от LLM API.
LLM_REQUEST_TIMEOUT: Final[int] = int(os.getenv("AI_LLM_REQUEST_TIMEOUT", "30"))

# Таймаут чтения ответа от LLM (секунды).
# RAG-ответы могут генерироваться дольше — устанавливаем выше, чем общий таймаут.
LLM_READ_TIMEOUT: Final[int] = int(os.getenv("AI_LLM_READ_TIMEOUT", "120"))

# Параметры генерации LLM для intent-классификации.
LLM_CLASSIFICATION_TEMPERATURE: Final[float] = float(
    os.getenv("AI_LLM_CLASSIFICATION_TEMPERATURE", "0.1")
)
LLM_CLASSIFICATION_MAX_TOKENS: Final[int] = int(
    os.getenv("AI_LLM_CLASSIFICATION_MAX_TOKENS", "1024")
)

# Параметры генерации LLM для свободного диалога/chat-ответов.
LLM_CHAT_TEMPERATURE: Final[float] = float(
    os.getenv("AI_LLM_CHAT_TEMPERATURE", "0.7")
)
LLM_CHAT_MAX_TOKENS: Final[int] = int(
    os.getenv("AI_LLM_CHAT_MAX_TOKENS", "1024")
)

# Логирование prompt/response модели
# Включить логирование входа/выхода модели в приложении.
AI_LOG_MODEL_IO: Final[bool] = os.getenv("AI_LOG_MODEL_IO", "1") == "1"
# Максимальная длина логируемого prompt/response (символов).
AI_LOG_MODEL_IO_MAX_CHARS: Final[int] = int(os.getenv("AI_LOG_MODEL_IO_MAX_CHARS", "8000"))
# Включить сохранение логов model I/O в БД.
AI_MODEL_IO_DB_LOG_ENABLED: Final[bool] = os.getenv("AI_MODEL_IO_DB_LOG_ENABLED", "1") == "1"
# Срок хранения записей model I/O в БД (дней).
AI_MODEL_IO_DB_RETENTION_DAYS: Final[int] = int(os.getenv("AI_MODEL_IO_DB_RETENTION_DAYS", "30"))

# =============================================
# Пороги уверенности
# =============================================

# Минимальный порог уверенности для маршрутизации к модулю
CONFIDENCE_THRESHOLD: Final[float] = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.6"))

# Порог уверенности для свободного chat-ответа (ниже — показываем MESSAGE_UNRECOGNIZED_INPUT)
CHAT_CONFIDENCE_THRESHOLD: Final[float] = float(os.getenv("AI_CHAT_CONFIDENCE_THRESHOLD", "0.1"))

# =============================================
# Rate-limit: защита от спама и стоимости
# =============================================

# Максимальное число AI-запросов за окно
RATE_LIMIT_MAX_REQUESTS: Final[int] = int(os.getenv("AI_RATE_LIMIT_MAX", "10"))

# Окно rate-limit в секундах
RATE_LIMIT_WINDOW_SECONDS: Final[int] = int(os.getenv("AI_RATE_LIMIT_WINDOW", "60"))

# =============================================
# Контекст диалога
# =============================================

# Максимальное число сообщений в контексте
MAX_CONTEXT_MESSAGES: Final[int] = int(os.getenv("AI_MAX_CONTEXT_MESSAGES", "6"))

# TTL контекста в секундах (10 минут)
CONTEXT_TTL_SECONDS: Final[int] = int(os.getenv("AI_CONTEXT_TTL_SECONDS", "600"))

# =============================================
# Circuit breaker
# =============================================

# Число последовательных ошибок для перехода в OPEN
CIRCUIT_BREAKER_FAILURE_THRESHOLD: Final[int] = int(
    os.getenv("AI_CIRCUIT_BREAKER_FAILURES", "5")
)

# Время восстановления (секунды) для перехода в HALF_OPEN
CIRCUIT_BREAKER_RECOVERY_SECONDS: Final[int] = int(
    os.getenv("AI_CIRCUIT_BREAKER_RECOVERY", "300")
)

# =============================================
# Максимальная длина входного текста для AI
# =============================================

MAX_INPUT_LENGTH: Final[int] = int(os.getenv("AI_MAX_INPUT_LENGTH", "4000"))

# =============================================
# RAG (документы знаний)
# =============================================

# Включение RAG-режима в AI-маршрутизаторе
AI_RAG_ENABLED: Final[bool] = os.getenv("AI_RAG_ENABLED", "1") == "1"

# Лимиты входящих документов
# Максимальный размер загружаемого файла в MB.
AI_RAG_MAX_FILE_SIZE_MB: Final[int] = int(os.getenv("AI_RAG_MAX_FILE_SIZE_MB", "20"))
# Ограничение числа чанков на документ после разбиения.
AI_RAG_MAX_CHUNKS_PER_DOC: Final[int] = int(os.getenv("AI_RAG_MAX_CHUNKS_PER_DOC", "500"))

# Параметры chunking
# Целевой размер одного чанка (символов).
AI_RAG_CHUNK_SIZE: Final[int] = int(os.getenv("AI_RAG_CHUNK_SIZE", "1000"))
# Перекрытие соседних чанков (символов).
AI_RAG_CHUNK_OVERLAP: Final[int] = int(os.getenv("AI_RAG_CHUNK_OVERLAP", "150"))

# Параметры retrieval. Значение по умолчанию AI_RAG_TOP_K=8
# Сколько верхних чанков передавать в финальный контекст ответа.
AI_RAG_TOP_K: Final[int] = int(os.getenv("AI_RAG_TOP_K", "8"))
# Верхняя граница суммарного размера контекста RAG (символов).
AI_RAG_MAX_CONTEXT_CHARS: Final[int] = int(os.getenv("AI_RAG_MAX_CONTEXT_CHARS", "14000"))

# AI-summary для документов (используется при ingest и retrieval)
# Включить генерацию и использование summary документов.
AI_RAG_SUMMARY_ENABLED: Final[bool] = os.getenv("AI_RAG_SUMMARY_ENABLED", "1") == "1"
# Максимальный объём текста документа для входа в summary-генерацию (символов).
AI_RAG_SUMMARY_INPUT_MAX_CHARS: Final[int] = int(os.getenv("AI_RAG_SUMMARY_INPUT_MAX_CHARS", "12000"))
# Максимальная длина сохранённого summary (символов).
AI_RAG_SUMMARY_MAX_CHARS: Final[int] = int(os.getenv("AI_RAG_SUMMARY_MAX_CHARS", "1200"))
# Количество top-документов после summary-prefilter для chunk retrieval.
AI_RAG_PREFILTER_TOP_DOCS: Final[int] = int(os.getenv("AI_RAG_PREFILTER_TOP_DOCS", "4"))
# Не учитывать source_type=certification в квоте AI_RAG_PREFILTER_TOP_DOCS.
# Если включено, сертификационные документы остаются в prefilter-выдаче,
# но не занимают квоту обычных документов.
AI_RAG_PREFILTER_EXCLUDE_CERTIFICATION_FROM_COUNT: Final[bool] = (
    os.getenv("AI_RAG_PREFILTER_EXCLUDE_CERTIFICATION_FROM_COUNT", "1") == "1"
)
# Сколько summary-блоков включать в системный prompt ответа.
AI_RAG_PROMPT_SUMMARY_DOCS: Final[int] = int(os.getenv("AI_RAG_PROMPT_SUMMARY_DOCS", "1"))
# Исключать ли summary сертификационных вопросов из prompt-блока joined_summaries.
# Не влияет на retrieval/ranking: влияет только на блок summary в системном prompt.
AI_RAG_PROMPT_SUMMARIES_EXCLUDE_CERTIFICATION: Final[bool] = (
    os.getenv("AI_RAG_PROMPT_SUMMARIES_EXCLUDE_CERTIFICATION", "1") == "1"
)
# Вес точного/фразового совпадения вопроса с summary.
AI_RAG_SUMMARY_MATCH_PHRASE_WEIGHT: Final[float] = float(
    os.getenv("AI_RAG_SUMMARY_MATCH_PHRASE_WEIGHT", "1")
)
# Вес токенного совпадения вопроса с summary.
AI_RAG_SUMMARY_MATCH_TOKEN_WEIGHT: Final[float] = float(
    os.getenv("AI_RAG_SUMMARY_MATCH_TOKEN_WEIGHT", "1.0")
)
# Верхняя граница summary-score для fallback-нормализации в диапазон 0..1.
# В retrieval-пайплайне используется относительная min-max нормализация внутри текущего prefilter-пула.
AI_RAG_SUMMARY_SCORE_CAP: Final[float] = float(os.getenv("AI_RAG_SUMMARY_SCORE_CAP", "2.5"))
# Вес бонуса нормализованного summary-score на этапе lexical chunk scoring.
# Не влияет на prefilter документов; для prefilter используется AI_RAG_SUMMARY_VECTOR_WEIGHT.
AI_RAG_SUMMARY_BONUS_WEIGHT: Final[float] = float(os.getenv("AI_RAG_SUMMARY_BONUS_WEIGHT", "0.45"))
# Вес пост-бонуса нормализованного summary-score на этапе финального hybrid ранжирования 0.20
AI_RAG_SUMMARY_POSTRANK_WEIGHT: Final[float] = float(
    os.getenv("AI_RAG_SUMMARY_POSTRANK_WEIGHT", "1")
)
# Число fallback-документов (вне top prefilter) для повышения recall.
AI_RAG_SUMMARY_PREFILTER_FALLBACK_DOCS: Final[int] = int(
    os.getenv("AI_RAG_SUMMARY_PREFILTER_FALLBACK_DOCS", "0")
)
# Вес семантического (vector) вклада summary при prefilter документов.
# Влияет на ранжирование prefilter_docs и на поле vec_w в диагностическом логе prefilter_top.
AI_RAG_SUMMARY_VECTOR_WEIGHT: Final[float] = float(
    os.getenv("AI_RAG_SUMMARY_VECTOR_WEIGHT", "20")
)

# Summary-fallback: когда LLM сообщает, что чанки не содержат ответа,
# выполняется дополнительный LLM-запрос по summary документов.
# Мастер-переключатель summary-fallback.
AI_RAG_SUMMARY_FALLBACK_ENABLED: Final[bool] = (
    os.getenv("AI_RAG_SUMMARY_FALLBACK_ENABLED", "1") == "1"
)
# Количество top-summary документов для fallback-промпта.
AI_RAG_SUMMARY_FALLBACK_TOP_DOCS: Final[int] = int(
    os.getenv("AI_RAG_SUMMARY_FALLBACK_TOP_DOCS", "5")
)
# Верхняя граница суммарного размера summary-контекста в fallback-промпте (символов).
AI_RAG_SUMMARY_FALLBACK_MAX_CONTEXT_CHARS: Final[int] = int(
    os.getenv("AI_RAG_SUMMARY_FALLBACK_MAX_CONTEXT_CHARS", "8000")
)

# TTL-кэш ответов RAG (секунды)
# Время жизни кешированного ответа на одинаковый запрос.
AI_RAG_CACHE_TTL_SECONDS: Final[int] = int(os.getenv("AI_RAG_CACHE_TTL_SECONDS", "300"))

# Векторный retrieval (локальный индекс и локальная embedding-модель)
# Глобальный флаг включения векторного retrieval.
AI_RAG_VECTOR_ENABLED: Final[bool] = os.getenv("AI_RAG_VECTOR_ENABLED", "0") == "1"
# Включить гибридное объединение lexical + vector кандидатов.
AI_RAG_HYBRID_ENABLED: Final[bool] = os.getenv("AI_RAG_HYBRID_ENABLED", "1") == "1"
# Использовать локальный режим векторного индекса (без внешнего сервиса).
AI_RAG_VECTOR_LOCAL_MODE: Final[bool] = os.getenv("AI_RAG_VECTOR_LOCAL_MODE", "1") == "1"
# URL удалённого Qdrant (например, https://qdrant.example.com:6333).
AI_RAG_VECTOR_REMOTE_URL: Final[str] = os.getenv("AI_RAG_VECTOR_REMOTE_URL", "").strip()
# API-ключ удалённого Qdrant (если требуется сервером).
AI_RAG_VECTOR_REMOTE_API_KEY: Final[str] = os.getenv("AI_RAG_VECTOR_REMOTE_API_KEY", "")
# Таймаут запросов к удалённому Qdrant в секундах.
AI_RAG_VECTOR_REMOTE_TIMEOUT_SECONDS: Final[float] = float(
    os.getenv("AI_RAG_VECTOR_REMOTE_TIMEOUT_SECONDS", "5")
)
# Порог последовательных ошибок remote перед переключением на local.
AI_RAG_VECTOR_REMOTE_FAILURE_THRESHOLD: Final[int] = int(
    os.getenv("AI_RAG_VECTOR_REMOTE_FAILURE_THRESHOLD", "3")
)
# Время cooldown (секунды) перед повторной попыткой remote после failover.
AI_RAG_VECTOR_REMOTE_COOLDOWN_SECONDS: Final[int] = int(
    os.getenv("AI_RAG_VECTOR_REMOTE_COOLDOWN_SECONDS", "120")
)
# Путь к директории локального векторного хранилища.
AI_RAG_VECTOR_DB_PATH: Final[str] = os.getenv("AI_RAG_VECTOR_DB_PATH", "./data/qdrant")
# Имя коллекции чанков в векторном индексе.
AI_RAG_VECTOR_COLLECTION: Final[str] = os.getenv("AI_RAG_VECTOR_COLLECTION", "rag_chunks_v1")
# Имя отдельной коллекции summary-документов в векторном индексе.
# По умолчанию используется отдельная коллекция, чтобы не смешивать payload чанков и summary.
AI_RAG_SUMMARY_VECTOR_COLLECTION: Final[str] = os.getenv(
    "AI_RAG_SUMMARY_VECTOR_COLLECTION",
    "rag_document_summaries_v1",
)
# Имя коллекции для remote→local синхронизации Qdrant.
# По умолчанию наследует основную коллекцию AI_RAG_VECTOR_COLLECTION.
AI_RAG_VECTOR_SYNC_COLLECTION: Final[str] = os.getenv(
    "AI_RAG_VECTOR_SYNC_COLLECTION",
    AI_RAG_VECTOR_COLLECTION,
)
# Метрика расстояния в векторном индексе (например, cosine).
AI_RAG_VECTOR_DISTANCE: Final[str] = os.getenv("AI_RAG_VECTOR_DISTANCE", "cosine")
# Сколько top-кандидатов брать из векторного поиска.
AI_RAG_VECTOR_TOP_K: Final[int] = int(os.getenv("AI_RAG_VECTOR_TOP_K", "12"))
# Сколько top-документов брать из summary-векторного поиска на этапе prefilter.
# Если значение <= 0, используется AI_RAG_VECTOR_TOP_K.
AI_RAG_SUMMARY_VECTOR_TOP_K: Final[int] = int(os.getenv("AI_RAG_SUMMARY_VECTOR_TOP_K", "0"))
# Размер prefetch-выборки кандидатов до финального vector top-k.
AI_RAG_VECTOR_PREFETCH_K: Final[int] = int(os.getenv("AI_RAG_VECTOR_PREFETCH_K", "40"))
# Имя embedding-модели для расчёта векторов.
AI_RAG_VECTOR_EMBEDDING_MODEL: Final[str] = os.getenv("AI_RAG_VECTOR_EMBEDDING_MODEL", "BAAI/bge-m3")
# Устройство для инференса эмбеддингов (auto/cpu/cuda/mps).
AI_RAG_VECTOR_DEVICE: Final[str] = os.getenv("AI_RAG_VECTOR_DEVICE", "auto")
# Использовать fp16 при вычислении эмбеддингов (если поддерживается устройством).
AI_RAG_VECTOR_EMBEDDING_FP16: Final[bool] = os.getenv("AI_RAG_VECTOR_EMBEDDING_FP16", "0") == "1"
# Размер батча при вычислении эмбеддингов.
AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE: Final[int] = int(os.getenv("AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE", "8"))
# Максимальная длина текста для одного embedding-запроса (символов).
AI_RAG_VECTOR_EMBEDDING_MAX_CHARS: Final[int] = int(os.getenv("AI_RAG_VECTOR_EMBEDDING_MAX_CHARS", "6000"))
# Вес lexical-score в гибридной формуле ранжирования.
AI_RAG_VECTOR_LEXICAL_WEIGHT: Final[float] = float(os.getenv("AI_RAG_VECTOR_LEXICAL_WEIGHT", "0.45"))
# Вес semantic-score в гибридной формуле ранжирования.
AI_RAG_VECTOR_SEMANTIC_WEIGHT: Final[float] = float(os.getenv("AI_RAG_VECTOR_SEMANTIC_WEIGHT", "0.55"))

# Настройки ранжирования сертификационных Q/A в RAG
# Буст к score документа, если категория вопроса совпала с category-hint пользователя.
AI_RAG_CERTIFICATION_CATEGORY_BOOST: Final[float] = float(
    os.getenv("AI_RAG_CERTIFICATION_CATEGORY_BOOST", "0.35")
)
# Штраф к score для неактуальных/неактивных сертификационных вопросов.
AI_RAG_CERTIFICATION_STALE_PENALTY: Final[float] = float(
    os.getenv("AI_RAG_CERTIFICATION_STALE_PENALTY", "0.20")
)

# Лексический retrieval: режим ранжирования и нормализация русского текста
# Режим lexical scoring: legacy (coverage+density) или bm25.
AI_RAG_LEXICAL_SCORER: Final[str] = os.getenv("AI_RAG_LEXICAL_SCORER", "legacy")
# Ключ runtime-настройки режима lexical scoring в bot_settings.
AI_RAG_LEXICAL_SCORER_SETTING_KEY: Final[str] = "ai_rag_lexical_scorer"
# Параметр k1 для BM25.
AI_RAG_BM25_K1: Final[float] = float(os.getenv("AI_RAG_BM25_K1", "1.5"))
# Параметр b для BM25.
AI_RAG_BM25_B: Final[float] = float(os.getenv("AI_RAG_BM25_B", "0.75"))
# Включить нормализацию русских токенов (лемматизация/стемминг).
AI_RAG_RU_NORMALIZATION_ENABLED: Final[bool] = os.getenv("AI_RAG_RU_NORMALIZATION_ENABLED", "1") == "1"
# Ключ runtime-настройки нормализации русского текста в bot_settings.
AI_RAG_RU_NORMALIZATION_ENABLED_SETTING_KEY: Final[str] = "ai_rag_ru_normalization_enabled"
# Режим нормализации русского текста: lemma_then_stem, lemma_only, stem_only.
AI_RAG_RU_NORMALIZATION_MODE: Final[str] = os.getenv("AI_RAG_RU_NORMALIZATION_MODE", "lemma_then_stem")

# Стоп-слова для query preprocessing
# Удалять русские стоп-слова из запроса перед lexical scoring.
AI_RAG_STOPWORDS_ENABLED: Final[bool] = os.getenv("AI_RAG_STOPWORDS_ENABLED", "1") == "1"
# Ключ runtime-настройки стоп-слов в bot_settings.
AI_RAG_STOPWORDS_SETTING_KEY: Final[str] = "ai_rag_stopwords_enabled"

# Снятие шаблонных вопросительных паттернов ("что такое", "как работает" и т.д.)
# При включении из запроса удаляются типовые вопросительные конструкции,
# оставляя только предметную часть для lexical scoring.
AI_RAG_QUERY_PATTERN_STRIP_ENABLED: Final[bool] = os.getenv("AI_RAG_QUERY_PATTERN_STRIP_ENABLED", "1") == "1"
# Ключ runtime-настройки pattern-stripping в bot_settings.
AI_RAG_QUERY_PATTERN_STRIP_SETTING_KEY: Final[str] = "ai_rag_query_pattern_strip_enabled"

# Порог IDF-dampening для query-токенов в summary prefilter.
# Токены, встречающиеся более чем в данной доле summary (0..1), получают
# сниженный вес при BM25-scoring prefilter.
AI_RAG_PREFILTER_IDF_DAMPEN_RATIO: Final[float] = float(
    os.getenv("AI_RAG_PREFILTER_IDF_DAMPEN_RATIO", "0.8")
)
# Множитель для dampened-токенов (0..1). Чем ниже, тем сильнее подавление.
AI_RAG_PREFILTER_IDF_DAMPEN_FACTOR: Final[float] = float(
    os.getenv("AI_RAG_PREFILTER_IDF_DAMPEN_FACTOR", "0.1")
)

# HyDE (Hypothetical Document Embeddings)
# Включить генерацию гипотетического документа LLM для улучшения векторного поиска.
# LLM генерирует короткий ответ-гипотезу на запрос, и его эмбеддинг
# используется для vector search вместо эмбеддинга исходного вопроса.
AI_RAG_HYDE_ENABLED: Final[bool] = os.getenv("AI_RAG_HYDE_ENABLED", "0") == "1"
# Ключ runtime-настройки HyDE в bot_settings.
AI_RAG_HYDE_SETTING_KEY: Final[str] = "ai_rag_hyde_enabled"
# Максимальная длина гипотетического документа (символов).
AI_RAG_HYDE_MAX_CHARS: Final[int] = int(os.getenv("AI_RAG_HYDE_MAX_CHARS", "500"))
# TTL кэша HyDE-текстов (секунды).
AI_RAG_HYDE_CACHE_TTL_SECONDS: Final[int] = int(os.getenv("AI_RAG_HYDE_CACHE_TTL_SECONDS", "300"))
# Дополнять BM25 lexical scoring уникальными токенами из HyDE-текста.
# Если включено, токены из гипотетического документа (после фильтрации стоп-слов)
# добавляются к query-токенам для summary prefilter и chunk BM25 scoring.
AI_RAG_HYDE_LEXICAL_ENABLED: Final[bool] = os.getenv("AI_RAG_HYDE_LEXICAL_ENABLED", "1") == "1"
# Ключ runtime-настройки HyDE lexical в bot_settings.
AI_RAG_HYDE_LEXICAL_SETTING_KEY: Final[str] = "ai_rag_hyde_lexical_enabled"

# Включение header-aware HTML splitter для RAG chunking
# Флаг включения HTML splitter с учётом заголовков h1-h6.
AI_RAG_HTML_SPLITTER_ENABLED: Final[bool] = os.getenv("AI_RAG_HTML_SPLITTER_ENABLED", "1") == "1"
# Ключ настройки HTML splitter в bot_settings для runtime-переключения.
AI_RAG_HTML_SPLITTER_ENABLED_SETTING_KEY: Final[str] = "ai_rag_html_splitter_enabled"


def normalize_deepseek_model(model_name: str | None) -> str:
    """Нормализовать имя модели DeepSeek и вернуть безопасное значение."""
    normalized = (model_name or "").strip().lower()
    if normalized in ALLOWED_DEEPSEEK_MODELS:
        return normalized

    env_default = (DEEPSEEK_MODEL or "").strip().lower()
    if env_default in ALLOWED_DEEPSEEK_MODELS:
        return env_default

    return DEEPSEEK_MODEL_CHAT


def _safe_get_setting(setting_key: str) -> str | None:
    """Безопасно прочитать значение настройки из bot_settings по ключу."""
    try:
        from src.common import bot_settings
    except ImportError:
        return None

    try:
        value = bot_settings.get_setting(setting_key)
    except (AttributeError, TypeError, ValueError):
        value = None

    return value


def get_active_deepseek_model_for_classification() -> str:
    """
    Получить активную модель DeepSeek для классификации intent.

    Приоритет:
    1. Значение из bot_settings.ai_deepseek_model_classification
    2. Значение из bot_settings.ai_deepseek_model (legacy)
    3. Значение из переменной окружения DEEPSEEK_MODEL
    4. deepseek-chat
    """
    db_value = _safe_get_setting(AI_DEEPSEEK_MODEL_CLASSIFICATION_SETTING_KEY)
    if db_value:
        return normalize_deepseek_model(db_value)

    legacy_value = _safe_get_setting(AI_DEEPSEEK_MODEL_SETTING_KEY_LEGACY)
    return normalize_deepseek_model(legacy_value)


def get_active_deepseek_model_for_response() -> str:
    """
    Получить активную модель DeepSeek для генерации ответов (chat/RAG).

    Приоритет:
    1. Значение из bot_settings.ai_deepseek_model_response
    2. Значение из bot_settings.ai_deepseek_model (legacy)
    3. Значение из переменной окружения DEEPSEEK_MODEL
    4. deepseek-chat
    """
    db_value = _safe_get_setting(AI_DEEPSEEK_MODEL_RESPONSE_SETTING_KEY)
    if db_value:
        return normalize_deepseek_model(db_value)

    legacy_value = _safe_get_setting(AI_DEEPSEEK_MODEL_SETTING_KEY_LEGACY)
    return normalize_deepseek_model(legacy_value)


def get_active_deepseek_model() -> str:
    """Совместимость со старым API: активная модель ответов (chat/RAG)."""
    return get_active_deepseek_model_for_response()


def get_directory_ingest_summary_model_override() -> str | None:
    """Получить override-модель для summary в `rag_directory_ingest`.

    Возвращает `None`, если override не задан или значение не входит
    в whitelist поддерживаемых DeepSeek-моделей.
    """
    raw_value = (AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL or "").strip().lower()
    if not raw_value:
        return None

    if raw_value in ALLOWED_DEEPSEEK_MODELS:
        return raw_value

    return None


def is_rag_html_splitter_enabled() -> bool:
    """Проверить, включён ли header-aware HTML splitter для RAG."""
    db_value = _safe_get_setting(AI_RAG_HTML_SPLITTER_ENABLED_SETTING_KEY)
    if db_value is None:
        return AI_RAG_HTML_SPLITTER_ENABLED

    normalized = str(db_value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def get_rag_lexical_scorer() -> str:
    """Получить активный режим lexical scoring (`legacy` или `bm25`)."""
    db_value = _safe_get_setting(AI_RAG_LEXICAL_SCORER_SETTING_KEY)
    raw_value = db_value if db_value is not None else AI_RAG_LEXICAL_SCORER
    normalized = str(raw_value or "").strip().lower()
    if normalized in {"legacy", "bm25"}:
        return normalized
    return "legacy"


def is_rag_ru_normalization_enabled() -> bool:
    """Проверить, включена ли нормализация русских токенов для lexical retrieval."""
    db_value = _safe_get_setting(AI_RAG_RU_NORMALIZATION_ENABLED_SETTING_KEY)
    if db_value is None:
        return AI_RAG_RU_NORMALIZATION_ENABLED

    normalized = str(db_value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def get_rag_ru_normalization_mode() -> str:
    """Получить режим нормализации русских токенов."""
    normalized = str(AI_RAG_RU_NORMALIZATION_MODE or "").strip().lower()
    if normalized in {"lemma_then_stem", "lemma_only", "stem_only"}:
        return normalized
    return "lemma_then_stem"


def is_rag_stopwords_enabled() -> bool:
    """Проверить, включена ли фильтрация стоп-слов из запроса перед lexical scoring."""
    db_value = _safe_get_setting(AI_RAG_STOPWORDS_SETTING_KEY)
    if db_value is None:
        return AI_RAG_STOPWORDS_ENABLED

    normalized = str(db_value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def is_rag_query_pattern_strip_enabled() -> bool:
    """Проверить, включено ли снятие шаблонных вопросительных паттернов из запроса."""
    db_value = _safe_get_setting(AI_RAG_QUERY_PATTERN_STRIP_SETTING_KEY)
    if db_value is None:
        return AI_RAG_QUERY_PATTERN_STRIP_ENABLED

    normalized = str(db_value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def is_rag_hyde_enabled() -> bool:
    """Проверить, включена ли генерация гипотетического документа (HyDE) для vector search."""
    db_value = _safe_get_setting(AI_RAG_HYDE_SETTING_KEY)
    if db_value is None:
        return AI_RAG_HYDE_ENABLED

    normalized = str(db_value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def is_rag_hyde_lexical_enabled() -> bool:
    """Проверить, включено ли дополнение BM25 lexical scoring токенами из HyDE-текста."""
    db_value = _safe_get_setting(AI_RAG_HYDE_LEXICAL_SETTING_KEY)
    if db_value is None:
        return AI_RAG_HYDE_LEXICAL_ENABLED

    normalized = str(db_value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def is_rag_summary_vector_enabled() -> bool:
    """Проверить, включён ли summary-vector prefilter (по умолчанию следует AI_RAG_VECTOR_ENABLED)."""
    raw_value = os.getenv("AI_RAG_SUMMARY_VECTOR_ENABLED")
    if raw_value is None:
        return bool(AI_RAG_VECTOR_ENABLED)

    normalized = str(raw_value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def get_rag_summary_vector_top_k() -> int:
    """Получить top-k для summary-векторного prefilter с безопасным fallback."""
    configured = int(AI_RAG_SUMMARY_VECTOR_TOP_K)
    if configured > 0:
        return configured
    return max(1, int(AI_RAG_VECTOR_TOP_K))
