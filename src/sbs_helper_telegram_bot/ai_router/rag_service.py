"""
rag_service.py — backward-compat stub.

DEPRECATED: Импортируйте из src.core.ai.rag_service.
Этот файл перенаправляет все импорты в src.core.ai.rag_service.
"""

import warnings as _warnings
from src.core.ai.rag_service import *  # noqa: F401, F403
from src.core.ai.rag_service import _RAG_FIXED_QUERY_TERMS  # noqa: F401

_warnings.warn(
    "Импорт из src.sbs_helper_telegram_bot.ai_router.rag_service устарел. "
    "Используйте src.core.ai.rag_service.",
    DeprecationWarning,
    stacklevel=2,
)
