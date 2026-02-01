"""
Common Messages

Contains only truly common messages used across the entire bot,
not specific to any module.

Module-specific messages should be in their respective module's messages.py file.
"""
# pylint: disable=line-too-long

from src.common.constants.sync import SYNC_INTERVAL_HOURS

# Welcome and authentication messages
MESSAGE_WELCOME = "👋 *Добро пожаловать в бот\-помощник инженера СберСервис\!*\n\nЭтот бот помогает:\n• ✅ Проверять заявки на соответствие требованиям \(функционал не окончательный, происходит наполнение правилами\)\n• 📸 Обрабатывать скриншоты карты из Спринта\n• 🔢 Искать коды ошибок UPOS с рекомендациями по устранению\n\n🔑 *Для начала работы введите инвайт\-код*\n\nКод можно получить у другого пользователя бота командой /invite\n\n📚 *GitHub:* https://github\.com/sberservice/sbs\_helper\_telegram\_bot"
MESSAGE_PLEASE_ENTER_INVITE = "Пожалуйста, введите ваш инвайт.\nЕго можно попросить у другого пользователя этого бота, если он введет команду /invite или выберет её из меню."

# Invite-related messages
MESSAGE_AVAILABLE_INVITES = "Доступные инвайты:"
MESSAGE_NO_INVITES = "У вас нет доступных инвайтов."
MESSAGE_WELCOME_SHORT = "Добро пожаловать!"
MESSAGE_WELCOME_PRE_INVITED = "🎉 Добро пожаловать! Вы были заранее добавлены в список пользователей бота."
MESSAGE_INVITE_ISSUED = "Вам выдан инвайт. Вы можете им поделиться: {invite}"
MESSAGE_INVITE_ALREADY_USED = "Данный инвайт уже был использован. Пожалуйста, введите другой инвайт."
MESSAGE_NO_ADMIN_RIGHTS = "⛔ У вас нет прав администратора\\."

# Invite system disabled message
def get_invite_system_disabled_message() -> str:
    """
    Get the invite system disabled message with dynamic sync interval.
    
    Returns:
        Formatted message with the actual sync interval from settings.
    """
    if SYNC_INTERVAL_HOURS == 24:
        interval_text = "ежедневно"
    elif SYNC_INTERVAL_HOURS < 24:
        interval_text = f"каждые {SYNC_INTERVAL_HOURS} час(а/ов)"
    else:
        days = round(SYNC_INTERVAL_HOURS / 24)
        interval_text = f"каждые {days} дня/дней"
    
    return f"""⚠️ В настоящий момент доступ к боту имеют только участники группы Telegram "Техподдержка POS СБС".

Если стали участником этой группы, ждите, список участников обновляется {interval_text}."""

# Keep backward compatibility - use function result as constant
MESSAGE_INVITE_SYSTEM_DISABLED = get_invite_system_disabled_message()

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

*📝 Аттестация*
Прохождение тестирования для проверки знаний по различным категориям\\. Система рейтингов и история попыток\\.

*⏱️ КТР \\(Коэффициент Трудозатрат\\)*
Поиск кодов КТР и получение информации о нормативном времени выполнения работ в минутах\\.

*📬 Обратная связь*
Отправка отзывов, предложений и вопросов команде поддержки с возможностью получения ответов\\.

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
BUTTON_BOT_ADMIN = "🛠️ Админ бота"
BUTTON_PROFILE = "🏆 Достижения"

# Module buttons - deprecated, now loaded from bot_settings.MODULE_CONFIG
# These constants remain for backward compatibility but are not used in keyboard generation
BUTTON_VALIDATE_TICKET = "✅ Валидация заявок"
BUTTON_SCREENSHOT = "📸 Обработать скриншот"
BUTTON_UPOS_ERRORS = "🔢 UPOS Ошибки"
BUTTON_CERTIFICATION = "📝 Аттестация"
BUTTON_KTR = "⏱️ КТР"
BUTTON_FEEDBACK = "📬 Обратная связь"
BUTTON_NEWS = "📰 Новости"


def get_main_menu_keyboard(is_admin: bool = False):
    """
    Build main menu keyboard with Modules and Settings buttons.
    For admins, includes the Bot Admin button.
    
    Args:
        is_admin: Whether the user is an admin
        
    Returns:
        ReplyKeyboardMarkup for main menu.
    """
    from telegram import ReplyKeyboardMarkup
    
    if is_admin:
        buttons = [
            [BUTTON_MODULES, BUTTON_PROFILE],
            [BUTTON_NEWS, BUTTON_SETTINGS],
            [BUTTON_BOT_ADMIN]
        ]
    else:
        buttons = [
            [BUTTON_MODULES, BUTTON_PROFILE],
            [BUTTON_NEWS, BUTTON_SETTINGS]
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
    Only shows enabled modules in configured order.
    
    The module configuration (order, labels, columns) is loaded from
    bot_settings.MODULE_CONFIG. To change module order or add new modules,
    modify the MODULE_CONFIG list in src/common/bot_settings.py.
    
    Returns:
        ReplyKeyboardMarkup for modules menu.
    """
    from telegram import ReplyKeyboardMarkup
    from src.common import bot_settings
    
    # Get enabled modules in configured order
    modules = bot_settings.get_modules_config(enabled_only=True)
    
    # Build button rows dynamically based on columns setting
    buttons = []
    current_row = []
    
    for module in modules:
        button_label = module['button_label']
        columns = module.get('columns', 2)  # Default to 2 columns
        
        # Add button to current row
        current_row.append(button_label)
        
        # If row is full (based on columns setting), start a new row
        if len(current_row) >= columns:
            buttons.append(current_row)
            current_row = []
    
    # Add any remaining buttons in the last row
    if current_row:
        buttons.append(current_row)
    
    # Always add main menu button at the bottom
    buttons.append([BUTTON_MAIN_MENU])
    
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )
