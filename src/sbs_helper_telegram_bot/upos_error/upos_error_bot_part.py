"""
UPOS Error Bot Part

Main bot handlers for UPOS error code lookup module.
Includes user-facing lookup functionality and admin CRUD operations.
"""
# pylint: disable=line-too-long

import csv
import io
import logging
import math
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
from src.common.telegram_user import check_if_user_legit, check_if_user_admin
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE, get_main_menu_keyboard

from . import messages
from . import keyboards
from . import settings

logger = logging.getLogger(__name__)

# Conversation states for user lookup
WAITING_FOR_ERROR_CODE = 1

# Conversation states for admin operations
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


# ===== DATABASE OPERATIONS =====

def get_error_code_by_code(error_code: str) -> Optional[dict]:
    """
    Look up an error code in the database.
    
    Args:
        error_code: The error code to look up
        
    Returns:
        Dict with error info or None if not found
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
    Get error code by ID (for admin).
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
    Get paginated list of error codes.
    
    Returns:
        Tuple of (error_codes_list, total_count)
    """
    if per_page is None:
        per_page = settings.ERRORS_PER_PAGE
    
    offset = (page - 1) * per_page
    active_filter = "" if include_inactive else "WHERE e.active = 1"
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Get total count
            cursor.execute(f"SELECT COUNT(*) as cnt FROM upos_error_codes e {active_filter}")
            total = cursor.fetchone()['cnt']
            
            # Get page
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
    Create a new error code.
    
    Returns:
        The new error code ID
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
    Update a field of an error code.
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
    Delete an error code (hard delete).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("DELETE FROM upos_error_codes WHERE id = %s", (error_id,))
            return cursor.rowcount > 0


def error_code_exists(error_code: str) -> bool:
    """
    Check if error code already exists.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM upos_error_codes WHERE error_code = %s", (error_code,))
            return cursor.fetchone() is not None


# Category operations

def get_all_categories(page: int = 1, per_page: int = None) -> Tuple[List[dict], int]:
    """
    Get paginated list of categories.
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
    Get category by ID.
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
    Create a new category.
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
    Update a category field.
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
    Delete a category (sets error codes category_id to NULL).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # FK constraint with ON DELETE SET NULL handles error codes
            cursor.execute("DELETE FROM upos_error_categories WHERE id = %s", (category_id,))
            return cursor.rowcount > 0


def category_exists(name: str) -> bool:
    """
    Check if category name already exists.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM upos_error_categories WHERE name = %s", (name,))
            return cursor.fetchone() is not None


def get_category_by_name(name: str) -> Optional[dict]:
    """
    Get category by name.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT * FROM upos_error_categories WHERE name = %s AND active = 1", (name,))
            return cursor.fetchone()


# CSV Import structures and functions

@dataclass
class CSVImportResult:
    """Result of CSV import operation."""
    success_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def parse_csv_error_codes(csv_content: str, delimiter: str = ',') -> Tuple[List[dict], List[str]]:
    """
    Parse CSV content and validate error codes data.
    
    Expected CSV format:
    error_code,description,suggested_actions,category (optional)
    
    Args:
        csv_content: Raw CSV content as string
        delimiter: CSV delimiter character
        
    Returns:
        Tuple of (valid_records, errors_list)
    """
    valid_records = []
    errors = []
    
    try:
        # Try to detect the delimiter if it's not comma
        if delimiter == ',' and ';' in csv_content and ',' not in csv_content.split('\n')[0]:
            delimiter = ';'
        
        reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)
        
        # Check for required fields
        if not reader.fieldnames:
            errors.append("CSV файл пуст или имеет неверный формат")
            return [], errors
        
        fieldnames_lower = [f.lower().strip() if f else '' for f in reader.fieldnames]
        
        # Map possible column names
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
        
        for row_num, row in enumerate(reader, start=2):  # Start from 2 (header is row 1)
            try:
                error_code = (row.get(code_col) or '').strip()
                description = (row.get(desc_col) or '').strip()
                suggested_actions = (row.get(actions_col) or '').strip()
                category_name = (row.get(category_col) or '').strip() if category_col else None
                
                # Validate required fields
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
    Import error codes from parsed CSV records.
    
    Args:
        records: List of validated record dicts
        skip_existing: If True, skip existing codes; if False, update them
        
    Returns:
        CSVImportResult with import statistics
    """
    result = CSVImportResult()
    
    for record in records:
        try:
            error_code = record['error_code']
            description = record['description']
            suggested_actions = record['suggested_actions']
            category_name = record.get('category_name')
            
            # Check if code exists
            existing = get_error_code_by_code(error_code)
            
            if existing:
                if skip_existing:
                    result.skipped_count += 1
                    continue
                else:
                    # Update existing
                    update_error_code(existing['id'], 'description', description)
                    update_error_code(existing['id'], 'suggested_actions', suggested_actions, update_timestamp=True)
                    if category_name:
                        cat = get_category_by_name(category_name)
                        if cat:
                            update_error_code(existing['id'], 'category_id', cat['id'])
                    result.success_count += 1
                    continue
            
            # Get category ID if provided
            category_id = None
            if category_name:
                cat = get_category_by_name(category_name)
                if cat:
                    category_id = cat['id']
                # If category doesn't exist, create it
                elif category_name:
                    category_id = create_category(category_name, None, 0)
            
            # Create new error code
            create_error_code(error_code, description, suggested_actions, category_id)
            result.success_count += 1
            
        except Exception as e:
            result.error_count += 1
            result.errors.append(messages.MESSAGE_CSV_ERROR_IMPORT.format(code=record.get('error_code', '?'), error=str(e)))
    
    return result


# Unknown codes and statistics

def record_error_request(user_id: int, error_code: str, found: bool) -> None:
    """
    Record an error code request in the log.
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
    Record or increment an unknown code request.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Try to update existing
            cursor.execute("""
                UPDATE upos_error_unknown_codes 
                SET times_requested = times_requested + 1,
                    last_requested_timestamp = UNIX_TIMESTAMP()
                WHERE error_code = %s
            """, (error_code,))
            
            if cursor.rowcount == 0:
                # Insert new
                cursor.execute("""
                    INSERT INTO upos_error_unknown_codes 
                    (error_code, times_requested, first_requested_timestamp, last_requested_timestamp)
                    VALUES (%s, 1, UNIX_TIMESTAMP(), UNIX_TIMESTAMP())
                """, (error_code,))


def get_unknown_codes(page: int = 1, per_page: int = None) -> Tuple[List[dict], int]:
    """
    Get paginated list of unknown codes.
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
    Get unknown code by ID.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT * FROM upos_error_unknown_codes WHERE id = %s", (unknown_id,))
            return cursor.fetchone()


def delete_unknown_code(unknown_id: int) -> bool:
    """
    Delete an unknown code entry (after adding it to known codes).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("DELETE FROM upos_error_unknown_codes WHERE id = %s", (unknown_id,))
            return cursor.rowcount > 0


def get_popular_error_codes(limit: int = None) -> List[dict]:
    """
    Get most requested error codes.
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
    Get module statistics.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            stats = {}
            
            # Total counts
            cursor.execute("SELECT COUNT(*) as cnt FROM upos_error_codes WHERE active = 1")
            stats['total_codes'] = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM upos_error_categories WHERE active = 1")
            stats['total_categories'] = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM upos_error_unknown_codes")
            stats['unknown_codes'] = cursor.fetchone()['cnt']
            
            # Last 7 days
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
            
            # Top codes
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


# ===== USER HANDLERS =====

async def enter_upos_module(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for UPOS error module.
    Shows the submenu.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
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
    return ConversationHandler.END


async def start_error_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start error code search flow.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    await update.message.reply_text(
        messages.MESSAGE_ENTER_ERROR_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return WAITING_FOR_ERROR_CODE


async def process_error_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process user's error code input and return result.
    """
    user_id = update.effective_user.id
    input_text = update.message.text.strip()
    
    # Validate input - allow numeric and alphanumeric codes
    if not input_text or len(input_text) > 50:
        await update.message.reply_text(
            messages.MESSAGE_INVALID_ERROR_CODE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return WAITING_FOR_ERROR_CODE
    
    # Look up the error code
    error_info = get_error_code_by_code(input_text)
    
    if error_info:
        # Found - log and display
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
        # Not found - log and add to unknown
        record_error_request(user_id, input_text, found=False)
        record_unknown_code(input_text)
        
        escaped_code = messages.escape_markdown_v2(input_text)
        await update.message.reply_text(
            messages.MESSAGE_ERROR_NOT_FOUND.format(code=escaped_code),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    # Return to submenu
    if check_if_user_admin(user_id):
        keyboard = keyboards.get_admin_submenu_keyboard()
    else:
        keyboard = keyboards.get_submenu_keyboard()
    
    await update.message.reply_text(
        messages.MESSAGE_SELECT_ACTION,
        reply_markup=keyboard
    )
    
    return ConversationHandler.END


async def direct_error_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle direct error code input from submenu (without pressing search button).
    This allows users to enter error codes directly.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    # Reuse the same processing logic as process_error_code_input
    return await process_error_code_input(update, context)


async def show_popular_errors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show most requested error codes.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    popular = get_popular_error_codes()
    
    if not popular:
        await update.message.reply_text(
            messages.MESSAGE_NO_POPULAR_ERRORS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
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


async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the error search flow.
    """
    await update.message.reply_text(
        messages.MESSAGE_SEARCH_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


async def cancel_search_on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel search when menu button is pressed.
    """
    # Clear any context data
    context.user_data.pop('upos_temp', None)
    return ConversationHandler.END


# ===== ADMIN HANDLERS =====

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show admin menu for UPOS errors.
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
    Handle admin menu button presses.
    """
    text = update.message.text
    
    if text == "📋 Список ошибок":
        return await admin_show_errors_list(update, context)
    elif text == "➕ Добавить ошибку":
        return await admin_start_add_error(update, context)
    elif text == "🔍 Найти ошибку":
        return await admin_start_search_error(update, context)
    elif text == "📁 Категории":
        return await admin_show_categories(update, context)
    elif text == "❓ Неизвестные коды":
        return await admin_show_unknown_codes(update, context)
    elif text == "📈 Статистика":
        return await admin_show_statistics(update, context)
    elif text == "📥 Импорт CSV":
        return await admin_start_csv_import(update, context)
    elif text == "🔙 Назад в UPOS":
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
    elif text == "🏠 Главное меню":
        await update.message.reply_text(
            "🏠 *Главное меню*",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    return ADMIN_MENU


async def admin_show_errors_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> int:
    """
    Show paginated list of error codes.
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
    Start the flow to search for an error code by code.
    Admin can type the error code directly instead of scrolling through the list.
    """
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_SEARCH_ERROR_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_SEARCH_ERROR_CODE


async def admin_receive_search_error_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive error code for search and show it for editing.
    """
    error_code = update.message.text.strip()
    
    # Look up the error code in the database (include inactive)
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
    
    # Store error info for potential edit
    context.user_data['upos_temp'] = {'error_id': error['id']}
    
    # Format error details
    text = messages.format_error_code_response(
        error_code=error['error_code'],
        description=error['description'],
        suggested_actions=error['suggested_actions'],
        category_name=error.get('category_name'),
        updated_timestamp=error.get('updated_timestamp')
    )
    
    # Add status indicator
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
    Start the flow to add a new error code.
    """
    context.user_data['upos_temp'] = {}
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_ERROR_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_ERROR_CODE


async def admin_receive_error_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive error code for new error.
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
    Receive description for new error.
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
    Receive suggested actions for new error, then show category selection.
    """
    suggested_actions = update.message.text.strip()
    context.user_data['upos_temp']['suggested_actions'] = suggested_actions
    
    error_code = context.user_data['upos_temp']['error_code']
    escaped = messages.escape_markdown_v2(error_code)
    
    # Get categories for selection
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
        # No categories - create error without category
        return await _create_error_code(update, context, category_id=None)


async def admin_select_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle category selection callback.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "upos_cat_skip":
        # Skip category selection
        return await _create_error_code(query, context, category_id=None)
    elif data.startswith("upos_cat_select_"):
        category_id = int(data.replace("upos_cat_select_", ""))
        return await _create_error_code(query, context, category_id=category_id)
    
    return ADMIN_SELECT_CATEGORY


async def _create_error_code(update_or_query, context: ContextTypes.DEFAULT_TYPE, category_id: Optional[int]) -> int:
    """
    Helper to create the error code after all inputs collected.
    """
    temp = context.user_data.get('upos_temp', {})
    error_code = temp.get('error_code')
    description = temp.get('description')
    suggested_actions = temp.get('suggested_actions')
    
    if not all([error_code, description, suggested_actions]):
        return ADMIN_MENU
    
    # Create the error code
    create_error_code(error_code, description, suggested_actions, category_id)
    
    # Get category name for response
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
    
    # Check if this was a callback query or message
    if hasattr(update_or_query, 'message') and update_or_query.message:
        await update_or_query.message.reply_text(
            response,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
    else:
        # It's a callback query
        await update_or_query.edit_message_text(
            response,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        # Send new message with keyboard
        await context.bot.send_message(
            chat_id=update_or_query.message.chat_id,
            text=messages.MESSAGE_SELECT_ACTION,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
    
    # Clear temp data
    context.user_data.pop('upos_temp', None)
    
    return ADMIN_MENU


async def admin_show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> int:
    """
    Show categories list.
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
    Show unknown codes list.
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
    Show module statistics.
    """
    stats = get_statistics()
    
    # Format top codes
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
    Handle admin inline keyboard callbacks.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # View error details
    if data.startswith("upos_view_"):
        error_id = int(data.replace("upos_view_", ""))
        return await _show_error_details(query, context, error_id)
    
    # Edit error description
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
    
    # Edit suggested actions
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
    
    # Edit category
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
    
    # Activate/deactivate
    elif data.startswith("upos_activate_"):
        error_id = int(data.replace("upos_activate_", ""))
        update_error_code(error_id, 'active', 1)
        return await _show_error_details(query, context, error_id)
    
    elif data.startswith("upos_deactivate_"):
        error_id = int(data.replace("upos_deactivate_", ""))
        update_error_code(error_id, 'active', 0)
        return await _show_error_details(query, context, error_id)
    
    # Delete error
    elif data.startswith("upos_delete_"):
        error_id = int(data.replace("upos_delete_", ""))
        keyboard = keyboards.get_confirm_delete_keyboard('error', error_id)
        await query.edit_message_text(
            "⚠️ *Удалить код ошибки?*\n\nЭто действие нельзя отменить\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        return ADMIN_MENU
    
    # Confirm delete
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
    
    # Back to errors list
    elif data == "upos_errors_list":
        # Can't show full list in callback, just acknowledge
        await query.edit_message_text(messages.MESSAGE_USE_LIST_BUTTON)
        return ADMIN_MENU
    
    # Back to admin menu
    elif data == "upos_admin_menu":
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    # Category callbacks
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
    
    # Add from unknown codes
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
    
    # Pagination
    elif data.startswith("upos_page_"):
        page = int(data.replace("upos_page_", ""))
        # Re-fetch and display
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
    Show error code details with edit options.
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


# ===== CSV IMPORT HANDLERS =====

async def admin_start_csv_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start CSV import flow.
    """
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CSV_IMPORT_START,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_csv_import_keyboard()
    )
    
    return ADMIN_IMPORT_CSV_WAITING


async def admin_receive_csv_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive and process CSV file for import.
    """
    # Check if file was sent
    if not update.message.document:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CSV_NO_FILE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_IMPORT_CSV_WAITING
    
    document = update.message.document
    
    # Validate file type
    file_name = document.file_name or ''
    if not file_name.lower().endswith('.csv'):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CSV_WRONG_FORMAT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_IMPORT_CSV_WAITING
    
    # Check file size (max 5MB)
    if document.file_size > 5 * 1024 * 1024:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CSV_TOO_LARGE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_IMPORT_CSV_WAITING
    
    try:
        # Download file
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()
        raw_bytes = bytes(file_bytes)
        
        # Try to decode with different encodings
        csv_content = None
        
        # Check for BOM (Byte Order Mark) first
        if raw_bytes.startswith(b'\xef\xbb\xbf'):
            # UTF-8 with BOM
            csv_content = raw_bytes[3:].decode('utf-8')
        elif raw_bytes.startswith(b'\xff\xfe') or raw_bytes.startswith(b'\xfe\xff'):
            # UTF-16
            csv_content = raw_bytes.decode('utf-16')
        else:
            # Try different encodings
            # Order matters: utf-8 first, then Mac-specific, then Windows, then fallback
            for encoding in ['utf-8', 'mac_roman', 'cp1251', 'iso-8859-1']:
                try:
                    csv_content = raw_bytes.decode(encoding)
                    # Verify the content looks reasonable (has some Cyrillic or ASCII)
                    # This helps detect wrong encoding
                    if encoding != 'utf-8':
                        # For non-UTF8, check if result has garbage characters
                        test_chars = set(csv_content[:500])
                        # If we see replacement characters, try next encoding
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
        
        # Normalize line endings (Mac uses \r, Windows uses \r\n, Unix uses \n)
        csv_content = csv_content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Parse CSV
        records, parse_errors = parse_csv_error_codes(csv_content)
        
        if parse_errors and not records:
            # Only errors, no valid records
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
        
        # Store parsed records in context for confirmation
        context.user_data['upos_temp'] = {
            'csv_records': records,
            'csv_parse_errors': parse_errors
        }
        
        # Count existing codes
        existing_count = sum(1 for r in records if error_code_exists(r['error_code']))
        new_count = len(records) - existing_count
        
        # Show preview and ask for confirmation
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
        # Import, skip existing
        return await _perform_csv_import(query, context, skip_existing=True)
    
    elif data == "upos_csv_import_update":
        # Import, update existing
        return await _perform_csv_import(query, context, skip_existing=False)
    
    return ADMIN_IMPORT_CSV_CONFIRM


async def _perform_csv_import(query, context: ContextTypes.DEFAULT_TYPE, skip_existing: bool) -> int:
    """
    Perform the actual CSV import.
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
    
    # Perform import
    result = import_error_codes_from_csv(records, skip_existing=skip_existing)
    
    # Format result message
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
    Cancel CSV import via button.
    """
    context.user_data.pop('upos_temp', None)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CSV_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_MENU


# ===== CONVERSATION HANDLER BUILDER =====

def get_menu_button_regex_pattern() -> str:
    """
    Get regex pattern matching all UPOS module menu buttons.
    Used for fallback handlers.
    """
    buttons = []
    for row in settings.SUBMENU_BUTTONS:
        buttons.extend(row)
    for row in settings.ADMIN_SUBMENU_BUTTONS:
        buttons.extend(row)
    for row in settings.ADMIN_MENU_BUTTONS:
        buttons.extend(row)
    for row in settings.ADMIN_CATEGORIES_BUTTONS:
        buttons.extend(row)
    
    # Add main menu navigation buttons that should also exit the conversation
    buttons.extend([
        "📦 Модули",
        "⚙️ Настройки",
        "✅ Валидация заявок",
        "📸 Обработать скриншот",
        "🎫 Мои инвайты",
        "❓ Помощь",
        "⚡ Начать работу",
        "🏠 Главное меню",
        "🛠️ Админ бота",
        "🏆 Профиль",
        "🔢 UPOS Ошибки",
        "📝 Аттестация",
        "⏱️ КТР",
        "📬 Обратная связь",
    ])
    
    # Remove duplicates and escape for regex
    unique_buttons = list(set(buttons))
    escaped = [b.replace("(", "\\(").replace(")", "\\)").replace("+", "\\+") for b in unique_buttons]
    
    return "^(" + "|".join(escaped) + ")$"


def get_user_conversation_handler() -> ConversationHandler:
    """
    Get ConversationHandler for user error lookup flow.
    Allows both button-based and direct error code entry.
    """
    menu_pattern = get_menu_button_regex_pattern()
    
    return ConversationHandler(
        entry_points=[
            # Button-based entry (backward compatibility)
            MessageHandler(filters.Regex("^🔍 Найти код ошибки$"), start_error_search),
            # Direct text input entry - filtered to exclude menu buttons
            MessageHandler(
                filters.TEXT & ~filters.COMMAND & ~filters.Regex(menu_pattern),
                direct_error_code_input
            ),
        ],
        states={
            WAITING_FOR_ERROR_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_error_code_input)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_search),
            MessageHandler(filters.COMMAND, cancel_search_on_menu),
            MessageHandler(filters.Regex(menu_pattern), cancel_search_on_menu)
        ]
    )


def get_admin_conversation_handler() -> ConversationHandler:
    """
    Get ConversationHandler for admin CRUD operations.
    """
    menu_pattern = get_menu_button_regex_pattern()
    
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🔐 Админ UPOS$"), admin_menu),
        ],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(admin_callback_handler, pattern="^upos_"),
                MessageHandler(filters.Regex("^📋 Список ошибок$"), admin_show_errors_list),
                MessageHandler(filters.Regex("^➕ Добавить ошибку$"), admin_start_add_error),
                MessageHandler(filters.Regex("^🔍 Найти ошибку$"), admin_start_search_error),
                MessageHandler(filters.Regex("^📁 Категории$"), admin_show_categories),
                MessageHandler(filters.Regex("^❓ Неизвестные коды$"), admin_show_unknown_codes),
                MessageHandler(filters.Regex("^📈 Статистика$"), admin_show_statistics),
                MessageHandler(filters.Regex("^📋 Все категории$"), admin_show_categories),
                MessageHandler(filters.Regex("^➕ Добавить категорию$"), admin_start_add_category),
                MessageHandler(filters.Regex("^📥 Импорт CSV$"), admin_start_csv_import),
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
                MessageHandler(filters.Regex("^🔙 Админ UPOS$"), admin_menu),
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
            MessageHandler(filters.Regex("^🏠 Главное меню$"), cancel_search_on_menu),
            MessageHandler(filters.Regex("^🔙 Назад в UPOS$"), enter_upos_module),
            MessageHandler(filters.COMMAND, cancel_search_on_menu),  # Handle /start and other commands
        ]
    )
