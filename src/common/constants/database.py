"""
Константы, связанные с базой данных.

DEPRECATED: Импортируйте из config.database_settings.
Этот файл сохранён для обратной совместимости.
"""

import warnings as _warnings

from config.database_settings import (  # noqa: F401
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_DATABASE,
)

_warnings.warn(
    "Импорт из src.common.constants.database устарел. "
    "Используйте config.database_settings.",
    DeprecationWarning,
    stacklevel=2,
)
