"""
prompts.py — backward-compat stub.

DEPRECATED: Импортируйте из src.core.ai.prompts.
Этот файл перенаправляет все импорты в src.core.ai.prompts.
"""

import warnings as _warnings
from src.core.ai.prompts import *  # noqa: F401, F403

_warnings.warn(
    "Импорт из src.sbs_helper_telegram_bot.ai_router.prompts устарел. "
    "Используйте src.core.ai.prompts.",
    DeprecationWarning,
    stacklevel=2,
)
