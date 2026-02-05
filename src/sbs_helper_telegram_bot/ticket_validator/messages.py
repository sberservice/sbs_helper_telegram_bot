"""
Ticket Validator Module Messages

All user-facing messages for the ticket validation module.
Messages use Telegram MarkdownV2 format where needed.
"""
# pylint: disable=line-too-long
# Note: Double backslashes are intentional for Telegram MarkdownV2 escaping

from typing import List, Tuple
import src.common.database as database

# ===== USER MESSAGES =====

MESSAGE_SEND_TICKET = "📋 Пожалуйста, отправьте текст заявки для проверки\\.\n\nВы можете скопировать текст заявки и вставить его в чат\\.\n\nДля отмены используйте /cancel или любую кнопку меню\\."

MESSAGE_VALIDATION_CANCELLED = "❌ Проверка заявки отменена\\."

MESSAGE_VALIDATION_SUCCESS = "✅ *Заявка прошла валидацию\\!*\n\nВсе обязательные поля заполнены корректно\\."

MESSAGE_VALIDATION_FAILED = "❌ *Заявка не прошла валидацию*\n\n*Найдены следующие ошибки:*\n{errors}\n\nПожалуйста, исправьте ошибки и отправьте заявку повторно\\."


def _escape_markdown_v2(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.
    
    Args:
        text: Text to escape
        
    Returns:
        Escaped text
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def _get_stats() -> Tuple[int, int]:
    """
    Get counts of active rules and ticket types from the database.
    
    Returns:
        Tuple of (rules_count, ticket_types_count)
    """
    rules_count = 0
    ticket_types_count = 0
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as cnt 
                    FROM ticket_validator_validation_rules 
                    WHERE active = 1
                """)
                result = cursor.fetchone()
                if result:
                    rules_count = result['cnt']
                
                cursor.execute("""
                    SELECT COUNT(*) as cnt 
                    FROM ticket_validator_ticket_types 
                    WHERE active = 1
                """)
                result = cursor.fetchone()
                if result:
                    ticket_types_count = result['cnt']
    except Exception:
        pass
    return rules_count, ticket_types_count


def get_submenu_message() -> str:
    """
    Build submenu message with statistics.
    
    Returns:
        Formatted message for MarkdownV2
    """
    rules_count, ticket_types_count = _get_stats()
    return (
        "✅ *Валидация заявок*\n\n"
        f"📊 В базе: *{rules_count}* правил для *{ticket_types_count}* типов заявок"
        "\n\nВыберите действие:"
    )


def _get_ticket_types() -> List[str]:
    """
    Load all active ticket types from the database.
    
    Returns:
        List of ticket type names
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT type_name 
                    FROM ticket_validator_ticket_types 
                    WHERE active = 1
                    ORDER BY type_name
                """)
                results = cursor.fetchall()
                return [row['type_name'] for row in results]
    except Exception:
        return []


def _get_validation_rules() -> List[str]:
    """
    Load all active validation rules from the database.
    
    Returns:
        List of rule names
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT rule_name 
                    FROM ticket_validator_validation_rules 
                    WHERE active = 1
                    ORDER BY priority DESC, id ASC
                """)
                results = cursor.fetchall()
                return [row['rule_name'] for row in results]
    except Exception:
        return []


def get_validation_help_message() -> str:
    """
    Generate the validation help message with dynamic content from the database.
    
    Returns:
        Formatted help message with ticket types and validation rules
    """
    ticket_types = _get_ticket_types()
    validation_rules = _get_validation_rules()
    
    # Build ticket types section
    if ticket_types:
        ticket_types_text = "*Типы заявок:*\n"
        for tt in ticket_types:
            ticket_types_text += f"• {_escape_markdown_v2(tt)}\n"
    else:
        ticket_types_text = "*Типы заявок:* не настроены\n"
    
    # Build validation rules section (limit to 10)
    if validation_rules:
        rules_text = "*Проверяемые правила:*\n"
        display_rules = validation_rules[:10]
        for rule in display_rules:
            rules_text += f"• {_escape_markdown_v2(rule)}\n"
        
        # Add "и другие N шт" if there are more than 10 rules
        remaining = len(validation_rules) - 10
        if remaining > 0:
            rules_text += f"• и другие {remaining} шт\\.\n"
    else:
        rules_text = "*Проверяемые правила:* не настроены\n"
    
    return f"""*Проверка заявок*

*Доступные команды:*
• /validate \\- начать проверку заявки

*Как пользоваться:*
1\\. Введите команду /validate
2\\. Скопируйте текст заявки
3\\. Отправьте текст в чат
4\\. Получите результат проверки

*Что проверяется:*

{ticket_types_text}
{rules_text}
"""


# For backward compatibility, provide a static message that falls back to dynamic generation
MESSAGE_VALIDATION_HELP = get_validation_help_message()

MESSAGE_SUBMENU = "✅ *Валидация заявок*\n\nВыберите действие:"

MESSAGE_CANCEL = "❌ Операция отменена\\."

# Debug mode messages
MESSAGE_DEBUG_MODE_ENABLED = "🔍 *Режим отладки включен*\n\nТеперь при валидации заявок вы будете видеть подробную информацию о процессе определения типа заявки\\."

MESSAGE_DEBUG_MODE_DISABLED = "🔍 *Режим отладки выключен*\n\nПодробная информация о валидации больше не будет отображаться\\."

MESSAGE_DEBUG_MODE_NOT_ADMIN = "⛔ Режим отладки доступен только администраторам\\."


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

*Ключевые слова:*
{keywords}

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


# ===== ADMIN TEST TEMPLATES MESSAGES =====

MESSAGE_ADMIN_TEMPLATES_MENU = """🧪 *Тестовые шаблоны*

Шаблоны используются для автоматической проверки правил валидации\\.

Создайте шаблон с образцом заявки, укажите какие правила он должен тестировать и ожидаемые результаты \\(пройдёт/провалится\\)\\.

Выберите действие:"""

MESSAGE_ADMIN_TEMPLATES_LIST = "🧪 *Тестовые шаблоны*\n\nВсего шаблонов: {count}\n\nНажмите на шаблон для управления:"

MESSAGE_ADMIN_TEMPLATE_DETAILS = """🧪 *Шаблон: {name}*

*ID:* {id}
*Описание:* {description}
*Тип заявки:* {ticket_type}
*Ожидаемый результат:* {expected_result}
*Статус:* {status}

*Правила для тестирования:* {rule_count}
{rules_list}"""

MESSAGE_ADMIN_CREATE_TEMPLATE_NAME = "📝 Создание тестового шаблона\\.\n\nВведите *название* шаблона \\(например: \"Тест ИНН \\- валидный\"\\)\\.\n\nДля отмены используйте /cancel"

MESSAGE_ADMIN_CREATE_TEMPLATE_TEXT = "Введите *текст образца заявки* для тестирования\\.\n\nЭто должен быть реальный пример заявки, на которой будут проверяться правила\\."

MESSAGE_ADMIN_CREATE_TEMPLATE_DESC = "Введите *описание* шаблона \\(что он проверяет\\)\\."

MESSAGE_ADMIN_CREATE_TEMPLATE_EXPECTED = """Выберите *ожидаемый результат* валидации:

• *pass* \\- заявка должна пройти валидацию
• *fail* \\- заявка должна провалить валидацию"""

MESSAGE_ADMIN_TEMPLATE_CREATED = "✅ Тестовый шаблон *{name}* успешно создан\\!\n\nТеперь добавьте правила, которые он должен тестировать\\."

MESSAGE_ADMIN_TEMPLATE_DELETED = "🗑️ Шаблон *{name}* удалён\\.\n\nУдалено ожиданий правил: {expectations}"

MESSAGE_ADMIN_TEMPLATE_TOGGLED = "✅ Шаблон *{name}* {status}\\."

MESSAGE_ADMIN_ADD_RULE_TO_TEMPLATE = "Выберите правило для добавления к шаблону *{template_name}*:"

MESSAGE_ADMIN_RULE_EXPECTATION_SET = "✅ Правило *{rule_name}* добавлено к шаблону\\.\n\nОжидание: {expectation}"

MESSAGE_ADMIN_RULE_EXPECTATION_REMOVED = "✅ Ожидание правила *{rule_name}* удалено из шаблона\\."

MESSAGE_ADMIN_SELECT_EXPECTATION = """Выберите ожидаемый результат для правила *{rule_name}*:

• ✅ *Должно пройти* \\- правило должно успешно пройти
• ❌ *Должно провалиться* \\- правило должно провалить проверку"""

MESSAGE_ADMIN_TEST_RESULT_PASS = "✅ *Тест пройден\\!*\n\nШаблон: *{template_name}*\n\nВсе правила работают как ожидалось\\.\n✅ Пройдено: {passed}/{total}"

MESSAGE_ADMIN_TEST_RESULT_FAIL = """❌ *Тест провален\\!*

Шаблон: *{template_name}*

Некоторые правила работают не как ожидалось\\.
✅ Пройдено: {passed}/{total}
❌ Провалено: {failed}/{total}

*Несоответствия:*
{mismatches}"""

MESSAGE_ADMIN_RUN_ALL_TESTS = "▶️ *Запуск всех тестов*\n\nБудут протестированы все активные шаблоны\\."

MESSAGE_ADMIN_NO_TEMPLATES = "⚠️ *Тестовые шаблоны не найдены*\n\nСоздайте первый шаблон с помощью кнопки ➕"

MESSAGE_ADMIN_NO_RULES_FOR_TEMPLATE = "⚠️ *Для этого шаблона не настроены правила*\n\nДобавьте правила, которые должен тестировать этот шаблон\\."


# ===== ADMIN UI MESSAGES =====

MESSAGE_ADMIN_NOT_ASSIGNED = "Не назначено"
MESSAGE_ADMIN_ENABLED = "включено"
MESSAGE_ADMIN_DISABLED = "отключено"
MESSAGE_ADMIN_NO_ASSIGNED_RULES = "Нет назначенных правил"
MESSAGE_ADMIN_NO_KEYWORDS = "Нет ключевых слов"
MESSAGE_ADMIN_ALL_RULES_ADDED = "Все правила уже добавлены к этому типу"
MESSAGE_ADMIN_SELECT_RULE_TO_ADD = "Выберите правило для добавления:"
MESSAGE_ADMIN_RULE_ADDED = "Правило {rule_name} добавлено!"
MESSAGE_ADMIN_RULE_ALREADY_ADDED = "Правило уже добавлено"
MESSAGE_ADMIN_ERROR = "Ошибка"
MESSAGE_ADMIN_RULE_REMOVED = "Правило удалено из типа"
MESSAGE_ADMIN_ERROR_REMOVING = "Ошибка при удалении"
MESSAGE_ADMIN_ASSIGNED_TYPES = "Назначено типов: {count}"
MESSAGE_ADMIN_NOT_CONFIGURED = "Не настроены"
MESSAGE_ADMIN_NOT_SPECIFIED = "Не указан"
MESSAGE_ADMIN_TEMPLATE_ENABLED = "включен"
MESSAGE_ADMIN_TEMPLATE_DISABLED = "отключен"
MESSAGE_ADMIN_CONFIRM_DELETE_TEMPLATE = "Это удалит все настроенные ожидания правил \\({count} ожиданий\\)\\."
MESSAGE_ADMIN_UNKNOWN_TEMPLATE = "Неизвестный"
MESSAGE_ADMIN_RULES_CONFIGURED = "Настроено правил: {count}\n\n"
MESSAGE_ADMIN_CLICK_RULE_TO_REMOVE = "Нажмите на правило чтобы удалить:"
MESSAGE_ADMIN_NO_RULES_CONFIGURED = "Правила не настроены\\. Добавьте правила для тестирования\\."
MESSAGE_ADMIN_ALL_RULES_IN_TEMPLATE = "Все активные правила уже добавлены к этому шаблону\\."
MESSAGE_ADMIN_UNKNOWN_RULE = "Неизвестное"
MESSAGE_ADMIN_SHOULD_PASS = "должно пройти"
MESSAGE_ADMIN_SHOULD_FAIL = "должно провалиться"
MESSAGE_ADMIN_EXPECTED_PASS = "пройти"
MESSAGE_ADMIN_EXPECTED_FAIL = "провалиться"
MESSAGE_ADMIN_ACTUAL_PASSED = "прошло"
MESSAGE_ADMIN_ACTUAL_FAILED = "провалилось"
MESSAGE_ADMIN_ALL_TESTS_PASSED = "Все тесты пройдены\\!"
MESSAGE_ADMIN_TESTS_FAILED = "Провалено тестов: {count}"
MESSAGE_ADMIN_RULE_NOT_FOUND = "❌ Правило не найдено\\."
MESSAGE_ADMIN_ERROR_UPDATING = "❌ Ошибка при обновлении правила\\."


# ===== TICKET TYPE DETECTION MESSAGES =====

MESSAGE_AMBIGUOUS_TYPE_WARNING = """⚠️ *Предупреждение: неоднозначный тип заявки*

Несколько типов заявок получили одинаковый балл:
{types}

Используется первый тип: _{detected_type}_

Пожалуйста, уточните заявку или обратитесь к администратору для настройки ключевых слов\\."""

MESSAGE_NO_TICKET_TYPES = "Нет доступных типов заявок\\."

MESSAGE_TYPE_NOT_DETECTED = """⚠️ *Не удалось определить тип заявки для проверки*

Пожалуйста, убедитесь что заявка соответствует одному из известных форматов\\.

*Поддерживаемые на данный момент типы заявок:*
{types}"""

MESSAGE_NO_RULES_CONFIGURED = "⚠️ Правила валидации не настроены\\. Обратитесь к администратору\\."

MESSAGE_VALIDATION_ERROR = "❌ Произошла ошибка при валидации\\. Попробуйте позже\\."

MESSAGE_RUNNING_TESTS = "🧪 *Запуск тестов шаблонов\\.\\.\\.*"

MESSAGE_NO_TEST_TEMPLATES = """⚠️ *Тестовые шаблоны не найдены*

Создайте тестовые шаблоны в админ\\-панели\\."""


# ===== FILE UPLOAD MESSAGES =====

MESSAGE_SEND_FILE = """📁 *Пакетная валидация заявок*

Отправьте файл Excel \\(\\.xls или \\.xlsx\\) с заявками\\.

📌 *Требования:*
• Файл должен содержать столбец с текстами заявок
• Максимальный размер файла: 20 МБ
• Поддерживаются форматы: \\.xls, \\.xlsx

После загрузки файла выберите столбец с заявками\\.

Для отмены нажмите ❌ Отмена или используйте /cancel"""

MESSAGE_FILE_TOO_LARGE = """❌ *Файл слишком большой*

Максимальный размер: {max_size} МБ
Размер вашего файла: {file_size} МБ

Пожалуйста, уменьшите файл или разделите на несколько частей\\."""

MESSAGE_UNSUPPORTED_FORMAT = """❌ *Неподдерживаемый формат файла*

Поддерживаются только файлы Excel:
• \\.xls \\(Excel 97\\-2003\\)
• \\.xlsx \\(Excel 2007\\+\\)

Пожалуйста, отправьте файл в одном из этих форматов\\."""

MESSAGE_FILE_NO_COLUMNS = """❌ *Не удалось прочитать структуру файла*

Файл не содержит заголовков столбцов или пуст\\.

Убедитесь, что первая строка содержит названия столбцов\\."""

MESSAGE_SELECT_COLUMN = """📁 *Файл загружен:* {filename} \\({file_size} КБ\\)

🔍 *Найденные столбцы:*
{columns}

Отправьте *номер* или *название* столбца, содержащего тексты заявок\\."""

MESSAGE_INVALID_COLUMN = """❌ *Столбец не найден*

Введите номер столбца \\(1, 2, 3\\.\\.\\.\\) или его точное название\\.

Доступные столбцы: {columns}"""

MESSAGE_FILE_READ_ERROR = """❌ *Ошибка чтения файла*

{error}

Убедитесь, что файл не повреждён и имеет правильный формат\\."""

MESSAGE_FILE_EXPIRED = """⚠️ *Файл устарел*

Пожалуйста, загрузите файл заново\\."""

MESSAGE_PROCESSING_START = """⏳ *Начинаю обработку\\.\\.\\.*

Столбец с заявками: *{column}*

Это может занять некоторое время\\.\\.\\."""

MESSAGE_PROCESSING_PROGRESS = """⚙️ *Обработка\\.\\.\\.*

Прогресс: {bar} {current}/{total} \\({percent}%\\)"""

MESSAGE_PROCESSING_COMPLETE = """✅ *Обработка завершена\\!*

📊 *Результаты:*
• Всего строк: *{total}*
• ✅ Валидных: *{valid}* \\({percent_valid}%\\)
• ❌ С ошибками: *{invalid}* \\({percent_invalid}%\\)
• ⏭️ Пропущено: *{skipped}*

Файл с результатами готов к скачиванию 👇"""

MESSAGE_PROCESSING_ERROR = """❌ *Ошибка обработки*

{error}

Попробуйте загрузить файл заново или обратитесь к администратору\\."""

MESSAGE_FILE_VALIDATION_CANCELLED = """❌ *Валидация файла отменена*

Загруженный файл удалён\\."""

