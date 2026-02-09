"""
Модуль новостей

Модуль для публикации новостей и объявлений с поддержкой рассылок.

Возможности:
- Категории, управляемые администраторами
- Контент в формате MarkdownV2
- Вложения изображений и файлов
- Публикация без уведомлений или с рассылкой
- Обязательные новости с блокировкой
- Кнопки реакций (лайк/любовь/дизлайк)
- Поиск и архив
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
    Реализация модуля новостей.
    
    Возможности:
    - Создание и публикация новостей
    - Категории для группировки новостей
    - Публикация без уведомлений или с рассылкой
    - Обязательные новости с блокировкой
    - Кнопки реакций
    - Архив и поиск
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
        return [
            get_news_user_handler(),
            get_mandatory_ack_handler(),  # Глобальный обработчик обязательных подтверждений новостей
        ]
    
    def get_admin_handlers(self) -> List[BaseHandler]:
        """
        Вернуть админ-обработчики для этого модуля.
        """
        return [get_news_admin_handler()]
    
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
        Делегирует обработчику news_entry.
        """
        await news_entry(update, context)
    
    def get_commands(self) -> List[BotCommand]:
        """
        Вернуть команды бота для этого модуля.
        """
        return [
            BotCommand("news", "Просмотреть новости")
        ]
    
    async def on_load(self) -> None:
        """Вызывается при загрузке модуля."""
        # Инициализация модуля — настройка не требуется
    
    async def on_unload(self) -> None:
        """Вызывается при выгрузке модуля."""
        # Очистка модуля — не требуется


# Синглтон модуля для удобного доступа
_module_instance: Optional[NewsModule] = None


def get_module() -> NewsModule:
    """Получить или создать экземпляр модуля."""
    global _module_instance
    if _module_instance is None:
        _module_instance = NewsModule()
    return _module_instance


# Экспорт вспомогательных функций
def get_unread_count(user_id: int) -> int:
    """Получить количество непрочитанных новостей для пользователя."""
    return news_logic.get_unread_count(user_id)


def get_unacked_mandatory_news(user_id: int):
    """Получить неподтверждённые обязательные новости для пользователя."""
    return news_logic.get_unacked_mandatory_news(user_id)


def has_unacked_mandatory_news(user_id: int) -> bool:
    """Проверить, есть ли у пользователя неподтверждённые обязательные новости."""
    return news_logic.has_unacked_mandatory_news(user_id)


def get_menu_button_with_badge(user_id: int) -> str:
    """
    Получить текст кнопки меню с бейджем непрочитанных, если нужно.
    
    Args:
        user_id: ID пользователя для проверки количества непрочитанных
        
    Returns:
        Текст кнопки вида "📰 Новости" или "📰 Новости (3)"
    """
    unread = get_unread_count(user_id)
    if unread > 0:
        return f"{settings.MENU_BUTTON_TEXT} ({unread})"
    return settings.MENU_BUTTON_TEXT
