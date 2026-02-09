"""
Константы конфигурации синхронизации

Переменные окружения для скрипта синхронизации участников чата.
Использует Telethon (MTProto) для получения всех участников группы Telegram.
"""
from typing import Final
import os
from dotenv import load_dotenv

load_dotenv()

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
