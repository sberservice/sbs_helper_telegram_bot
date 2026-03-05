"""
database_settings.py — настройки подключения к базе данных.

Единый источник правды для MySQL/MariaDB credentials.
Все компоненты проекта (бот, скрипты, prompt_tester) импортируют
настройки БД отсюда.
"""

from typing import Final
import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# Настройки подключения MySQL / MariaDB
# ─────────────────────────────────────────────────────────────

# Основные креды — всегда читаем из окружения
MYSQL_USER: Final[str] = os.getenv("MYSQL_USER", "dev_user")
MYSQL_PASSWORD: Final[str] = os.getenv("MYSQL_PASSWORD", "dev_password")
MYSQL_HOST: Final[str] = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT: Final[int] = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DATABASE: Final[str] = os.getenv("MYSQL_DATABASE", "myapp_dev")
