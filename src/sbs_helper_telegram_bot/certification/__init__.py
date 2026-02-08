"""
Employee Certification Module

A Telegram bot module for employee certification testing with:
- Timed multiple-choice tests
- Category-based questions
- Monthly rankings
- Test history tracking
- Admin panel for question/category management
"""

from typing import List, Optional, Dict
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import BaseHandler, ContextTypes

from src.sbs_helper_telegram_bot.base_module import BotModule
from src.common.telegram_user import check_if_user_admin

from . import settings
from . import messages
from . import keyboards
from .certification_bot_part import (
    get_user_conversation_handler,
    certification_submenu,
    show_my_ranking,
    show_test_history,
    show_monthly_top,
    show_help,
    handle_top_category_selection
)
from .admin_panel_bot_part import get_admin_conversation_handler


class CertificationModule(BotModule):
    """
    Employee Certification Module.
    
    Provides functionality for:
    - Taking timed certification tests
    - Viewing personal rankings and history
    - Monthly leaderboards
    - Admin management of questions and categories
    """
    
    @property
    def name(self) -> str:
        return settings.MODULE_NAME
    
    @property
    def description(self) -> str:
        return settings.MODULE_DESCRIPTION
    
    @property
    def version(self) -> str:
        return settings.MODULE_VERSION
    
    @property
    def author(self) -> str:
        return settings.MODULE_AUTHOR
    
    def get_handlers(self) -> List[BaseHandler]:
        """
        Return user-facing handlers for certification.
        
        Returns:
            List of handlers for test taking and viewing results
        """
        import re
        from telegram.ext import MessageHandler, CallbackQueryHandler, filters
        
        return [
            # User conversation handler for test taking
            get_user_conversation_handler(),
            # Direct menu button handlers
            MessageHandler(
                filters.Regex(f"^{re.escape(settings.MENU_BUTTON_TEXT)}$"),
                certification_submenu
            ),
            MessageHandler(
                filters.Regex(f"^{re.escape(settings.BUTTON_MY_RANKING)}$"),
                show_my_ranking
            ),
            MessageHandler(
                filters.Regex(f"^{re.escape(settings.BUTTON_TEST_HISTORY)}$"),
                show_test_history
            ),
            MessageHandler(
                filters.Regex(f"^{re.escape(settings.BUTTON_MONTHLY_TOP)}$"),
                show_monthly_top
            ),
            # Callback handler for top category selection
            CallbackQueryHandler(
                handle_top_category_selection,
                pattern="^cert_top_"
            ),
        ]
    
    def get_admin_handlers(self) -> List[BaseHandler]:
        """
        Return admin handlers for certification management.
        
        Returns:
            List of admin handlers
        """
        return [
            get_admin_conversation_handler(),
        ]
    
    def get_menu_button(self) -> Optional[str]:
        """
        Return menu button text for main menu.
        
        Returns:
            Button text with emoji
        """
        return settings.MENU_BUTTON_TEXT
    
    async def handle_menu_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Handle when user clicks the certification menu button.
        
        Args:
            update: Telegram Update object
            context: Telegram context
            
        Returns:
            True if handled
        """
        if update.message and update.message.text == settings.MENU_BUTTON_TEXT:
            await certification_submenu(update, context)
            return True
        return False
    
    def get_submenu_keyboard(self, user_id: int) -> Optional[ReplyKeyboardMarkup]:
        """
        Return submenu keyboard for this module.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            ReplyKeyboardMarkup appropriate for user's role
        """
        if check_if_user_admin(user_id):
            return keyboards.get_admin_submenu_keyboard()
        return keyboards.get_submenu_keyboard()
    
    def get_commands(self) -> Dict[str, str]:
        """
        Return commands for bot menu.
        
        Returns:
            Dict of command -> description
        """
        return {
            "certification": "Начать аттестацию",
        }


# Export the module class and key components
__all__ = [
    'CertificationModule',
    'settings',
    'messages',
    'keyboards',
]
