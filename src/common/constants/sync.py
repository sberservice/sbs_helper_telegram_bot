"""
Константы конфигурации синхронизации

Переменные окружения для скрипта синхронизации участников чата.
Использует Telethon (MTProto) для получения всех участников группы Telegram.
"""
from typing import Final
import os
from pathlib import Path
from dotenv import load_dotenv

# Сначала загружаем стандартный проектный .env в корне,
# затем fallback на legacy deploy-путь config/.env.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv(_PROJECT_ROOT / "config" / ".env")

# Учётные данные Telethon API (получить на https://my.telegram.org)
TELETHON_API_ID: Final[int] = int(os.getenv("TELETHON_API_ID", "0"))
TELETHON_API_HASH: Final[str] = os.getenv("TELETHON_API_HASH", "")

# ID группы/чата Telegram для синхронизации участников
# Можно узнать, добавив @userinfobot в группу, или из ссылки на группу
SYNC_CHAT_ID: Final[int] = int(os.getenv("SYNC_CHAT_ID", "0"))

# Как часто запускать синхронизацию (в часах)
SYNC_INTERVAL_HOURS: Final[int] = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))

# Имя сессии Telethon (хранится в корне проекта)
TELETHON_SESSION_NAME: Final[str] = os.getenv("TELETHON_SESSION_NAME", "chat_sync_session")

# Заметка, добавляемая при автосинхронизации пользователей
SYNC_AUTO_NOTE: Final[str] = "Auto-synced from Telegram group"

# ===========================================================================
# THE_HELPER — Telethon-скрипт мониторинга /help в группах
# ===========================================================================

# Имя сессии Telethon для THE_HELPER (отдельная от sync_chat_members)
HELPER_SESSION_NAME: Final[str] = os.getenv("HELPER_SESSION_NAME", "helper_session")

# Rate-limit: максимальное количество запросов одного пользователя за окно
HELPER_RATE_LIMIT_USER_MAX: Final[int] = int(os.getenv("HELPER_RATE_LIMIT_USER_MAX", "10"))

# Rate-limit: окно в секундах для пользователя
HELPER_RATE_LIMIT_USER_WINDOW: Final[int] = int(os.getenv("HELPER_RATE_LIMIT_USER_WINDOW", "60"))

# Rate-limit: максимальное количество запросов в группе за окно
HELPER_RATE_LIMIT_GROUP_MAX: Final[int] = int(os.getenv("HELPER_RATE_LIMIT_GROUP_MAX", "60"))

# Rate-limit: окно в секундах для группы
HELPER_RATE_LIMIT_GROUP_WINDOW: Final[int] = int(os.getenv("HELPER_RATE_LIMIT_GROUP_WINDOW", "300"))

# ===========================================================================
# GROUP_KNOWLEDGE — сбор знаний из Telegram-групп
# ===========================================================================

# Имя сессии Telethon для коллектора сообщений
GK_COLLECTOR_SESSION_NAME: Final[str] = os.getenv("GK_COLLECTOR_SESSION_NAME", "gk_collector_session")

# Имя сессии Telethon для автоответчика
GK_RESPONDER_SESSION_NAME: Final[str] = os.getenv("GK_RESPONDER_SESSION_NAME", "gk_responder_session")

# Rate-limit: максимальное число ответов одному пользователю за окно
GK_RATE_LIMIT_USER_MAX: Final[int] = int(os.getenv("GK_RATE_LIMIT_USER_MAX", "5"))

# Rate-limit: окно в секундах для пользователя
GK_RATE_LIMIT_USER_WINDOW: Final[int] = int(os.getenv("GK_RATE_LIMIT_USER_WINDOW", "120"))

# Rate-limit: максимальное число ответов в группе за окно
GK_RATE_LIMIT_GROUP_MAX: Final[int] = int(os.getenv("GK_RATE_LIMIT_GROUP_MAX", "30"))

# Rate-limit: окно в секундах для группы
GK_RATE_LIMIT_GROUP_WINDOW: Final[int] = int(os.getenv("GK_RATE_LIMIT_GROUP_WINDOW", "300"))
