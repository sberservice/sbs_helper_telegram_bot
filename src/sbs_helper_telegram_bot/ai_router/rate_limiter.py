"""
rate_limiter.py — backward-compat stub.

DEPRECATED: Импортируйте из src.core.ai.rate_limiter.
Этот файл перенаправляет все импорты в src.core.ai.rate_limiter.
"""

import warnings as _warnings
from src.core.ai.rate_limiter import *  # noqa: F401, F403

_warnings.warn(
    "Импорт из src.sbs_helper_telegram_bot.ai_router.rate_limiter устарел. "
    "Используйте src.core.ai.rate_limiter.",
    DeprecationWarning,
    stacklevel=2,
)
