"""
    messages.py
    Contains constant text messages used throughout the Telegram bot.
"""
# pylint: disable=line-too-long

MESSAGE_WELCOME =  "Привет\!\n*Бот принимает скриншоты только в виде файлов*\.\n\nВыберите изображение из галереи, нажмите 3 точки и выберите _Отправить как файл_, либо _Отправить без сжатия_\n\nПроект на GitHub: https://github\\.com/sberservice/sbs\\_helper\\_telegram\\_bot"
MESSAGE_PLEASE_ENTER_INVITE = "Пожалуйста, введите ваш инвайт.\nЕго можно попросить у другого пользователя этого бота, если он введет команду /invite или выберет её из меню."

# Ticket Validation Messages
MESSAGE_SEND_TICKET = "📋 Пожалуйста, отправьте текст заявки для проверки\\.\n\nВы можете скопировать текст заявки и вставить его в чат\\.\n\nДля отмены используйте /cancel"

MESSAGE_VALIDATION_SUCCESS = "✅ *Заявка прошла валидацию\\!*\n\nВсе обязательные поля заполнены корректно\\."

MESSAGE_VALIDATION_FAILED = "❌ *Заявка не прошла валидацию*\n\n*Найдены следующие ошибки:*\n{errors}\n\nПожалуйста, исправьте ошибки и отправьте заявку повторно\\.\nИспользуйте /template для просмотра образца заявки\\."

MESSAGE_VALIDATION_HELP = """*Проверка заявок*

*Доступные команды:*
• `/validate` \\- начать проверку заявки
• `/history` \\- история последних проверок
• `/template` \\- список доступных шаблонов
• `/template <название>` \\- показать конкретный шаблон

*Как пользоваться:*
1\\. Введите команду `/validate`
2\\. Скопируйте текст заявки
3\\. Отправьте текст в чат
4\\. Получите результат проверки

*Что проверяется:*
• Наличие системы налогообложения
• Код активации
• ИНН организации
• Адрес установки
• Другие обязательные поля

Если заявка не прошла проверку, бот укажет какие поля нужно исправить\\."""

MESSAGE_MAIN_MENU = "🏠 *Главное меню*\n\nВыберите действие:"
MESSAGE_VALIDATOR_SUBMENU = "✅ *Валидация заявок*\n\nВыберите действие:"
MESSAGE_IMAGE_INSTRUCTIONS = "📸 *Обработка скриншота*\n\nОтправьте изображение _как файл_ \\(не фото\\)\\:\n\n1\\. Выберите изображение из галереи\n2\\. Нажмите 3 точки\n3\\. Выберите _Отправить как файл_"
MESSAGE_UNRECOGNIZED_INPUT = "🤔 Не понял вашу команду\\.\n\n*Используйте:*\n• Кнопки меню ниже\n• Команды бота \\(/menu, /validate\\)\n• Или /help для справки"

MESSAGE_MAIN_HELP = """❓ *Помощь*

*Модули бота:*

*✅ Валидация заявок*
Проверяет заявки на соответствие требованиям\. Бот проверяет наличие всех обязательных полей, корректность ИНН, кода активации и других данных\. Сохраняет историю проверок и предоставляет шаблоны правильно заполненных заявок\.

*📸 Обработка скриншота*
Обрабатывает скриншоты карт\. Отправьте изображение как файл \\(не фото\\), и бот выполнит необходимую обработку\.

*🎫 Мои инвайты*
Показывает ваши доступные инвайт\-коды, которыми вы можете поделиться с другими пользователями для предоставления доступа к боту\.

*Команды бота:*
• `/start` \\- начать работу с ботом
• `/menu` \\- показать главное меню
• `/validate` \\- проверить заявку
• `/history` \\- история проверок
• `/template` \\- шаблоны заявок
• `/invite` \\- показать инвайт\-коды
• `/help_validate` \\- помощь по валидации"""


def get_main_menu_keyboard():
    """
    Build main menu keyboard with all bot functions.
    Returns ReplyKeyboardMarkup for main menu.
    """
    from telegram import ReplyKeyboardMarkup
    from config.settings import MAIN_MENU_BUTTONS
    
    return ReplyKeyboardMarkup(
        MAIN_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_validator_submenu_keyboard():
    """
    Build ticket validator submenu keyboard.
    Returns ReplyKeyboardMarkup for validator submenu.
    """
    from telegram import ReplyKeyboardMarkup
    from config.settings import VALIDATOR_SUBMENU_BUTTONS
    
    return ReplyKeyboardMarkup(
        VALIDATOR_SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_admin_validator_submenu_keyboard():
    """
    Build ticket validator submenu keyboard with admin panel button.
    Returns ReplyKeyboardMarkup for admin validator submenu.
    """
    from telegram import ReplyKeyboardMarkup
    from config.settings import ADMIN_VALIDATOR_SUBMENU_BUTTONS
    
    return ReplyKeyboardMarkup(
        ADMIN_VALIDATOR_SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_image_menu_keyboard():
    """
    Build image processing module menu keyboard.
    Returns ReplyKeyboardMarkup for image processing menu.
    """
    from telegram import ReplyKeyboardMarkup
    from config.settings import IMAGE_MENU_BUTTONS
    
    return ReplyKeyboardMarkup(
        IMAGE_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False
    )


# ===== ADMIN PANEL MESSAGES =====

MESSAGE_ADMIN_NOT_AUTHORIZED = "⛔ У вас нет прав администратора\\."

MESSAGE_ADMIN_MENU = """🔐 *Панель администратора*

Управление правилами валидации заявок\\.

Выберите действие:"""

MESSAGE_ADMIN_RULES_LIST = "📋 *Список правил валидации*\n\nВсего правил: {count}\n\n{rules}"

MESSAGE_ADMIN_RULE_DETAILS = """📝 *Правило: {name}*

*ID:* {id}
*Тип:* {rule_type}
*Паттерн:* `{pattern}`
*Сообщение об ошибке:* {error_message}
*Приоритет:* {priority}
*Статус:* {status}

*Применяется к типам заявок:*
{ticket_types}"""

MESSAGE_ADMIN_CREATE_RULE_NAME = "📝 Создание нового правила\\.\n\nВведите *название* правила \\(например: \"Проверка ИНН\"\\)\\.\n\nДля отмены используйте /cancel"

MESSAGE_ADMIN_CREATE_RULE_TYPE = """Выберите *тип* правила:

• *regex* \\- регулярное выражение
• *required\\_field* \\- обязательное поле
• *format* \\- формат \\(phone, email, date, inn\\)
• *length* \\- проверка длины \\(min:X,max:Y\\)
• *custom* \\- пользовательское"""

MESSAGE_ADMIN_CREATE_RULE_PATTERN = "Введите *паттерн* \\(регулярное выражение или спецификацию\\)\\.\n\n*Примеры:*\n• regex: `ИНН[:\\s]*\\\\d{{10,12}}`\n• format: `phone` или `date`\n• length: `min:10,max:1000`"

MESSAGE_ADMIN_CREATE_RULE_ERROR_MSG = "Введите *сообщение об ошибке*, которое увидит пользователь при невалидной заявке\\."

MESSAGE_ADMIN_CREATE_RULE_PRIORITY = "Введите *приоритет* правила \\(число от 0 до 100\\)\\.\n\nЧем выше число, тем раньше проверяется правило\\."

MESSAGE_ADMIN_RULE_CREATED = "✅ Правило *{name}* успешно создано\\!"

MESSAGE_ADMIN_RULE_DELETED = "🗑️ Правило *{name}* удалено\\.\n\nУдалено связей с типами заявок: {associations}"

MESSAGE_ADMIN_RULE_UPDATED = "✅ Правило *{name}* обновлено\\."

MESSAGE_ADMIN_RULE_TOGGLED = "✅ Правило *{name}* {status}\\."

MESSAGE_ADMIN_SELECT_TICKET_TYPE = "Выберите *тип заявки* для управления правилами:"

MESSAGE_ADMIN_TICKET_TYPE_RULES = """📋 *Тип заявки: {type_name}*

*Назначенные правила:*
{rules}

Выберите действие:"""

MESSAGE_ADMIN_RULE_ADDED_TO_TYPE = "✅ Правило *{rule_name}* добавлено к типу *{type_name}*\\."

MESSAGE_ADMIN_RULE_REMOVED_FROM_TYPE = "✅ Правило *{rule_name}* удалено из типа *{type_name}*\\."

MESSAGE_ADMIN_TEST_REGEX = "🔬 *Тестирование регулярного выражения*\n\nВведите паттерн для проверки\\.\n\nДля отмены используйте /cancel"

MESSAGE_ADMIN_TEST_REGEX_SAMPLE = "Введите *тестовый текст* для проверки паттерна:\n`{pattern}`"

MESSAGE_ADMIN_TEST_REGEX_RESULT = "🔬 *Результат тестирования*\n\n*Паттерн:* `{pattern}`\n\n{result}"

MESSAGE_ADMIN_INVALID_REGEX = "❌ Некорректное регулярное выражение: {error}"

MESSAGE_ADMIN_CONFIRM_DELETE = "⚠️ Вы уверены, что хотите удалить правило *{name}*?\n\nЭто также удалит все связи с типами заявок \\({count} связей\\)\\."

MESSAGE_ADMIN_OPERATION_CANCELLED = "❌ Операция отменена\\."

MESSAGE_ADMIN_INVALID_INPUT = "❌ Некорректный ввод\\. Попробуйте снова\\."

# Debug mode messages
MESSAGE_DEBUG_MODE_ENABLED = "🔍 *Режим отладки включен*\n\nТеперь при валидации заявок вы будете видеть подробную информацию о процессе определения типа заявки\\."

MESSAGE_DEBUG_MODE_DISABLED = "🔍 *Режим отладки выключен*\n\nПодробная информация о валидации больше не будет отображаться\\."

MESSAGE_DEBUG_MODE_NOT_ADMIN = "⛔ Режим отладки доступен только администраторам\\."


def get_admin_menu_keyboard():
    """
    Build admin panel main menu keyboard.
    Returns ReplyKeyboardMarkup for admin menu.
    """
    from telegram import ReplyKeyboardMarkup
    from config.settings import ADMIN_MENU_BUTTONS
    
    return ReplyKeyboardMarkup(
        ADMIN_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_admin_rules_keyboard():
    """
    Build admin rules management keyboard.
    Returns ReplyKeyboardMarkup for rules management.
    """
    from telegram import ReplyKeyboardMarkup
    from config.settings import ADMIN_RULES_BUTTONS
    
    return ReplyKeyboardMarkup(
        ADMIN_RULES_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False
    )

