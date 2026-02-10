"""
Часть бота для ошибок UPOS

Основные обработчики бота для модуля поиска кодов ошибок UPOS.
Включает пользовательский поиск и админские CRUD-операции.
"""
# pylint: disable=line-too-long

import csv
import io
import logging
import math
import re
from typing import Optional, List, Tuple
from dataclasses import dataclass

from telegram import Update, constants
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

import src.common.database as database
from src.common.telegram_user import check_if_user_legit, check_if_user_admin, get_unauthorized_message
from src.common.messages import (
    get_main_menu_message,
    get_main_menu_keyboard,
    BUTTON_MAIN_MENU,
    BUTTON_MODULES,
    BUTTON_SETTINGS,
    BUTTON_VALIDATE_TICKET,
    BUTTON_SCREENSHOT,
    BUTTON_CERTIFICATION,
    BUTTON_KTR,
    BUTTON_FEEDBACK,
    BUTTON_PROFILE,
    BUTTON_MY_INVITES,
    BUTTON_HELP,
    BUTTON_BOT_ADMIN,
)

from . import messages
from . import keyboards
from . import settings
from src.sbs_helper_telegram_bot.ticket_validator import settings as validator_settings

logger = logging.getLogger(__name__)

# Состояния диалога для пользовательского поиска
SUBMENU = 0  # Пользователь находится в подменю модуля
WAITING_FOR_ERROR_CODE = 1

# Состояния диалога для админских операций
(
    ADMIN_MENU,
    ADMIN_ADD_ERROR_CODE,
    ADMIN_ADD_DESCRIPTION,
    ADMIN_ADD_ACTIONS,
    ADMIN_SELECT_CATEGORY,
    ADMIN_EDIT_DESCRIPTION,
    ADMIN_EDIT_ACTIONS,
    ADMIN_ADD_CATEGORY_NAME,
    ADMIN_ADD_CATEGORY_DESCRIPTION,
    ADMIN_ADD_CATEGORY_ORDER,
    ADMIN_EDIT_CATEGORY_NAME,
    ADMIN_EDIT_CATEGORY_DESCRIPTION,
    ADMIN_CONFIRM_UPDATE_DATE,
    ADMIN_IMPORT_CSV_WAITING,
    ADMIN_IMPORT_CSV_CONFIRM,
    ADMIN_SEARCH_ERROR_CODE
) = range(100, 116)


# ===== ОПЕРАЦИИ С БАЗОЙ ДАННЫХ =====

def get_error_code_by_code(error_code: str) -> Optional[dict]:
    """
    Найти код ошибки в базе данных.

    Args:
        error_code: Код ошибки для поиска.

    Returns:
        Словарь с информацией об ошибке или None, если не найдено.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT e.*, c.name as category_name
                FROM upos_error_codes e
                LEFT JOIN upos_error_categories c ON e.category_id = c.id
                WHERE e.error_code = %s AND e.active = 1
            """, (error_code,))
            return cursor.fetchone()


def get_error_code_by_id(error_id: int) -> Optional[dict]:
    """
    Получить код ошибки по ID (для админа).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT e.*, c.name as category_name
                FROM upos_error_codes e
                LEFT JOIN upos_error_categories c ON e.category_id = c.id
                WHERE e.id = %s
            """, (error_id,))
            return cursor.fetchone()


def get_all_error_codes(page: int = 1, per_page: int = None, include_inactive: bool = False) -> Tuple[List[dict], int]:
    """
    Получить постраничный список кодов ошибок.

    Returns:
        Кортеж (список_кодов_ошибок, общее_количество).
    """
    if per_page is None:
        per_page = settings.ERRORS_PER_PAGE
    
    offset = (page - 1) * per_page
    active_filter = "" if include_inactive else "WHERE e.active = 1"
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Получаем общее количество
            cursor.execute(f"SELECT COUNT(*) as cnt FROM upos_error_codes e {active_filter}")
            total = cursor.fetchone()['cnt']
            
            # Получаем страницу
            cursor.execute(f"""
                SELECT e.*, c.name as category_name
                FROM upos_error_codes e
                LEFT JOIN upos_error_categories c ON e.category_id = c.id
                {active_filter}
                ORDER BY e.error_code
                LIMIT %s OFFSET %s
            """, (per_page, offset))
            
            return cursor.fetchall(), total


def create_error_code(error_code: str, description: str, suggested_actions: str, category_id: Optional[int] = None) -> int:
    """
    Создать новый код ошибки.

    Returns:
        ID нового кода ошибки.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                INSERT INTO upos_error_codes 
                (error_code, description, suggested_actions, category_id, created_timestamp)
                VALUES (%s, %s, %s, %s, UNIX_TIMESTAMP())
            """, (error_code, description, suggested_actions, category_id))
            return cursor.lastrowid


def update_error_code(error_id: int, field: str, value: str, update_timestamp: bool = False) -> bool:
    """
    Обновить поле кода ошибки.
    """
    allowed_fields = ['description', 'suggested_actions', 'category_id', 'active']
    if field not in allowed_fields:
        return False
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            if update_timestamp:
                cursor.execute(f"""
                    UPDATE upos_error_codes 
                    SET {field} = %s, updated_timestamp = UNIX_TIMESTAMP()
                    WHERE id = %s
                """, (value, error_id))
            else:
                cursor.execute(f"""
                    UPDATE upos_error_codes 
                    SET {field} = %s
                    WHERE id = %s
                """, (value, error_id))
            return cursor.rowcount > 0


def delete_error_code(error_id: int) -> bool:
    """
    Удалить код ошибки (жёсткое удаление).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("DELETE FROM upos_error_codes WHERE id = %s", (error_id,))
            return cursor.rowcount > 0


def error_code_exists(error_code: str) -> bool:
    """
    Проверить, существует ли код ошибки.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM upos_error_codes WHERE error_code = %s", (error_code,))
            return cursor.fetchone() is not None


# Операции с категориями

def get_all_categories(page: int = 1, per_page: int = None) -> Tuple[List[dict], int]:
    """
    Получить постраничный список категорий.
    """
    if per_page is None:
        per_page = settings.CATEGORIES_PER_PAGE
    
    offset = (page - 1) * per_page
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT COUNT(*) as cnt FROM upos_error_categories WHERE active = 1")
            total = cursor.fetchone()['cnt']
            
            cursor.execute("""
                SELECT c.*, 
                    (SELECT COUNT(*) FROM upos_error_codes WHERE category_id = c.id) as error_count
                FROM upos_error_categories c
                WHERE c.active = 1
                ORDER BY c.display_order, c.name
                LIMIT %s OFFSET %s
            """, (per_page, offset))
            
            return cursor.fetchall(), total


def get_category_by_id(category_id: int) -> Optional[dict]:
    """
    Получить категорию по ID.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT c.*, 
                    (SELECT COUNT(*) FROM upos_error_codes WHERE category_id = c.id) as error_count
                FROM upos_error_categories c
                WHERE c.id = %s
            """, (category_id,))
            return cursor.fetchone()


def create_category(name: str, description: Optional[str] = None, display_order: int = 0) -> int:
    """
    Создать новую категорию.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                INSERT INTO upos_error_categories 
                (name, description, display_order, created_timestamp)
                VALUES (%s, %s, %s, UNIX_TIMESTAMP())
            """, (name, description, display_order))
            return cursor.lastrowid


def update_category(category_id: int, field: str, value) -> bool:
    """
    Обновить поле категории.
    """
    allowed_fields = ['name', 'description', 'display_order', 'active']
    if field not in allowed_fields:
        return False
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(f"""
                UPDATE upos_error_categories 
                SET {field} = %s, updated_timestamp = UNIX_TIMESTAMP()
                WHERE id = %s
            """, (value, category_id))
            return cursor.rowcount > 0


def delete_category(category_id: int) -> bool:
    """
    Удалить категорию (у кодов ошибок category_id станет NULL).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Внешний ключ с ON DELETE SET NULL обработает связанные коды ошибок
            cursor.execute("DELETE FROM upos_error_categories WHERE id = %s", (category_id,))
            return cursor.rowcount > 0


def category_exists(name: str) -> bool:
    """
    Проверить, существует ли название категории.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM upos_error_categories WHERE name = %s", (name,))
            return cursor.fetchone() is not None


def get_category_by_name(name: str) -> Optional[dict]:
    """
    Получить категорию по названию.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT * FROM upos_error_categories WHERE name = %s AND active = 1", (name,))
            return cursor.fetchone()


# Структуры и функции импорта CSV

@dataclass
class CSVImportResult:
    """Результат операции импорта CSV."""
    success_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def parse_csv_error_codes(csv_content: str, delimiter: str = ',') -> Tuple[List[dict], List[str]]:
    """
    Разобрать CSV и проверить данные кодов ошибок.

    Ожидаемый формат CSV:
    error_code,description,suggested_actions,category (optional)

    Args:
        csv_content: Содержимое CSV в виде строки.
        delimiter: Разделитель CSV.

    Returns:
        Кортеж (валидные_записи, список_ошибок).
    """
    valid_records = []
    errors = []
    
    try:
        # Пытаемся определить разделитель, если это не запятая
        if delimiter == ',' and ';' in csv_content and ',' not in csv_content.split('\n')[0]:
            delimiter = ';'
        
        reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)
        
        # Проверяем обязательные поля
        if not reader.fieldnames:
            errors.append("CSV файл пуст или имеет неверный формат")
            return [], errors
        
        fieldnames_lower = [f.lower().strip() if f else '' for f in reader.fieldnames]
        
        # Сопоставляем возможные названия колонок
        code_col = None
        desc_col = None
        actions_col = None
        category_col = None
        
        for i, fname in enumerate(fieldnames_lower):
            if fname in ('error_code', 'код', 'код_ошибки', 'код ошибки', 'code', 'errorcode'):
                code_col = reader.fieldnames[i]
            elif fname in ('description', 'описание', 'desc'):
                desc_col = reader.fieldnames[i]
            elif fname in ('suggested_actions', 'рекомендации', 'actions', 'действия', 'рекомендуемые_действия'):
                actions_col = reader.fieldnames[i]
            elif fname in ('category', 'категория', 'cat'):
                category_col = reader.fieldnames[i]
        
        if not code_col:
            errors.append(messages.MESSAGE_CSV_ERROR_NO_CODE_COLUMN)
            return [], errors
        if not desc_col:
            errors.append(messages.MESSAGE_CSV_ERROR_NO_DESC_COLUMN)
            return [], errors
        if not actions_col:
            errors.append(messages.MESSAGE_CSV_ERROR_NO_ACTIONS_COLUMN)
            return [], errors
        
        for row_num, row in enumerate(reader, start=2):  # Начинаем с 2 (заголовок — строка 1)
            try:
                error_code = (row.get(code_col) or '').strip()
                description = (row.get(desc_col) or '').strip()
                suggested_actions = (row.get(actions_col) or '').strip()
                category_name = (row.get(category_col) or '').strip() if category_col else None
                
                # Валидируем обязательные поля
                if not error_code:
                    errors.append(messages.MESSAGE_CSV_ERROR_EMPTY_CODE.format(row=row_num))
                    continue
                
                if len(error_code) > 50:
                    errors.append(messages.MESSAGE_CSV_ERROR_CODE_TOO_LONG.format(row=row_num, code=error_code[:20]))
                    continue
                
                if not description:
                    errors.append(messages.MESSAGE_CSV_ERROR_EMPTY_DESC.format(row=row_num, code=error_code))
                    continue
                
                if not suggested_actions:
                    errors.append(messages.MESSAGE_CSV_ERROR_EMPTY_ACTIONS.format(row=row_num, code=error_code))
                    continue
                
                valid_records.append({
                    'error_code': error_code,
                    'description': description,
                    'suggested_actions': suggested_actions,
                    'category_name': category_name
                })
                
            except Exception as e:
                errors.append(messages.MESSAGE_CSV_ERROR_ROW_PROCESSING.format(row=row_num, error=str(e)))
                
    except csv.Error as e:
        errors.append(messages.MESSAGE_CSV_ERROR_PARSE.format(error=str(e)))
    except Exception as e:
        errors.append(messages.MESSAGE_CSV_ERROR_UNEXPECTED.format(error=str(e)))
    
    return valid_records, errors


def import_error_codes_from_csv(records: List[dict], skip_existing: bool = True) -> CSVImportResult:
    """
    Импортировать коды ошибок из разобранных CSV-записей.

    Args:
        records: Список валидированных словарей записей.
        skip_existing: Если True, пропускать существующие коды; если False — обновлять их.

    Returns:
        CSVImportResult со статистикой импорта.
    """
    result = CSVImportResult()
    
    for record in records:
        try:
            error_code = record['error_code']
            description = record['description']
            suggested_actions = record['suggested_actions']
            category_name = record.get('category_name')
            
            # Проверяем, существует ли код
            existing = get_error_code_by_code(error_code)
            
            if existing:
                if skip_existing:
                    result.skipped_count += 1
                    continue
                else:
                    # Обновляем существующий
                    update_error_code(existing['id'], 'description', description)
                    update_error_code(existing['id'], 'suggested_actions', suggested_actions, update_timestamp=True)
                    if category_name:
                        cat = get_category_by_name(category_name)
                        if cat:
                            update_error_code(existing['id'], 'category_id', cat['id'])
                    result.success_count += 1
                    continue
            
            # Получаем ID категории, если указана
            category_id = None
            if category_name:
                cat = get_category_by_name(category_name)
                if cat:
                    category_id = cat['id']
                # Если категории нет, создаём её
                elif category_name:
                    category_id = create_category(category_name, None, 0)
            
            # Создаём новый код ошибки
            create_error_code(error_code, description, suggested_actions, category_id)
            result.success_count += 1
            
        except Exception as e:
            result.error_count += 1
            result.errors.append(messages.MESSAGE_CSV_ERROR_IMPORT.format(code=record.get('error_code', '?'), error=str(e)))
    
    return result


# Неизвестные коды и статистика

def record_error_request(user_id: int, error_code: str, found: bool) -> None:
    """
    Записать запрос кода ошибки в лог.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                INSERT INTO upos_error_request_log 
                (user_id, error_code, found, request_timestamp)
                VALUES (%s, %s, %s, UNIX_TIMESTAMP())
            """, (user_id, error_code, 1 if found else 0))


def record_unknown_code(error_code: str) -> None:
    """
    Записать или увеличить счётчик запроса неизвестного кода.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Пытаемся обновить существующую запись
            cursor.execute("""
                UPDATE upos_error_unknown_codes 
                SET times_requested = times_requested + 1,
                    last_requested_timestamp = UNIX_TIMESTAMP()
                WHERE error_code = %s
            """, (error_code,))
            
            if cursor.rowcount == 0:
                # Вставляем новую запись
                cursor.execute("""
                    INSERT INTO upos_error_unknown_codes 
                    (error_code, times_requested, first_requested_timestamp, last_requested_timestamp)
                    VALUES (%s, 1, UNIX_TIMESTAMP(), UNIX_TIMESTAMP())
                """, (error_code,))


def get_unknown_codes(page: int = 1, per_page: int = None) -> Tuple[List[dict], int]:
    """
    Получить постраничный список неизвестных кодов.
    """
    if per_page is None:
        per_page = settings.UNKNOWN_CODES_PER_PAGE
    
    offset = (page - 1) * per_page
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT COUNT(*) as cnt FROM upos_error_unknown_codes")
            total = cursor.fetchone()['cnt']
            
            cursor.execute("""
                SELECT * FROM upos_error_unknown_codes
                ORDER BY times_requested DESC, last_requested_timestamp DESC
                LIMIT %s OFFSET %s
            """, (per_page, offset))
            
            return cursor.fetchall(), total


def get_unknown_code_by_id(unknown_id: int) -> Optional[dict]:
    """
    Получить неизвестный код по ID.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT * FROM upos_error_unknown_codes WHERE id = %s", (unknown_id,))
            return cursor.fetchone()


def delete_unknown_code(unknown_id: int) -> bool:
    """
    Удалить запись неизвестного кода (после добавления в известные).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("DELETE FROM upos_error_unknown_codes WHERE id = %s", (unknown_id,))
            return cursor.rowcount > 0


def get_popular_error_codes(limit: int = None) -> List[dict]:
    """
    Получить самые запрашиваемые коды ошибок.
    """
    if limit is None:
        limit = settings.TOP_POPULAR_COUNT
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT e.error_code, e.description, COUNT(r.id) as request_count
                FROM upos_error_codes e
                INNER JOIN upos_error_request_log r ON r.error_code = e.error_code AND r.found = 1
                WHERE e.active = 1
                GROUP BY e.id
                ORDER BY request_count DESC
                LIMIT %s
            """, (limit,))
            return cursor.fetchall()


def get_statistics() -> dict:
    """
    Получить статистику модуля.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            stats = {}
            
            # Общие количества
            cursor.execute("SELECT COUNT(*) as cnt FROM upos_error_codes WHERE active = 1")
            stats['total_codes'] = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM upos_error_categories WHERE active = 1")
            stats['total_categories'] = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM upos_error_unknown_codes")
            stats['unknown_codes'] = cursor.fetchone()['cnt']
            
            # Последние 7 дней
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(found) as found,
                    SUM(1 - found) as not_found
                FROM upos_error_request_log
                WHERE request_timestamp >= UNIX_TIMESTAMP() - 604800
            """)
            result = cursor.fetchone()
            stats['requests_7d'] = result['total'] or 0
            stats['found_7d'] = result['found'] or 0
            stats['not_found_7d'] = result['not_found'] or 0
            
            # Топ кодов
            cursor.execute("""
                SELECT error_code, COUNT(*) as cnt
                FROM upos_error_request_log
                WHERE request_timestamp >= UNIX_TIMESTAMP() - 604800
                GROUP BY error_code
                ORDER BY cnt DESC
                LIMIT 5
            """)
            stats['top_codes'] = cursor.fetchall()
            
            return stats


# ===== ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЕЙ =====

async def enter_upos_module(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Точка входа в модуль ошибок UPOS.
    Показывает подменю.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(get_unauthorized_message(update.effective_user.id))
        return ConversationHandler.END
    
    if check_if_user_admin(update.effective_user.id):
        keyboard = keyboards.get_admin_submenu_keyboard()
    else:
        keyboard = keyboards.get_submenu_keyboard()
    
    await update.message.reply_text(
        messages.MESSAGE_SUBMENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    return SUBMENU  # Входим в состояние подменю, чтобы принимать коды напрямую


async def start_error_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запустить сценарий поиска кода ошибки.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(get_unauthorized_message(update.effective_user.id))
        return ConversationHandler.END
    
    await update.message.reply_text(
        messages.MESSAGE_ENTER_ERROR_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return WAITING_FOR_ERROR_CODE


async def process_error_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать ввод кода ошибки пользователем и вернуть результат.
    """
    user_id = update.effective_user.id
    input_text = update.message.text.strip()
    
    # Валидируем ввод: допускаем числовые и буквенно-цифровые коды
    if not input_text or len(input_text) > 50:
        await update.message.reply_text(
            messages.MESSAGE_INVALID_ERROR_CODE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return WAITING_FOR_ERROR_CODE
    
    # Ищем код ошибки
    error_info = get_error_code_by_code(input_text)
    
    if error_info:
        # Найдено — логируем и показываем
        record_error_request(user_id, input_text, found=True)
        
        response = messages.format_error_code_response(
            error_code=error_info['error_code'],
            description=error_info['description'],
            suggested_actions=error_info['suggested_actions'],
            category_name=error_info.get('category_name'),
            updated_timestamp=error_info.get('updated_timestamp')
        )
        
        await update.message.reply_text(
            response,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        # Не найдено — логируем и добавляем в неизвестные
        record_error_request(user_id, input_text, found=False)
        record_unknown_code(input_text)
        
        escaped_code = messages.escape_markdown_v2(input_text)
        await update.message.reply_text(
            messages.MESSAGE_ERROR_NOT_FOUND.format(code=escaped_code),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    # Возвращаемся в подменю
    if check_if_user_admin(user_id):
        keyboard = keyboards.get_admin_submenu_keyboard()
    else:
        keyboard = keyboards.get_submenu_keyboard()
    
    await update.message.reply_text(
        messages.MESSAGE_SELECT_ACTION,
        reply_markup=keyboard
    )
    
    return SUBMENU  # Остаёмся в подменю для повторных запросов


async def direct_error_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать прямой ввод кода ошибки из подменю (без нажатия кнопки поиска).
    Это позволяет пользователям вводить коды напрямую.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(get_unauthorized_message(update.effective_user.id))
        return ConversationHandler.END
    
    # Переиспользуем логику обработки из process_error_code_input
    return await process_error_code_input(update, context)


async def show_popular_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показать самые запрашиваемые коды ошибок.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(get_unauthorized_message(update.effective_user.id))
        return ConversationHandler.END
    
    popular = get_popular_error_codes()
    
    if not popular:
        await update.message.reply_text(
            messages.MESSAGE_NO_POPULAR_ERRORS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return SUBMENU
    
    text = messages.MESSAGE_POPULAR_ERRORS_HEADER.format(count=len(popular))
    
    for i, error in enumerate(popular, 1):
        line = messages.format_error_list_item(
            error_code=error['error_code'],
            description=error['description'],
            times_requested=error['request_count']
        )
        text += f"{i}\\. {line}\n"
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return SUBMENU


async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменить сценарий поиска ошибки.
    """
    await update.message.reply_text(
        messages.MESSAGE_SEARCH_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


async def cancel_search_on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменить поиск при нажатии кнопки меню.
    Показывает ответ в зависимости от нажатой кнопки.
    """
    # Очищаем временные данные контекста
    context.user_data.pop('upos_temp', None)
    
    # Проверяем, какая кнопка нажата, и отвечаем соответствующим образом
    text = update.message.text if update.message else None
    user_id = update.effective_user.id
    is_admin = check_if_user_admin(user_id)
    
    if text == BUTTON_MAIN_MENU:
        await update.message.reply_text(
            get_main_menu_message(user_id, update.effective_user.first_name),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=is_admin)
        )
        return ConversationHandler.END

    if text:
        from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import text_entered
        await text_entered(update, context)

    return ConversationHandler.END


# ===== ОБРАБОТЧИКИ АДМИНА =====

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показать админ-меню для ошибок UPOS.
    """
    if not check_if_user_admin(update.effective_user.id):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_NOT_AUTHORIZED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    return ADMIN_MENU


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать нажатия кнопок админ-меню.
    """
    text = update.message.text
    
    if text == settings.BUTTON_ADMIN_LIST_ERRORS:
        return await admin_show_errors_list(update, context)
    elif text == settings.BUTTON_ADMIN_ADD_ERROR:
        return await admin_start_add_error(update, context)
    elif text == settings.BUTTON_ADMIN_FIND_ERROR:
        return await admin_start_search_error(update, context)
    elif text == settings.BUTTON_ADMIN_CATEGORIES:
        return await admin_show_categories(update, context)
    elif text == settings.BUTTON_ADMIN_UNKNOWN:
        return await admin_show_unknown_codes(update, context)
    elif text == settings.BUTTON_ADMIN_STATS:
        return await admin_show_statistics(update, context)
    elif text == settings.BUTTON_ADMIN_IMPORT_CSV:
        return await admin_start_csv_import(update, context)
    elif text == settings.BUTTON_ADMIN_BACK_TO_UPOS:
        if check_if_user_admin(update.effective_user.id):
            keyboard = keyboards.get_admin_submenu_keyboard()
        else:
            keyboard = keyboards.get_submenu_keyboard()
        await update.message.reply_text(
            messages.MESSAGE_SUBMENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        return ConversationHandler.END
    elif text == BUTTON_MAIN_MENU:
        await update.message.reply_text(
            get_main_menu_message(update.effective_user.id, update.effective_user.first_name),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=check_if_user_admin(update.effective_user.id))
        )
        return ConversationHandler.END
    
    return ADMIN_MENU


async def admin_show_errors_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> int:
    """
    Показать постраничный список кодов ошибок.
    """
    errors, total = get_all_error_codes(page=page, include_inactive=True)
    
    if not errors:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_ERRORS_LIST_EMPTY,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    
    total_pages = math.ceil(total / settings.ERRORS_PER_PAGE)
    
    text = messages.MESSAGE_ADMIN_ERRORS_LIST_HEADER.format(page=page, total_pages=total_pages)
    
    for error in errors:
        status = "✅" if error['active'] else "🚫"
        line = messages.format_error_list_item(
            error_code=error['error_code'],
            description=error['description'],
            category_name=error.get('category_name')
        )
        text += f"{status} {line}\n"
    
    keyboard = keyboards.get_error_codes_inline_keyboard(errors, page, total_pages)
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return ADMIN_MENU


async def admin_start_search_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запустить сценарий поиска кода ошибки по коду.
    Администратор может ввести код напрямую, не пролистывая список.
    """
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_SEARCH_ERROR_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_SEARCH_ERROR_CODE


async def admin_receive_search_error_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Принять код ошибки для поиска и показать его для редактирования.
    """
    error_code = update.message.text.strip()
    
    # Ищем код ошибки в базе (включая неактивные)
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT e.*, c.name as category_name
                FROM upos_error_codes e
                LEFT JOIN upos_error_categories c ON e.category_id = c.id
                WHERE e.error_code = %s
            """, (error_code,))
            error = cursor.fetchone()
    
    if not error:
        escaped = messages.escape_markdown_v2(error_code)
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_ERROR_NOT_FOUND_FOR_EDIT.format(code=escaped),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    
    # Сохраняем данные ошибки для возможного редактирования
    context.user_data['upos_temp'] = {'error_id': error['id']}
    
    # Форматируем детали ошибки
    text = messages.format_error_code_response(
        error_code=error['error_code'],
        description=error['description'],
        suggested_actions=error['suggested_actions'],
        category_name=error.get('category_name'),
        updated_timestamp=error.get('updated_timestamp')
    )
    
    # Добавляем индикатор статуса
    status = "✅ Активна" if error['active'] else "🚫 Деактивирована"
    status_escaped = messages.escape_markdown_v2(status)
    text += f"\n\n📌 *Статус:* {status_escaped}"
    
    keyboard = keyboards.get_error_detail_keyboard(error['id'], error['active'])
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return ADMIN_MENU


async def admin_start_add_error(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запустить сценарий добавления нового кода ошибки.
    """
    context.user_data['upos_temp'] = {}
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_ERROR_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_ERROR_CODE


async def admin_receive_error_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Принять код ошибки для новой записи.
    """
    error_code = update.message.text.strip()
    
    if error_code_exists(error_code):
        escaped = messages.escape_markdown_v2(error_code)
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_ERROR_EXISTS.format(code=escaped),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_ADD_ERROR_CODE
    
    context.user_data['upos_temp']['error_code'] = error_code
    
    escaped = messages.escape_markdown_v2(error_code)
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_DESCRIPTION.format(code=escaped),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_DESCRIPTION


async def admin_receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Принять описание для новой ошибки.
    """
    description = update.message.text.strip()
    context.user_data['upos_temp']['description'] = description
    
    error_code = context.user_data['upos_temp']['error_code']
    escaped = messages.escape_markdown_v2(error_code)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_SUGGESTED_ACTIONS.format(code=escaped),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_ACTIONS


async def admin_receive_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Принять рекомендации для новой ошибки и показать выбор категории.
    """
    suggested_actions = update.message.text.strip()
    context.user_data['upos_temp']['suggested_actions'] = suggested_actions
    
    error_code = context.user_data['upos_temp']['error_code']
    escaped = messages.escape_markdown_v2(error_code)
    
    # Получаем категории для выбора
    categories, total = get_all_categories(page=1, per_page=20)
    
    if categories:
        keyboard = keyboards.get_categories_inline_keyboard(categories, for_selection=True)
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_SELECT_CATEGORY.format(code=escaped),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        return ADMIN_SELECT_CATEGORY
    else:
        # Категорий нет — создаём ошибку без категории
        return await _create_error_code(update, context, category_id=None)


async def admin_select_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать callback выбора категории.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "upos_cat_skip":
        # Пропускаем выбор категории
        return await _create_error_code(query, context, category_id=None)
    elif data.startswith("upos_cat_select_"):
        category_id = int(data.replace("upos_cat_select_", ""))
        return await _create_error_code(query, context, category_id=category_id)
    
    return ADMIN_SELECT_CATEGORY


async def _create_error_code(update_or_query, context: ContextTypes.DEFAULT_TYPE, category_id: Optional[int]) -> int:
    """
    Вспомогательная функция создания кода ошибки после сбора всех данных.
    """
    temp = context.user_data.get('upos_temp', {})
    error_code = temp.get('error_code')
    description = temp.get('description')
    suggested_actions = temp.get('suggested_actions')
    
    if not all([error_code, description, suggested_actions]):
        return ADMIN_MENU
    
    # Создаём код ошибки
    create_error_code(error_code, description, suggested_actions, category_id)
    
    # Получаем название категории для ответа
    category_name = messages.MESSAGE_NO_CATEGORY
    if category_id:
        cat = get_category_by_id(category_id)
        if cat:
            category_name = cat['name']
    
    escaped_code = messages.escape_markdown_v2(error_code)
    escaped_cat = messages.escape_markdown_v2(category_name)
    escaped_desc = messages.escape_markdown_v2(description[:100] + "..." if len(description) > 100 else description)
    
    response = messages.MESSAGE_ADMIN_ERROR_CREATED.format(
        code=escaped_code,
        category=escaped_cat,
        description=escaped_desc
    )
    
    # Проверяем, это callback-запрос или сообщение
    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(
            response,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
    else:
        # Это callback-запрос
        await update_or_query.edit_message_text(
            response,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        # Отправляем новое сообщение с клавиатурой
        await context.bot.send_message(
            chat_id=update_or_query.message.chat_id,
            text=messages.MESSAGE_SELECT_ACTION,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
    
    # Очищаем временные данные
    context.user_data.pop('upos_temp', None)
    
    return ADMIN_MENU


async def admin_show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> int:
    """
    Показать список категорий.
    """
    categories, total = get_all_categories(page=page)
    
    if not categories:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CATEGORIES_LIST_EMPTY,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_categories_keyboard()
        )
        return ADMIN_MENU
    
    total_pages = math.ceil(total / settings.CATEGORIES_PER_PAGE)
    
    text = messages.MESSAGE_ADMIN_CATEGORIES_LIST_HEADER.format(page=page, total_pages=total_pages)
    
    for cat in categories:
        line = messages.format_category_list_item(
            name=cat['name'],
            error_count=cat['error_count'],
            display_order=cat['display_order']
        )
        text += f"{line}\n"
    
    keyboard = keyboards.get_categories_inline_keyboard(categories, page, total_pages)
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    await update.message.reply_text(
        messages.MESSAGE_SELECT_ACTION,
        reply_markup=keyboards.get_admin_categories_keyboard()
    )
    
    return ADMIN_MENU


async def admin_show_unknown_codes(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> int:
    """
    Показать список неизвестных кодов.
    """
    codes, total = get_unknown_codes(page=page)
    
    if not codes:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_UNKNOWN_CODES_EMPTY,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    
    total_pages = math.ceil(total / settings.UNKNOWN_CODES_PER_PAGE)
    
    text = messages.MESSAGE_ADMIN_UNKNOWN_CODES_HEADER.format(page=page, total_pages=total_pages)
    
    for code in codes:
        line = messages.format_unknown_code_item(
            error_code=code['error_code'],
            times_requested=code['times_requested'],
            last_timestamp=code['last_requested_timestamp']
        )
        text += f"{line}\n"
    
    text += "\nНажмите на код, чтобы добавить его в базу:"
    
    keyboard = keyboards.get_unknown_codes_inline_keyboard(codes, page, total_pages)
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return ADMIN_MENU


async def admin_show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показать статистику модуля.
    """
    stats = get_statistics()
    
    # Форматируем топ-коды
    top_codes_text = ""
    if stats['top_codes']:
        for i, code_info in enumerate(stats['top_codes'], 1):
            escaped_code = messages.escape_markdown_v2(code_info['error_code'])
            top_codes_text += f"{i}\\. `{escaped_code}` \\({code_info['cnt']}x\\)\n"
    else:
        top_codes_text = messages.MESSAGE_NO_DATA
    
    text = messages.MESSAGE_ADMIN_STATS.format(
        total_codes=stats['total_codes'],
        total_categories=stats['total_categories'],
        unknown_codes=stats['unknown_codes'],
        requests_7d=stats['requests_7d'],
        found_7d=stats['found_7d'],
        not_found_7d=stats['not_found_7d'],
        top_codes=top_codes_text
    )
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_MENU


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать callback-и inline-клавиатуры админа.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Просмотр деталей ошибки
    if data.startswith("upos_view_"):
        error_id = int(data.replace("upos_view_", ""))
        return await _show_error_details(query, context, error_id)
    
    # Редактировать описание ошибки
    elif data.startswith("upos_edit_desc_"):
        error_id = int(data.replace("upos_edit_desc_", ""))
        context.user_data['upos_temp'] = {'error_id': error_id, 'edit_field': 'description'}
        error = get_error_code_by_id(error_id)
        if error:
            escaped = messages.escape_markdown_v2(error['description'])
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_EDIT_DESCRIPTION.format(current=escaped),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ADMIN_EDIT_DESCRIPTION
    
    # Редактировать рекомендации
    elif data.startswith("upos_edit_actions_"):
        error_id = int(data.replace("upos_edit_actions_", ""))
        context.user_data['upos_temp'] = {'error_id': error_id, 'edit_field': 'suggested_actions'}
        error = get_error_code_by_id(error_id)
        if error:
            escaped = messages.escape_markdown_v2(error['suggested_actions'])
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_EDIT_ACTIONS.format(current=escaped),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ADMIN_EDIT_ACTIONS
    
    # Редактировать категорию
    elif data.startswith("upos_edit_cat_"):
        error_id = int(data.replace("upos_edit_cat_", ""))
        context.user_data['upos_temp'] = {'error_id': error_id, 'edit_field': 'category_id'}
        categories, _ = get_all_categories(page=1, per_page=20)
        keyboard = keyboards.get_categories_inline_keyboard(categories, for_selection=True)
        await query.edit_message_text(
            "📁 Выберите новую категорию:",
            reply_markup=keyboard
        )
        return ADMIN_SELECT_CATEGORY
    
    # Активировать/деактивировать
    elif data.startswith("upos_activate_"):
        error_id = int(data.replace("upos_activate_", ""))
        update_error_code(error_id, 'active', 1)
        return await _show_error_details(query, context, error_id)
    
    elif data.startswith("upos_deactivate_"):
        error_id = int(data.replace("upos_deactivate_", ""))
        update_error_code(error_id, 'active', 0)
        return await _show_error_details(query, context, error_id)
    
    # Удалить ошибку
    elif data.startswith("upos_delete_"):
        error_id = int(data.replace("upos_delete_", ""))
        keyboard = keyboards.get_confirm_delete_keyboard('error', error_id)
        await query.edit_message_text(
            "⚠️ *Удалить код ошибки?*\n\nЭто действие нельзя отменить\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        return ADMIN_MENU
    
    # Подтвердить удаление
    elif data.startswith("upos_confirm_delete_error_"):
        error_id = int(data.replace("upos_confirm_delete_error_", ""))
        error = get_error_code_by_id(error_id)
        if error:
            delete_error_code(error_id)
            escaped = messages.escape_markdown_v2(error['error_code'])
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_ERROR_DELETED.format(code=escaped),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        return ADMIN_MENU
    
    # Назад к списку ошибок
    elif data == "upos_errors_list":
        # В callback нельзя показать полный список — просто подтверждаем
        await query.edit_message_text(messages.MESSAGE_USE_LIST_BUTTON)
        return ADMIN_MENU
    
    # Назад в админ-меню
    elif data == "upos_admin_menu":
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    # Колбэки категорий
    elif data.startswith("upos_cat_view_"):
        category_id = int(data.replace("upos_cat_view_", ""))
        return await _show_category_details(query, context, category_id)
    
    elif data.startswith("upos_cat_delete_"):
        category_id = int(data.replace("upos_cat_delete_", ""))
        keyboard = keyboards.get_confirm_delete_keyboard('category', category_id)
        await query.edit_message_text(
            "⚠️ *Удалить категорию?*\n\nОшибки в этой категории останутся без категории\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        return ADMIN_MENU
    
    elif data.startswith("upos_confirm_delete_category_"):
        category_id = int(data.replace("upos_confirm_delete_category_", ""))
        cat = get_category_by_id(category_id)
        if cat:
            delete_category(category_id)
            escaped = messages.escape_markdown_v2(cat['name'])
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_CATEGORY_DELETED.format(name=escaped),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        return ADMIN_MENU
    
    # Добавление из неизвестных кодов
    elif data.startswith("upos_add_unknown_"):
        unknown_id = int(data.replace("upos_add_unknown_", ""))
        unknown = get_unknown_code_by_id(unknown_id)
        if unknown:
            context.user_data['upos_temp'] = {
                'error_code': unknown['error_code'],
                'unknown_id': unknown_id
            }
            escaped = messages.escape_markdown_v2(unknown['error_code'])
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_ENTER_DESCRIPTION.format(code=escaped),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ADMIN_ADD_DESCRIPTION
        return ADMIN_MENU
    
    # Пагинация
    elif data.startswith("upos_page_"):
        page = int(data.replace("upos_page_", ""))
        # Пере-запрашиваем и показываем
        errors, total = get_all_error_codes(page=page, include_inactive=True)
        total_pages = math.ceil(total / settings.ERRORS_PER_PAGE)
        
        text = messages.MESSAGE_ADMIN_ERRORS_LIST_HEADER.format(page=page, total_pages=total_pages)
        for error in errors:
            status = "✅" if error['active'] else "🚫"
            line = messages.format_error_list_item(
                error_code=error['error_code'],
                description=error['description'],
                category_name=error.get('category_name')
            )
            text += f"{status} {line}\n"
        
        keyboard = keyboards.get_error_codes_inline_keyboard(errors, page, total_pages)
        await query.edit_message_text(text, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=keyboard)
        return ADMIN_MENU
    
    return ADMIN_MENU


async def _show_error_details(query, context: ContextTypes.DEFAULT_TYPE, error_id: int) -> int:
    """
    Показать детали кода ошибки с опциями редактирования.
    """
    error = get_error_code_by_id(error_id)
    if not error:
        await query.edit_message_text("❌ Ошибка не найдена")
        return ADMIN_MENU
    
    response = messages.format_error_code_response(
        error_code=error['error_code'],
        description=error['description'],
        suggested_actions=error['suggested_actions'],
        category_name=error.get('category_name'),
        updated_timestamp=error.get('updated_timestamp')
    )
    
    if not error['active']:
        response += "\n\n🚫 _Код деактивирован_"
    
    keyboard = keyboards.get_error_detail_keyboard(error_id, error['active'])
    
    await query.edit_message_text(
        response,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return ADMIN_MENU


async def _show_category_details(query, context: ContextTypes.DEFAULT_TYPE, category_id: int) -> int:
    """
    Show category details with edit options.
    """
    cat = get_category_by_id(category_id)
    if not cat:
        await query.edit_message_text("❌ Категория не найдена")
        return ADMIN_MENU
    
    escaped_name = messages.escape_markdown_v2(cat['name'])
    escaped_desc = messages.escape_markdown_v2(cat.get('description') or 'Нет описания')
    
    text = f"📁 *Категория:* {escaped_name}\n\n"
    text += f"📋 *Описание:* {escaped_desc}\n"
    text += f"🔢 *Ошибок в категории:* {cat['error_count']}\n"
    text += f"📊 *Порядок:* {cat['display_order']}"
    
    keyboard = keyboards.get_category_detail_keyboard(category_id)
    
    await query.edit_message_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return ADMIN_MENU


async def admin_receive_edit_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive edited description.
    """
    temp = context.user_data.get('upos_temp', {})
    error_id = temp.get('error_id')
    
    if not error_id:
        return ADMIN_MENU
    
    new_description = update.message.text.strip()
    update_error_code(error_id, 'description', new_description)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ERROR_UPDATED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    context.user_data.pop('upos_temp', None)
    return ADMIN_MENU


async def admin_receive_edit_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive edited suggested actions, ask about updating timestamp.
    """
    temp = context.user_data.get('upos_temp', {})
    error_id = temp.get('error_id')
    
    if not error_id:
        return ADMIN_MENU
    
    new_actions = update.message.text.strip()
    context.user_data['upos_temp']['new_actions'] = new_actions
    
    keyboard = keyboards.get_yes_no_keyboard('upos_update_date', error_id)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_UPDATE_DATE_PROMPT,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return ADMIN_CONFIRM_UPDATE_DATE


async def admin_confirm_update_date_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle update date confirmation.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    temp = context.user_data.get('upos_temp', {})
    error_id = temp.get('error_id')
    new_actions = temp.get('new_actions')
    
    if not error_id or not new_actions:
        return ADMIN_MENU
    
    update_timestamp = data.startswith("upos_update_date_yes")
    
    update_error_code(error_id, 'suggested_actions', new_actions, update_timestamp=update_timestamp)
    
    await query.edit_message_text(
        messages.MESSAGE_ADMIN_ERROR_UPDATED,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=messages.MESSAGE_SELECT_ACTION,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    context.user_data.pop('upos_temp', None)
    return ADMIN_MENU


async def admin_start_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start flow to add a new category.
    """
    context.user_data['upos_temp'] = {}
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_CATEGORY_NAME,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_CATEGORY_NAME


async def admin_receive_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive category name.
    """
    name = update.message.text.strip()
    
    if category_exists(name):
        escaped = messages.escape_markdown_v2(name)
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CATEGORY_EXISTS.format(name=escaped),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_ADD_CATEGORY_NAME
    
    context.user_data['upos_temp']['name'] = name
    
    escaped = messages.escape_markdown_v2(name)
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_CATEGORY_DESCRIPTION.format(name=escaped),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_CATEGORY_DESCRIPTION


async def admin_receive_category_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive category description.
    """
    description = update.message.text.strip()
    
    if description == "-":
        description = None
    
    context.user_data['upos_temp']['description'] = description
    
    name = context.user_data['upos_temp']['name']
    escaped = messages.escape_markdown_v2(name)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_CATEGORY_ORDER.format(name=escaped),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_CATEGORY_ORDER


async def admin_receive_category_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive category display order and create category.
    """
    try:
        display_order = int(update.message.text.strip())
    except ValueError:
        display_order = 0
    
    temp = context.user_data.get('upos_temp', {})
    name = temp.get('name')
    description = temp.get('description')
    
    create_category(name, description, display_order)
    
    escaped = messages.escape_markdown_v2(name)
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CATEGORY_CREATED.format(name=escaped),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    context.user_data.pop('upos_temp', None)
    return ADMIN_MENU


# ===== ОБРАБОТЧИКИ ИМПОРТА CSV =====

async def admin_start_csv_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запустить процесс импорта CSV.
    """
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CSV_IMPORT_START,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_csv_import_keyboard()
    )
    
    return ADMIN_IMPORT_CSV_WAITING


async def admin_receive_csv_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Получить и обработать CSV-файл для импорта.
    """
    # Проверяем, что файл был отправлен
    if not update.message.document:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CSV_NO_FILE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_IMPORT_CSV_WAITING
    
    document = update.message.document
    
    # Проверяем тип файла
    file_name = document.file_name or ''
    if not file_name.lower().endswith('.csv'):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CSV_WRONG_FORMAT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_IMPORT_CSV_WAITING
    
    # Проверяем размер файла (максимум 5 МБ)
    if document.file_size > 5 * 1024 * 1024:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CSV_TOO_LARGE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_IMPORT_CSV_WAITING
    
    try:
        # Загружаем файл
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        raw_bytes = bytes(file_bytes)
        
        # Пытаемся декодировать разными кодировками
        csv_content = None
        
        # Сначала проверяем BOM (маркер порядка байтов)
        if raw_bytes.startswith(b'\xef\xbb\xbf'):
            # UTF-8 с BOM
            csv_content = raw_bytes[3:].decode('utf-8')
        elif raw_bytes.startswith(b'\xff\xfe') or raw_bytes.startswith(b'\xfe\xff'):
            # UTF-16
            csv_content = raw_bytes.decode('utf-16')
        else:
            # Пробуем разные кодировки
            # Порядок важен: сначала utf-8, затем Mac-специфичная, затем Windows, затем запасная
            for encoding in ['utf-8', 'mac_roman', 'cp1251', 'iso-8859-1']:
                try:
                    csv_content = raw_bytes.decode(encoding)
                    # Проверяем, что содержимое похоже на текст (есть кириллица или ASCII)
                    # Это помогает отсеять неверную кодировку
                    if encoding != 'utf-8':
                        # Для не-UTF8 проверяем, нет ли «мусорных» символов
                        test_chars = set(csv_content[:500])
                        # Если видим символы замены, пробуем следующую кодировку
                        if '\ufffd' in test_chars:
                            continue
                    break
                except UnicodeDecodeError:
                    continue
        
        if csv_content is None:
            await update.message.reply_text(
                messages.MESSAGE_ADMIN_CSV_ENCODING_ERROR,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ADMIN_IMPORT_CSV_WAITING
        
        # Нормализуем переводы строк (Mac использует \r, Windows — \r\n, Unix — \n)
        csv_content = csv_content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Разбираем CSV
        records, parse_errors = parse_csv_error_codes(csv_content)
        
        if parse_errors and not records:
            # Только ошибки, валидных записей нет
            escaped_errors = [messages.escape_markdown_v2(e) for e in parse_errors[:10]]
            error_text = messages.MESSAGE_ADMIN_CSV_PARSE_ERRORS.format(
                error_count=len(parse_errors),
                errors='\n'.join(f"• {e}" for e in escaped_errors)
            )
            await update.message.reply_text(
                error_text,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboards.get_csv_import_keyboard()
            )
            return ADMIN_IMPORT_CSV_WAITING
        
        if not records:
            await update.message.reply_text(
                messages.MESSAGE_ADMIN_CSV_NO_RECORDS,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboards.get_csv_import_keyboard()
            )
            return ADMIN_IMPORT_CSV_WAITING
        
        # Сохраняем разобранные записи в контекст для подтверждения
        context.user_data['upos_temp'] = {
            'csv_records': records,
            'csv_parse_errors': parse_errors
        }
        
        # Подсчитываем уже существующие коды
        existing_count = sum(1 for r in records if error_code_exists(r['error_code']))
        new_count = len(records) - existing_count
        
        # Показываем превью и просим подтверждение
        preview_text = messages.MESSAGE_ADMIN_CSV_PREVIEW.format(
            total=len(records),
            new=new_count,
            existing=existing_count,
            parse_errors=len(parse_errors)
        )
        
        if parse_errors:
            preview_text += "\n\n⚠️ *Ошибки парсинга \\(будут пропущены\\):*\n"
            escaped_errors = [messages.escape_markdown_v2(e) for e in parse_errors[:5]]
            preview_text += '\n'.join(f"• {e}" for e in escaped_errors)
            if len(parse_errors) > 5:
                preview_text += messages.MESSAGE_AND_MORE.format(count=len(parse_errors) - 5)
        
        await update.message.reply_text(
            preview_text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_csv_confirm_keyboard()
        )
        
        return ADMIN_IMPORT_CSV_CONFIRM
        
    except Exception as e:
        logger.error(f"Error processing CSV file: {e}")
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CSV_PROCESS_ERROR.format(
                error=messages.escape_markdown_v2(str(e))
            ),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_csv_import_keyboard()
        )
        return ADMIN_IMPORT_CSV_WAITING


async def admin_csv_import_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle CSV import confirmation callbacks.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "upos_csv_cancel":
        context.user_data.pop('upos_temp', None)
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_CSV_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=messages.MESSAGE_SELECT_ACTION,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    
    elif data == "upos_csv_import_skip":
        # Импортировать, пропуская существующие
        return await _perform_csv_import(query, context, skip_existing=True)
    
    elif data == "upos_csv_import_update":
        # Импортировать, обновляя существующие
        return await _perform_csv_import(query, context, skip_existing=False)
    
    return ADMIN_IMPORT_CSV_CONFIRM


async def _perform_csv_import(query, context: ContextTypes.DEFAULT_TYPE, skip_existing: bool) -> int:
    """
    Выполнить фактический импорт CSV.
    """
    temp = context.user_data.get('upos_temp', {})
    records = temp.get('csv_records', [])
    
    if not records:
        await query.edit_message_text(
            messages.MESSAGE_NO_IMPORT_DATA,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    await query.edit_message_text(
        messages.MESSAGE_IMPORT_IN_PROGRESS,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    # Выполняем импорт
    result = import_error_codes_from_csv(records, skip_existing=skip_existing)
    
    # Форматируем сообщение с результатом
    result_text = messages.MESSAGE_ADMIN_CSV_IMPORT_RESULT.format(
        success=result.success_count,
        skipped=result.skipped_count,
        errors=result.error_count
    )
    
    if result.errors:
        result_text += "\n\n⚠️ *Ошибки импорта:*\n"
        escaped_errors = [messages.escape_markdown_v2(e) for e in result.errors[:5]]
        result_text += '\n'.join(f"• {e}" for e in escaped_errors)
        if len(result.errors) > 5:
            result_text += messages.MESSAGE_AND_MORE.format(count=len(result.errors) - 5)
    
    await query.edit_message_text(
        result_text,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=messages.MESSAGE_SELECT_ACTION,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    context.user_data.pop('upos_temp', None)
    return ADMIN_MENU


async def admin_cancel_csv_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменить импорт CSV через кнопку.
    """
    context.user_data.pop('upos_temp', None)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CSV_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_MENU


# ===== СБОРКА CONVERSATION HANDLER =====

def get_menu_button_regex_pattern() -> str:
    """
    Получить regex-шаблон для кнопок модуля UPOS в fallback.
    Также включает кнопки других модулей, чтобы корректно завершать диалог при переключении.
    """
    buttons = []
    # Добавляем кнопки, относящиеся к UPOS
    for row in settings.SUBMENU_BUTTONS:
        for button in row:
            buttons.append(button)
    for row in settings.ADMIN_SUBMENU_BUTTONS:
        for button in row:
            buttons.append(button)
    for row in settings.ADMIN_MENU_BUTTONS:
        buttons.extend(row)
    for row in settings.ADMIN_CATEGORIES_BUTTONS:
        for button in row:
            buttons.append(button)
    
    # Добавляем кнопки основного меню и других модулей, чтобы завершать диалог при переключении
    # Эти кнопки означают, что пользователь хочет выйти из модуля UPOS
    other_module_buttons = [
        BUTTON_MAIN_MENU,
        BUTTON_MODULES,
        BUTTON_SETTINGS,
        BUTTON_VALIDATE_TICKET,
        BUTTON_SCREENSHOT,
        BUTTON_CERTIFICATION,
        BUTTON_KTR,
        BUTTON_FEEDBACK,
        BUTTON_PROFILE,
        BUTTON_MY_INVITES,
        BUTTON_HELP,
        BUTTON_BOT_ADMIN,
        validator_settings.BUTTON_VALIDATE_TICKET,
    ]
    buttons.extend(other_module_buttons)
    
    # Удаляем дубли и экранируем для regex
    unique_buttons = list(set(buttons))
    escaped = [b.replace("(", "\\(").replace(")", "\\)").replace("+", "\\+") for b in unique_buttons]
    
    return "^(" + "|".join(escaped) + ")$"


def get_user_conversation_handler() -> ConversationHandler:
    """
    Получить ConversationHandler для пользовательского поиска ошибок.
    Пользователь должен нажать кнопку поиска, чтобы вводить коды ошибок.
    """
    menu_pattern = get_menu_button_regex_pattern()
    
    return ConversationHandler(
        entry_points=[
            # Вход при нажатии кнопки модуля UPOS
            MessageHandler(filters.Regex(f"^{re.escape(settings.MENU_BUTTON_TEXT)}$"), enter_upos_module),
        ],
        states={
            SUBMENU: [
                # В подменю принимаем кнопку запуска поиска
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_FIND_ERROR)}$"), start_error_search),
                # Кнопка популярных ошибок
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_POPULAR_ERRORS)}$"), show_popular_errors),
            ],
            WAITING_FOR_ERROR_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(menu_pattern), process_error_code_input)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_search),
            CommandHandler("reset", cancel_search_on_menu),
            CommandHandler("menu", cancel_search_on_menu),
            MessageHandler(filters.COMMAND, cancel_search_on_menu),
            MessageHandler(filters.Regex(menu_pattern), cancel_search_on_menu)
        ],
        name="upos_user_conversation",
        persistent=False
    )


def get_admin_conversation_handler() -> ConversationHandler:
    """
    Get ConversationHandler for admin CRUD operations.
    """
    menu_pattern = get_menu_button_regex_pattern()
    
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_PANEL)}$"), admin_menu),
        ],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(admin_callback_handler, pattern="^upos_"),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_LIST_ERRORS)}$"), admin_show_errors_list),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_ADD_ERROR)}$"), admin_start_add_error),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_FIND_ERROR)}$"), admin_start_search_error),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_CATEGORIES)}$"), admin_show_categories),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_UNKNOWN)}$"), admin_show_unknown_codes),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_STATS)}$"), admin_show_statistics),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_ALL_CATEGORIES)}$"), admin_show_categories),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_ADD_CATEGORY)}$"), admin_start_add_category),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_IMPORT_CSV)}$"), admin_start_csv_import),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
            ],
            ADMIN_ADD_ERROR_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_error_code)
            ],
            ADMIN_ADD_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_description)
            ],
            ADMIN_ADD_ACTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_actions)
            ],
            ADMIN_SELECT_CATEGORY: [
                CallbackQueryHandler(admin_select_category_callback, pattern="^upos_cat_")
            ],
            ADMIN_EDIT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_edit_description)
            ],
            ADMIN_EDIT_ACTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_edit_actions)
            ],
            ADMIN_CONFIRM_UPDATE_DATE: [
                CallbackQueryHandler(admin_confirm_update_date_callback, pattern="^upos_update_date_")
            ],
            ADMIN_ADD_CATEGORY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_category_name)
            ],
            ADMIN_ADD_CATEGORY_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_category_description)
            ],
            ADMIN_ADD_CATEGORY_ORDER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_category_order)
            ],
            ADMIN_IMPORT_CSV_WAITING: [
                MessageHandler(filters.Document.FileExtension("csv"), admin_receive_csv_file),
                MessageHandler(filters.Regex("^❌ Отмена$"), admin_cancel_csv_import),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_BACK)}$"), admin_menu),
            ],
            ADMIN_IMPORT_CSV_CONFIRM: [
                CallbackQueryHandler(admin_csv_import_callback, pattern="^upos_csv_"),
            ],
            ADMIN_SEARCH_ERROR_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_search_error_code)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_search),
            CommandHandler("reset", cancel_search_on_menu),
            CommandHandler("menu", cancel_search_on_menu),
            MessageHandler(filters.Regex(f"^{re.escape(BUTTON_MAIN_MENU)}$"), cancel_search_on_menu),
            MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_BACK_TO_UPOS)}$"), enter_upos_module),
            MessageHandler(filters.COMMAND, cancel_search_on_menu),  # Обрабатываем /start и другие команды
        ]
    )
