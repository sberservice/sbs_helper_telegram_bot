"""
News Module

Module for publishing news and announcements with broadcast support.

Features:
- Admin-managed categories
- MarkdownV2 formatted content
- Image and file attachments
- Silent or broadcast publishing
- Mandatory news with blocking
- Reaction buttons (like/love/dislike)
- Search and archive functionality
"""

from typing import List, Optional
from telegram import Update, BotCommand
from telegram.ext import BaseHandler, ContextTypes

from src.sbs_helper_telegram_bot.base_module import BotModule
from src.common.telegram_user import check_if_user_admin

from . import settings
from . import messages
from . import keyboards
from . import news_logic
from .news_bot_part import (
    get_news_user_handler,
    get_mandatory_ack_handler,
    news_entry,
)
from .admin_panel_bot_part import get_news_admin_handler


class NewsModule(BotModule):
    """
    News module implementation.
    
    Features:
    - Create and publish news articles
    - Categories for organizing news
    - Silent or broadcast publishing
    - Mandatory news with blocking
    - Reaction buttons
    - Archive and search
    """
    
    @property
    def name(self) -> str:
        """Return module name."""
        return settings.MODULE_NAME
    
    @property
    def description(self) -> str:
        """Return module description."""
        return settings.MODULE_DESCRIPTION
    
    @property
    def version(self) -> str:
        """Return module version."""
        return settings.MODULE_VERSION
    
    @property
    def author(self) -> str:
        """Return module author."""
        return settings.MODULE_AUTHOR
    
    def get_handlers(self) -> List[BaseHandler]:
        """
        Return user-facing handlers for this module.
        """
        return [
            get_news_user_handler(),
            get_mandatory_ack_handler(),  # Global handler for mandatory news ack
        ]
    
    def get_admin_handlers(self) -> List[BaseHandler]:
        """
        Return admin handlers for this module.
        """
        return [get_news_admin_handler()]
    
    def get_menu_button(self) -> Optional[str]:
        """
        Return menu button text for main menu.
        """
        return settings.MENU_BUTTON_TEXT
    
    async def handle_menu_button(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle menu button click.
        Delegates to news_entry handler.
        """
        await news_entry(update, context)
    
    def get_commands(self) -> List[BotCommand]:
        """
        Return bot commands for this module.
        """
        return [
            BotCommand("news", "Просмотреть новости")
        ]
    
    async def on_load(self) -> None:
        """Called when module is loaded."""
        # Module initialization - no setup required
    
    async def on_unload(self) -> None:
        """Called when module is unloaded."""
        # Module cleanup - no cleanup required


# Module singleton for easier access
_module_instance: Optional[NewsModule] = None


def get_module() -> NewsModule:
    """Get or create module instance."""
    global _module_instance
    if _module_instance is None:
        _module_instance = NewsModule()
    return _module_instance


# Export convenience functions
def get_unread_count(user_id: int) -> int:
    """Get unread news count for a user."""
    return news_logic.get_unread_count(user_id)


def get_unacked_mandatory_news(user_id: int):
    """Get unacknowledged mandatory news for a user."""
    return news_logic.get_unacked_mandatory_news(user_id)


def has_unacked_mandatory_news(user_id: int) -> bool:
    """Check if user has unacknowledged mandatory news."""
    return news_logic.has_unacked_mandatory_news(user_id)


def get_menu_button_with_badge(user_id: int) -> str:
    """
    Get menu button text with unread badge if applicable.
    
    Args:
        user_id: User ID to check unread count for
        
    Returns:
        Button text like "📰 Новости" or "📰 Новости (3)"
    """
    unread = get_unread_count(user_id)
    if unread > 0:
        return f"{settings.MENU_BUTTON_TEXT} ({unread})"
    return settings.MENU_BUTTON_TEXT
