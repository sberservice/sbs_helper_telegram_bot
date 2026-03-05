"""
qdrant_sync.py — backward-compat stub.

DEPRECATED: Импортируйте из src.core.ai.qdrant_sync.
Этот файл перенаправляет все импорты в src.core.ai.qdrant_sync.
"""

import warnings as _warnings
from src.core.ai.qdrant_sync import *  # noqa: F401, F403

_warnings.warn(
    "Импорт из src.sbs_helper_telegram_bot.ai_router.qdrant_sync устарел. "
    "Используйте src.core.ai.qdrant_sync.",
    DeprecationWarning,
    stacklevel=2,
)
