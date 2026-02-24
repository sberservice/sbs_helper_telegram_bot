"""
settings.py — настройки модуля AI-маршрутизации.

Содержит конфигурационные константы, ключи настроек, тексты кнопок
и пороговые значения для AI-классификации.
"""

from typing import Final
import os


# =============================================
# Идентификаторы модуля
# =============================================

AI_MODULE_KEY: Final[str] = "ai_router"
AI_SETTING_KEY: Final[str] = "module_ai_router_enabled"

# =============================================
# Настройки LLM-провайдера
# =============================================

AI_PROVIDER: Final[str] = os.getenv("AI_PROVIDER", "deepseek")
DEEPSEEK_API_KEY: Final[str] = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: Final[str] = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL: Final[str] = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Ключи настроек модели в bot_settings (переключаются из админ-панели)
AI_DEEPSEEK_MODEL_SETTING_KEY_LEGACY: Final[str] = "ai_deepseek_model"
AI_DEEPSEEK_MODEL_CLASSIFICATION_SETTING_KEY: Final[str] = "ai_deepseek_model_classification"
AI_DEEPSEEK_MODEL_RESPONSE_SETTING_KEY: Final[str] = "ai_deepseek_model_response"

# Поддерживаемые модели DeepSeek для runtime-переключения
DEEPSEEK_MODEL_CHAT: Final[str] = "deepseek-chat"
DEEPSEEK_MODEL_REASONER: Final[str] = "deepseek-reasoner"
ALLOWED_DEEPSEEK_MODELS: Final[tuple[str, ...]] = (
    DEEPSEEK_MODEL_CHAT,
    DEEPSEEK_MODEL_REASONER,
)

# Таймаут HTTP-запросов к LLM (секунды)
LLM_REQUEST_TIMEOUT: Final[int] = int(os.getenv("AI_LLM_REQUEST_TIMEOUT", "30"))

# Логирование prompt/response модели
AI_LOG_MODEL_IO: Final[bool] = os.getenv("AI_LOG_MODEL_IO", "1") == "1"
AI_LOG_MODEL_IO_MAX_CHARS: Final[int] = int(os.getenv("AI_LOG_MODEL_IO_MAX_CHARS", "8000"))
AI_MODEL_IO_DB_LOG_ENABLED: Final[bool] = os.getenv("AI_MODEL_IO_DB_LOG_ENABLED", "1") == "1"
AI_MODEL_IO_DB_RETENTION_DAYS: Final[int] = int(os.getenv("AI_MODEL_IO_DB_RETENTION_DAYS", "30"))

# =============================================
# Пороги уверенности
# =============================================

# Минимальный порог уверенности для маршрутизации к модулю
CONFIDENCE_THRESHOLD: Final[float] = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.6"))

# Порог уверенности для свободного chat-ответа (ниже — показываем MESSAGE_UNRECOGNIZED_INPUT)
CHAT_CONFIDENCE_THRESHOLD: Final[float] = float(os.getenv("AI_CHAT_CONFIDENCE_THRESHOLD", "0.3"))

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
AI_RAG_MAX_FILE_SIZE_MB: Final[int] = int(os.getenv("AI_RAG_MAX_FILE_SIZE_MB", "20"))
AI_RAG_MAX_CHUNKS_PER_DOC: Final[int] = int(os.getenv("AI_RAG_MAX_CHUNKS_PER_DOC", "500"))

# Параметры chunking
AI_RAG_CHUNK_SIZE: Final[int] = int(os.getenv("AI_RAG_CHUNK_SIZE", "1000"))
AI_RAG_CHUNK_OVERLAP: Final[int] = int(os.getenv("AI_RAG_CHUNK_OVERLAP", "150"))

# Параметры retrieval. Значение по умолчанию AI_RAG_TOP_K=5
AI_RAG_TOP_K: Final[int] = int(os.getenv("AI_RAG_TOP_K", "8")) 
AI_RAG_MAX_CONTEXT_CHARS: Final[int] = int(os.getenv("AI_RAG_MAX_CONTEXT_CHARS", "14000"))

# AI-summary для документов (используется при ingest и retrieval)
AI_RAG_SUMMARY_ENABLED: Final[bool] = os.getenv("AI_RAG_SUMMARY_ENABLED", "1") == "1"
AI_RAG_SUMMARY_INPUT_MAX_CHARS: Final[int] = int(os.getenv("AI_RAG_SUMMARY_INPUT_MAX_CHARS", "12000"))
AI_RAG_SUMMARY_MAX_CHARS: Final[int] = int(os.getenv("AI_RAG_SUMMARY_MAX_CHARS", "1200"))
AI_RAG_PREFILTER_TOP_DOCS: Final[int] = int(os.getenv("AI_RAG_PREFILTER_TOP_DOCS", "12"))
AI_RAG_PROMPT_SUMMARY_DOCS: Final[int] = int(os.getenv("AI_RAG_PROMPT_SUMMARY_DOCS", "3"))

# TTL-кэш ответов RAG (секунды)
AI_RAG_CACHE_TTL_SECONDS: Final[int] = int(os.getenv("AI_RAG_CACHE_TTL_SECONDS", "300"))

# Векторный retrieval (локальный индекс и локальная embedding-модель)
AI_RAG_VECTOR_ENABLED: Final[bool] = os.getenv("AI_RAG_VECTOR_ENABLED", "0") == "1"
AI_RAG_HYBRID_ENABLED: Final[bool] = os.getenv("AI_RAG_HYBRID_ENABLED", "1") == "1"
AI_RAG_VECTOR_LOCAL_MODE: Final[bool] = os.getenv("AI_RAG_VECTOR_LOCAL_MODE", "1") == "1"
AI_RAG_VECTOR_DB_PATH: Final[str] = os.getenv("AI_RAG_VECTOR_DB_PATH", "./data/qdrant")
AI_RAG_VECTOR_COLLECTION: Final[str] = os.getenv("AI_RAG_VECTOR_COLLECTION", "rag_chunks_v1")
AI_RAG_VECTOR_DISTANCE: Final[str] = os.getenv("AI_RAG_VECTOR_DISTANCE", "cosine")
AI_RAG_VECTOR_TOP_K: Final[int] = int(os.getenv("AI_RAG_VECTOR_TOP_K", "12"))
AI_RAG_VECTOR_PREFETCH_K: Final[int] = int(os.getenv("AI_RAG_VECTOR_PREFETCH_K", "40"))
AI_RAG_VECTOR_EMBEDDING_MODEL: Final[str] = os.getenv("AI_RAG_VECTOR_EMBEDDING_MODEL", "BAAI/bge-m3")
AI_RAG_VECTOR_DEVICE: Final[str] = os.getenv("AI_RAG_VECTOR_DEVICE", "auto")
AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE: Final[int] = int(os.getenv("AI_RAG_VECTOR_EMBEDDING_BATCH_SIZE", "8"))
AI_RAG_VECTOR_EMBEDDING_MAX_CHARS: Final[int] = int(os.getenv("AI_RAG_VECTOR_EMBEDDING_MAX_CHARS", "6000"))
AI_RAG_VECTOR_LEXICAL_WEIGHT: Final[float] = float(os.getenv("AI_RAG_VECTOR_LEXICAL_WEIGHT", "0.45"))
AI_RAG_VECTOR_SEMANTIC_WEIGHT: Final[float] = float(os.getenv("AI_RAG_VECTOR_SEMANTIC_WEIGHT", "0.55"))

# Включение header-aware HTML splitter для RAG chunking
AI_RAG_HTML_SPLITTER_ENABLED: Final[bool] = os.getenv("AI_RAG_HTML_SPLITTER_ENABLED", "1") == "1"
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


def is_rag_html_splitter_enabled() -> bool:
    """Проверить, включён ли header-aware HTML splitter для RAG."""
    db_value = _safe_get_setting(AI_RAG_HTML_SPLITTER_ENABLED_SETTING_KEY)
    if db_value is None:
        return AI_RAG_HTML_SPLITTER_ENABLED

    normalized = str(db_value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}
