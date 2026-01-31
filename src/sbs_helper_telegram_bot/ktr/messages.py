"""
KTR Module Messages

All user-facing messages for the KTR (Коэффициент Трудозатрат) code lookup module.
Messages use Telegram MarkdownV2 format where needed.
"""
# pylint: disable=line-too-long
# Note: Double backslashes are intentional for Telegram MarkdownV2 escaping

from typing import Optional
from datetime import datetime
import src.common.database as database

# ===== USER MESSAGES =====

MESSAGE_SUBMENU = "⏱️ *КТР \\(Коэффициент Трудозатрат\\)*\n\n💡 _Выберите действие:_"


def _get_codes_count() -> int:
    """
    Get count of active KTR codes from the database.
    
    Returns:
        Number of active KTR codes
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as cnt 
                    FROM ktr_codes 
                    WHERE active = 1
                """)
                result = cursor.fetchone()
                if result:
                    return result['cnt']
    except Exception:
        pass
    return 0


def get_submenu_message() -> str:
    """
    Build submenu message with statistics.
    
    Returns:
        Formatted message for MarkdownV2
    """
    codes_count = _get_codes_count()
    return (
        "⏱️ *КТР \\(Коэффициент Трудозатрат\\)*\n\n"
        f"📊 В базе: *{codes_count}* кодов КТР"
        "\n\n💡 _Выберите действие:_"
    )

MESSAGE_ENTER_CODE = "🔍 *Поиск кода КТР*\n\nВведите код КТР \\(например: `POS2421`\\)\\.\n\nДля отмены используйте /cancel или любую кнопку меню\\."

MESSAGE_SEARCH_CANCELLED = "❌ Поиск отменён\\."

MESSAGE_CODE_NOT_FOUND = "❌ *Код КТР не найден*\n\nКод `{code}` отсутствует в базе данных\\.\n\nИнформация о запросе сохранена — мы добавим этот код в будущем\\."

MESSAGE_INVALID_CODE = "⚠️ *Некорректный код*\n\nПожалуйста, введите корректный код КТР \\(например: `POS2421`\\)\\."

MESSAGE_NO_POPULAR_CODES = "📊 *Популярные коды КТР*\n\nПока нет данных о запросах\\."

MESSAGE_POPULAR_CODES_HEADER = "📊 *Топ\\-{count} запрашиваемых кодов КТР:*\n\n"


# ===== ADMIN MESSAGES =====

MESSAGE_ADMIN_MENU = "🔐 *Админ\\-панель КТР*\n\nВыберите действие:"

MESSAGE_ADMIN_NOT_AUTHORIZED = "⛔ У вас нет прав администратора\\."

# KTR code management
MESSAGE_ADMIN_CODES_LIST_EMPTY = "📋 *Список кодов пуст*\n\nДобавьте первый код с помощью кнопки «➕ Добавить код»\\."

MESSAGE_ADMIN_CODES_LIST_HEADER = "📋 *Коды КТР* \\(стр\\. {page}/{total_pages}\\):\n\n"

MESSAGE_ADMIN_ENTER_CODE = "➕ *Добавление кода КТР*\n\nВведите код \\(например: `POS2421`\\):"

MESSAGE_ADMIN_SEARCH_CODE = "🔍 *Поиск кода КТР*\n\nВведите код для редактирования:"

MESSAGE_ADMIN_CODE_NOT_FOUND_FOR_EDIT = "❌ *Код не найден*\n\nКод `{code}` отсутствует в базе данных\\. Используйте кнопку «➕ Добавить код» для добавления\\."

MESSAGE_ADMIN_ENTER_DESCRIPTION = "📝 *Описание работы*\n\nВведите описание для кода `{code}`:"

MESSAGE_ADMIN_ENTER_MINUTES = "⏱️ *Трудозатраты*\n\nВведите количество минут для кода `{code}`:"

MESSAGE_ADMIN_INVALID_MINUTES = "⚠️ Введите корректное число минут \\(целое положительное число\\)\\."

MESSAGE_ADMIN_SELECT_CATEGORY = "📁 *Категория*\n\nВыберите категорию для кода `{code}` или пропустите:"

MESSAGE_ADMIN_CODE_CREATED = "✅ *Код КТР добавлен\\!*\n\nКод: `{code}`\nКатегория: {category}\nОписание: {description}\nТрудозатраты: {minutes} мин\\."

MESSAGE_ADMIN_CODE_EXISTS = "⚠️ Код `{code}` уже существует в базе данных\\."

MESSAGE_ADMIN_CODE_DELETED = "🗑️ Код `{code}` удалён\\."

MESSAGE_ADMIN_CODE_DEACTIVATED = "🚫 Код `{code}` деактивирован\\."

MESSAGE_ADMIN_CODE_ACTIVATED = "✅ Код `{code}` активирован\\."

# Edit prompts
MESSAGE_ADMIN_EDIT_DESCRIPTION = "📝 *Редактирование описания*\n\nТекущее описание:\n{current}\n\nВведите новое описание:"

MESSAGE_ADMIN_EDIT_MINUTES = "⏱️ *Редактирование трудозатрат*\n\nТекущее значение: {current} мин\\.\n\nВведите новое количество минут:"

MESSAGE_ADMIN_CODE_UPDATED = "✅ *Код КТР обновлён\\!*"

# Category management
MESSAGE_ADMIN_CATEGORIES_LIST_EMPTY = "📁 *Список категорий пуст*\n\nДобавьте первую категорию с помощью кнопки «➕ Добавить категорию»\\."

MESSAGE_ADMIN_CATEGORIES_LIST_HEADER = "📁 *Категории КТР* \\(стр\\. {page}/{total_pages}\\):\n\n"

MESSAGE_ADMIN_ENTER_CATEGORY_NAME = "➕ *Добавление категории*\n\nВведите название категории:"

MESSAGE_ADMIN_ENTER_CATEGORY_DESCRIPTION = "📝 *Описание категории*\n\nВведите описание для категории «{name}» \\(или отправьте «\\-» для пропуска\\):"

MESSAGE_ADMIN_ENTER_CATEGORY_ORDER = "🔢 *Порядок отображения*\n\nВведите порядковый номер для категории «{name}» \\(число, меньше \\= выше в списке\\):"

MESSAGE_ADMIN_CATEGORY_CREATED = "✅ *Категория создана\\!*\n\nНазвание: {name}"

MESSAGE_ADMIN_CATEGORY_EXISTS = "⚠️ Категория «{name}» уже существует\\."

MESSAGE_ADMIN_CATEGORY_DELETED = "🗑️ Категория «{name}» удалена\\."

# Unknown codes
MESSAGE_ADMIN_UNKNOWN_CODES_EMPTY = "❓ *Неизвестные коды*\n\nНет запросов по неизвестным кодам КТР\\."

MESSAGE_ADMIN_UNKNOWN_CODES_HEADER = "❓ *Неизвестные коды* \\(стр\\. {page}/{total_pages}\\):\n\nКоды, которые запрашивали пользователи, но их нет в базе:\n\n"

# Statistics
MESSAGE_ADMIN_STATS = """📈 *Статистика КТР*

*Общее количество:*
• Кодов КТР: {total_codes}
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

Отправьте CSV\\-файл с кодами КТР\\.

*Требуемый формат файла:*
• Кодировка: UTF\\-8 \\(рекомендуется\\)
• Разделитель: запятая \\(,\\) или точка с запятой \\(;\\)
• Максимальный размер: 5 МБ

💡 *Совет для Mac:* В Numbers выберите Файл → Экспортировать в → CSV, затем в настройках выберите кодировку Unicode \\(UTF\\-8\\)\\.

*Обязательные столбцы:*
• `code` или `код` \\— код КТР
• `description` или `описание` \\— описание работы
• `minutes` или `минуты` \\— трудозатраты в минутах

*Опциональные столбцы:*
• `category` или `категория` \\— название категории

*Пример CSV:*
`code,description,minutes,category`
`POS2421,Установка POS\\-терминала,90,POS\\-терминалы`"""

MESSAGE_ADMIN_CSV_NO_FILE = "⚠️ Пожалуйста, отправьте CSV\\-файл\\."

MESSAGE_ADMIN_CSV_WRONG_FORMAT = "⚠️ Неверный формат файла\\. Отправьте файл с расширением \\.csv\\."

MESSAGE_ADMIN_CSV_TOO_LARGE = "⚠️ Файл слишком большой\\. Максимальный размер: 5 МБ\\."

MESSAGE_ADMIN_CSV_ENCODING_ERROR = "⚠️ *Ошибка кодировки файла*\n\nНе удалось прочитать CSV файл ни с одной известной кодировкой\.\n\nПопробуйте пересохранить файл в UTF\-8 кодировке\.\n\n*Для Mac:* Excel → Файл → Сохранить как → Формат: CSV UTF\-8"

MESSAGE_ADMIN_CSV_PARSE_ERRORS = """❌ *Ошибки при разборе CSV*

Найдено ошибок: {error_count}

{errors}"""

MESSAGE_ADMIN_CSV_NO_RECORDS = "⚠️ В файле не найдено ни одной корректной записи\\. Проверьте формат данных\\."

MESSAGE_ADMIN_CSV_PREVIEW = """📋 *Предпросмотр импорта*

• Всего записей: *{total}*
• Новых кодов: *{new}*
• Уже существуют: *{existing}*
• Ошибок парсинга: *{parse_errors}*
{encoding_info}
Выберите действие:"""

MESSAGE_ADMIN_CSV_CANCELLED = "❌ Импорт отменён\\."

MESSAGE_ADMIN_CSV_IMPORT_RESULT = """✅ *Импорт завершён\\!*

• Добавлено/обновлено: *{success}*
• Пропущено \\(уже существуют\\): *{skipped}*
• Ошибок: *{errors}*"""

MESSAGE_ADMIN_CSV_PROCESS_ERROR = "❌ Ошибка обработки файла\\: {error}"


# ===== CSV PARSING ERROR MESSAGES =====

MESSAGE_CSV_ERROR_NO_CODE_COLUMN = "Не найден столбец с кодом. Ожидаемые названия: code, код, ktr_code"
MESSAGE_CSV_ERROR_NO_DESC_COLUMN = "Не найден столбец с описанием. Ожидаемые названия: description, описание, desc"
MESSAGE_CSV_ERROR_NO_MINUTES_COLUMN = "Не найден столбец с минутами. Ожидаемые названия: minutes, минуты, время, time"
MESSAGE_CSV_ERROR_EMPTY_CODE = "Строка {row}: пустой код"
MESSAGE_CSV_ERROR_CODE_TOO_LONG = "Строка {row}: код '{code}...' слишком длинный (макс. 50 символов)"
MESSAGE_CSV_ERROR_EMPTY_DESC = "Строка {row}: пустое описание для кода '{code}'"
MESSAGE_CSV_ERROR_INVALID_MINUTES = "Строка {row}: некорректное значение минут для кода '{code}'"
MESSAGE_CSV_ERROR_ROW_PROCESSING = "Строка {row}: ошибка обработки - {error}"
MESSAGE_CSV_ERROR_PARSE = "Ошибка парсинга CSV: {error}"
MESSAGE_CSV_ERROR_UNEXPECTED = "Неожиданная ошибка: {error}"
MESSAGE_CSV_ERROR_IMPORT = "Ошибка импорта '{code}': {error}"


# ===== COMMON UI MESSAGES =====

MESSAGE_SELECT_ACTION = "Выберите действие:"
MESSAGE_NO_CATEGORY = "Без категории"
MESSAGE_NO_DATA = "Нет данных"
MESSAGE_USE_LIST_BUTTON = "Используйте кнопку «📋 Список кодов» для просмотра списка."
MESSAGE_NO_IMPORT_DATA = "❌ Нет данных для импорта\\."
MESSAGE_IMPORT_IN_PROGRESS = "⏳ *Импорт данных\\.\\.\\.*\n\nПожалуйста, подождите\\."
MESSAGE_AND_MORE = "\\.\\.\\. и ещё {count}"


# ===== KEYBOARD BUTTON LABELS =====

BUTTON_FORWARD = "Вперёд ➡️"
BUTTON_BACK = "⬅️ Назад"
BUTTON_BACK_TO_MENU = "🔙 Назад в меню"


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


def format_ktr_code_response(
    code: str,
    description: str,
    minutes: int,
    category_name: Optional[str] = None,
    updated_timestamp: Optional[int] = None,
    date_updated: Optional[str] = None
) -> str:
    """
    Format KTR code information for display to user.
    
    Args:
        code: The KTR code
        description: Work description
        minutes: Labor cost in minutes
        category_name: Optional category name
        updated_timestamp: Optional Unix timestamp of last update
        date_updated: Optional date when minutes value was updated (dd.mm.yyyy)
        
    Returns:
        Formatted MarkdownV2 message
    """
    escaped_code = escape_markdown_v2(code)
    escaped_desc = escape_markdown_v2(description)
    
    parts = [f"⏱️ *Код КТР:* `{escaped_code}`\n"]
    
    if category_name:
        escaped_category = escape_markdown_v2(category_name)
        parts.append(f"📁 *Категория:* {escaped_category}\n")
    
    parts.append(f"\n📋 *Описание:*\n{escaped_desc}\n")
    parts.append(f"\n🕐 *Трудозатраты:* *{minutes}* минут")
    
    if date_updated:
        escaped_date = escape_markdown_v2(date_updated)
        parts.append(f" _{escaped_date}_")
    
    # Format hours and minutes for convenience
    if minutes >= 60:
        hours = minutes // 60
        remaining_mins = minutes % 60
        if remaining_mins > 0:
            parts.append(f" \\({hours} ч\\. {remaining_mins} мин\\.\\)")
        else:
            parts.append(f" \\({hours} ч\\.\\)")
    
    if updated_timestamp:
        date_str = datetime.fromtimestamp(updated_timestamp).strftime('%d.%m.%Y')
        escaped_date = escape_markdown_v2(date_str)
        parts.append(f"\n\n📅 _Обновлено: {escaped_date}_")
    
    return "".join(parts)


def format_code_list_item(
    code: str,
    description: str,
    minutes: int,
    category_name: Optional[str] = None,
    times_requested: int = 0
) -> str:
    """
    Format KTR code for list display (admin).
    
    Args:
        code: The KTR code
        description: Short description (will be truncated)
        minutes: Labor cost in minutes
        category_name: Optional category
        times_requested: Number of times requested (for popular list)
        
    Returns:
        Formatted line for list
    """
    escaped_code = escape_markdown_v2(code)
    
    # Truncate description to 40 chars
    short_desc = description[:40] + "..." if len(description) > 40 else description
    escaped_desc = escape_markdown_v2(short_desc)
    
    if times_requested > 0:
        return f"• `{escaped_code}` \\({times_requested}x\\) \\- {escaped_desc} \\[{minutes} мин\\.\\]"
    elif category_name:
        escaped_cat = escape_markdown_v2(category_name)
        return f"• `{escaped_code}` \\[{escaped_cat}\\] \\- {escaped_desc} \\[{minutes} мин\\.\\]"
    else:
        return f"• `{escaped_code}` \\- {escaped_desc} \\[{minutes} мин\\.\\]"


def format_unknown_code_item(code: str, times_requested: int, last_timestamp: int) -> str:
    """
    Format unknown code for list display.
    
    Args:
        code: The unknown KTR code
        times_requested: Number of times requested
        last_timestamp: Last request timestamp
        
    Returns:
        Formatted line for list
    """
    escaped_code = escape_markdown_v2(code)
    date_str = datetime.fromtimestamp(last_timestamp).strftime('%d.%m.%Y')
    escaped_date = escape_markdown_v2(date_str)
    
    return f"• `{escaped_code}` \\- {times_requested}x \\(последний: {escaped_date}\\)"


def format_category_list_item(name: str, code_count: int, display_order: int = 0) -> str:
    """
    Format category for list display.
    
    Args:
        name: Category name
        code_count: Number of codes in category
        display_order: Display order value (unused, kept for API compatibility)
        
    Returns:
        Formatted line for list
    """
    _ = display_order  # Unused, kept for API compatibility
    escaped_name = escape_markdown_v2(name)
    return f"• {escaped_name} \\({code_count} кодов\\)"
