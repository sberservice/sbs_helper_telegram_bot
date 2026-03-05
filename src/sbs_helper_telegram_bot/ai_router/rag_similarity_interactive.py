"""
rag_similarity_interactive.py — backward-compat stub.

DEPRECATED: Импортируйте из src.core.ai.rag_similarity_interactive.
Этот файл перенаправляет все импорты в src.core.ai.rag_similarity_interactive.
"""

import warnings as _warnings
from src.core.ai.rag_similarity_interactive import *  # noqa: F401, F403
from src.core.ai.rag_similarity_interactive import (  # noqa: F401
    _fmt_score,
    _bar,
    _verdict_str,
    _truncate,
    _parse_input,
    _setup_readline,
    _save_readline_history,
)

_warnings.warn(
    "Импорт из src.sbs_helper_telegram_bot.ai_router.rag_similarity_interactive устарел. "
    "Используйте src.core.ai.rag_similarity_interactive.",
    DeprecationWarning,
    stacklevel=2,
)
