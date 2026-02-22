"""
Bot Admin Module - Admin Bot Part

Telegram handlers for bot-wide administration:
- User management (list, search, view, admin grant/revoke)
- Pre-invite management
- Statistics
- Invite management
"""

import logging
import re
from datetime import datetime
from typing import Optional

from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

from src.common.telegram_user import check_if_user_legit, check_if_user_admin, set_user_admin
from src.common.messages import (
    MESSAGE_PLEASE_ENTER_INVITE,
    get_main_menu_message,
    get_main_menu_keyboard,
    BUTTON_MAIN_MENU,
)
from src.common import invites as invites_module
from src.common import database
from src.common import bot_settings
from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings
from src.sbs_helper_telegram_bot.ai_router.intent_router import reset_router as reset_ai_router
from src.common.health_check import (
    OUTAGE_TYPE_BLUE_LONG,
    OUTAGE_TYPE_BLUE_SHORT,
    OUTAGE_TYPE_LABELS,
    OUTAGE_TYPE_RED,
    create_planned_outage,
    delete_planned_outage,
    get_planned_outage_by_id,
    list_planned_outages,
)

from . import settings
from . import messages
from . import keyboards

logger = logging.getLogger(__name__)

# Состояния диалога
(
    ADMIN_MENU,
    # Состояния управления пользователями
    USER_MANAGEMENT_MENU,
    USER_LIST,
    USER_VIEW,
    USER_SEARCH,
    USER_SEARCH_RESULTS,
    ADMIN_LIST,
    CONFIRM_ADMIN_ACTION,
    # Состояния предварительных приглашений
    PREINVITE_MENU,
    PREINVITE_LIST,
    PREINVITE_VIEW,
    PREINVITE_ADD_ID,
    PREINVITE_ADD_NOTES,
    PREINVITE_CONFIRM_DELETE,
    # Состояния ручных пользователей
    MANUAL_USERS_MENU,
    MANUAL_USERS_LIST,
    MANUAL_USER_VIEW,
    MANUAL_USER_ADD_ID,
    MANUAL_USER_ADD_NOTES,
    MANUAL_USER_CONFIRM_DELETE,
    # Состояния статистики
    STATISTICS_MENU,
    # Состояния управления инвайтами
    INVITE_MENU,
    INVITE_LIST,
    INVITE_ISSUE_USER,
    INVITE_ISSUE_COUNT,
    # Состояния настроек бота
    BOT_SETTINGS_MENU,
    INVITE_SYSTEM_SETTINGS,
    AI_MODEL_SETTINGS,
    # Состояния управления модулями
    MODULES_MANAGEMENT_MENU,
    # Состояния плановых работ
    PLANNED_OUTAGES_MENU,
    PLANNED_OUTAGES_LIST,
    PLANNED_OUTAGE_ADD_DATE,
    PLANNED_OUTAGE_ADD_TYPE,
    PLANNED_OUTAGE_CONFIRM_DELETE,
) = range(34)


# ============================================================================
# Вспомогательные функции
# ============================================================================

def escape_markdown(text: str) -> str:
    """Экранировать спецсимволы для MarkdownV2."""
    if text is None:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = str(text).replace(char, f'\\{char}')
    return text


def get_users_list(page: int = 1, limit: int = 10) -> tuple:
    """Получить список пользователей из БД с пагинацией."""
    offset = (page - 1) * limit
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Получаем общее количество
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total = cursor.fetchone()['count']
            
            # Получаем пользователей для текущей страницы
            cursor.execute("""
                SELECT userid, first_name, last_name, username, timestamp, is_admin
                FROM users
                ORDER BY timestamp DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            users = cursor.fetchall()
            
            total_pages = max(1, (total + limit - 1) // limit)
            return users, total, total_pages


def get_user_details(user_id: int) -> Optional[dict]:
    """Получить подробную информацию о пользователе."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Получаем данные пользователя
            cursor.execute("""
                SELECT userid, first_name, last_name, username, timestamp, is_admin
                FROM users WHERE userid = %s
            """, (user_id,))
            user = cursor.fetchone()
            
            if not user:
                return None
            
            # Получаем статистику по инвайтам
            cursor.execute("""
                SELECT COUNT(*) as issued FROM invites WHERE userid = %s
            """, (user_id,))
            invites_issued = cursor.fetchone()['issued']
            
            cursor.execute("""
                SELECT COUNT(*) as used FROM invites WHERE userid = %s AND consumed_userid IS NOT NULL
            """, (user_id,))
            invites_used = cursor.fetchone()['used']
            
            # Получаем информацию, кто пригласил пользователя
            cursor.execute("""
                SELECT userid FROM invites WHERE consumed_userid = %s LIMIT 1
            """, (user_id,))
            invited_by_result = cursor.fetchone()
            invited_by = invited_by_result['userid'] if invited_by_result else None
            
            return {
                **user,
                'invites_issued': invites_issued,
                'invites_used': invites_used,
                'invited_by': invited_by
            }


def search_users(query: str) -> list:
    """Искать пользователей по ID, username или имени."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Сначала пробуем точное совпадение ID
            if query.isdigit():
                cursor.execute("""
                    SELECT userid, first_name, last_name, username, is_admin
                    FROM users WHERE userid = %s
                """, (int(query),))
                result = cursor.fetchone()
                if result:
                    return [result]
            
            # Ищем по имени/username
            search_pattern = f"%{query}%"
            cursor.execute("""
                SELECT userid, first_name, last_name, username, is_admin
                FROM users 
                WHERE first_name LIKE %s 
                   OR last_name LIKE %s 
                   OR username LIKE %s
                ORDER BY first_name
                LIMIT 20
            """, (search_pattern, search_pattern, search_pattern))
            return cursor.fetchall()


def get_admin_list() -> list:
    """Получить список всех администраторов."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT userid, first_name, last_name, username
                FROM users WHERE is_admin = 1
                ORDER BY first_name
            """)
            return cursor.fetchall()


def get_bot_statistics() -> dict:
    """Получить общую статистику бота."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Статистика пользователей
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_admin = 1")
            admin_count = cursor.fetchone()['count']
            
            # Статистика инвайтов
            cursor.execute("SELECT COUNT(*) as count FROM invites")
            total_invites = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM invites WHERE consumed_userid IS NOT NULL")
            used_invites = cursor.fetchone()['count']
            
            # Статистика пред-инвайтов
            total_preinvites = invites_module.get_pre_invited_user_count(include_activated=True)
            activated_preinvites = invites_module.get_pre_invited_user_count(include_activated=True) - \
                                   invites_module.get_pre_invited_user_count(include_activated=False)
            
            # Месячная статистика (последние 30 дней)
            thirty_days_ago = int(datetime.now().timestamp()) - (30 * 24 * 60 * 60)
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM users WHERE timestamp >= %s
            """, (thirty_days_ago,))
            new_users_month = cursor.fetchone()['count']
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM invites 
                WHERE consumed_timestamp >= %s
            """, (thirty_days_ago,))
            used_invites_month = cursor.fetchone()['count']
            
            return {
                'total_users': total_users,
                'admin_count': admin_count,
                'total_invites': total_invites,
                'used_invites': used_invites,
                'available_invites': total_invites - used_invites,
                'total_preinvites': total_preinvites,
                'activated_preinvites': activated_preinvites,
                'pending_preinvites': total_preinvites - activated_preinvites,
                'new_users_month': new_users_month,
                'used_invites_month': used_invites_month
            }


def get_new_feedback_count() -> int:
    """Получить количество новых (неотвеченных) обращений."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM feedback_entries
                    WHERE status = %s
                """, ("new",))
                return cursor.fetchone()['count']
    except Exception as e:
        logger.error("Error getting new feedback count: %s", e)
        return 0


# ============================================================================
# Точка входа и главное меню
# ============================================================================

async def bot_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать /botadmin или кнопку 🛠️ Админ бота."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    if not check_if_user_admin(update.effective_user.id):
        from src.common.messages import MESSAGE_NO_ADMIN_RIGHTS
        await update.message.reply_text(
            MESSAGE_NO_ADMIN_RIGHTS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        messages.MESSAGE_BOT_ADMIN_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    return ADMIN_MENU


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать нажатия кнопок админ-меню."""
    text = update.message.text
    
    if not check_if_user_admin(update.effective_user.id):
        from src.common.messages import MESSAGE_NO_ADMIN_RIGHTS
        await update.message.reply_text(
            MESSAGE_NO_ADMIN_RIGHTS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    if text == "👥 Пользователи":
        return await show_user_management_menu(update, context)
    elif text == "👤 Пре-инвайты":
        return await show_preinvite_menu(update, context)
    elif text == "➕ Ручные пользователи":
        return await show_manual_users_menu(update, context)
    elif text == "📊 Статистика":
        return await show_statistics_menu(update, context)
    elif text == "🎫 Инвайты":
        return await show_invite_management_menu(update, context)
    elif text == "🔙 Админ бота":
        await update.message.reply_text(
            messages.MESSAGE_BOT_ADMIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    elif text == BUTTON_MAIN_MENU:
        main_menu_message = get_main_menu_message(update.effective_user.id, update.effective_user.first_name)
        new_feedback_count = get_new_feedback_count()
        if new_feedback_count > 0:
            main_menu_message += f"\n\n🔔 *Новые обращения:* *{new_feedback_count}*"
        await update.message.reply_text(
            main_menu_message,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=check_if_user_admin(update.effective_user.id))
        )
        return ConversationHandler.END
    
    # Обработчики меню управления пользователями
    elif text == "📋 Список пользователей":
        return await show_user_list(update, context)
    elif text == "🔍 Поиск пользователя":
        return await start_user_search(update, context)
    elif text == "👑 Список админов":
        return await show_admin_list(update, context)
    
    # Обработчики меню пред-инвайтов
    elif text == "📋 Список пре-инвайтов":
        return await show_preinvite_list(update, context)
    elif text == "➕ Добавить пользователя":
        return await start_add_preinvite(update, context)
    
    # Обработчики меню ручных пользователей
    elif text == "📋 Список ручных пользователей":
        return await show_manual_users_list(update, context)
    elif text == "➕ Добавить ручного пользователя":
        return await start_add_manual_user(update, context)
    
    # Обработчики статистики
    elif text == "📈 Общая статистика":
        return await show_general_statistics(update, context)
    elif text == "📅 Статистика за период":
        return await show_general_statistics(update, context)  # Пока так же, как общая статистика
    
    # Обработчики управления инвайтами
    elif text == "📋 Все инвайты":
        return await show_invite_list(update, context)
    elif text == "🎁 Выдать инвайты":
        return await start_issue_invites(update, context)
    
    # Обработчики настроек бота
    elif text == "⚙️ Настройки бота":
        return await show_bot_settings_menu(update, context)
    elif text == "🔐 Инвайт-система":
        return await show_invite_system_settings(update, context)
    elif text == settings.BUTTON_AI_MODEL:
        return await show_ai_model_settings(update, context)
    elif text == "🧩 Модули":
        return await show_modules_management_menu(update, context)
    elif text == settings.BUTTON_PLANNED_OUTAGES:
        return await show_planned_outages_menu(update, context)
    elif text == "🔙 Настройки бота":
        return await show_bot_settings_menu(update, context)
    elif text == settings.BUTTON_OUTAGE_LIST:
        return await show_planned_outages_list(update, context)
    elif text == settings.BUTTON_OUTAGE_ADD:
        return await start_add_planned_outage(update, context)
    
    return ADMIN_MENU


# ============================================================================
# Управление пользователями
# ============================================================================

async def show_user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать подменю управления пользователями."""
    await update.message.reply_text(
        messages.MESSAGE_USER_MANAGEMENT_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_user_management_keyboard()
    )
    return USER_MANAGEMENT_MENU


async def show_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> int:
    """Показать список пользователей с пагинацией."""
    users, total, total_pages = get_users_list(page=page, limit=settings.USERS_PER_PAGE)
    
    if not users:
        await update.message.reply_text(
            "⚠️ Пользователи не найдены\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_user_management_keyboard()
        )
        return USER_MANAGEMENT_MENU
    
    # Собираем инлайн-клавиатуру с пользователями
    keyboard = []
    for user in users:
        status = "👑" if user['is_admin'] else "👤"
        # Формируем полное имя: first_name + last_name
        name_parts = []
        if user['first_name']:
            name_parts.append(user['first_name'])
        if user['last_name']:
            name_parts.append(user['last_name'])
        full_name = " ".join(name_parts) if name_parts else "Без имени"
        username = f"@{user['username']}" if user['username'] else ""
        # Формат: статус + полное имя + (username, если есть)
        display_text = f"{status} {full_name}"
        if username:
            display_text += f" {username}"
        keyboard.append([
            InlineKeyboardButton(
                display_text,
                callback_data=f"bot_admin_user_view_{user['userid']}"
            )
        ])
    
    # Добавляем пагинацию
    if total_pages > 1:
        keyboard.append(keyboards.get_pagination_keyboard(page, total_pages, "bot_admin_users"))
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_user_menu")])
    
    await update.message.reply_text(
        messages.MESSAGE_USER_LIST.format(total=total, page=page, total_pages=total_pages),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return USER_LIST


async def start_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запустить процесс поиска пользователя."""
    await update.message.reply_text(
        messages.MESSAGE_USER_SEARCH,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_user_management_keyboard()
    )
    return USER_SEARCH


async def receive_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать поисковый запрос пользователя."""
    query = update.message.text.strip()
    
    # Обрабатываем кнопки меню
    if query in ["🔙 Админ бота", BUTTON_MAIN_MENU, "📋 Список пользователей", "👑 Список админов"]:
        return await admin_menu_handler(update, context)
    
    users = search_users(query)
    
    if not users:
        await update.message.reply_text(
            messages.MESSAGE_USER_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_user_management_keyboard()
        )
        return USER_MANAGEMENT_MENU
    
    # Собираем инлайн-клавиатуру с результатами
    keyboard = []
    for user in users:
        status = "👑" if user['is_admin'] else "👤"
        # Формируем полное имя: first_name + last_name
        name_parts = []
        if user['first_name']:
            name_parts.append(user['first_name'])
        if user.get('last_name'):
            name_parts.append(user['last_name'])
        full_name = " ".join(name_parts) if name_parts else "Без имени"
        username = f"@{user['username']}" if user.get('username') else ""
        display_text = f"{status} {full_name}"
        if username:
            display_text += f" {username}"
        keyboard.append([
            InlineKeyboardButton(
                display_text,
                callback_data=f"bot_admin_user_view_{user['userid']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_user_menu")])
    
    await update.message.reply_text(
        messages.MESSAGE_USER_SEARCH_RESULTS.format(query=escape_markdown(query), count=len(users)),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return USER_SEARCH_RESULTS


async def show_admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать список администраторов."""
    admins = get_admin_list()
    
    if not admins:
        await update.message.reply_text(
            "⚠️ Администраторы не найдены\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_user_management_keyboard()
        )
        return USER_MANAGEMENT_MENU
    
    # Собираем инлайн-клавиатуру с администраторами
    keyboard = []
    for admin in admins:
        # Формируем полное имя: first_name + last_name
        name_parts = []
        if admin['first_name']:
            name_parts.append(admin['first_name'])
        if admin.get('last_name'):
            name_parts.append(admin['last_name'])
        full_name = " ".join(name_parts) if name_parts else "Без имени"
        username = f"@{admin['username']}" if admin.get('username') else ""
        display_text = f"👑 {full_name}"
        if username:
            display_text += f" {username}"
        keyboard.append([
            InlineKeyboardButton(
                display_text,
                callback_data=f"bot_admin_user_view_{admin['userid']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_user_menu")])
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_LIST.format(count=len(admins)),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_LIST


async def show_user_details_callback(query, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int:
    """Показать подробную информацию о пользователе."""
    user = get_user_details(user_id)
    
    if not user:
        await query.edit_message_text(
            messages.MESSAGE_USER_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return USER_LIST
    
    # Форматируем детали пользователя
    registered = datetime.fromtimestamp(user['timestamp']).strftime("%Y-%m-%d %H:%M")
    
    # Проверяем, есть ли у пользователя пред-инвайт
    status_parts = []
    if invites_module.check_if_user_pre_invited(user_id):
        if invites_module.is_pre_invited_user_activated(user_id):
            status_parts.append("Пре-инвайт (активирован)")
        else:
            status_parts.append("Пре-инвайт (ожидает)")
    
    # Проверяем, добавлен ли пользователь вручную
    if invites_module.check_if_user_manual(user_id):
        status_parts.append("Ручной пользователь")
    
    # Проверяем, использован ли инвайт
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT COUNT(*) as c FROM invites WHERE consumed_userid = %s", (user_id,))
            if cursor.fetchone()['c'] > 0:
                status_parts.append("Инвайт")
    
    status = ", ".join(status_parts) if status_parts else "Активен"
    
    is_self = query.from_user.id == user_id
    
    # Форматируем поле invited_by
    if user['invited_by']:
        invited_by_text = escape_markdown(f"#{user['invited_by']}")
    else:
        invited_by_text = escape_markdown("Самостоятельно/Пре-инвайт")
    
    await query.edit_message_text(
        messages.MESSAGE_USER_DETAILS.format(
            user_id=user_id,
            first_name=escape_markdown(user['first_name'] or "Не указано"),
            last_name=escape_markdown(user['last_name'] or "Не указана"),
            username=f"@{user['username']}" if user['username'] else "Не указан",
            registered=escape_markdown(registered),
            status=escape_markdown(status),
            is_admin="✅ Да" if user['is_admin'] else "❌ Нет",
            invites_issued=user['invites_issued'],
            invites_used=user['invites_used'],
            invited_by=invited_by_text
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_user_details_keyboard(user_id, user['is_admin'], is_self)
    )
    return USER_VIEW


# ============================================================================
# Управление пред-инвайтами
# ============================================================================

async def show_preinvite_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню управления пред-инвайтами."""
    await update.message.reply_text(
        messages.MESSAGE_PREINVITE_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_preinvite_keyboard()
    )
    return PREINVITE_MENU


async def show_preinvite_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать список предварительно приглашённых пользователей."""
    users = invites_module.get_pre_invited_users(include_activated=True, limit=50)
    total = invites_module.get_pre_invited_user_count(include_activated=True)
    activated = total - invites_module.get_pre_invited_user_count(include_activated=False)
    pending = total - activated
    
    if not users:
        await update.message.reply_text(
            messages.MESSAGE_PREINVITE_NO_USERS,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_preinvite_keyboard()
        )
        return PREINVITE_MENU
    
    # Собираем инлайн-клавиатуру с пользователями
    keyboard = []
    for user in users:
        status = "✅" if user['activated_timestamp'] else "⏳"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {user['telegram_id']}",
                callback_data=f"bot_admin_preinvite_view_{user['telegram_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_preinvite_menu")])
    
    await update.message.reply_text(
        messages.MESSAGE_PREINVITE_LIST.format(total=total, activated=activated, pending=pending),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PREINVITE_LIST


async def start_add_preinvite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать добавление нового пред-инвайта."""
    context.user_data['new_preinvite'] = {}
    
    await update.message.reply_text(
        messages.MESSAGE_PREINVITE_ADD,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_preinvite_keyboard()
    )
    return PREINVITE_ADD_ID


async def receive_preinvite_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принять Telegram ID для нового пред-инвайта."""
    text = update.message.text.strip()
    
    # Обрабатываем кнопки меню
    if text in ["🔙 Админ бота", BUTTON_MAIN_MENU, "📋 Список пре-инвайтов"]:
        context.user_data.pop('new_preinvite', None)
        return await admin_menu_handler(update, context)
    
    try:
        telegram_id = int(text)
    except ValueError:
        await update.message.reply_text(
            messages.MESSAGE_PREINVITE_INVALID_ID,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return PREINVITE_ADD_ID
    
    if invites_module.check_if_user_pre_invited(telegram_id):
        await update.message.reply_text(
            messages.MESSAGE_PREINVITE_EXISTS.format(telegram_id=telegram_id),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_preinvite_keyboard()
        )
        context.user_data.pop('new_preinvite', None)
        return PREINVITE_MENU
    
    context.user_data['new_preinvite']['telegram_id'] = telegram_id
    
    await update.message.reply_text(
        messages.MESSAGE_PREINVITE_ADD_NOTES,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return PREINVITE_ADD_NOTES


async def receive_preinvite_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принять заметки и завершить добавление пред-инвайта."""
    text = update.message.text.strip()
    
    # Обрабатываем кнопки меню
    if text in ["🔙 Админ бота", BUTTON_MAIN_MENU, "📋 Список пре-инвайтов"]:
        context.user_data.pop('new_preinvite', None)
        return await admin_menu_handler(update, context)
    
    preinvite_data = context.user_data.get('new_preinvite', {})
    telegram_id = preinvite_data.get('telegram_id')
    
    if not telegram_id:
        await update.message.reply_text(
            messages.MESSAGE_ERROR,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_preinvite_keyboard()
        )
        return PREINVITE_MENU
    
    notes = None if text == "-" else text
    
    try:
        success = invites_module.add_pre_invited_user(
            telegram_id=telegram_id,
            added_by_userid=update.effective_user.id,
            notes=notes
        )
        
        if success:
            await update.message.reply_text(
                messages.MESSAGE_PREINVITE_ADDED.format(telegram_id=telegram_id),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboards.get_preinvite_keyboard()
            )
        else:
            await update.message.reply_text(
                messages.MESSAGE_PREINVITE_EXISTS.format(telegram_id=telegram_id),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboards.get_preinvite_keyboard()
            )
    except Exception as e:
        logger.error(f"Error adding pre-invite: {e}", exc_info=True)
        await update.message.reply_text(
            messages.MESSAGE_ERROR,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_preinvite_keyboard()
        )
    
    context.user_data.pop('new_preinvite', None)
    return PREINVITE_MENU


async def show_preinvite_details_callback(query, context: ContextTypes.DEFAULT_TYPE, telegram_id: int) -> int:
    """Показать детали пред-инвайта."""
    users = invites_module.get_pre_invited_users(include_activated=True, limit=100)
    user = next((u for u in users if u['telegram_id'] == telegram_id), None)
    
    if not user:
        await query.edit_message_text(
            messages.MESSAGE_USER_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return PREINVITE_LIST
    
    # Форматируем детали
    if user['added_by_userid']:
        added_by = messages.MESSAGE_PREINVITE_ADDED_BY_ADMIN.format(admin_id=user['added_by_userid'])
    else:
        added_by = messages.MESSAGE_PREINVITE_ADDED_BY_UNKNOWN
    
    notes = escape_markdown(user['notes']) if user['notes'] else messages.MESSAGE_PREINVITE_NO_NOTES
    created = datetime.fromtimestamp(user['created_timestamp']).strftime("%Y-%m-%d %H:%M")
    
    if user['activated_timestamp']:
        activated = datetime.fromtimestamp(user['activated_timestamp']).strftime("%Y-%m-%d %H:%M")
        status = messages.MESSAGE_PREINVITE_STATUS_ACTIVATED.format(date=escape_markdown(activated))
    else:
        status = messages.MESSAGE_PREINVITE_STATUS_PENDING
    
    await query.edit_message_text(
        messages.MESSAGE_PREINVITE_DETAILS.format(
            telegram_id=telegram_id,
            added_by=added_by,
            notes=notes,
            created=escape_markdown(created),
            status=status
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_preinvite_details_keyboard(telegram_id)
    )
    return PREINVITE_VIEW


# ============================================================================
# Управление ручными пользователями
# ============================================================================

async def show_manual_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню управления ручными пользователями."""
    await update.message.reply_text(
        messages.MESSAGE_MANUAL_USERS_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_manual_users_keyboard()
    )
    return MANUAL_USERS_MENU


async def show_manual_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать список ручных пользователей."""
    users = invites_module.get_manual_users(limit=50)
    total = invites_module.get_manual_user_count()
    
    if not users:
        await update.message.reply_text(
            messages.MESSAGE_MANUAL_USERS_NO_USERS,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_manual_users_keyboard()
        )
        return MANUAL_USERS_MENU
    
    # Собираем инлайн-клавиатуру с пользователями
    keyboard = []
    for user in users:
        # Формируем отображаемое имя
        name_parts = []
        if user.get('first_name'):
            name_parts.append(user['first_name'])
        if user.get('last_name'):
            name_parts.append(user['last_name'])
        display_name = " ".join(name_parts) if name_parts else f"ID: {user['telegram_id']}"
        
        keyboard.append([
            InlineKeyboardButton(
                f"👤 {display_name}",
                callback_data=f"bot_admin_manual_view_{user['telegram_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_manual_menu")])
    
    await update.message.reply_text(
        messages.MESSAGE_MANUAL_USERS_LIST.format(total=total),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return MANUAL_USERS_LIST


async def start_add_manual_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать добавление нового ручного пользователя."""
    context.user_data['new_manual_user'] = {}
    
    await update.message.reply_text(
        messages.MESSAGE_MANUAL_USER_ADD,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_manual_users_keyboard()
    )
    return MANUAL_USER_ADD_ID


async def receive_manual_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принять Telegram ID для нового ручного пользователя."""
    text = update.message.text.strip()
    
    # Обрабатываем кнопки меню
    if text in ["🔙 Админ бота", BUTTON_MAIN_MENU, "📋 Список ручных пользователей"]:
        context.user_data.pop('new_manual_user', None)
        return await admin_menu_handler(update, context)
    
    try:
        telegram_id = int(text)
    except ValueError:
        await update.message.reply_text(
            messages.MESSAGE_MANUAL_USER_INVALID_ID,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return MANUAL_USER_ADD_ID
    
    if invites_module.check_if_user_manual(telegram_id):
        await update.message.reply_text(
            messages.MESSAGE_MANUAL_USER_EXISTS.format(telegram_id=telegram_id),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_manual_users_keyboard()
        )
        context.user_data.pop('new_manual_user', None)
        return MANUAL_USERS_MENU
    
    context.user_data['new_manual_user']['telegram_id'] = telegram_id
    
    await update.message.reply_text(
        messages.MESSAGE_MANUAL_USER_ADD_NOTES,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return MANUAL_USER_ADD_NOTES


async def receive_manual_user_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принять заметки и завершить добавление ручного пользователя."""
    text = update.message.text.strip()
    
    # Обрабатываем кнопки меню
    if text in ["🔙 Админ бота", BUTTON_MAIN_MENU, "📋 Список ручных пользователей"]:
        context.user_data.pop('new_manual_user', None)
        return await admin_menu_handler(update, context)
    
    user_data = context.user_data.get('new_manual_user', {})
    telegram_id = user_data.get('telegram_id')
    
    if not telegram_id:
        await update.message.reply_text(
            messages.MESSAGE_ERROR,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_manual_users_keyboard()
        )
        return MANUAL_USERS_MENU
    
    notes = None if text == "-" else text
    
    try:
        success = invites_module.add_manual_user(
            telegram_id=telegram_id,
            added_by_userid=update.effective_user.id,
            notes=notes
        )
        
        if success:
            await update.message.reply_text(
                messages.MESSAGE_MANUAL_USER_ADDED.format(telegram_id=telegram_id),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboards.get_manual_users_keyboard()
            )
        else:
            await update.message.reply_text(
                messages.MESSAGE_MANUAL_USER_EXISTS.format(telegram_id=telegram_id),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboards.get_manual_users_keyboard()
            )
    except Exception as e:
        logger.error(f"Error adding manual user: {e}", exc_info=True)
        await update.message.reply_text(
            messages.MESSAGE_ERROR,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_manual_users_keyboard()
        )
    
    context.user_data.pop('new_manual_user', None)
    return MANUAL_USERS_MENU


async def show_manual_user_details_callback(query, context: ContextTypes.DEFAULT_TYPE, telegram_id: int) -> int:
    """Показать детали ручного пользователя."""
    user = invites_module.get_manual_user_details(telegram_id)
    
    if not user:
        await query.edit_message_text(
            messages.MESSAGE_USER_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return MANUAL_USERS_LIST
    
    # Форматируем детали
    first_name = escape_markdown(user['first_name']) if user.get('first_name') else "Не указано"
    last_name = escape_markdown(user['last_name']) if user.get('last_name') else "Не указана"
    username = f"@{user['username']}" if user.get('username') else "Не указан"
    added_by = f"#{user['added_by_userid']}" if user['added_by_userid'] else "Неизвестно"
    notes = escape_markdown(user['notes']) if user.get('notes') else "Нет"
    created = datetime.fromtimestamp(user['created_timestamp']).strftime("%Y-%m-%d %H:%M")
    
    await query.edit_message_text(
        messages.MESSAGE_MANUAL_USER_DETAILS.format(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
            added_by=escape_markdown(added_by),
            notes=notes,
            created=escape_markdown(created)
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_manual_user_details_keyboard(telegram_id)
    )
    return MANUAL_USER_VIEW


# ============================================================================
# Статистика
# ============================================================================

async def show_statistics_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню статистики."""
    await update.message.reply_text(
        messages.MESSAGE_STATISTICS_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_statistics_keyboard()
    )
    return STATISTICS_MENU


async def show_general_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать общую статистику бота."""
    try:
        stats = get_bot_statistics()
        
        await update.message.reply_text(
            messages.MESSAGE_GENERAL_STATISTICS.format(**stats),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_statistics_keyboard()
        )
    except Exception as e:
        logger.error(f"Error getting statistics: {e}", exc_info=True)
        await update.message.reply_text(
            messages.MESSAGE_ERROR,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_statistics_keyboard()
        )
    
    return STATISTICS_MENU


# ============================================================================
# Управление инвайтами
# ============================================================================

async def show_invite_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню управления инвайтами."""
    await update.message.reply_text(
        messages.MESSAGE_INVITE_MANAGEMENT_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_invite_management_keyboard()
    )
    return INVITE_MENU


async def show_invite_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать статистику инвайтов."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM invites")
            total = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as used FROM invites WHERE consumed_userid IS NOT NULL")
            used = cursor.fetchone()['used']
    
    await update.message.reply_text(
        messages.MESSAGE_INVITE_LIST.format(
            total=total,
            used=used,
            available=total - used,
            page=1,
            total_pages=1
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_invite_management_keyboard()
    )
    return INVITE_MENU


async def start_issue_invites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начать выдачу инвайтов пользователю."""
    await update.message.reply_text(
        messages.MESSAGE_INVITE_ISSUE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_invite_management_keyboard()
    )
    return INVITE_ISSUE_USER


async def receive_invite_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принять ID пользователя для выдачи инвайтов."""
    text = update.message.text.strip()
    
    # Обрабатываем кнопки меню
    if text in ["🔙 Админ бота", BUTTON_MAIN_MENU, "📋 Все инвайты"]:
        return await admin_menu_handler(update, context)
    
    try:
        user_id = int(text)
    except ValueError:
        await update.message.reply_text(
            messages.MESSAGE_INVALID_INPUT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return INVITE_ISSUE_USER
    
    # Проверяем, существует ли пользователь
    user = get_user_details(user_id)
    if not user:
        await update.message.reply_text(
            messages.MESSAGE_USER_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return INVITE_ISSUE_USER
    
    context.user_data['issue_invites_user'] = user_id
    
    await update.message.reply_text(
        messages.MESSAGE_INVITE_ISSUE_COUNT.format(user_id=user_id),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return INVITE_ISSUE_COUNT


async def receive_invite_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принять количество и выдать инвайты."""
    text = update.message.text.strip()
    
    # Обрабатываем кнопки меню
    if text in ["🔙 Админ бота", BUTTON_MAIN_MENU, "📋 Все инвайты"]:
        context.user_data.pop('issue_invites_user', None)
        return await admin_menu_handler(update, context)
    
    try:
        count = int(text)
        if count < 1 or count > 10:
            raise ValueError()
    except ValueError:
        await update.message.reply_text(
            messages.MESSAGE_INVITE_ISSUE_INVALID_COUNT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return INVITE_ISSUE_COUNT
    
    user_id = context.user_data.get('issue_invites_user')
    if not user_id:
        await update.message.reply_text(
            messages.MESSAGE_ERROR,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_invite_management_keyboard()
        )
        return INVITE_MENU
    
    # Выдаём инвайты
    for _ in range(count):
        invites_module.generate_invite_for_user(user_id)
    
    await update.message.reply_text(
        messages.MESSAGE_INVITES_ISSUED.format(user_id=user_id, count=count),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_invite_management_keyboard()
    )
    
    context.user_data.pop('issue_invites_user', None)
    return INVITE_MENU


# ============================================================================
# Настройки бота
# ============================================================================

async def show_bot_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать подменю настроек бота."""
    await update.message.reply_text(
        messages.MESSAGE_BOT_SETTINGS_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_bot_settings_keyboard()
    )
    return BOT_SETTINGS_MENU


async def show_invite_system_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать настройки инвайт-системы с кнопкой переключения."""
    is_enabled = bot_settings.is_invite_system_enabled()
    status = messages.MESSAGE_INVITE_SYSTEM_STATUS_ENABLED if is_enabled else messages.MESSAGE_INVITE_SYSTEM_STATUS_DISABLED
    
    await update.message.reply_text(
        messages.MESSAGE_INVITE_SYSTEM_SETTINGS.format(status=status),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_invite_system_toggle_keyboard(is_enabled)
    )
    return INVITE_SYSTEM_SETTINGS


async def toggle_invite_system(query, context: ContextTypes.DEFAULT_TYPE, enable: bool) -> int:
    """Включить или отключить инвайт-систему."""
    admin_id = query.from_user.id
    bot_settings.set_invite_system_enabled(enable, admin_id)
    
    if enable:
        message = messages.MESSAGE_INVITE_SYSTEM_ENABLED
    else:
        message = messages.MESSAGE_INVITE_SYSTEM_DISABLED
    
    await query.edit_message_text(
        message,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_invite_system_toggle_keyboard(enable)
    )
    return INVITE_SYSTEM_SETTINGS


async def show_ai_model_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню переключения модели DeepSeek."""
    del context
    current_classification_model = ai_settings.get_active_deepseek_model_for_classification()
    current_response_model = ai_settings.get_active_deepseek_model_for_response()
    html_splitter_enabled = ai_settings.is_rag_html_splitter_enabled()
    html_splitter_status = "✅ Включён" if html_splitter_enabled else "❌ Выключен"
    await update.message.reply_text(
        messages.MESSAGE_AI_MODEL_SETTINGS.format(
            classification_model=escape_markdown(current_classification_model),
            response_model=escape_markdown(current_response_model),
            html_splitter_status=escape_markdown(html_splitter_status),
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_ai_model_toggle_keyboard(
            current_classification_model,
            current_response_model,
            html_splitter_enabled,
        ),
    )
    return AI_MODEL_SETTINGS


async def switch_ai_model(query, model_name: str, target: str) -> int:
    """Переключить AI-модель для выбранного сценария через bot_settings."""
    normalized = ai_settings.normalize_deepseek_model(model_name)

    if target == "classification":
        setting_key = ai_settings.AI_DEEPSEEK_MODEL_CLASSIFICATION_SETTING_KEY
        target_label = "классификации"
    elif target == "response":
        setting_key = ai_settings.AI_DEEPSEEK_MODEL_RESPONSE_SETTING_KEY
        target_label = "ответов"
    else:
        setting_key = ai_settings.AI_DEEPSEEK_MODEL_RESPONSE_SETTING_KEY
        target_label = "ответов"

    bot_settings.set_setting(
        setting_key,
        normalized,
        updated_by=query.from_user.id,
    )

    # Сбрасываем singleton-роутер, чтобы новые инстансы брали актуальную конфигурацию.
    reset_ai_router()

    current_classification_model = ai_settings.get_active_deepseek_model_for_classification()
    current_response_model = ai_settings.get_active_deepseek_model_for_response()
    html_splitter_enabled = ai_settings.is_rag_html_splitter_enabled()

    await query.edit_message_text(
        messages.MESSAGE_AI_MODEL_SWITCHED.format(
            target=escape_markdown(target_label),
            model=escape_markdown(normalized),
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_ai_model_toggle_keyboard(
            current_classification_model,
            current_response_model,
            html_splitter_enabled,
        ),
    )
    return AI_MODEL_SETTINGS


async def toggle_ai_html_splitter(query, enable: bool) -> int:
    """Включить или отключить HTML header-splitter для RAG через bot_settings."""
    bot_settings.set_setting(
        ai_settings.AI_RAG_HTML_SPLITTER_ENABLED_SETTING_KEY,
        "1" if enable else "0",
        updated_by=query.from_user.id,
    )

    current_classification_model = ai_settings.get_active_deepseek_model_for_classification()
    current_response_model = ai_settings.get_active_deepseek_model_for_response()
    html_splitter_enabled = ai_settings.is_rag_html_splitter_enabled()

    await query.edit_message_text(
        messages.MESSAGE_AI_HTML_SPLITTER_SWITCHED.format(
            status=escape_markdown("включён" if enable else "выключен"),
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_ai_model_toggle_keyboard(
            current_classification_model,
            current_response_model,
            html_splitter_enabled,
        ),
    )
    return AI_MODEL_SETTINGS


# ============================================================================
# Управление модулями
# ============================================================================

def get_modules_status_text() -> str:
    """Сформировать текст статусов для всех модулей."""
    from src.common.bot_settings import MODULE_NAMES
    
    module_states = bot_settings.get_all_module_states()
    lines = []
    for module_key, is_enabled in module_states.items():
        module_name = MODULE_NAMES.get(module_key, module_key)
        status = "✅" if is_enabled else "❌"
        lines.append(f"{status} {escape_markdown(module_name)}")
    return "\n".join(lines)


async def show_modules_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать меню управления модулями с кнопками переключения."""
    module_states = bot_settings.get_all_module_states()
    modules_status = get_modules_status_text()
    
    await update.message.reply_text(
        messages.MESSAGE_MODULES_MANAGEMENT_MENU.format(modules_status=modules_status),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_modules_toggle_keyboard(module_states)
    )
    return MODULES_MANAGEMENT_MENU


async def toggle_module(query, context: ContextTypes.DEFAULT_TYPE, module_key: str, enable: bool) -> int:
    """Включить или выключить конкретный модуль."""
    from src.common.bot_settings import MODULE_NAMES
    
    admin_id = query.from_user.id
    bot_settings.set_module_enabled(module_key, enable, admin_id)
    
    module_name = MODULE_NAMES.get(module_key, module_key)
    
    if enable:
        message = messages.MESSAGE_MODULE_ENABLED.format(module_name=escape_markdown(module_name))
    else:
        message = messages.MESSAGE_MODULE_DISABLED.format(module_name=escape_markdown(module_name))
    
    # Обновляем клавиатуру с новыми состояниями
    module_states = bot_settings.get_all_module_states()
    
    await query.edit_message_text(
        message,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_modules_toggle_keyboard(module_states)
    )
    return MODULES_MANAGEMENT_MENU


# ============================================================================
# Плановые работы
# ============================================================================

def _format_outage_label(outage) -> str:
    date_text = outage.outage_date.strftime("%d.%m.%Y")
    window = OUTAGE_TYPE_LABELS.get(outage.outage_type, outage.outage_type)
    return f"{date_text} — {window}"


async def show_planned_outages_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать подменю плановых работ."""
    await update.message.reply_text(
        messages.MESSAGE_PLANNED_OUTAGES_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_planned_outages_keyboard()
    )
    return PLANNED_OUTAGES_MENU


async def show_planned_outages_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать список плановых работ с возможностью удаления."""
    outages = list_planned_outages(limit=40, include_past=False)
    if not outages:
        await update.message.reply_text(
            messages.MESSAGE_PLANNED_OUTAGES_EMPTY,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_planned_outages_keyboard()
        )
        return PLANNED_OUTAGES_MENU

    keyboard = []
    for outage in outages:
        label = _format_outage_label(outage)
        keyboard.append([
            InlineKeyboardButton(
                f"🗑️ {label}",
                callback_data=f"bot_admin_outage_delete_{outage.outage_id}"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_planned_outages_menu")])

    await update.message.reply_text(
        messages.MESSAGE_PLANNED_OUTAGES_LIST,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PLANNED_OUTAGES_LIST


async def start_add_planned_outage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запросить дату плановых работ."""
    await update.message.reply_text(
        messages.MESSAGE_PLANNED_OUTAGE_ADD_DATE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_planned_outages_keyboard()
    )
    return PLANNED_OUTAGE_ADD_DATE


async def receive_planned_outage_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принять дату плановых работ."""
    text = update.message.text.strip()
    if text in [settings.BUTTON_BACK_SETTINGS, BUTTON_MAIN_MENU, settings.BUTTON_OUTAGE_LIST, settings.BUTTON_OUTAGE_ADD]:
        return await admin_menu_handler(update, context)
    try:
        outage_date = datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(
            messages.MESSAGE_PLANNED_OUTAGE_INVALID_DATE,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_planned_outages_keyboard()
        )
        return PLANNED_OUTAGE_ADD_DATE

    context.user_data["planned_outage_date"] = outage_date
    await update.message.reply_text(
        messages.MESSAGE_PLANNED_OUTAGE_SELECT_TYPE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_planned_outage_type_keyboard()
    )
    return PLANNED_OUTAGE_ADD_TYPE


async def receive_planned_outage_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Принять тип плановых работ и сохранить запись."""
    text = update.message.text.strip()
    if text in [settings.BUTTON_BACK_SETTINGS, BUTTON_MAIN_MENU]:
        return await admin_menu_handler(update, context)

    outage_date = context.user_data.get("planned_outage_date")
    if not outage_date:
        await update.message.reply_text(
            messages.MESSAGE_ERROR,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_planned_outages_keyboard()
        )
        return PLANNED_OUTAGES_MENU

    type_map = {
        settings.BUTTON_OUTAGE_TYPE_BLUE_SHORT: OUTAGE_TYPE_BLUE_SHORT,
        settings.BUTTON_OUTAGE_TYPE_BLUE_LONG: OUTAGE_TYPE_BLUE_LONG,
        settings.BUTTON_OUTAGE_TYPE_RED: OUTAGE_TYPE_RED,
    }
    outage_type = type_map.get(text)
    if not outage_type:
        await update.message.reply_text(
            messages.MESSAGE_INVALID_INPUT,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_planned_outage_type_keyboard()
        )
        return PLANNED_OUTAGE_ADD_TYPE

    create_planned_outage(outage_date, outage_type, update.effective_user.id)
    window = OUTAGE_TYPE_LABELS.get(outage_type, outage_type)
    await update.message.reply_text(
        messages.MESSAGE_PLANNED_OUTAGE_ADDED.format(
            date=outage_date.strftime("%d.%m.%Y"),
            window=window,
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_planned_outages_keyboard()
    )
    context.user_data.pop("planned_outage_date", None)
    return PLANNED_OUTAGES_MENU


# ============================================================================
# Обработчик колбэков
# ============================================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать все колбэки инлайн-кнопок."""
    query = update.callback_query
    await query.answer()

    # Повторная проверка admin-прав в callback-ветках (защита от stale-клавиатур)
    if not check_if_user_admin(query.from_user.id):
        await query.message.reply_text(
            "⛔ Доступ запрещён\\. Вы больше не являетесь администратором\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
        )
        return ConversationHandler.END
    
    data = query.data
    
    # Навигационные колбэки
    if data == "bot_admin_noop":
        return None
    
    if data == "bot_admin_menu":
        await query.message.reply_text(
            messages.MESSAGE_BOT_ADMIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    
    if data == "bot_admin_user_menu":
        await query.message.reply_text(
            messages.MESSAGE_USER_MANAGEMENT_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_user_management_keyboard()
        )
        return USER_MANAGEMENT_MENU
    
    if data == "bot_admin_user_list":
        # Обновляем список пользователей через колбэк
        users, total, total_pages = get_users_list(page=1, limit=settings.USERS_PER_PAGE)
        keyboard = []
        for user in users:
            status = "👑" if user['is_admin'] else "👤"
            name = user['first_name'] or "Без имени"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {name}",
                    callback_data=f"bot_admin_user_view_{user['userid']}"
                )
            ])
        if total_pages > 1:
            keyboard.append(keyboards.get_pagination_keyboard(1, total_pages, "bot_admin_users"))
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_user_menu")])
        
        await query.edit_message_text(
            messages.MESSAGE_USER_LIST.format(total=total, page=1, total_pages=total_pages),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return USER_LIST
    
    # Пагинация пользователей
    if data.startswith("bot_admin_users_page_"):
        page = int(data.replace("bot_admin_users_page_", ""))
        users, total, total_pages = get_users_list(page=page, limit=settings.USERS_PER_PAGE)
        keyboard = []
        for user in users:
            status = "👑" if user['is_admin'] else "👤"
            name = user['first_name'] or "Без имени"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {name}",
                    callback_data=f"bot_admin_user_view_{user['userid']}"
                )
            ])
        if total_pages > 1:
            keyboard.append(keyboards.get_pagination_keyboard(page, total_pages, "bot_admin_users"))
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_user_menu")])
        
        await query.edit_message_text(
            messages.MESSAGE_USER_LIST.format(total=total, page=page, total_pages=total_pages),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return USER_LIST
    
    # Просмотр пользователя
    if data.startswith("bot_admin_user_view_"):
        user_id = int(data.replace("bot_admin_user_view_", ""))
        return await show_user_details_callback(query, context, user_id)
    
    # Назначение/снятие админа
    if data.startswith("bot_admin_grant_"):
        user_id = int(data.replace("bot_admin_grant_", ""))
        await query.edit_message_text(
            f"⚠️ Вы уверены, что хотите назначить пользователя *{user_id}* администратором?",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_confirm_admin_action_keyboard(user_id, "grant")
        )
        return CONFIRM_ADMIN_ACTION
    
    if data.startswith("bot_admin_revoke_"):
        user_id = int(data.replace("bot_admin_revoke_", ""))
        if user_id == query.from_user.id:
            await query.answer(messages.MESSAGE_CANNOT_REVOKE_SELF.replace("\\", ""), show_alert=True)
            return USER_VIEW
        await query.edit_message_text(
            f"⚠️ Вы уверены, что хотите отозвать права администратора у пользователя *{user_id}*?",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_confirm_admin_action_keyboard(user_id, "revoke")
        )
        return CONFIRM_ADMIN_ACTION
    
    if data.startswith("bot_admin_confirm_grant_"):
        user_id = int(data.replace("bot_admin_confirm_grant_", ""))
        set_user_admin(user_id, True)
        await query.edit_message_text(
            messages.MESSAGE_USER_ADMIN_GRANTED.format(user_id=user_id),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return await show_user_details_callback(query, context, user_id)
    
    if data.startswith("bot_admin_confirm_revoke_"):
        user_id = int(data.replace("bot_admin_confirm_revoke_", ""))
        set_user_admin(user_id, False)
        await query.edit_message_text(
            messages.MESSAGE_USER_ADMIN_REVOKED.format(user_id=user_id),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return await show_user_details_callback(query, context, user_id)
    
    # Выдача инвайтов из карточки пользователя
    if data.startswith("bot_admin_issue_invites_"):
        user_id = int(data.replace("bot_admin_issue_invites_", ""))
        context.user_data['issue_invites_user'] = user_id
        await query.message.reply_text(
            messages.MESSAGE_INVITE_ISSUE_COUNT.format(user_id=user_id),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_invite_management_keyboard()
        )
        return INVITE_ISSUE_COUNT
    
    # Колбэки пред-инвайтов
    if data == "bot_admin_preinvite_menu":
        await query.message.reply_text(
            messages.MESSAGE_PREINVITE_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_preinvite_keyboard()
        )
        return PREINVITE_MENU
    
    if data == "bot_admin_preinvite_list":
        # Обновляем список через колбэк
        users = invites_module.get_pre_invited_users(include_activated=True, limit=50)
        total = invites_module.get_pre_invited_user_count(include_activated=True)
        activated = total - invites_module.get_pre_invited_user_count(include_activated=False)
        pending = total - activated
        
        keyboard = []
        for user in users:
            status = "✅" if user['activated_timestamp'] else "⏳"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {user['telegram_id']}",
                    callback_data=f"bot_admin_preinvite_view_{user['telegram_id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_preinvite_menu")])
        
        await query.edit_message_text(
            messages.MESSAGE_PREINVITE_LIST.format(total=total, activated=activated, pending=pending),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return PREINVITE_LIST
    
    if data.startswith("bot_admin_preinvite_view_"):
        telegram_id = int(data.replace("bot_admin_preinvite_view_", ""))
        return await show_preinvite_details_callback(query, context, telegram_id)
    
    if data.startswith("bot_admin_preinvite_delete_"):
        telegram_id = int(data.replace("bot_admin_preinvite_delete_", ""))
        await query.edit_message_text(
            messages.MESSAGE_PREINVITE_CONFIRM_DELETE.format(telegram_id=telegram_id),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_confirm_delete_preinvite_keyboard(telegram_id)
        )
        return PREINVITE_CONFIRM_DELETE
    
    if data.startswith("bot_admin_preinvite_confirm_delete_"):
        telegram_id = int(data.replace("bot_admin_preinvite_confirm_delete_", ""))
        invites_module.remove_pre_invited_user(telegram_id)
        await query.edit_message_text(
            messages.MESSAGE_PREINVITE_DELETED.format(telegram_id=telegram_id),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return PREINVITE_MENU
    
    if data == "bot_admin_preinvite_cancel_delete":
        await query.edit_message_text(
            messages.MESSAGE_OPERATION_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return PREINVITE_MENU
    
    # Колбэки ручных пользователей
    if data == "bot_admin_manual_menu":
        await query.message.reply_text(
            messages.MESSAGE_MANUAL_USERS_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_manual_users_keyboard()
        )
        return MANUAL_USERS_MENU
    
    if data == "bot_admin_manual_list":
        # Обновляем список через колбэк
        users = invites_module.get_manual_users(limit=50)
        total = invites_module.get_manual_user_count()
        
        if not users:
            await query.edit_message_text(
                messages.MESSAGE_MANUAL_USERS_NO_USERS,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return MANUAL_USERS_MENU
        
        keyboard = []
        for user in users:
            # Формируем отображаемое имя
            name_parts = []
            if user.get('first_name'):
                name_parts.append(user['first_name'])
            if user.get('last_name'):
                name_parts.append(user['last_name'])
            display_name = " ".join(name_parts) if name_parts else f"ID: {user['telegram_id']}"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"👤 {display_name}",
                    callback_data=f"bot_admin_manual_view_{user['telegram_id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="bot_admin_manual_menu")])
        
        await query.edit_message_text(
            messages.MESSAGE_MANUAL_USERS_LIST.format(total=total),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MANUAL_USERS_LIST
    
    if data.startswith("bot_admin_manual_view_"):
        telegram_id = int(data.replace("bot_admin_manual_view_", ""))
        return await show_manual_user_details_callback(query, context, telegram_id)
    
    if data.startswith("bot_admin_manual_delete_"):
        telegram_id = int(data.replace("bot_admin_manual_delete_", ""))
        await query.edit_message_text(
            messages.MESSAGE_MANUAL_USER_CONFIRM_DELETE.format(telegram_id=telegram_id),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_confirm_delete_manual_user_keyboard(telegram_id)
        )
        return MANUAL_USER_CONFIRM_DELETE
    
    if data.startswith("bot_admin_manual_confirm_delete_"):
        telegram_id = int(data.replace("bot_admin_manual_confirm_delete_", ""))
        invites_module.remove_manual_user(telegram_id)
        await query.edit_message_text(
            messages.MESSAGE_MANUAL_USER_DELETED.format(telegram_id=telegram_id),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return MANUAL_USERS_MENU
    
    if data == "bot_admin_manual_cancel_delete":
        await query.edit_message_text(
            messages.MESSAGE_OPERATION_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return MANUAL_USERS_MENU
    
    # Колбэки настроек бота
    if data == "bot_admin_settings_menu":
        await query.message.reply_text(
            messages.MESSAGE_BOT_SETTINGS_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_bot_settings_keyboard()
        )
        return BOT_SETTINGS_MENU

    if data == "bot_admin_planned_outages_menu":
        await query.message.reply_text(
            messages.MESSAGE_PLANNED_OUTAGES_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_planned_outages_keyboard()
        )
        return PLANNED_OUTAGES_MENU
    
    if data == "bot_admin_invite_system_enable":
        return await toggle_invite_system(query, context, True)
    
    if data == "bot_admin_invite_system_disable":
        return await toggle_invite_system(query, context, False)

    if data == "bot_admin_ai_model_class_chat":
        return await switch_ai_model(query, ai_settings.DEEPSEEK_MODEL_CHAT, "classification")

    if data == "bot_admin_ai_model_class_reasoner":
        return await switch_ai_model(query, ai_settings.DEEPSEEK_MODEL_REASONER, "classification")

    if data == "bot_admin_ai_model_response_chat":
        return await switch_ai_model(query, ai_settings.DEEPSEEK_MODEL_CHAT, "response")

    if data == "bot_admin_ai_model_response_reasoner":
        return await switch_ai_model(query, ai_settings.DEEPSEEK_MODEL_REASONER, "response")

    if data == "bot_admin_ai_html_splitter_enable":
        return await toggle_ai_html_splitter(query, True)

    if data == "bot_admin_ai_html_splitter_disable":
        return await toggle_ai_html_splitter(query, False)
    
    # Колбэки управления модулями
    if data.startswith("bot_admin_module_enable_"):
        module_key = data.replace("bot_admin_module_enable_", "")
        return await toggle_module(query, context, module_key, True)
    
    if data.startswith("bot_admin_module_disable_"):
        module_key = data.replace("bot_admin_module_disable_", "")
        return await toggle_module(query, context, module_key, False)

    # Колбэки плановых работ
    if data.startswith("bot_admin_outage_delete_"):
        outage_id = int(data.replace("bot_admin_outage_delete_", ""))
        outage = get_planned_outage_by_id(outage_id)
        if not outage:
            await query.edit_message_text(
                messages.MESSAGE_ERROR,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return PLANNED_OUTAGES_MENU
        label = _format_outage_label(outage)
        date_text, window = label.split(" — ")
        await query.edit_message_text(
            messages.MESSAGE_PLANNED_OUTAGE_CONFIRM_DELETE.format(date=date_text, window=window),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_confirm_delete_outage_keyboard(outage_id)
        )
        return PLANNED_OUTAGE_CONFIRM_DELETE

    if data.startswith("bot_admin_outage_confirm_delete_"):
        outage_id = int(data.replace("bot_admin_outage_confirm_delete_", ""))
        delete_planned_outage(outage_id)
        await query.edit_message_text(
            messages.MESSAGE_PLANNED_OUTAGE_DELETED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return PLANNED_OUTAGES_MENU

    if data == "bot_admin_outage_cancel_delete":
        await query.edit_message_text(
            messages.MESSAGE_OPERATION_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return PLANNED_OUTAGES_MENU
    
    return None


# ============================================================================
# Обработчик отмены
# ============================================================================

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменить админский диалог."""
    context.user_data.pop('new_preinvite', None)
    context.user_data.pop('issue_invites_user', None)
    
    if update.message and update.message.text == BUTTON_MAIN_MENU:
        await update.message.reply_text(
            get_main_menu_message(update.effective_user.id, update.effective_user.first_name),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=check_if_user_admin(update.effective_user.id))
        )
    else:
        await update.message.reply_text(
            messages.MESSAGE_OPERATION_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=check_if_user_admin(update.effective_user.id))
        )
    return ConversationHandler.END


# ============================================================================
# Сборка ConversationHandler
# ============================================================================

def get_admin_conversation_handler() -> ConversationHandler:
    """Собрать и вернуть ConversationHandler для админ-панели бота."""
    
    menu_buttons_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler)
    
    return ConversationHandler(
        entry_points=[
            CommandHandler("botadmin", bot_admin_command),
            MessageHandler(filters.Regex("^🛠️ Админ бота$"), bot_admin_command),
        ],
        states={
            ADMIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_callback)
            ],
            # Состояния управления пользователями
            USER_MANAGEMENT_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_callback)
            ],
            USER_LIST: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            USER_VIEW: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            USER_SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_search)
            ],
            USER_SEARCH_RESULTS: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            ADMIN_LIST: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            CONFIRM_ADMIN_ACTION: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            # Состояния пред-инвайтов
            PREINVITE_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_callback)
            ],
            PREINVITE_LIST: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            PREINVITE_VIEW: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            PREINVITE_ADD_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_preinvite_id)
            ],
            PREINVITE_ADD_NOTES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_preinvite_notes)
            ],
            PREINVITE_CONFIRM_DELETE: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            # Состояния ручных пользователей
            MANUAL_USERS_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_callback)
            ],
            MANUAL_USERS_LIST: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            MANUAL_USER_VIEW: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            MANUAL_USER_ADD_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_manual_user_id)
            ],
            MANUAL_USER_ADD_NOTES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_manual_user_notes)
            ],
            MANUAL_USER_CONFIRM_DELETE: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            # Состояния статистики
            STATISTICS_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_callback)
            ],
            # Состояния управления инвайтами
            INVITE_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_callback)
            ],
            INVITE_LIST: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            INVITE_ISSUE_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_invite_user_id)
            ],
            INVITE_ISSUE_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_invite_count)
            ],
            # Состояния настроек бота
            BOT_SETTINGS_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_callback)
            ],
            INVITE_SYSTEM_SETTINGS: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            AI_MODEL_SETTINGS: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            # Состояния управления модулями
            MODULES_MANAGEMENT_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_callback)
            ],
            # Состояния плановых работ
            PLANNED_OUTAGES_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_callback)
            ],
            PLANNED_OUTAGES_LIST: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
            PLANNED_OUTAGE_ADD_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_planned_outage_date)
            ],
            PLANNED_OUTAGE_ADD_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_planned_outage_type)
            ],
            PLANNED_OUTAGE_CONFIRM_DELETE: [
                CallbackQueryHandler(handle_callback),
                menu_buttons_handler
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_admin),
            CommandHandler("reset", cancel_admin),
            CommandHandler("menu", cancel_admin),
            MessageHandler(filters.Regex(f"^{re.escape(BUTTON_MAIN_MENU)}$"), cancel_admin),
            MessageHandler(filters.COMMAND, cancel_admin),  # Обрабатываем /start и другие команды
        ],
        name="bot_admin_panel",
        persistent=False
    )
