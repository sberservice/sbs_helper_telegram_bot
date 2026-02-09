"""
Модуль аттестации сотрудников

Модуль Telegram-бота для аттестации сотрудников с возможностями:
- Тестирование с ограничением времени
- Вопросы по категориям
- Ежемесячные рейтинги
- История попыток
- Админ-панель для управления вопросами и категориями
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
    Модуль аттестации сотрудников.
    
    Возможности:
    - Прохождение тестов с ограничением времени
    - Просмотр личного рейтинга и истории
    - Ежемесячные лидерборды
    - Админ-управление вопросами и категориями
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
        Вернуть пользовательские хендлеры модуля аттестации.
        
        Возвращает:
            Список хендлеров для тестирования и просмотра результатов
        """
        import re
        from telegram.ext import MessageHandler, CallbackQueryHandler, filters
        
        return [
            # Пользовательский хендлер диалога прохождения теста
            get_user_conversation_handler(),
            # Прямые обработчики кнопок меню
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
            # Колбэк-обработчик выбора категории топа
            CallbackQueryHandler(
                handle_top_category_selection,
                pattern="^cert_top_"
            ),
        ]
    
    def get_admin_handlers(self) -> List[BaseHandler]:
        """
        Вернуть административные хендлеры управления аттестацией.
        
        Возвращает:
            Список административных хендлеров
        """
        return [
            get_admin_conversation_handler(),
        ]
    
    def get_menu_button(self) -> Optional[str]:
        """
        Вернуть текст кнопки модуля для главного меню.
        
        Возвращает:
            Текст кнопки с эмодзи
        """
        return settings.MENU_BUTTON_TEXT
    
    async def handle_menu_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Обработать нажатие кнопки аттестации в меню.
        
        Аргументы:
            update: Объект Telegram Update
            context: Контекст Telegram
            
        Возвращает:
            True, если обработано
        """
        if update.message and update.message.text == settings.MENU_BUTTON_TEXT:
            await certification_submenu(update, context)
            return True
        return False
    
    def get_submenu_keyboard(self, user_id: int) -> Optional[ReplyKeyboardMarkup]:
        """
        Вернуть клавиатуру подменю для этого модуля.
        
        Аргументы:
            user_id: Telegram ID пользователя
            
        Возвращает:
            ReplyKeyboardMarkup в зависимости от роли пользователя
        """
        if check_if_user_admin(user_id):
            return keyboards.get_admin_submenu_keyboard()
        return keyboards.get_submenu_keyboard()
    
    def get_commands(self) -> Dict[str, str]:
        """
        Вернуть команды для меню бота.
        
        Возвращает:
            Словарь команда -> описание
        """
        return {
            "certification": "Начать аттестацию",
        }


# Экспорт класса модуля и ключевых компонентов
__all__ = [
    'CertificationModule',
    'settings',
    'messages',
    'keyboards',
]
