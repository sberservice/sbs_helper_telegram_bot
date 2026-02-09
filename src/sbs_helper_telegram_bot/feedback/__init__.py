"""
Модуль обратной связи

Позволяет пользователям отправлять отзывы и получать анонимные ответы от админов.
Личность админа НИКОГДА не раскрывается пользователям.
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
    Реализация модуля обратной связи.
    
    Возможности:
    - Пользователи могут отправлять отзывы по категориям
    - Ограничение частоты (1 отправка в час)
    - Поиск ссылок и блокировка
    - Админы могут просматривать и отвечать
    - Все ответы админов АНОНИМНЫ
    - Пользователи могут отслеживать статус обращения
    """
    
    @property
    def name(self) -> str:
        """Вернуть название модуля."""
        return settings.MODULE_NAME
    
    @property
    def description(self) -> str:
        """Вернуть описание модуля."""
        return settings.MODULE_DESCRIPTION
    
    @property
    def version(self) -> str:
        """Вернуть версию модуля."""
        return settings.MODULE_VERSION
    
    @property
    def author(self) -> str:
        """Вернуть автора модуля."""
        return settings.MODULE_AUTHOR
    
    def get_handlers(self) -> List[BaseHandler]:
        """
        Вернуть обработчики пользовательских сценариев модуля.
        """
        return [get_feedback_user_handler()]
    
    def get_admin_handlers(self) -> List[BaseHandler]:
        """
        Вернуть админ-обработчики для этого модуля.
        """
        return [get_feedback_admin_handler()]
    
    def get_menu_button(self) -> Optional[str]:
        """
        Вернуть текст кнопки для главного меню.
        """
        return settings.MENU_BUTTON_TEXT
    
    async def handle_menu_button(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Обработать нажатие кнопки меню.
        Делегирует обработчику feedback_entry.
        """
        await feedback_entry(update, context)
    
    def get_commands(self) -> List[BotCommand]:
        """
        Вернуть команды бота для этого модуля.
        """
        return [
            BotCommand("feedback", "Отправить отзыв или предложение")
        ]
    
    async def on_load(self) -> None:
        """Вызывается при загрузке модуля."""
        # Инициализация модуля — настройка не требуется
    
    async def on_unload(self) -> None:
        """Вызывается при выгрузке модуля."""
        # Очистка модуля — не требуется


# Экспорт модуля
__all__ = [
    'FeedbackModule',
    'settings',
    'messages',
    'keyboards',
    'get_feedback_user_handler',
    'get_feedback_admin_handler',
]
