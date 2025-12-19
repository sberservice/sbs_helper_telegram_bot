"""
Database-related constants.
Never hardcode real credentials in source code!
Use environment variables + fallback defaults for local dev.
"""

from typing import Final
import os
from dotenv import load_dotenv

load_dotenv()
# ─────────────────────────────────────────────────────────────
# MySQL / MariaDB connection settings
# ─────────────────────────────────────────────────────────────

# Core credentials – always read from environment
MYSQL_USER: Final[str] = os.getenv("MYSQL_USER", "dev_user")
MYSQL_PASSWORD: Final[str] = os.getenv("MYSQL_PASSWORD", "dev_password")
MYSQL_HOST: Final[str] = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT: Final[int] = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DATABASE: Final[str] = os.getenv("MYSQL_DATABASE", "myapp_dev")
