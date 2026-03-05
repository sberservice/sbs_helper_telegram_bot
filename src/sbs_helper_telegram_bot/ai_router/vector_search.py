"""
vector_search.py — backward-compat stub.

DEPRECATED: Импортируйте из src.core.ai.vector_search.
Этот файл перенаправляет все импорты в src.core.ai.vector_search.
"""

import warnings as _warnings
from src.core.ai.vector_search import *  # noqa: F401, F403

_warnings.warn(
    "Импорт из src.sbs_helper_telegram_bot.ai_router.vector_search устарел. "
    "Используйте src.core.ai.vector_search.",
    DeprecationWarning,
    stacklevel=2,
)
