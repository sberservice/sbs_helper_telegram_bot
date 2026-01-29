"""
Feedback Module

Allows users to submit feedback and receive anonymous replies from admins.
Admin identity is NEVER exposed to users.
"""

from typing import List, Optional
from telegram import Update, BotCommand
from telegram.ext import BaseHandler, ContextTypes

from src.sbs_helper_telegram_bot.base_module import BotModule
from src.common.telegram_user import check_if_user_admin

from . import settings
from . import messages
from . import keyboards
from .feedback_bot_part import (
    get_feedback_user_handler,
    feedback_entry,
)
from .admin_panel_bot_part import get_feedback_admin_handler


class FeedbackModule(BotModule):
    """
    Feedback module implementation.
    
    Features:
    - Users can submit categorized feedback
    - Rate limiting (1 submission per hour)
    - Link detection and blocking
    - Admins can view and respond to feedback
    - All admin responses are ANONYMOUS
    - Users can track their feedback status
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
        return [get_feedback_user_handler()]
    
    def get_admin_handlers(self) -> List[BaseHandler]:
        """
        Return admin handlers for this module.
        """
        return [get_feedback_admin_handler()]
    
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
        Delegates to feedback_entry handler.
        """
        await feedback_entry(update, context)
    
    def get_commands(self) -> List[BotCommand]:
        """
        Return bot commands for this module.
        """
        return [
            BotCommand("feedback", "Отправить отзыв или предложение")
        ]
    
    async def on_load(self) -> None:
        """Called when module is loaded."""
        # Module initialization - no setup required
    
    async def on_unload(self) -> None:
        """Called when module is unloaded."""
        # Module cleanup - no cleanup required


# Module exports
__all__ = [
    'FeedbackModule',
    'settings',
    'messages',
    'keyboards',
    'get_feedback_user_handler',
    'get_feedback_admin_handler',
]
