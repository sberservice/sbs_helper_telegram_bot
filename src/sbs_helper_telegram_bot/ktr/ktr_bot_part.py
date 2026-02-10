"""
Часть бота для КТР (Коэффициент трудозатрат)

Основные обработчики бота для модуля поиска кодов КТР.
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
    BUTTON_UPOS_ERRORS,
    BUTTON_CERTIFICATION,
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
WAITING_FOR_CODE = 1

# Состояния диалога для админских операций
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


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

def _validate_date_format(date_str: str) -> bool:
    """
    Проверить, что строка даты в формате dd.mm.yyyy.
    
    Args:
        date_str: Строка даты для проверки
        
    Returns:
        True, если формат валиден, иначе False
    """
    if not date_str:
        return False
    
    parts = date_str.split('.')
    if len(parts) != 3:
        return False
    
    try:
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        # Базовая проверка
        if not (1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100):
            return False
        return True
    except (ValueError, IndexError):
        return False


# ===== ОПЕРАЦИИ С БАЗОЙ ДАННЫХ =====

def get_ktr_code_by_code(code: str) -> Optional[dict]:
    """
    Найти код КТР в базе данных.
    
    Args:
        code: Код КТР для поиска
        
    Returns:
        Словарь с данными кода или None, если не найден
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
    Получить код КТР по ID (для админа).
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
    Получить постраничный список кодов КТР.
    
    Returns:
        Кортеж (список_кодов, общее_количество)
    """
    if per_page is None:
        per_page = settings.CODES_PER_PAGE
    
    offset = (page - 1) * per_page
    active_filter = "" if include_inactive else "WHERE k.active = 1"
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Получаем общее количество
            cursor.execute(f"SELECT COUNT(*) as cnt FROM ktr_codes k {active_filter}")
            total = cursor.fetchone()['cnt']
            
            # Получаем страницу
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
    Создать новый код КТР.
    
    Args:
        code: Код КТР
        description: Описание работ
        minutes: Трудозатраты в минутах
        category_id: Необязательный ID категории
        date_updated: Необязательная дата обновления в формате dd.mm.yyyy
    
    Returns:
        ID нового кода
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
    Обновить поле кода КТР.
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
    Удалить код КТР (жёсткое удаление).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("DELETE FROM ktr_codes WHERE id = %s", (code_id,))
            return cursor.rowcount > 0


def ktr_code_exists(code: str) -> bool:
    """
    Проверить, существует ли код КТР (включая неактивные).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM ktr_codes WHERE code = %s", (code,))
            return cursor.fetchone() is not None


def get_ktr_code_by_code_any_status(code: str) -> Optional[dict]:
    """
    Найти код КТР в базе данных (включая неактивные коды).
    Используется для операций импорта.
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
    Проверить, какие коды уже есть в базе (пакетная операция).
    Возвращает множество существующих кодов.
    """
    if not codes:
        return set()
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Используем IN для пакетной проверки
            placeholders = ','.join(['%s'] * len(codes))
            cursor.execute(f"SELECT code FROM ktr_codes WHERE code IN ({placeholders})", tuple(codes))
            return {row['code'] for row in cursor.fetchall()}


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
    Получить категорию по ID.
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
    Создать новую категорию.
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
    Обновить поле категории.
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
    Удалить категорию (у кодов category_id станет NULL).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Ограничение FK с ON DELETE SET NULL корректно обрабатывает коды
            cursor.execute("DELETE FROM ktr_categories WHERE id = %s", (category_id,))
            return cursor.rowcount > 0


def category_exists(name: str) -> bool:
    """
    Проверить, существует ли уже название категории.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM ktr_categories WHERE name = %s", (name,))
            return cursor.fetchone() is not None


def get_category_by_name(name: str) -> Optional[dict]:
    """
    Получить категорию по названию.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT * FROM ktr_categories WHERE name = %s AND active = 1", (name,))
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


def parse_csv_ktr_codes(csv_content: str, delimiter: str = ',') -> Tuple[List[dict], List[str]]:
    """
    Разобрать CSV и проверить данные кодов КТР.
    
    Ожидаемый формат CSV:
    code,description,minutes,category (optional)
    
    Неизвестные столбцы игнорируются.
    
    Args:
        csv_content: Содержимое CSV в виде строки
        delimiter: Разделитель CSV
        
    Returns:
        Кортеж (валидные_записи, список_ошибок)
    """
    valid_records = []
    errors = []
    seen_codes = set()  # Отслеживаем дубликаты внутри CSV
    
    try:
        # Ограничиваем размер содержимого, чтобы избежать проблем с памятью
        max_content_size = 5 * 1024 * 1024  # 5MB
        if len(csv_content) > max_content_size:
            errors.append("CSV файл слишком большой")
            return [], errors
        
        # Пытаемся определить разделитель, если это не запятая
        first_line = csv_content.split('\n')[0] if csv_content else ''
        if delimiter == ',' and ';' in first_line and ',' not in first_line:
            delimiter = ';'
        
        reader = csv.DictReader(io.StringIO(csv_content), delimiter=delimiter)
        
        # Проверяем обязательные поля
        if not reader.fieldnames:
            errors.append("CSV файл пуст или имеет неверный формат")
            return [], errors
        
        fieldnames_lower = [f.lower().strip() if f else '' for f in reader.fieldnames]
        
        # Сопоставляем возможные названия колонок (только ожидаемые)
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
            # Любые другие столбцы игнорируются
        
        if not code_col:
            errors.append(messages.MESSAGE_CSV_ERROR_NO_CODE_COLUMN)
            return [], errors
        if not desc_col:
            errors.append(messages.MESSAGE_CSV_ERROR_NO_DESC_COLUMN)
            return [], errors
        if not minutes_col:
            errors.append(messages.MESSAGE_CSV_ERROR_NO_MINUTES_COLUMN)
            return [], errors
        
        row_num = 1  # Заголовок — строка 1
        max_rows = 10000  # Ограничиваем число строк, чтобы избежать зависаний
        
        for row in reader:
            row_num += 1
            
            # Предохранительный лимит
            if row_num > max_rows + 1:
                errors.append(f"Превышен лимит строк ({max_rows}). Остальные строки пропущены.")
                break
            
            try:
                # Извлекаем только сопоставленные столбцы, остальное игнорируем
                code = (row.get(code_col) or '').strip().upper()  # Нормализуем в верхний регистр
                description = (row.get(desc_col) or '').strip()
                minutes_str = (row.get(minutes_col) or '').strip()
                category_name = (row.get(category_col) or '').strip() if category_col else None
                date_updated = (row.get(date_col) or '').strip() if date_col else None
                
                # Пропускаем пустые строки
                if not code and not description and not minutes_str:
                    continue
                
                # Валидируем обязательные поля
                if not code:
                    errors.append(messages.MESSAGE_CSV_ERROR_EMPTY_CODE.format(row=row_num))
                    continue
                
                # Проверяем формат кода (буквы/цифры)
                if not code.replace('-', '').replace('_', '').replace('.', '').isalnum():
                    errors.append(f"Строка {row_num}: код '{code}' содержит недопустимые символы")
                    continue
                
                if len(code) > 50:
                    errors.append(messages.MESSAGE_CSV_ERROR_CODE_TOO_LONG.format(row=row_num, code=code[:20]))
                    continue
                
                # Проверяем дубликаты внутри CSV
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
                
                # Парсим минуты
                try:
                    # Обрабатываем различные форматы чисел
                    minutes_str = minutes_str.replace(',', '.').strip()
                    minutes = int(float(minutes_str))
                    if minutes < 0:
                        raise ValueError("Negative minutes")
                    if minutes > 100000:  # Проверка здравого смысла: максимум около 70 дней
                        raise ValueError("Minutes too large")
                except (ValueError, TypeError):
                    errors.append(messages.MESSAGE_CSV_ERROR_INVALID_MINUTES.format(row=row_num, code=code))
                    continue
                
                # Валидируем название категории, если оно задано
                if category_name and len(category_name) > 100:
                    category_name = category_name[:100]
                
                # Валидируем формат даты, если он задан (dd.mm.yyyy)
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
                if len(errors) > 100:  # Ограничиваем количество ошибок
                    errors.append("Слишком много ошибок, обработка прервана")
                    break
                
    except csv.Error as e:
        errors.append(messages.MESSAGE_CSV_ERROR_PARSE.format(error=str(e)))
    except Exception as e:
        errors.append(messages.MESSAGE_CSV_ERROR_UNEXPECTED.format(error=str(e)))
    
    return valid_records, errors


def import_ktr_codes_from_csv(records: List[dict], skip_existing: bool = True) -> CSVImportResult:
    """
    Импортировать коды КТР из разобранных CSV-записей.
    
    Args:
        records: Список валидированных словарей записей
        skip_existing: Если True, пропускать существующие коды; если False — обновлять
        
    Returns:
        CSVImportResult со статистикой импорта
    """
    result = CSVImportResult()
    
    if not records:
        return result
    
    # Предзагружаем существующие коды пакетом, чтобы избежать N+1 запросов
    all_codes = [r['code'] for r in records]
    existing_codes_set = batch_check_existing_codes(all_codes)
    
    # Предзагружаем категории
    category_cache = {}
    
    for record in records:
        try:
            code = record['code']
            description = record['description']
            minutes = record['minutes']
            category_name = record.get('category_name')
            date_updated = record.get('date_updated')
            
            # Проверяем наличие кода (используем предзагруженный набор)
            code_exists = code in existing_codes_set
            
            if code_exists:
                if skip_existing:
                    result.skipped_count += 1
                    continue
                else:
                    # Обновляем существующий — нужно загрузить полный объект
                    existing = get_ktr_code_by_code_any_status(code)
                    if existing:
                        update_ktr_code(existing['id'], 'description', description)
                        update_ktr_code(existing['id'], 'minutes', minutes, update_timestamp=True)
                        if date_updated:
                            update_ktr_code(existing['id'], 'date_updated', date_updated)
                        # Также активируем, если был неактивен
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
            
            # Получаем ID категории, если она задана
            category_id = None
            if category_name:
                category_id = _get_or_create_category(category_name, category_cache)
            
            # Создаём новый код
            create_ktr_code(code, description, minutes, category_id, date_updated)
            result.success_count += 1
            
        except Exception as e:
            result.error_count += 1
            error_msg = str(e)
            if len(error_msg) > 100:
                error_msg = error_msg[:100] + '...'
            result.errors.append(messages.MESSAGE_CSV_ERROR_IMPORT.format(code=record.get('code', '?'), error=error_msg))
            
            # Останавливаемся при слишком большом числе ошибок
            if result.error_count > 50:
                result.errors.append("Слишком много ошибок импорта, обработка прервана")
                break
    
    return result


def _get_or_create_category(category_name: str, cache: dict) -> Optional[int]:
    """
    Получить ID категории из кэша или базы, создать при отсутствии.
    """
    if not category_name:
        return None
    
    # Сначала проверяем кэш
    if category_name in cache:
        return cache[category_name]
    
    # Проверяем базу данных
    cat = get_category_by_name(category_name)
    if cat:
        cache[category_name] = cat['id']
        return cat['id']
    
    # Создаём новую категорию
    try:
        cat_id = create_category(category_name, None, 0)
        cache[category_name] = cat_id
        return cat_id
    except Exception:
        return None


# Неизвестные коды и статистика

def record_ktr_request(user_id: int, code: str, found: bool) -> None:
    """
    Записать запрос кода КТР в лог.
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
    Записать или увеличить счётчик запроса неизвестного кода.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Пытаемся обновить существующий
            cursor.execute("""
                UPDATE ktr_unknown_codes 
                SET times_requested = times_requested + 1,
                    last_requested_timestamp = UNIX_TIMESTAMP()
                WHERE code = %s
            """, (code,))
            
            if cursor.rowcount == 0:
                # Вставляем новый
                cursor.execute("""
                    INSERT INTO ktr_unknown_codes 
                    (code, times_requested, first_requested_timestamp, last_requested_timestamp)
                    VALUES (%s, 1, UNIX_TIMESTAMP(), UNIX_TIMESTAMP())
                """, (code,))


def get_unknown_codes(page: int = 1, per_page: int = None) -> Tuple[List[dict], int]:
    """
    Получить постраничный список неизвестных кодов.
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
    Получить неизвестный код по ID.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT * FROM ktr_unknown_codes WHERE id = %s", (unknown_id,))
            return cursor.fetchone()


def delete_unknown_code(unknown_id: int) -> bool:
    """
    Удалить запись неизвестного кода (после добавления в известные коды).
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("DELETE FROM ktr_unknown_codes WHERE id = %s", (unknown_id,))
            return cursor.rowcount > 0


def get_popular_ktr_codes(limit: int = None) -> List[dict]:
    """
    Получить наиболее запрашиваемые коды КТР.
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
    Получить статистику модуля.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            stats = {}
            
            # Общие количества
            cursor.execute("SELECT COUNT(*) as cnt FROM ktr_codes WHERE active = 1")
            stats['total_codes'] = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM ktr_categories WHERE active = 1")
            stats['total_categories'] = cursor.fetchone()['cnt']
            
            cursor.execute("SELECT COUNT(*) as cnt FROM ktr_unknown_codes")
            stats['unknown_codes'] = cursor.fetchone()['cnt']
            
            # Последние 7 дней
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
            
            # Топ кодов
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


# ===== ПОЛЬЗОВАТЕЛЬСКИЕ ОБРАБОТЧИКИ =====

async def enter_ktr_module(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Точка входа в модуль КТР.
    Сразу ожидает ввод кода.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(get_unauthorized_message(update.effective_user.id))
        return ConversationHandler.END
    
    if check_if_user_admin(update.effective_user.id):
        keyboard = keyboards.get_admin_submenu_keyboard()
    else:
        keyboard = keyboards.get_submenu_keyboard()
    
    await update.message.reply_text(
        messages.MESSAGE_ENTER_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    return WAITING_FOR_CODE


async def start_code_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Запустить процесс поиска кода КТР.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(get_unauthorized_message(update.effective_user.id))
        return ConversationHandler.END
    
    if check_if_user_admin(update.effective_user.id):
        keyboard = keyboards.get_admin_submenu_keyboard()
    else:
        keyboard = keyboards.get_submenu_keyboard()

    await update.message.reply_text(
        messages.MESSAGE_ENTER_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    return WAITING_FOR_CODE


async def process_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать ввод кода КТР и вернуть результат.
    """
    # Импортируем события геймификации (ленивый импорт, чтобы избежать циклов)
    from src.sbs_helper_telegram_bot.gamification.events import emit_event
    
    user_id = update.effective_user.id
    input_text = update.message.text.strip().upper()  # Коды КТР обычно в верхнем регистре
    
    # Валидируем ввод
    if not input_text or len(input_text) > 50:
        await update.message.reply_text(
            messages.MESSAGE_INVALID_CODE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return WAITING_FOR_CODE
    
    # Отправляем событие геймификации о попытке поиска
    emit_event("ktr.lookup", user_id, {"code": input_text})
    
    # Ищем код КТР
    code_info = get_ktr_code_by_code(input_text)
    
    if code_info:
        # Найдено — логируем и показываем
        record_ktr_request(user_id, input_text, found=True)
        
        # Отправляем событие геймификации об успешном поиске
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
        # Не найдено — логируем и добавляем в неизвестные
        record_ktr_request(user_id, input_text, found=False)
        record_unknown_code(input_text)
        
        escaped_code = messages.escape_markdown_v2(input_text)
        await update.message.reply_text(
            messages.MESSAGE_CODE_NOT_FOUND.format(code=escaped_code),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    # Возвращаемся в подменю
    if check_if_user_admin(user_id):
        keyboard = keyboards.get_admin_submenu_keyboard()
    else:
        keyboard = keyboards.get_submenu_keyboard()
    
    await update.message.reply_text(
        messages.MESSAGE_ENTER_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    
    return WAITING_FOR_CODE


async def direct_code_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать прямой ввод кода КТР из подменю (без нажатия кнопки поиска).
    Это позволяет пользователям вводить коды напрямую.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(get_unauthorized_message(update.effective_user.id))
        return ConversationHandler.END
    
    # Переиспользуем логику process_code_input
    return await process_code_input(update, context)


async def show_popular_codes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показать наиболее запрашиваемые коды КТР.
    """
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(get_unauthorized_message(update.effective_user.id))
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
    return WAITING_FOR_CODE


async def show_ktr_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показать достижения модуля КТР для текущего пользователя.
    """
    from src.sbs_helper_telegram_bot.gamification import gamification_logic
    from src.sbs_helper_telegram_bot.gamification import messages as gf_messages
    from src.sbs_helper_telegram_bot.gamification import keyboards as gf_keyboards
    
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(get_unauthorized_message(update.effective_user.id))
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    
    # Получаем достижения КТР с прогрессом
    achievements = gamification_logic.get_user_achievements_with_progress(user_id, 'ktr')
    
    if not achievements:
        await update.message.reply_text(
            "🎖️ *Достижения модуля КТР*\n\nДостижения пока не настроены\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return SUBMENU
    
    # Считаем разблокированные
    unlocked = sum(1 for a in achievements if a['unlocked_level'] > 0)
    total = len(achievements) * 3  # 3 уровня на достижение
    
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
    return WAITING_FOR_CODE


async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменить процесс поиска кода.
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
    Показывает соответствующий ответ в зависимости от нажатой кнопки.
    """
    # Очищаем данные контекста
    context.user_data.pop('ktr_temp', None)
    
    # Проверяем, какая кнопка была нажата, и отвечаем соответствующим образом
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


# ===== АДМИНСКИЕ ОБРАБОТЧИКИ =====

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Показать админ-меню для КТР.
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
    
    if text == settings.BUTTON_ADMIN_LIST_CODES:
        return await admin_show_codes_list(update, context)
    elif text == settings.BUTTON_ADMIN_ADD_CODE:
        return await admin_start_add_code(update, context)
    elif text == settings.BUTTON_ADMIN_SEARCH_CODE:
        return await admin_start_search_code(update, context)
    elif text == settings.BUTTON_ADMIN_CATEGORIES:
        return await admin_show_categories(update, context)
    elif text == settings.BUTTON_ADMIN_UNKNOWN_CODES:
        return await admin_show_unknown_codes(update, context)
    elif text == settings.BUTTON_ADMIN_STATS:
        return await admin_show_statistics(update, context)
    elif text == settings.BUTTON_ADMIN_IMPORT_CSV:
        return await admin_start_csv_import(update, context)
    elif text == settings.BUTTON_ADMIN_BACK_TO_KTR:
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


async def admin_show_codes_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> int:
    """
    Показать постраничный список кодов КТР.
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
    Запустить процесс поиска кода КТР.
    Админ может ввести код напрямую, не прокручивая список.
    """
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_SEARCH_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_SEARCH_CODE


async def admin_receive_search_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Получить код для поиска и показать его для редактирования.
    """
    code = update.message.text.strip().upper()
    
    # Ищем код в базе данных (включая неактивные)
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
    
    # Сохраняем данные кода для возможного редактирования
    context.user_data['ktr_temp'] = {'code_id': ktr['id']}
    
    # Форматируем детали кода
    text = messages.format_ktr_code_response(
        code=ktr['code'],
        description=ktr['description'],
        minutes=ktr['minutes'],
        category_name=ktr.get('category_name'),
        updated_timestamp=ktr.get('updated_timestamp'),
        date_updated=ktr.get('date_updated')
    )
    
    # Добавляем индикатор статуса
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
    Запустить процесс добавления нового кода КТР.
    """
    context.user_data['ktr_temp'] = {}
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_CODE,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_CODE


async def admin_receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Получить код для новой записи КТР.
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
    Получить описание для нового кода КТР.
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
    Получить минуты для нового кода КТР, затем показать выбор категории.
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
        # Категорий нет — создаём код без категории
        return await _create_ktr_code(update, context, category_id=None)


async def admin_select_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработать callback выбора категории.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "ktr_cat_skip":
        # Пропускаем выбор категории
        return await _create_ktr_code(query, context, category_id=None)
    elif data.startswith("ktr_cat_select_"):
        category_id = int(data.replace("ktr_cat_select_", ""))
        return await _create_ktr_code(query, context, category_id=category_id)
    
    return ADMIN_SELECT_CATEGORY


async def _create_ktr_code(update_or_query, context: ContextTypes.DEFAULT_TYPE, category_id: Optional[int]) -> int:
    """
    Вспомогательная функция для создания кода КТР после сбора всех данных.
    """
    temp = context.user_data.get('ktr_temp', {})
    code = temp.get('code')
    description = temp.get('description')
    minutes = temp.get('minutes')
    
    if not all([code, description, minutes is not None]):
        return ADMIN_MENU
    
    # Создаём код КТР
    create_ktr_code(code, description, minutes, category_id)
    
    # Получаем название категории для ответа
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
    context.user_data.pop('ktr_temp', None)
    
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
    Показать статистику модуля.
    """
    stats = get_statistics()
    
    # Форматируем топ кодов
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
    Обработать callback-и админской inline-клавиатуры.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Просмотр деталей кода
    if data.startswith("ktr_view_"):
        code_id = int(data.replace("ktr_view_", ""))
        return await _show_code_details(query, context, code_id)
    
    # Редактирование описания кода
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
    
    # Редактирование минут
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
    
    # Редактирование категории
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
    
    # Активация/деактивация
    elif data.startswith("ktr_activate_"):
        code_id = int(data.replace("ktr_activate_", ""))
        update_ktr_code(code_id, 'active', 1)
        return await _show_code_details(query, context, code_id)
    
    elif data.startswith("ktr_deactivate_"):
        code_id = int(data.replace("ktr_deactivate_", ""))
        update_ktr_code(code_id, 'active', 0)
        return await _show_code_details(query, context, code_id)
    
    # Удаление кода
    elif data.startswith("ktr_delete_"):
        code_id = int(data.replace("ktr_delete_", ""))
        keyboard = keyboards.get_confirm_delete_keyboard('code', code_id)
        await query.edit_message_text(
            "⚠️ *Удалить код КТР?*\n\nЭто действие нельзя отменить\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboard
        )
        return ADMIN_MENU
    
    # Подтверждение удаления
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
    
    # Назад к списку кодов
    elif data == "ktr_codes_list":
        # В callback нельзя показать полный список — просто подтверждаем
        await query.edit_message_text(messages.MESSAGE_USE_LIST_BUTTON)
        return ADMIN_MENU
    
    # Назад в админ-меню
    elif data == "ktr_admin_menu":
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    # Коллбэки категорий
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
    
    # Добавление из неизвестных кодов
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
    
    # Пагинация
    elif data.startswith("ktr_page_"):
        page = int(data.replace("ktr_page_", ""))
        # Перезапрашиваем и показываем
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
    Показать детали кода КТР с вариантами редактирования.
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
    Показать детали категории с вариантами редактирования.
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
    Получить отредактированное описание.
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
    Получить отредактированное значение минут.
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
    Запустить процесс добавления новой категории.
    """
    context.user_data['ktr_temp'] = {}
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_CATEGORY_NAME,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ADMIN_ADD_CATEGORY_NAME


async def admin_receive_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Получить название категории.
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
    Получить описание категории.
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
    Получить порядок отображения и создать категорию.
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
        detected_encoding = None
        
        # Сначала проверяем BOM (маркер порядка байтов)
        if raw_bytes.startswith(b'\xef\xbb\xbf'):
            # UTF-8 с BOM
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
            # Пробуем разные кодировки в порядке вероятности для Mac
            # macroman (alias для mac_roman) часто используется при экспорте из Excel на Mac
            encodings_to_try = [
                'utf-8',
                'macroman',      # Mac OS Roman (основная mac-кодировка)
                'mac-cyrillic',  # Mac-кодировка для кириллицы
                'cp1251',        # Кириллица Windows
                'windows-1251',  # Альтернативное имя для cp1251
                'koi8-r',        # KOI8-R для кириллицы
                'iso-8859-5',    # ISO-кодировка для кириллицы
                'utf-16',        # UTF-16 без BOM
                'latin1',        # ISO-8859-1
            ]
            
            for encoding in encodings_to_try:
                try:
                    test_content = raw_bytes.decode(encoding)
                    
                    # Проверяем, появились ли символы замены при декодировании
                    # это указывает на неверную кодировку
                    if '\ufffd' in test_content:
                        continue
                    
                    # Для не-UTF-8 выполняем дополнительную проверку
                    if encoding != 'utf-8':
                        # Проверяем, похоже ли содержимое на текст (есть ASCII)
                        sample = test_content[:1000]
                        ascii_chars = sum(1 for c in sample if ord(c) < 128)
                        if len(sample) > 0 and ascii_chars / len(sample) < 0.3:
                            # Слишком мало ASCII — вероятно, неверная кодировка
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
        
        # Нормализуем переводы строк
        csv_content = csv_content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Логируем определённую кодировку для отладки
        if detected_encoding:
            logger.info(f"CSV file decoded successfully using {detected_encoding} encoding")
        
        # Разбираем CSV
        records, parse_errors = parse_csv_ktr_codes(csv_content)
        
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
        context.user_data['ktr_temp'] = {
            'csv_records': records,
            'csv_parse_errors': parse_errors
        }
        
        # Подсчитываем существующие коды пакетной операцией
        all_codes = [r['code'] for r in records]
        existing_codes_set = batch_check_existing_codes(all_codes)
        existing_count = len(existing_codes_set)
        new_count = len(records) - existing_count
        
        # Готовим информацию о кодировке для отображения
        encoding_info = ""
        if detected_encoding and detected_encoding != 'utf-8':
            escaped_enc = messages.escape_markdown_v2(detected_encoding)
            encoding_info = f"\n_\\(кодировка: {escaped_enc}\\)_"
        
        # Показываем превью и просим подтверждение
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
    Обработать callback-и подтверждения импорта CSV.
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
        # Импортировать, пропуская существующие
        return await _perform_csv_import(query, context, skip_existing=True)
    
    elif data == "ktr_csv_import_update":
        # Импортировать, обновляя существующие
        return await _perform_csv_import(query, context, skip_existing=False)
    
    return ADMIN_IMPORT_CSV_CONFIRM


async def _perform_csv_import(query, context: ContextTypes.DEFAULT_TYPE, skip_existing: bool) -> int:
    """
    Выполнить фактический импорт CSV.
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
    
    # Выполняем импорт
    result = import_ktr_codes_from_csv(records, skip_existing=skip_existing)
    
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
    
    context.user_data.pop('ktr_temp', None)
    return ADMIN_MENU


async def admin_cancel_csv_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Отменить импорт CSV через кнопку.
    """
    context.user_data.pop('ktr_temp', None)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CSV_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_MENU


# ===== СБОРКА CONVERSATION HANDLER =====

def get_menu_button_regex_pattern() -> str:
    """
    Получить regex-шаблон для кнопок модуля КТР в fallback.
    Также включает кнопки других модулей, чтобы корректно завершать диалог при переключении.
    """
    buttons = []
    # Добавляем кнопки, относящиеся к КТР
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
    # Эти кнопки означают, что пользователь хочет выйти из модуля КТР
    other_module_buttons = [
        BUTTON_MAIN_MENU,
        BUTTON_MODULES,
        BUTTON_SETTINGS,
        BUTTON_VALIDATE_TICKET,
        BUTTON_SCREENSHOT,
        BUTTON_UPOS_ERRORS,
        BUTTON_CERTIFICATION,
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
    Получить ConversationHandler для пользовательского поиска кодов КТР.
    Пользователь вводит коды сразу после входа в модуль.
    """
    menu_pattern = get_menu_button_regex_pattern()
    
    return ConversationHandler(
        entry_points=[
            # Вход при нажатии кнопки модуля КТР
            MessageHandler(filters.Regex(f"^{re.escape(settings.MENU_BUTTON_TEXT)}$"), enter_ktr_module),
        ],
        states={
            WAITING_FOR_CODE: [
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_FIND_CODE)}$"), start_code_search),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_POPULAR_CODES)}$"), show_popular_codes),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ACHIEVEMENTS)}$"), show_ktr_achievements),
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(menu_pattern), process_code_input)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_search),
            CommandHandler("reset", cancel_search_on_menu),
            CommandHandler("menu", cancel_search_on_menu),
            MessageHandler(filters.COMMAND, cancel_search_on_menu),
            MessageHandler(filters.Regex(menu_pattern), cancel_search_on_menu)
        ],
        name="ktr_user_conversation",
        persistent=False
    )


def get_admin_conversation_handler() -> ConversationHandler:
    """
    Получить ConversationHandler для админских CRUD-операций.
    """
    menu_pattern = get_menu_button_regex_pattern()
    
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_PANEL)}$"), admin_menu),
        ],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(admin_callback_handler, pattern="^ktr_"),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_LIST_CODES)}$"), admin_show_codes_list),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_ADD_CODE)}$"), admin_start_add_code),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_SEARCH_CODE)}$"), admin_start_search_code),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_CATEGORIES)}$"), admin_show_categories),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_UNKNOWN_CODES)}$"), admin_show_unknown_codes),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_STATS)}$"), admin_show_statistics),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_ALL_CATEGORIES)}$"), admin_show_categories),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_ADD_CATEGORY)}$"), admin_start_add_category),
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_IMPORT_CSV)}$"), admin_start_csv_import),
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
                MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_BACK)}$"), admin_menu),
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
            CommandHandler("reset", cancel_search_on_menu),
            CommandHandler("menu", cancel_search_on_menu),
            MessageHandler(filters.Regex(f"^{re.escape(BUTTON_MAIN_MENU)}$"), cancel_search_on_menu),
            MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_ADMIN_BACK_TO_KTR)}$"), enter_ktr_module),
            MessageHandler(filters.COMMAND, cancel_search_on_menu),  # Обрабатываем /start и другие команды
        ]
    )
