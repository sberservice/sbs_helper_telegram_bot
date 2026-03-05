"""
settings.py — настройки модуля AI-маршрутизации (Telegram-бот).

Содержит идентификаторы модуля. Все AI/RAG настройки вынесены
в config.ai_settings и реэкспортируются для обратной совместимости.
"""

from typing import Final

# Реэкспорт всех AI/RAG настроек из config.ai_settings
# для обратной совместимости с существующими импортами.
# Новый код должен импортировать из config.ai_settings.
from config.ai_settings import *  # noqa: F401, F403
from config.ai_settings import _safe_get_setting  # noqa: F401

# =============================================
# Идентификаторы модуля (бот-специфичные)
# =============================================

# Ключ модуля AI-роутера в общей конфигурации модулей.
AI_MODULE_KEY: Final[str] = "ai_router"
# Ключ флага включения/выключения AI-роутера в таблице bot_settings.
AI_SETTING_KEY: Final[str] = "module_ai_router_enabled"
