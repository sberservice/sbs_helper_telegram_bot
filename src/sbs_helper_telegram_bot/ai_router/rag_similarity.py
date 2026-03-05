"""
rag_similarity.py — backward-compat stub.

DEPRECATED: Импортируйте из src.core.ai.rag_similarity.
Этот файл перенаправляет все импорты в src.core.ai.rag_similarity.
"""

import warnings as _warnings
from src.core.ai.rag_similarity import *  # noqa: F401, F403

_warnings.warn(
    "Импорт из src.sbs_helper_telegram_bot.ai_router.rag_similarity устарел. "
    "Используйте src.core.ai.rag_similarity.",
    DeprecationWarning,
    stacklevel=2,
)
