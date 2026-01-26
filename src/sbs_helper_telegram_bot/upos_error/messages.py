"""
UPOS Error Module Messages

All user-facing messages for the UPOS error code lookup module.
Messages use Telegram MarkdownV2 format where needed.
"""
# pylint: disable=line-too-long
# Note: Double backslashes are intentional for Telegram MarkdownV2 escaping

from typing import Optional
from datetime import datetime

# ===== USER MESSAGES =====

MESSAGE_SUBMENU = "🔢 *UPOS Ошибки*\n\nВведите код ошибки UPOS для получения описания и рекомендаций по устранению\\.\n\nВыберите действие:"

MESSAGE_ENTER_ERROR_CODE = "🔍 *Поиск ошибки*\n\nВведите код ошибки UPOS \\(число\\)\\.\n\nДля отмены используйте /cancel или любую кнопку меню\\."

MESSAGE_SEARCH_CANCELLED = "❌ Поиск отменён\\."

MESSAGE_ERROR_NOT_FOUND = "❌ *Код ошибки не найден*\n\nКод `{code}` отсутствует в базе данных\\.\n\nИнформация о запросе сохранена \\— мы добавим описание этой ошибки в будущем\\."

MESSAGE_INVALID_ERROR_CODE = "⚠️ *Некорректный код ошибки*\n\nПожалуйста, введите числовой код ошибки \\(например: `101`, `2005`\\)\\."

MESSAGE_NO_POPULAR_ERRORS = "📊 *Популярные ошибки*\n\nПока нет данных о запросах\\."

MESSAGE_POPULAR_ERRORS_HEADER = "📊 *Топ\\-{count} запрашиваемых ошибок:*\n\n"


# ===== ADMIN MESSAGES =====

MESSAGE_ADMIN_MENU = "🔐 *Админ\\-панель UPOS Ошибки*\n\nВыберите действие:"

MESSAGE_ADMIN_NOT_AUTHORIZED = "⛔ У вас нет прав администратора\\."

# Error code management
MESSAGE_ADMIN_ERRORS_LIST_EMPTY = "📋 *Список ошибок пуст*\n\nДобавьте первую ошибку с помощью кнопки «➕ Добавить ошибку»\\."

MESSAGE_ADMIN_ERRORS_LIST_HEADER = "📋 *Коды ошибок UPOS* \\(стр\\. {page}/{total_pages}\\):\n\n"

MESSAGE_ADMIN_ENTER_ERROR_CODE = "➕ *Добавление ошибки*\n\nВведите код ошибки \\(число или текст, например: `101`, `E\\-001`\\):"

MESSAGE_ADMIN_ENTER_DESCRIPTION = "📝 *Описание ошибки*\n\nВведите описание для кода `{code}`:"

MESSAGE_ADMIN_ENTER_SUGGESTED_ACTIONS = "💡 *Рекомендации*\n\nВведите рекомендации по устранению ошибки `{code}`:"

MESSAGE_ADMIN_SELECT_CATEGORY = "📁 *Категория*\n\nВыберите категорию для ошибки `{code}` или пропустите:"

MESSAGE_ADMIN_ERROR_CREATED = "✅ *Ошибка добавлена\\!*\n\nКод: `{code}`\nКатегория: {category}\nОписание: {description}"

MESSAGE_ADMIN_ERROR_EXISTS = "⚠️ Код ошибки `{code}` уже существует в базе данных\\."

MESSAGE_ADMIN_ERROR_DELETED = "🗑️ Код ошибки `{code}` удалён\\."

MESSAGE_ADMIN_ERROR_DEACTIVATED = "🚫 Код ошибки `{code}` деактивирован\\."

MESSAGE_ADMIN_ERROR_ACTIVATED = "✅ Код ошибки `{code}` активирован\\."

# Edit prompts
MESSAGE_ADMIN_EDIT_DESCRIPTION = "📝 *Редактирование описания*\n\nТекущее описание:\n{current}\n\nВведите новое описание:"

MESSAGE_ADMIN_EDIT_ACTIONS = "💡 *Редактирование рекомендаций*\n\nТекущие рекомендации:\n{current}\n\nВведите новые рекомендации:"

MESSAGE_ADMIN_UPDATE_DATE_PROMPT = "📅 *Обновить дату?*\n\nОбновить дату последнего изменения рекомендаций?"

MESSAGE_ADMIN_ERROR_UPDATED = "✅ *Ошибка обновлена\\!*"

# Category management
MESSAGE_ADMIN_CATEGORIES_LIST_EMPTY = "📁 *Список категорий пуст*\n\nДобавьте первую категорию с помощью кнопки «➕ Добавить категорию»\\."

MESSAGE_ADMIN_CATEGORIES_LIST_HEADER = "📁 *Категории UPOS ошибок* \\(стр\\. {page}/{total_pages}\\):\n\n"

MESSAGE_ADMIN_ENTER_CATEGORY_NAME = "➕ *Добавление категории*\n\nВведите название категории:"

MESSAGE_ADMIN_ENTER_CATEGORY_DESCRIPTION = "📝 *Описание категории*\n\nВведите описание для категории «{name}» \\(или отправьте «\\-» для пропуска\\):"

MESSAGE_ADMIN_ENTER_CATEGORY_ORDER = "🔢 *Порядок отображения*\n\nВведите порядковый номер для категории «{name}» \\(число, меньше \\= выше в списке\\):"

MESSAGE_ADMIN_CATEGORY_CREATED = "✅ *Категория создана\\!*\n\nНазвание: {name}"

MESSAGE_ADMIN_CATEGORY_EXISTS = "⚠️ Категория «{name}» уже существует\\."

MESSAGE_ADMIN_CATEGORY_DELETED = "🗑️ Категория «{name}» удалена\\."

# Unknown codes
MESSAGE_ADMIN_UNKNOWN_CODES_EMPTY = "❓ *Неизвестные коды*\n\nНет запросов по неизвестным кодам ошибок\\."

MESSAGE_ADMIN_UNKNOWN_CODES_HEADER = "❓ *Неизвестные коды* \\(стр\\. {page}/{total_pages}\\):\n\nКоды, которые запрашивали пользователи, но их нет в базе:\n\n"

# Statistics
MESSAGE_ADMIN_STATS = """📈 *Статистика UPOS Ошибки*

*Общее количество:*
• Кодов ошибок: {total_codes}
• Категорий: {total_categories}
• Неизвестных кодов: {unknown_codes}

*За последние 7 дней:*
• Всего запросов: {requests_7d}
• Найдено: {found_7d}
• Не найдено: {not_found_7d}

*Топ запрашиваемых кодов:*
{top_codes}"""


# ===== CSV IMPORT MESSAGES =====

MESSAGE_ADMIN_CSV_IMPORT_START = """📥 *Импорт из CSV*

Отправьте CSV\\-файл с кодами ошибок\\.

*Требуемый формат файла:*
• Кодировка: UTF\\-8 \\(рекомендуется\\) или Windows\\-1251
• Разделитель: запятая \\(,\\) или точка с запятой \\(;\\)
• Максимальный размер: 5 МБ

*Обязательные столбцы:*
• `error\\_code` или `код` \\— код ошибки
• `description` или `описание` \\— описание
• `suggested\\_actions` или `рекомендации` \\— рекомендации

*Опциональные столбцы:*
• `category` или `категория` \\— название категории

*Пример CSV:*
`error\\_code,description,suggested\\_actions,category`
`101,Нет бумаги,Заменить рулон,Принтер`"""

MESSAGE_ADMIN_CSV_NO_FILE = "⚠️ Пожалуйста, отправьте CSV\\-файл\\."

MESSAGE_ADMIN_CSV_WRONG_FORMAT = "⚠️ Неверный формат файла\\. Отправьте файл с расширением \\.csv\\."

MESSAGE_ADMIN_CSV_TOO_LARGE = "⚠️ Файл слишком большой\\. Максимальный размер: 5 МБ\\."

MESSAGE_ADMIN_CSV_ENCODING_ERROR = "⚠️ Не удалось прочитать файл\\. Проверьте кодировку \\(UTF\\-8 или Windows\\-1251\\)\\."

MESSAGE_ADMIN_CSV_PARSE_ERRORS = """❌ *Ошибки при разборе CSV*

Найдено ошибок: {error_count}

{errors}"""

MESSAGE_ADMIN_CSV_NO_RECORDS = "⚠️ В файле не найдено ни одной корректной записи\\. Проверьте формат данных\\."

MESSAGE_ADMIN_CSV_PREVIEW = """📋 *Предпросмотр импорта*

• Всего записей: *{total}*
• Новых кодов: *{new}*
• Уже существуют: *{existing}*
• Ошибок парсинга: *{parse_errors}*

Выберите действие:"""

MESSAGE_ADMIN_CSV_CANCELLED = "❌ Импорт отменён\\."

MESSAGE_ADMIN_CSV_IMPORT_RESULT = """✅ *Импорт завершён\\!*

• Добавлено/обновлено: *{success}*
• Пропущено \\(уже существуют\\): *{skipped}*
• Ошибок: *{errors}*"""

MESSAGE_ADMIN_CSV_PROCESS_ERROR = "❌ Ошибка обработки файла: {error}"


# ===== HELPER FUNCTIONS =====

def escape_markdown_v2(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.
    
    Args:
        text: Text to escape
        
    Returns:
        Escaped text
    """
    if not text:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def format_error_code_response(
    error_code: str,
    description: str,
    suggested_actions: str,
    category_name: Optional[str] = None,
    updated_timestamp: Optional[int] = None
) -> str:
    """
    Format error code information for display to user.
    
    Args:
        error_code: The error code
        description: Error description
        suggested_actions: Suggested actions to resolve
        category_name: Optional category name
        updated_timestamp: Optional Unix timestamp of last update
        
    Returns:
        Formatted MarkdownV2 message
    """
    escaped_code = escape_markdown_v2(error_code)
    escaped_desc = escape_markdown_v2(description)
    escaped_actions = escape_markdown_v2(suggested_actions)
    
    parts = [f"🔢 *Код ошибки:* `{escaped_code}`\n"]
    
    if category_name:
        escaped_category = escape_markdown_v2(category_name)
        parts.append(f"📁 *Категория:* {escaped_category}\n")
    
    parts.append(f"\n📋 *Описание:*\n{escaped_desc}\n")
    parts.append(f"\n💡 *Рекомендации:*\n{escaped_actions}")
    
    if updated_timestamp:
        date_str = datetime.fromtimestamp(updated_timestamp).strftime('%d.%m.%Y')
        escaped_date = escape_markdown_v2(date_str)
        parts.append(f"\n\n📅 _Обновлено: {escaped_date}_")
    
    return "".join(parts)


def format_error_list_item(
    error_code: str,
    description: str,
    category_name: Optional[str] = None,
    times_requested: int = 0
) -> str:
    """
    Format error code for list display (admin).
    
    Args:
        error_code: The error code
        description: Short description (will be truncated)
        category_name: Optional category
        times_requested: Number of times requested (for popular list)
        
    Returns:
        Formatted line for list
    """
    escaped_code = escape_markdown_v2(error_code)
    
    # Truncate description to 50 chars
    short_desc = description[:50] + "..." if len(description) > 50 else description
    escaped_desc = escape_markdown_v2(short_desc)
    
    if times_requested > 0:
        return f"• `{escaped_code}` \\({times_requested}x\\) \\- {escaped_desc}"
    elif category_name:
        escaped_cat = escape_markdown_v2(category_name)
        return f"• `{escaped_code}` \\[{escaped_cat}\\] \\- {escaped_desc}"
    else:
        return f"• `{escaped_code}` \\- {escaped_desc}"


def format_unknown_code_item(error_code: str, times_requested: int, last_timestamp: int) -> str:
    """
    Format unknown code for list display.
    
    Args:
        error_code: The unknown error code
        times_requested: Number of times requested
        last_timestamp: Last request timestamp
        
    Returns:
        Formatted line for list
    """
    escaped_code = escape_markdown_v2(error_code)
    date_str = datetime.fromtimestamp(last_timestamp).strftime('%d.%m.%Y')
    escaped_date = escape_markdown_v2(date_str)
    
    return f"• `{escaped_code}` \\- {times_requested}x \\(последний: {escaped_date}\\)"


def format_category_list_item(name: str, error_count: int, display_order: int = 0) -> str:
    """
    Format category for list display.
    
    Args:
        name: Category name
        error_count: Number of errors in category
        display_order: Display order value (unused, kept for API compatibility)
        
    Returns:
        Formatted line for list
    """
    _ = display_order  # Unused, kept for API compatibility
    escaped_name = escape_markdown_v2(name)
    return f"• {escaped_name} \\({error_count} ошибок\\)"
