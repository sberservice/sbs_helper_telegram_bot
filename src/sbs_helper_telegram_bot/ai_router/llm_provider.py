"""
llm_provider.py — backward-compat stub.

DEPRECATED: Импортируйте из src.core.ai.llm_provider.
Этот файл перенаправляет все импорты в src.core.ai.llm_provider.
"""

import warnings as _warnings
from src.core.ai.llm_provider import *  # noqa: F401, F403

_warnings.warn(
    "Импорт из src.sbs_helper_telegram_bot.ai_router.llm_provider устарел. "
    "Используйте src.core.ai.llm_provider.",
    DeprecationWarning,
    stacklevel=2,
)
