"""
circuit_breaker.py — backward-compat stub.

DEPRECATED: Импортируйте из src.core.ai.circuit_breaker.
Этот файл перенаправляет все импорты в src.core.ai.circuit_breaker.
"""

import warnings as _warnings
from src.core.ai.circuit_breaker import *  # noqa: F401, F403

_warnings.warn(
    "Импорт из src.sbs_helper_telegram_bot.ai_router.circuit_breaker устарел. "
    "Используйте src.core.ai.circuit_breaker.",
    DeprecationWarning,
    stacklevel=2,
)
