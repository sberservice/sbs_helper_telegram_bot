"""
context_manager.py — backward-compat stub.

DEPRECATED: Импортируйте из src.core.ai.context_manager.
Этот файл перенаправляет все импорты в src.core.ai.context_manager.
"""

import warnings as _warnings
from src.core.ai.context_manager import *  # noqa: F401, F403

_warnings.warn(
    "Импорт из src.sbs_helper_telegram_bot.ai_router.context_manager устарел. "
    "Используйте src.core.ai.context_manager.",
    DeprecationWarning,
    stacklevel=2,
)
