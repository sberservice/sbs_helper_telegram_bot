"""
Sync Configuration Constants

Environment variables for the chat members sync script.
Uses Telethon (MTProto) to fetch all members from a Telegram group.
"""
from typing import Final
import os
from dotenv import load_dotenv

load_dotenv()

# Telethon API credentials (get from https://my.telegram.org)
TELETHON_API_ID: Final[int] = int(os.getenv("TELETHON_API_ID", "0"))
TELETHON_API_HASH: Final[str] = os.getenv("TELETHON_API_HASH", "")

# Telegram group/chat ID to sync members from
# Can be found by adding @userinfobot to the group or from the group link
SYNC_CHAT_ID: Final[int] = int(os.getenv("SYNC_CHAT_ID", "0"))

# How often to run the sync (in hours)
SYNC_INTERVAL_HOURS: Final[int] = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))

# Session name for Telethon (stored in project root)
TELETHON_SESSION_NAME: Final[str] = os.getenv("TELETHON_SESSION_NAME", "chat_sync_session")

# Note to add when auto-syncing users
SYNC_AUTO_NOTE: Final[str] = "Auto-synced from Telegram group"
