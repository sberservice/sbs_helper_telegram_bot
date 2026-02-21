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

# Таймаут HTTP-запросов к LLM (секунды)
LLM_REQUEST_TIMEOUT: Final[int] = int(os.getenv("AI_LLM_REQUEST_TIMEOUT", "30"))

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
