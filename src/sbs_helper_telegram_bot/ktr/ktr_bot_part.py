"""
KTR Bot Part (Коэффициент Трудозатрат)

Main bot handlers for KTR code lookup module.
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
SUBMENU = 0  # User is in the module submenu
WAITING_FOR_CODE = 1

# Conversation states for admin operations
(
    ADMIN_MENU,
    ADMIN_ADD_CODE,
    ADMIN_ADD_DESCRIPTION,
    ADMIN_ADD_MINUTES,
    ADMIN_SELECT_CATEGORY,
    ADMIN_EDIT_DESCRIPTION,
    ADMIN_EDIT_MINUTES,
    ADMIN_ADD_CATEGORY_NAME,
    ADMIN_ADD_CATEGORY_DESCRIPTION,
    ADMIN_ADD_CATEGORY_ORDER,
    ADMIN_EDIT_CATEGORY_NAME,
    ADMIN_EDIT_CATEGORY_DESCRIPTION,
    ADMIN_IMPORT_CSV_WAITING,
    ADMIN_IMPORT_CSV_CONFIRM,
    ADMIN_SEARCH_CODE
) = range(200, 215)


# ===== HELPER FUNCTIONS =====

def _validate_date_format(date_str: str) -> bool:
    """
    Validate date string is in dd.mm.yyyy format.
    
    Args:
        date_str: Date string to validate
        
    Returns:
        True if valid format, False otherwise
    """
    if not date_str:
        return False
    
    parts = date_str.split('.')
    if len(parts) != 3:
        return False
    
    try:
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        # Basic validation
        if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
            return False
        return True
    except (ValueError, IndexError):
        return False


# ===== DATABASE OPERATIONS =====

def get_ktr_code_by_code(code: str) -> Optional[dict]:
    """
    Look up a KTR code in the database.
    
    Args:
        code: The KTR code to look up
        
    Returns:
        Dict with code info or None if not found
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT k.*, c.name as category_name
                FROM ktr_codes k
                LEFT JOIN ktr_categories c ON k.category_id = c.id
                WHERE k.code = %s AND k.active = 1
            """, (code,))
            return cursor.fetchone()


def get_ktr_code_by_id(code_id: int) -> Optional[dict]:
    """
    Get KTR code by ID (for admin).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT k.*, c.name as category_name
                FROM ktr_codes k
                LEFT JOIN ktr_categories c ON k.category_id = c.id
                WHERE k.id = %s
            """, (code_id,))
            return cursor.fetchone()


def get_all_ktr_codes(page: int = 1, per_page: int = None, include_inactive: bool = False) -> Tuple[List[dict], int]:
    """
    Get paginated list of KTR codes.
    
    Returns:
        Tuple of (codes_list, total_count)
    """
    if per_page is None:
        per_page = settings.CODES_PER_PAGE
    
    offset = (page - 1) * per_page
    active_filter = "" if include_inactive else "WHERE k.active = 1"
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Get total count
            cursor.execute(f"SELECT COUNT(*) as cnt FROM ktr_codes k {active_filter}")
            total = cursor.fetchone()['cnt']
            
            # Get page
            cursor.execute(f"""
                SELECT k.*, c.name as category_name
                FROM ktr_codes k
                LEFT JOIN ktr_categories c ON k.category_id = c.id
                {active_filter}
                ORDER BY k.code
                LIMIT %s OFFSET %s
            """, (per_page, offset))
            
            return cursor.fetchall(), total


def create_ktr_code(code: str, description: str, minutes: int, category_id: Optional[int] = None, date_updated: Optional[str] = None) -> int:
    """
    Create a new KTR code.
    
    Args:
        code: KTR code
        description: Work description
        minutes: Labor cost in minutes
        category_id: Optional category ID
        date_updated: Optional update date in dd.mm.yyyy format
    
    Returns:
        The new code ID
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                INSERT INTO ktr_codes 
                (code, description, minutes, category_id, date_updated, created_timestamp)
                VALUES (%s, %s, %s, %s, %s, UNIX_TIMESTAMP())
            """, (code, description, minutes, category_id, date_updated))
            return cursor.lastrowid


def update_ktr_code(code_id: int, field: str, value, update_timestamp: bool = False) -> bool:
    """
    Update a field of a KTR code.
    """
    allowed_fields = ['description', 'minutes', 'category_id', 'active', 'date_updated']
    if field not in allowed_fields:
        return False
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            if update_timestamp:
                cursor.execute(f"""
                    UPDATE ktr_codes 
                    SET {field} = %s, updated_timestamp = UNIX_TIMESTAMP()
                    WHERE id = %s
                """, (value, code_id))
            else:
                cursor.execute(f"""
                    UPDATE ktr_codes 
                    SET {field} = %s
                    WHERE id = %s
                """, (value, code_id))
            return cursor.rowcount > 0


def delete_ktr_code(code_id: int) -> bool:
    """
    Delete a KTR code (hard delete).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("DELETE FROM ktr_codes WHERE id = %s", (code_id,))
            return cursor.rowcount > 0


def ktr_code_exists(code: str) -> bool:
    """
    Check if KTR code already exists (including inactive).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM ktr_codes WHERE code = %s", (code,))
            return cursor.fetchone() is not None


def get_ktr_code_by_code_any_status(code: str) -> Optional[dict]:
    """
    Look up a KTR code in the database (including inactive codes).
    Used for import operations.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT k.*, c.name as category_name
                FROM ktr_codes k
                LEFT JOIN ktr_categories c ON k.category_id = c.id
                WHERE k.code = %s
            """, (code,))
            return cursor.fetchone()


def batch_check_existing_codes(codes: List[str]) -> set:
    """
    Check which codes already exist in the database (batch operation).
    Returns a set of existing codes.
    """
    if not codes:
        return set()
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Use IN clause for batch check
            placeholders = ','.join(['%s'] * len(codes))
            cursor.execute(f"SELECT code FROM ktr_codes WHERE code IN ({placeholders})", tuple(codes))
            return {row['code'] for row in cursor.fetchall()}


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
            cursor.execute("SELECT COUNT(*) as cnt FROM ktr_categories WHERE active = 1")
            total = cursor.fetchone()['cnt']
            
            cursor.execute("""
                SELECT c.*, 
                    (SELECT COUNT(*) FROM ktr_codes WHERE category_id = c.id) as code_count
                FROM ktr_categories c
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
                    (SELECT COUNT(*) FROM ktr_codes WHERE category_id = c.id) as code_count
                FROM ktr_categories c
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
                INSERT INTO ktr_categories 
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
                UPDATE ktr_categories 
                SET {field} = %s, updated_timestamp = UNIX_TIMESTAMP()
                WHERE id = %s
            """, (value, category_id))
            return cursor.rowcount > 0


def delete_category(category_id: int) -> bool:
    """
    Delete a category (sets codes category_id to NULL).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # FK constraint with ON DELETE SET NULL handles codes
            cursor.execute("DELETE FROM ktr_categories WHERE id = %s", (category_id,))
            return cursor.rowcount > 0


def category_exists(name: str) -> bool:
    """
    Check if category name already exists.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM ktr_categories WHERE name = %s", (name,))
            return cursor.fetchone() is not None


def get_category_by_name(name: str) -> Optional[dict]:
    """
    Get category by name.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT * FROM ktr_categories WHERE name = %s AND active = 1", (name,))
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


def parse_csv_ktr_codes(csv_content: str, delimiter: str = ',') -> Tuple[List[dict], List[str]]:
    """
    Parse CSV content and validate KTR codes data.
    
    Expected CSV format:
    code,description,minutes,category (optional)
    
    Unexpected columns are ignored.
    
    Args:
        csv_content: Raw CSV content as string
        delimiter: CSV delimiter character
        
    Returns:
        Tuple of (valid_records, errors_list)
    """
    valid_records = []
    errors = []
    seen_codes = set()  # Track duplicates within CSV
    
    try:
        # Limit content size to prevent memory issues
        max_content_size = 5 * 1024 * 1024  # 5MB
        if len(csv_content) > max_content_size:
            errors.append("CSV файл слишком большой")
            return [], errors
        
        # Try to detect the delimiter if it's not comma
        first_line = csv_content.split('\n')[0] if csv_content else ''
        if delimiter == ',' and ';' in first_line and ',' not in first_line:
            delimiter = ';'
        
        reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)
        
        # Check for required fields
        if not reader.fieldnames:
            errors.append("CSV файл пуст или имеет неверный формат")
            return [], errors
        
        fieldnames_lower = [f.lower().strip() if f else '' for f in reader.fieldnames]
        
        # Map possible column names (only the ones we expect)
        code_col = None
        desc_col = None
        minutes_col = None
        category_col = None
        date_col = None
        
        for i, fname in enumerate(fieldnames_lower):
            if fname in ('code', 'код', 'ktr_code', 'код_ктр', 'ktr'):
                code_col = reader.fieldnames[i]
            elif fname in ('description', 'описание', 'desc', 'название'):
                desc_col = reader.fieldnames[i]
            elif fname in ('minutes', 'минуты', 'время', 'time', 'мин', 'min'):
                minutes_col = reader.fieldnames[i]
            elif fname in ('category', 'категория', 'cat'):
                category_col = reader.fieldnames[i]
            elif fname in ('date_updated', 'дата_обновления', 'дата', 'date', 'updated'):
                date_col = reader.fieldnames[i]
            # Any other columns are silently ignored
        
        if not code_col:
            errors.append(messages.MESSAGE_CSV_ERROR_NO_CODE_COLUMN)
            return [], errors
        if not desc_col:
            errors.append(messages.MESSAGE_CSV_ERROR_NO_DESC_COLUMN)
            return [], errors
        if not minutes_col:
            errors.append(messages.MESSAGE_CSV_ERROR_NO_MINUTES_COLUMN)
            return [], errors
        
        row_num = 1  # Header is row 1
        max_rows = 10000  # Limit number of rows to prevent hangs
        
        for row in reader:
            row_num += 1
            
            # Safety limit
            if row_num > max_rows + 1:
                errors.append(f"Превышен лимит строк ({max_rows}). Остальные строки пропущены.")
                break
            
            try:
                # Only extract the columns we mapped, ignore everything else
                code = (row.get(code_col) or '').strip().upper()  # Normalize to uppercase
                description = (row.get(desc_col) or '').strip()
                minutes_str = (row.get(minutes_col) or '').strip()
                category_name = (row.get(category_col) or '').strip() if category_col else None
                date_updated = (row.get(date_col) or '').strip() if date_col else None
                
                # Skip empty rows
                if not code and not description and not minutes_str:
                    continue
                
                # Validate required fields
                if not code:
                    errors.append(messages.MESSAGE_CSV_ERROR_EMPTY_CODE.format(row=row_num))
                    continue
                
                # Check code format (alphanumeric)
                if not code.replace('-', '').replace('_', '').replace('.', '').isalnum():
                    errors.append(f"Строка {row_num}: код '{code}' содержит недопустимые символы")
                    continue
                
                if len(code) > 50:
                    errors.append(messages.MESSAGE_CSV_ERROR_CODE_TOO_LONG.format(row=row_num, code=code[:20]))
                    continue
                
                # Check for duplicates within CSV
                if code in seen_codes:
                    errors.append(f"Строка {row_num}: дублирующийся код '{code}' в файле")
                    continue
                seen_codes.add(code)
                
                if not description:
                    errors.append(messages.MESSAGE_CSV_ERROR_EMPTY_DESC.format(row=row_num, code=code))
                    continue
                
                if len(description) > 1000:
                    errors.append(f"Строка {row_num}: описание слишком длинное (макс. 1000 символов)")
                    continue
                
                # Parse minutes
                try:
                    # Handle various number formats
                    minutes_str = minutes_str.replace(',', '.').strip()
                    minutes = int(float(minutes_str))
                    if minutes < 0:
                        raise ValueError("Negative minutes")
                    if minutes > 100000:  # Sanity check: ~70 days max
                        raise ValueError("Minutes too large")
                except (ValueError, TypeError):
                    errors.append(messages.MESSAGE_CSV_ERROR_INVALID_MINUTES.format(row=row_num, code=code))
                    continue
                
                # Validate category name if provided
                if category_name and len(category_name) > 100:
                    category_name = category_name[:100]
                
                # Validate date format if provided (dd.mm.yyyy)
                if date_updated:
                    if not _validate_date_format(date_updated):
                        errors.append(f"Строка {row_num}: некорректный формат даты '{date_updated}' (ожидается дд.мм.гггг)")
                        date_updated = None
                
                valid_records.append({
                    'code': code,
                    'description': description,
                    'minutes': minutes,
                    'category_name': category_name if category_name else None,
                    'date_updated': date_updated
                })
                
            except Exception as e:
                errors.append(messages.MESSAGE_CSV_ERROR_ROW_PROCESSING.format(row=row_num, error=str(e)))
                if len(errors) > 100:  # Limit error count
                    errors.append("Слишком много ошибок, обработка прервана")
                    break
                
    except csv.Error as e:
        errors.append(messages.MESSAGE_CSV_ERROR_PARSE.format(error=str(e)))
    except Exception as e:
        errors.append(messages.MESSAGE_CSV_ERROR_UNEXPECTED.format(error=str(e)))
    
    return valid_records, errors


def import_ktr_codes_from_csv(records: List[dict], skip_existing: bool = True) -> CSVImportResult:
    """
    Import KTR codes from parsed CSV records.
    
    Args:
        records: List of validated record dicts
        skip_existing: If True, skip existing codes; if False, update them
        
    Returns:
        CSVImportResult with import statistics
    """
    result = CSVImportResult()
    
    if not records:
        return result
    
    # Pre-fetch existing codes in batch to avoid N+1 queries
    all_codes = [r['code'] for r in records]
    existing_codes_set = batch_check_existing_codes(all_codes)
    
    # Pre-fetch categories
    category_cache = {}
    
    for record in records:
        try:
            code = record['code']
            description = record['description']
            minutes = record['minutes']
            category_name = record.get('category_name')
            date_updated = record.get('date_updated')
            
            # Check if code exists (using pre-fetched set)
            code_exists = code in existing_codes_set
            
            if code_exists:
                if skip_existing:
                    result.skipped_count += 1
                    continue
                else:
                    # Update existing - need to fetch full record
                    existing = get_ktr_code_by_code_any_status(code)
                    if existing:
                        update_ktr_code(existing['id'], 'description', description)
                        update_ktr_code(existing['id'], 'minutes', minutes, update_timestamp=True)
                        if date_updated:
                            update_ktr_code(existing['id'], 'date_updated', date_updated)
                        # Also reactivate if it was inactive
                        if not existing['active']:
                            update_ktr_code(existing['id'], 'active', 1)
                        if category_name:
                            cat_id = _get_or_create_category(category_name, category_cache)
                            if cat_id:
                                update_ktr_code(existing['id'], 'category_id', cat_id)
                        result.success_count += 1
                    else:
                        result.error_count += 1
                        result.errors.append(f"Не удалось найти код '{code}' для обновления")
                    continue
            
            # Get category ID if provided
            category_id = None
            if category_name:
                category_id = _get_or_create_category(category_name, category_cache)
            
            # Create new code
            create_ktr_code(code, description, minutes, category_id, date_updated)
            result.success_count += 1
            
        except Exception as e:
            result.error_count += 1
            error_msg = str(e)
            if len(error_msg) > 100:
                error_msg = error_msg[:100] + '...'
            result.errors.append(messages.MESSAGE_CSV_ERROR_IMPORT.format(code=record.get('code', '?'), error=error_msg))
            
            # Stop if too many errors
            if result.error_count > 50:
                result.errors.append("Слишком много ошибок импорта, обработка прервана")
                break
    
    return result


def _get_or_create_category(category_name: str, cache: dict) -> Optional[int]:
    """
    Get category ID from cache or database, create if doesn't exist.
    """
    if not category_name:
        return None
    
    # Check cache first
    if category_name in cache:
        return cache[category_name]
    
    # Check database
    cat = get_category_by_name(category_name)
    if cat:
        cache[category_name] = cat['id']
        return cat['id']
    
    # Create new category
    try:
        cat_id = create_category(category_name, None, 0)
        cache[category_name] = cat_id
        return cat_id
    except Exception:
        return None


# Unknown codes and statistics

def record_ktr_request(user_id: int, code: str, found: bool) -> None:
    """
    Record a KTR code request in the log.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                INSERT INTO ktr_request_log 
                (user_id, code, found, request_timestamp)
                VALUES (%s, %s, %s, UNIX_TIMESTAMP())
            """, (user_id, code, 1 if found else 0))


def record_unknown_code(code: str) -> None:
    """
    Record or increment an unknown code request.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Try to update existing
            cursor.execute("""
                UPDATE ktr_unknown_codes 
                SET times_requested = times_requested + 1,
                    last_requested_timestamp = UNIX_TIMESTAMP()
                WHERE code = %s
            """, (code,))
            
            if cursor.rowcount == 0:
                # Insert new
                cursor.execute("""
                    INSERT INTO ktr_unknown_codes 
                    (code, times_requested, first_requested_timestamp, last_requested_timestamp)
                    VALUES (%s, 1, UNIX_TIMESTAMP(), UNIX_TIMESTAMP())
                """, (code,))


def get_unknown_codes(page: int = 1, per_page: int = None) -> Tuple[List[dict], int]:
    """
    Get paginated list of unknown codes.
    """
    if per_page is None:
        per_page = settings.UNKNOWN_CODES_PER_PAGE
    
    offset = (page - 1) * per_page
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT COUNT(*) as cnt FROM ktr_unknown_codes")
            total = cursor.fetchone()['cnt']
            
            cursor.execute("""
                SELECT * FROM ktr_unknown_codes
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
            cursor.execute("SELECT * FROM ktr_unknown_codes WHERE id = %s", (unknown_id,))
            return cursor.fetchone()


def delete_unknown_code(unknown_id: int) -> bool:
    """
    Delete an unknown code entry (after adding it to known codes).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("DELETE FROM ktr_unknown_codes WHERE id = %s", (unknown_id,))
            return cursor.rowcount > 0


def get_popular_ktr_codes(limit: int = None) -> List[dict]:
    """
    Get most requested KTR codes.
    """
    if limit is None:
        limit = settings.TOP_POPULAR_COUNT
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT k.code, k.description, k.minutes, COUNT(r.id) as request_count
                FROM ktr_codes k
                INNER JOIN ktr_request_log r ON r.code = k.code AND r.found = 1
                WHERE k.active = 1
                GROUP BY k.id
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
            cursor.execute("SELECT COUNT(*) as cnt FROM ktr_codes WHERE active = 1")
            stats['total_codes'] = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM ktr_categories WHERE active = 1")
            stats['total_categories'] = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM ktr_unknown_codes")
            stats['unknown_codes'] = cursor.fetchone()['cnt']
            
            # Last 7 days
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(found) as found,
                    SUM(1 - found) as not_found
                FROM ktr_request_log
                WHERE request_timestamp >= UNIX_TIMESTAMP() - 604800
            """)
            result = cursor.fetchone()
            stats['requests_7d'] = result['total'] or 0
            stats['found_7d'] = result['found'] or 0
            stats['not_found_7d'] = result['not_found'] or 0
            
            # Top codes
            cursor.execute("""
                SELECT code, COUNT(*) as cnt
                FROM ktr_request_log
                WHERE request_timestamp >= UNIX_TIMESTAMP() - 604800
                GROUP BY code
                ORDER BY cnt DESC
                LIMIT 5
            """)
            stats['top_codes'] = cursor.fetchall()
            
            return stats


# ===== USER HANDLERS =====

async def enter_ktr_module(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for KTR module.
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
    return SUBMENU  # Enter submenu state to accept direct codes


async def start_code_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start KTR code search flow.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    await update.message.reply_text(
        messages.MESSAGE_ENTER_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return WAITING_FOR_CODE


async def process_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process user's KTR code input and return result.
    """
    # Import gamification events (lazy import to avoid circular deps)
    from src.sbs_helper_telegram_bot.gamification.events import emit_event
    
    user_id = update.effective_user.id
    input_text = update.message.text.strip().upper()  # KTR codes are typically uppercase
    
    # Validate input
    if not input_text or len(input_text) > 50:
        await update.message.reply_text(
            messages.MESSAGE_INVALID_CODE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return WAITING_FOR_CODE
    
    # Emit gamification event for lookup attempt
    emit_event("ktr.lookup", user_id, {"code": input_text})
    
    # Look up the KTR code
    code_info = get_ktr_code_by_code(input_text)
    
    if code_info:
        # Found - log and display
        record_ktr_request(user_id, input_text, found=True)
        
        # Emit gamification event for successful lookup
        emit_event("ktr.lookup_found", user_id, {"code": input_text})
        
        response = messages.format_ktr_code_response(
            code=code_info['code'],
            description=code_info['description'],
            minutes=code_info['minutes'],
            category_name=code_info.get('category_name'),
            updated_timestamp=code_info.get('updated_timestamp'),
            date_updated=code_info.get('date_updated')
        )
        
        await update.message.reply_text(
            response,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        # Not found - log and add to unknown
        record_ktr_request(user_id, input_text, found=False)
        record_unknown_code(input_text)
        
        escaped_code = messages.escape_markdown_v2(input_text)
        await update.message.reply_text(
            messages.MESSAGE_CODE_NOT_FOUND.format(code=escaped_code),
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
    
    return SUBMENU  # Stay in submenu to allow more lookups


async def direct_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle direct KTR code input from submenu (without pressing search button).
    This allows users to enter codes directly.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    # Reuse the same processing logic as process_code_input
    return await process_code_input(update, context)


async def show_popular_codes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show most requested KTR codes.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    popular = get_popular_ktr_codes()
    
    if not popular:
        await update.message.reply_text(
            messages.MESSAGE_NO_POPULAR_CODES,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return SUBMENU
    
    text = messages.MESSAGE_POPULAR_CODES_HEADER.format(count=len(popular))
    
    for i, code in enumerate(popular, 1):
        line = messages.format_code_list_item(
            code=code['code'],
            description=code['description'],
            minutes=code['minutes'],
            times_requested=code['request_count']
        )
        text += f"{i}\\. {line}\n"
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return SUBMENU


async def show_ktr_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show KTR module achievements for the current user.
    """
    from src.sbs_helper_telegram_bot.gamification import gamification_logic
    from src.sbs_helper_telegram_bot.gamification import messages as gf_messages
    from src.sbs_helper_telegram_bot.gamification import keyboards as gf_keyboards
    
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    
    # Get KTR achievements with progress
    achievements = gamification_logic.get_user_achievements_with_progress(user_id, 'ktr')
    
    if not achievements:
        await update.message.reply_text(
            "🎖️ *Достижения модуля КТР*\n\nДостижения пока не настроены\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return SUBMENU
    
    # Count unlocked
    unlocked = sum(1 for a in achievements if a['unlocked_level'] > 0)
    total = len(achievements) * 3  # 3 levels per achievement
    
    text = gf_messages.MESSAGE_MODULE_ACHIEVEMENTS_HEADER.format(
        module=gf_messages._escape_md("КТР"),
        unlocked=unlocked,
        total=total
    )
    
    for ach in achievements:
        card = gf_messages.format_achievement_card(
            name=ach['name'],
            description=ach['description'],
            icon=ach['icon'],
            current_count=ach['current_count'],
            threshold_bronze=ach['threshold_bronze'],
            threshold_silver=ach['threshold_silver'],
            threshold_gold=ach['threshold_gold'],
            unlocked_level=ach['unlocked_level']
        )
        text += card + "\n"
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return SUBMENU


async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the code search flow.
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
    context.user_data.pop('ktr_temp', None)
    return ConversationHandler.END


# ===== ADMIN HANDLERS =====

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show admin menu for KTR.
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
    
    if text == "📋 Список кодов":
        return await admin_show_codes_list(update, context)
    elif text == "➕ Добавить код":
        return await admin_start_add_code(update, context)
    elif text == "🔍 Найти код":
        return await admin_start_search_code(update, context)
    elif text == "📁 Категории":
        return await admin_show_categories(update, context)
    elif text == "❓ Неизвестные коды":
        return await admin_show_unknown_codes(update, context)
    elif text == "📈 Статистика":
        return await admin_show_statistics(update, context)
    elif text == "📥 Импорт CSV":
        return await admin_start_csv_import(update, context)
    elif text == "🔙 Назад в КТР":
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


async def admin_show_codes_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> int:
    """
    Show paginated list of KTR codes.
    """
    codes, total = get_all_ktr_codes(page=page, include_inactive=True)
    
    if not codes:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CODES_LIST_EMPTY,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    
    total_pages = math.ceil(total / settings.CODES_PER_PAGE)
    
    text = messages.MESSAGE_ADMIN_CODES_LIST_HEADER.format(page=page, total_pages=total_pages)
    
    for code in codes:
        status = "✅" if code['active'] else "🚫"
        line = messages.format_code_list_item(
            code=code['code'],
            description=code['description'],
            minutes=code['minutes'],
            category_name=code.get('category_name')
        )
        text += f"{status} {line}\n"
    
    keyboard = keyboards.get_codes_inline_keyboard(codes, page, total_pages)
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return ADMIN_MENU


async def admin_start_search_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the flow to search for a KTR code by code.
    Admin can type the code directly instead of scrolling through the list.
    """
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_SEARCH_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_SEARCH_CODE


async def admin_receive_search_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive code for search and show it for editing.
    """
    code = update.message.text.strip().upper()
    
    # Look up the code in the database (include inactive)
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT k.*, c.name as category_name
                FROM ktr_codes k
                LEFT JOIN ktr_categories c ON k.category_id = c.id
                WHERE k.code = %s
            """, (code,))
            ktr = cursor.fetchone()
    
    if not ktr:
        escaped = messages.escape_markdown_v2(code)
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CODE_NOT_FOUND_FOR_EDIT.format(code=escaped),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    
    # Store code info for potential edit
    context.user_data['ktr_temp'] = {'code_id': ktr['id']}
    
    # Format code details
    text = messages.format_ktr_code_response(
        code=ktr['code'],
        description=ktr['description'],
        minutes=ktr['minutes'],
        category_name=ktr.get('category_name'),
        updated_timestamp=ktr.get('updated_timestamp'),
        date_updated=ktr.get('date_updated')
    )
    
    # Add status indicator
    status = "✅ Активен" if ktr['active'] else "🚫 Деактивирован"
    status_escaped = messages.escape_markdown_v2(status)
    text += f"\n\n📌 *Статус:* {status_escaped}"
    
    keyboard = keyboards.get_code_detail_keyboard(ktr['id'], ktr['active'])
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return ADMIN_MENU


async def admin_start_add_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the flow to add a new KTR code.
    """
    context.user_data['ktr_temp'] = {}
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_CODE


async def admin_receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive code for new KTR entry.
    """
    code = update.message.text.strip().upper()
    
    if ktr_code_exists(code):
        escaped = messages.escape_markdown_v2(code)
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_CODE_EXISTS.format(code=escaped),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_ADD_CODE
    
    context.user_data['ktr_temp']['code'] = code
    
    escaped = messages.escape_markdown_v2(code)
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_DESCRIPTION.format(code=escaped),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_DESCRIPTION


async def admin_receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive description for new KTR code.
    """
    description = update.message.text.strip()
    context.user_data['ktr_temp']['description'] = description
    
    code = context.user_data['ktr_temp']['code']
    escaped = messages.escape_markdown_v2(code)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_MINUTES.format(code=escaped),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_MINUTES


async def admin_receive_minutes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive minutes for new KTR code, then show category selection.
    """
    try:
        minutes = int(update.message.text.strip())
        if minutes < 0:
            raise ValueError("Negative minutes")
    except (ValueError, TypeError):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_INVALID_MINUTES,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_ADD_MINUTES
    
    context.user_data['ktr_temp']['minutes'] = minutes
    
    code = context.user_data['ktr_temp']['code']
    escaped = messages.escape_markdown_v2(code)
    
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
        # No categories - create code without category
        return await _create_ktr_code(update, context, category_id=None)


async def admin_select_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handle category selection callback.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "ktr_cat_skip":
        # Skip category selection
        return await _create_ktr_code(query, context, category_id=None)
    elif data.startswith("ktr_cat_select_"):
        category_id = int(data.replace("ktr_cat_select_", ""))
        return await _create_ktr_code(query, context, category_id=category_id)
    
    return ADMIN_SELECT_CATEGORY


async def _create_ktr_code(update_or_query, context: ContextTypes.DEFAULT_TYPE, category_id: Optional[int]) -> int:
    """
    Helper to create the KTR code after all inputs collected.
    """
    temp = context.user_data.get('ktr_temp', {})
    code = temp.get('code')
    description = temp.get('description')
    minutes = temp.get('minutes')
    
    if not all([code, description, minutes is not None]):
        return ADMIN_MENU
    
    # Create the KTR code
    create_ktr_code(code, description, minutes, category_id)
    
    # Get category name for response
    category_name = messages.MESSAGE_NO_CATEGORY
    if category_id:
        cat = get_category_by_id(category_id)
        if cat:
            category_name = cat['name']
    
    escaped_code = messages.escape_markdown_v2(code)
    escaped_cat = messages.escape_markdown_v2(category_name)
    escaped_desc = messages.escape_markdown_v2(description[:100] + "..." if len(description) > 100 else description)
    
    response = messages.MESSAGE_ADMIN_CODE_CREATED.format(
        code=escaped_code,
        category=escaped_cat,
        description=escaped_desc,
        minutes=minutes
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
    context.user_data.pop('ktr_temp', None)
    
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
            code_count=cat['code_count'],
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
            code=code['code'],
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
            escaped_code = messages.escape_markdown_v2(code_info['code'])
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
    
    # View code details
    if data.startswith("ktr_view_"):
        code_id = int(data.replace("ktr_view_", ""))
        return await _show_code_details(query, context, code_id)
    
    # Edit code description
    elif data.startswith("ktr_edit_desc_"):
        code_id = int(data.replace("ktr_edit_desc_", ""))
        context.user_data['ktr_temp'] = {'code_id': code_id, 'edit_field': 'description'}
        ktr = get_ktr_code_by_id(code_id)
        if ktr:
            escaped = messages.escape_markdown_v2(ktr['description'])
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_EDIT_DESCRIPTION.format(current=escaped),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ADMIN_EDIT_DESCRIPTION
    
    # Edit minutes
    elif data.startswith("ktr_edit_minutes_"):
        code_id = int(data.replace("ktr_edit_minutes_", ""))
        context.user_data['ktr_temp'] = {'code_id': code_id, 'edit_field': 'minutes'}
        ktr = get_ktr_code_by_id(code_id)
        if ktr:
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_EDIT_MINUTES.format(current=ktr['minutes']),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ADMIN_EDIT_MINUTES
    
    # Edit category
    elif data.startswith("ktr_edit_cat_"):
        code_id = int(data.replace("ktr_edit_cat_", ""))
        context.user_data['ktr_temp'] = {'code_id': code_id, 'edit_field': 'category_id'}
        categories, _ = get_all_categories(page=1, per_page=20)
        keyboard = keyboards.get_categories_inline_keyboard(categories, for_selection=True)
        await query.edit_message_text(
            "📁 Выберите новую категорию:",
            reply_markup=keyboard
        )
        return ADMIN_SELECT_CATEGORY
    
    # Activate/deactivate
    elif data.startswith("ktr_activate_"):
        code_id = int(data.replace("ktr_activate_", ""))
        update_ktr_code(code_id, 'active', 1)
        return await _show_code_details(query, context, code_id)
    
    elif data.startswith("ktr_deactivate_"):
        code_id = int(data.replace("ktr_deactivate_", ""))
        update_ktr_code(code_id, 'active', 0)
        return await _show_code_details(query, context, code_id)
    
    # Delete code
    elif data.startswith("ktr_delete_"):
        code_id = int(data.replace("ktr_delete_", ""))
        keyboard = keyboards.get_confirm_delete_keyboard('code', code_id)
        await query.edit_message_text(
            "⚠️ *Удалить код КТР?*\n\nЭто действие нельзя отменить\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        return ADMIN_MENU
    
    # Confirm delete
    elif data.startswith("ktr_confirm_delete_code_"):
        code_id = int(data.replace("ktr_confirm_delete_code_", ""))
        ktr = get_ktr_code_by_id(code_id)
        if ktr:
            delete_ktr_code(code_id)
            escaped = messages.escape_markdown_v2(ktr['code'])
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_CODE_DELETED.format(code=escaped),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        return ADMIN_MENU
    
    # Back to codes list
    elif data == "ktr_codes_list":
        # Can't show full list in callback, just acknowledge
        await query.edit_message_text(messages.MESSAGE_USE_LIST_BUTTON)
        return ADMIN_MENU
    
    # Back to admin menu
    elif data == "ktr_admin_menu":
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    # Category callbacks
    elif data.startswith("ktr_cat_view_"):
        category_id = int(data.replace("ktr_cat_view_", ""))
        return await _show_category_details(query, context, category_id)
    
    elif data.startswith("ktr_cat_delete_"):
        category_id = int(data.replace("ktr_cat_delete_", ""))
        keyboard = keyboards.get_confirm_delete_keyboard('category', category_id)
        await query.edit_message_text(
            "⚠️ *Удалить категорию?*\n\nКоды в этой категории останутся без категории\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        return ADMIN_MENU
    
    elif data.startswith("ktr_confirm_delete_category_"):
        category_id = int(data.replace("ktr_confirm_delete_category_", ""))
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
    elif data.startswith("ktr_add_unknown_"):
        unknown_id = int(data.replace("ktr_add_unknown_", ""))
        unknown = get_unknown_code_by_id(unknown_id)
        if unknown:
            context.user_data['ktr_temp'] = {
                'code': unknown['code'],
                'unknown_id': unknown_id
            }
            escaped = messages.escape_markdown_v2(unknown['code'])
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_ENTER_DESCRIPTION.format(code=escaped),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ADMIN_ADD_DESCRIPTION
        return ADMIN_MENU
    
    # Pagination
    elif data.startswith("ktr_page_"):
        page = int(data.replace("ktr_page_", ""))
        # Re-fetch and display
        codes, total = get_all_ktr_codes(page=page, include_inactive=True)
        total_pages = math.ceil(total / settings.CODES_PER_PAGE)
        
        text = messages.MESSAGE_ADMIN_CODES_LIST_HEADER.format(page=page, total_pages=total_pages)
        for code in codes:
            status = "✅" if code['active'] else "🚫"
            line = messages.format_code_list_item(
                code=code['code'],
                description=code['description'],
                minutes=code['minutes'],
                category_name=code.get('category_name')
            )
            text += f"{status} {line}\n"
        
        keyboard = keyboards.get_codes_inline_keyboard(codes, page, total_pages)
        await query.edit_message_text(text, parse_mode=constants.ParseMode.MARKDOWN_V2, reply_markup=keyboard)
        return ADMIN_MENU
    
    return ADMIN_MENU


async def _show_code_details(query, context: ContextTypes.DEFAULT_TYPE, code_id: int) -> int:
    """
    Show KTR code details with edit options.
    """
    ktr = get_ktr_code_by_id(code_id)
    if not ktr:
        await query.edit_message_text("❌ Код не найден")
        return ADMIN_MENU
    
    response = messages.format_ktr_code_response(
        code=ktr['code'],
        description=ktr['description'],
        minutes=ktr['minutes'],
        category_name=ktr.get('category_name'),
        updated_timestamp=ktr.get('updated_timestamp'),
        date_updated=ktr.get('date_updated')
    )
    
    if not ktr['active']:
        response += "\n\n🚫 _Код деактивирован_"
    
    keyboard = keyboards.get_code_detail_keyboard(code_id, ktr['active'])
    
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
    text += f"🔢 *Кодов в категории:* {cat['code_count']}\n"
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
    temp = context.user_data.get('ktr_temp', {})
    code_id = temp.get('code_id')
    
    if not code_id:
        return ADMIN_MENU
    
    new_description = update.message.text.strip()
    update_ktr_code(code_id, 'description', new_description, update_timestamp=True)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CODE_UPDATED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    context.user_data.pop('ktr_temp', None)
    return ADMIN_MENU


async def admin_receive_edit_minutes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receive edited minutes value.
    """
    temp = context.user_data.get('ktr_temp', {})
    code_id = temp.get('code_id')
    
    if not code_id:
        return ADMIN_MENU
    
    try:
        new_minutes = int(update.message.text.strip())
        if new_minutes < 0:
            raise ValueError("Negative minutes")
    except (ValueError, TypeError):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_INVALID_MINUTES,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_EDIT_MINUTES
    
    update_ktr_code(code_id, 'minutes', new_minutes, update_timestamp=True)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CODE_UPDATED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    context.user_data.pop('ktr_temp', None)
    return ADMIN_MENU


async def admin_start_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start flow to add a new category.
    """
    context.user_data['ktr_temp'] = {}
    
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
    
    context.user_data['ktr_temp']['name'] = name
    
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
    
    context.user_data['ktr_temp']['description'] = description
    
    name = context.user_data['ktr_temp']['name']
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
    
    temp = context.user_data.get('ktr_temp', {})
    name = temp.get('name')
    description = temp.get('description')
    
    create_category(name, description, display_order)
    
    escaped = messages.escape_markdown_v2(name)
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CATEGORY_CREATED.format(name=escaped),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    context.user_data.pop('ktr_temp', None)
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
        detected_encoding = None
        
        # Check for BOM (Byte Order Mark) first
        if raw_bytes.startswith(b'\xef\xbb\xbf'):
            # UTF-8 with BOM
            csv_content = raw_bytes[3:].decode('utf-8')
            detected_encoding = 'UTF-8 with BOM'
        elif raw_bytes.startswith(b'\xff\xfe'):
            # UTF-16 LE
            csv_content = raw_bytes.decode('utf-16-le')
            detected_encoding = 'UTF-16 LE'
        elif raw_bytes.startswith(b'\xfe\xff'):
            # UTF-16 BE
            csv_content = raw_bytes.decode('utf-16-be')
            detected_encoding = 'UTF-16 BE'
        else:
            # Try different encodings in order of likelihood for Mac
            # macroman (alias for mac_roman) is common for Mac Excel exports
            encodings_to_try = [
                'utf-8',
                'macroman',      # Mac OS Roman (primary Mac encoding)
                'mac-cyrillic',  # Mac Cyrillic for Russian
                'cp1251',        # Windows Cyrillic
                'windows-1251',  # Alternative name for cp1251
                'koi8-r',        # KOI8-R Cyrillic
                'iso-8859-5',    # ISO Cyrillic
                'utf-16',        # UTF-16 without BOM
                'latin1',        # ISO-8859-1
            ]
            
            for encoding in encodings_to_try:
                try:
                    test_content = raw_bytes.decode(encoding)
                    
                    # Check if decoding produced replacement characters
                    # which would indicate wrong encoding
                    if '\ufffd' in test_content:
                        continue
                    
                    # For non-UTF-8, do additional validation
                    if encoding != 'utf-8':
                        # Check if the content looks reasonable (has some ASCII chars)
                        sample = test_content[:1000]
                        ascii_chars = sum(1 for c in sample if ord(c) < 128)
                        if len(sample) > 0 and ascii_chars / len(sample) < 0.3:
                            # Too few ASCII chars, probably wrong encoding
                            continue
                    
                    csv_content = test_content
                    detected_encoding = encoding
                    break
                    
                except (UnicodeDecodeError, LookupError):
                    continue
        
        if csv_content is None:
            await update.message.reply_text(
                messages.MESSAGE_ADMIN_CSV_ENCODING_ERROR,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ADMIN_IMPORT_CSV_WAITING
        
        # Normalize line endings
        csv_content = csv_content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Log detected encoding for debugging
        if detected_encoding:
            logger.info(f"CSV file decoded successfully using {detected_encoding} encoding")
        
        # Parse CSV
        records, parse_errors = parse_csv_ktr_codes(csv_content)
        
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
        context.user_data['ktr_temp'] = {
            'csv_records': records,
            'csv_parse_errors': parse_errors
        }
        
        # Count existing codes using batch operation
        all_codes = [r['code'] for r in records]
        existing_codes_set = batch_check_existing_codes(all_codes)
        existing_count = len(existing_codes_set)
        new_count = len(records) - existing_count
        
        # Prepare encoding info for display
        encoding_info = ""
        if detected_encoding and detected_encoding != 'utf-8':
            escaped_enc = messages.escape_markdown_v2(detected_encoding)
            encoding_info = f"\n_\\(кодировка: {escaped_enc}\\)_"
        
        # Show preview and ask for confirmation
        preview_text = messages.MESSAGE_ADMIN_CSV_PREVIEW.format(
            total=len(records),
            new=new_count,
            existing=existing_count,
            parse_errors=len(parse_errors),
            encoding_info=encoding_info
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
    
    if data == "ktr_csv_cancel":
        context.user_data.pop('ktr_temp', None)
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
    
    elif data == "ktr_csv_import_skip":
        # Import, skip existing
        return await _perform_csv_import(query, context, skip_existing=True)
    
    elif data == "ktr_csv_import_update":
        # Import, update existing
        return await _perform_csv_import(query, context, skip_existing=False)
    
    return ADMIN_IMPORT_CSV_CONFIRM


async def _perform_csv_import(query, context: ContextTypes.DEFAULT_TYPE, skip_existing: bool) -> int:
    """
    Perform the actual CSV import.
    """
    temp = context.user_data.get('ktr_temp', {})
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
    result = import_ktr_codes_from_csv(records, skip_existing=skip_existing)
    
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
    
    context.user_data.pop('ktr_temp', None)
    return ADMIN_MENU


async def admin_cancel_csv_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel CSV import via button.
    """
    context.user_data.pop('ktr_temp', None)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CSV_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_MENU


# ===== CONVERSATION HANDLER BUILDER =====

def get_menu_button_regex_pattern() -> str:
    """
    Get regex pattern matching KTR module-specific buttons for fallback.
    Also includes buttons from other modules to properly end conversation when switching modules.
    """
    buttons = []
    # Include KTR-specific buttons
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
    
    # Add main navigation and other module buttons to properly end conversation when switching
    # These buttons indicate user wants to leave KTR module
    other_module_buttons = [
        "🏠 Главное меню",
        "📦 Модули",
        "⚙️ Настройки",
        "📋 Проверить заявку",  # Ticket validator
        "✅ Валидация заявок",  # Ticket validator module entry
        "📸 Обработать скриншот",  # Screenshot module
        "🔢 UPOS Ошибки",  # UPOS module
        "📝 Аттестация",  # Certification module
        "📬 Обратная связь",  # Feedback module
        "🏆 Профиль",  # Gamification/Profile module
        "🎫 Мои инвайты",
        "❓ Помощь",
        "🛠️ Админ бота",
    ]
    buttons.extend(other_module_buttons)
    
    # Remove duplicates and escape for regex
    unique_buttons = list(set(buttons))
    escaped = [b.replace("(", "\\(").replace(")", "\\)").replace("+", "\\+") for b in unique_buttons]
    
    return "^(" + "|".join(escaped) + ")$"


def get_user_conversation_handler() -> ConversationHandler:
    """
    Get ConversationHandler for user KTR code lookup flow.
    Users must press the search button to enter KTR codes.
    """
    menu_pattern = get_menu_button_regex_pattern()
    
    return ConversationHandler(
        entry_points=[
            # Entry when user clicks on KTR module button
            MessageHandler(filters.Regex("^⏱️ КТР$"), enter_ktr_module),
        ],
        states={
            SUBMENU: [
                # In submenu, accept button to start search
                MessageHandler(filters.Regex("^🔍 Найти код КТР$"), start_code_search),
                # Popular codes button
                MessageHandler(filters.Regex("^📊 Популярные коды$"), show_popular_codes),
                # Achievements button
                MessageHandler(filters.Regex("^🎖️ Достижения$"), show_ktr_achievements),
            ],
            WAITING_FOR_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_code_input)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_search),
            MessageHandler(filters.COMMAND, cancel_search_on_menu),
            MessageHandler(filters.Regex(menu_pattern), cancel_search_on_menu)
        ],
        name="ktr_user_conversation",
        persistent=False
    )


def get_admin_conversation_handler() -> ConversationHandler:
    """
    Get ConversationHandler for admin CRUD operations.
    """
    menu_pattern = get_menu_button_regex_pattern()
    
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🔐 Админ КТР$"), admin_menu),
        ],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(admin_callback_handler, pattern="^ktr_"),
                MessageHandler(filters.Regex("^📋 Список кодов$"), admin_show_codes_list),
                MessageHandler(filters.Regex("^➕ Добавить код$"), admin_start_add_code),
                MessageHandler(filters.Regex("^🔍 Найти код$"), admin_start_search_code),
                MessageHandler(filters.Regex("^📁 Категории$"), admin_show_categories),
                MessageHandler(filters.Regex("^❓ Неизвестные коды$"), admin_show_unknown_codes),
                MessageHandler(filters.Regex("^📈 Статистика$"), admin_show_statistics),
                MessageHandler(filters.Regex("^📋 Все категории$"), admin_show_categories),
                MessageHandler(filters.Regex("^➕ Добавить категорию$"), admin_start_add_category),
                MessageHandler(filters.Regex("^📥 Импорт CSV$"), admin_start_csv_import),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
            ],
            ADMIN_ADD_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_code)
            ],
            ADMIN_ADD_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_description)
            ],
            ADMIN_ADD_MINUTES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_minutes)
            ],
            ADMIN_SELECT_CATEGORY: [
                CallbackQueryHandler(admin_select_category_callback, pattern="^ktr_cat_")
            ],
            ADMIN_EDIT_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_edit_description)
            ],
            ADMIN_EDIT_MINUTES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_edit_minutes)
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
                MessageHandler(filters.Regex("^🔙 Админ КТР$"), admin_menu),
            ],
            ADMIN_IMPORT_CSV_CONFIRM: [
                CallbackQueryHandler(admin_csv_import_callback, pattern="^ktr_csv_"),
            ],
            ADMIN_SEARCH_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_search_code)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_search),
            MessageHandler(filters.Regex("^🏠 Главное меню$"), cancel_search_on_menu),
            MessageHandler(filters.Regex("^🔙 Назад в КТР$"), enter_ktr_module),
            MessageHandler(filters.COMMAND, cancel_search_on_menu),  # Handle /start and other commands
        ]
    )
