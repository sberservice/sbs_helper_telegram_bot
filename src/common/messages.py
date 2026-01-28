"""
Common Messages

Contains only truly common messages used across the entire bot,
not specific to any module.

Module-specific messages should be in their respective module's messages.py file.
"""
# pylint: disable=line-too-long

# Welcome and authentication messages
MESSAGE_WELCOME = "👋 *Добро пожаловать в бот\-помощник инженера СберСервис\!*\n\nЭтот бот помогает:\n• ✅ Проверять заявки на соответствие требованиям \(функционал не окончательный, происходит наполнение правилами\)\n• 📸 Обрабатывать скриншоты карты из Спринта\n• 🔢 Искать коды ошибок UPOS с рекомендациями по устранению\n\n🔑 *Для начала работы введите инвайт\-код*\n\nКод можно получить у другого пользователя бота командой /invite\n\n📚 *GitHub:* https://github\.com/sberservice/sbs\_helper\_telegram\_bot"
MESSAGE_PLEASE_ENTER_INVITE = "Пожалуйста, введите ваш инвайт\\.\nЕго можно попросить у другого пользователя этого бота, если он введет команду /invite или выберет её из меню\\.\."

# Invite-related messages
MESSAGE_AVAILABLE_INVITES = "Доступные инвайты:"
MESSAGE_NO_INVITES = "У вас нет доступных инвайтов."
MESSAGE_WELCOME_SHORT = "Добро пожаловать!"
MESSAGE_INVITE_ISSUED = "Вам выдан инвайт. Вы можете им поделиться: {invite}"
MESSAGE_INVITE_ALREADY_USED = "Данный инвайт уже был использован. Пожалуйста, введите другой инвайт."
MESSAGE_NO_ADMIN_RIGHTS = "⛔ У вас нет прав администратора\\."

# Bot command descriptions
COMMAND_DESC_START = "Начать работу с ботом"
COMMAND_DESC_MENU = "Показать главное меню"
COMMAND_DESC_HELP = "Показать справку"

# Main menu messages
MESSAGE_MAIN_MENU = "🏠 *Главное меню*\n\nВыберите действие:"
MESSAGE_UNRECOGNIZED_INPUT = "🤔 Не понял вашу команду\\.\n\n*Используйте:*\n• Кнопки меню ниже\n• Команды бота \\(/menu, /validate\\)\n• Или /help для справки"

# Help message - overview of all modules
MESSAGE_MAIN_HELP = """❓ *Помощь*

*Модули бота:*

*✅ Валидация заявок*
Проверяет заявки на соответствие требованиям \\(функционал не окончательный, происходит наполнение правилами\\)\\.

*📸 Обработка скриншота*
Обрабатывает скриншоты карт\\. Отправьте изображение как файл \\(не фото\\), и бот выполнит необходимую обработку\\.

*🔢 UPOS Ошибки*
Поиск кодов ошибок системы UPOS с подробными описаниями и рекомендациями по устранению\\.

*🎫 Мои инвайты*
Показывает ваши доступные инвайт\\-коды, которыми вы можете поделиться с другими пользователями для предоставления доступа к боту\\.

*Основные команды бота:*
• `/start` \\- начать работу с ботом
• `/menu` \\- показать главное меню
• `/help` \\- показать эту справку

📚 *GitHub:* https://github\\.com/sberservice/sbs\\_helper\\_telegram\\_bot"""

# Settings menu message
MESSAGE_SETTINGS_MENU = "⚙️ *Настройки*\n\nВыберите действие:"

# Modules menu message
MESSAGE_MODULES_MENU = "⚡ *Функции бота*\n\nВыберите модуль:"

# Button labels for main menu
BUTTON_MODULES = "⚡ Начать работу"
BUTTON_SETTINGS = "⚙️ Настройки"
BUTTON_MAIN_MENU = "🏠 Главное меню"
BUTTON_MY_INVITES = "🎫 Мои инвайты"
BUTTON_HELP = "❓ Помощь"

# Module buttons
BUTTON_VALIDATE_TICKET = "✅ Валидация заявок"
BUTTON_SCREENSHOT = "📸 Обработать скриншот"
BUTTON_UPOS_ERRORS = "🔢 UPOS Ошибки"
BUTTON_CERTIFICATION = "📝 Аттестация"


def get_main_menu_keyboard(extra_buttons=None):
    """
    Build main menu keyboard with Modules and Settings buttons.
    
    Args:
        extra_buttons: Optional list of additional buttons to include
        
    Returns:
        ReplyKeyboardMarkup for main menu.
    """
    from telegram import ReplyKeyboardMarkup
    
    # Simplified main menu with just Modules and Settings
    buttons = [
        [BUTTON_MODULES, BUTTON_SETTINGS]
    ]
    
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_settings_menu_keyboard():
    """
    Build settings menu keyboard with invites, help, and back to main menu.
    
    Returns:
        ReplyKeyboardMarkup for settings menu.
    """
    from telegram import ReplyKeyboardMarkup
    
    buttons = [
        [BUTTON_MY_INVITES, BUTTON_HELP],
        [BUTTON_MAIN_MENU]
    ]
    
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_modules_menu_keyboard():
    """
    Build modules menu keyboard with all available bot modules.
    
    Returns:
        ReplyKeyboardMarkup for modules menu.
    """
    from telegram import ReplyKeyboardMarkup
    
    buttons = [
        [BUTTON_VALIDATE_TICKET, BUTTON_SCREENSHOT],
        [BUTTON_UPOS_ERRORS, BUTTON_CERTIFICATION],
        [BUTTON_MAIN_MENU]
    ]
    
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )
