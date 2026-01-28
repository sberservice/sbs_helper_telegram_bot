"""
Bot Admin Module - Admin Bot Part

Telegram handlers for bot-wide administration:
- User management (list, search, view, admin grant/revoke)
- Pre-invite management
- Statistics
- Invite management
"""

import logging
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
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE, MESSAGE_MAIN_MENU, get_main_menu_keyboard
from src.common import invites as invites_module
from src.common import database

from . import settings
from . import messages
from . import keyboards

logger = logging.getLogger(__name__)

# Conversation states
(
    ADMIN_MENU,
    # User management states
    USER_MANAGEMENT_MENU,
    USER_LIST,
    USER_VIEW,
    USER_SEARCH,
    USER_SEARCH_RESULTS,
    ADMIN_LIST,
    CONFIRM_ADMIN_ACTION,
    # Pre-invite states
    PREINVITE_MENU,
    PREINVITE_LIST,
    PREINVITE_VIEW,
    PREINVITE_ADD_ID,
    PREINVITE_ADD_NOTES,
    PREINVITE_CONFIRM_DELETE,
    # Statistics states
    STATISTICS_MENU,
    # Invite management states
    INVITE_MENU,
    INVITE_LIST,
    INVITE_ISSUE_USER,
    INVITE_ISSUE_COUNT,
) = range(19)


# ============================================================================
# Helper Functions
# ============================================================================

def escape_markdown(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    if text is None:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = str(text).replace(char, f'\\{char}')
    return text


def get_users_list(page: int = 1, limit: int = 10) -> tuple:
    """Get paginated list of users from database."""
    offset = (page - 1) * limit
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Get total count
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total = cursor.fetchone()['count']
            
            # Get users for current page
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
    """Get detailed user information."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Get user info
            cursor.execute("""
                SELECT userid, first_name, last_name, username, timestamp, is_admin
                FROM users WHERE userid = %s
            """, (user_id,))
            user = cursor.fetchone()
            
            if not user:
                return None
            
            # Get invites statistics
            cursor.execute("""
                SELECT COUNT(*) as issued FROM invites WHERE userid = %s
            """, (user_id,))
            invites_issued = cursor.fetchone()['issued']
            
            cursor.execute("""
                SELECT COUNT(*) as used FROM invites WHERE userid = %s AND consumed_userid IS NOT NULL
            """, (user_id,))
            invites_used = cursor.fetchone()['used']
            
            # Get who invited this user
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
    """Search users by ID, username, or name."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Try exact ID match first
            if query.isdigit():
                cursor.execute("""
                    SELECT userid, first_name, last_name, username, is_admin
                    FROM users WHERE userid = %s
                """, (int(query),))
                result = cursor.fetchone()
                if result:
                    return [result]
            
            # Search by name/username
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
    """Get list of all admin users."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("""
                SELECT userid, first_name, last_name, username
                FROM users WHERE is_admin = 1
                ORDER BY first_name
            """)
            return cursor.fetchall()


def get_bot_statistics() -> dict:
    """Get overall bot statistics."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # User stats
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_admin = 1")
            admin_count = cursor.fetchone()['count']
            
            # Invite stats
            cursor.execute("SELECT COUNT(*) as count FROM invites")
            total_invites = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM invites WHERE consumed_userid IS NOT NULL")
            used_invites = cursor.fetchone()['count']
            
            # Pre-invite stats
            total_preinvites = invites_module.get_pre_invited_user_count(include_activated=True)
            activated_preinvites = invites_module.get_pre_invited_user_count(include_activated=True) - \
                                   invites_module.get_pre_invited_user_count(include_activated=False)
            
            # Monthly stats (last 30 days)
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


# ============================================================================
# Entry Point and Main Menu
# ============================================================================

async def bot_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /botadmin command or 🛠️ Админ бота button."""
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
    """Handle admin menu button presses."""
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
    elif text == "🏠 Главное меню":
        await update.message.reply_text(
            MESSAGE_MAIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    # User management menu handlers
    elif text == "📋 Список пользователей":
        return await show_user_list(update, context)
    elif text == "🔍 Поиск пользователя":
        return await start_user_search(update, context)
    elif text == "👑 Список админов":
        return await show_admin_list(update, context)
    
    # Pre-invite menu handlers
    elif text == "📋 Список пре-инвайтов":
        return await show_preinvite_list(update, context)
    elif text == "➕ Добавить пользователя":
        return await start_add_preinvite(update, context)
    
    # Statistics handlers
    elif text == "📈 Общая статистика":
        return await show_general_statistics(update, context)
    elif text == "📅 Статистика за период":
        return await show_general_statistics(update, context)  # Same for now
    
    # Invite management handlers
    elif text == "📋 Все инвайты":
        return await show_invite_list(update, context)
    elif text == "🎁 Выдать инвайты":
        return await start_issue_invites(update, context)
    
    return ADMIN_MENU


# ============================================================================
# User Management
# ============================================================================

async def show_user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show user management submenu."""
    await update.message.reply_text(
        messages.MESSAGE_USER_MANAGEMENT_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_user_management_keyboard()
    )
    return USER_MANAGEMENT_MENU


async def show_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> int:
    """Show paginated list of users."""
    users, total, total_pages = get_users_list(page=page, limit=settings.USERS_PER_PAGE)
    
    if not users:
        await update.message.reply_text(
            "⚠️ Пользователи не найдены\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_user_management_keyboard()
        )
        return USER_MANAGEMENT_MENU
    
    # Build inline keyboard with users
    keyboard = []
    for user in users:
        status = "👑" if user['is_admin'] else "👤"
        name = user['first_name'] or "Без имени"
        username = f"@{user['username']}" if user['username'] else ""
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {name} {username}",
                callback_data=f"bot_admin_user_view_{user['userid']}"
            )
        ])
    
    # Add pagination
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
    """Start user search process."""
    await update.message.reply_text(
        messages.MESSAGE_USER_SEARCH,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_user_management_keyboard()
    )
    return USER_SEARCH


async def receive_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user search query."""
    query = update.message.text.strip()
    
    # Handle menu buttons
    if query in ["🔙 Админ бота", "🏠 Главное меню", "📋 Список пользователей", "👑 Список админов"]:
        return await admin_menu_handler(update, context)
    
    users = search_users(query)
    
    if not users:
        await update.message.reply_text(
            messages.MESSAGE_USER_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_user_management_keyboard()
        )
        return USER_MANAGEMENT_MENU
    
    # Build inline keyboard with results
    keyboard = []
    for user in users:
        status = "👑" if user['is_admin'] else "👤"
        name = user['first_name'] or "Без имени"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {name} ({user['userid']})",
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
    """Show list of admin users."""
    admins = get_admin_list()
    
    if not admins:
        await update.message.reply_text(
            "⚠️ Администраторы не найдены\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_user_management_keyboard()
        )
        return USER_MANAGEMENT_MENU
    
    # Build inline keyboard with admins
    keyboard = []
    for admin in admins:
        name = admin['first_name'] or "Без имени"
        username = f"@{admin['username']}" if admin['username'] else ""
        keyboard.append([
            InlineKeyboardButton(
                f"👑 {name} {username}",
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
    """Show detailed user information."""
    user = get_user_details(user_id)
    
    if not user:
        await query.edit_message_text(
            messages.MESSAGE_USER_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return USER_LIST
    
    # Format user details
    registered = datetime.fromtimestamp(user['timestamp']).strftime("%Y-%m-%d %H:%M")
    
    # Check if user has pre-invite
    is_preinvited = invites_module.check_if_user_pre_invited(user_id)
    status_parts = []
    if invites_module.check_if_user_pre_invited(user_id):
        if invites_module.is_pre_invited_user_activated(user_id):
            status_parts.append("Пре-инвайт (активирован)")
        else:
            status_parts.append("Пре-инвайт (ожидает)")
    
    # Check if has consumed invite
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute("SELECT COUNT(*) as c FROM invites WHERE consumed_userid = %s", (user_id,))
            if cursor.fetchone()['c'] > 0:
                status_parts.append("Инвайт")
    
    status = ", ".join(status_parts) if status_parts else "Активен"
    
    is_self = query.from_user.id == user_id
    
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
            invited_by=f"#{user['invited_by']}" if user['invited_by'] else "Самостоятельно/Пре-инвайт"
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_user_details_keyboard(user_id, user['is_admin'], is_self)
    )
    return USER_VIEW


# ============================================================================
# Pre-Invite Management
# ============================================================================

async def show_preinvite_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show pre-invite management menu."""
    await update.message.reply_text(
        messages.MESSAGE_PREINVITE_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_preinvite_keyboard()
    )
    return PREINVITE_MENU


async def show_preinvite_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show list of pre-invited users."""
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
    
    # Build inline keyboard with users
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
    """Start adding a new pre-invite."""
    context.user_data['new_preinvite'] = {}
    
    await update.message.reply_text(
        messages.MESSAGE_PREINVITE_ADD,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_preinvite_keyboard()
    )
    return PREINVITE_ADD_ID


async def receive_preinvite_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive Telegram ID for new pre-invite."""
    text = update.message.text.strip()
    
    # Handle menu buttons
    if text in ["🔙 Админ бота", "🏠 Главное меню", "📋 Список пре-инвайтов"]:
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
    """Receive notes and complete pre-invite addition."""
    text = update.message.text.strip()
    
    # Handle menu buttons
    if text in ["🔙 Админ бота", "🏠 Главное меню", "📋 Список пре-инвайтов"]:
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
    """Show pre-invite details."""
    users = invites_module.get_pre_invited_users(include_activated=True, limit=100)
    user = next((u for u in users if u['telegram_id'] == telegram_id), None)
    
    if not user:
        await query.edit_message_text(
            messages.MESSAGE_USER_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return PREINVITE_LIST
    
    # Format details
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
            added_by=escape_markdown(added_by),
            notes=notes,
            created=escape_markdown(created),
            status=status
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_preinvite_details_keyboard(telegram_id)
    )
    return PREINVITE_VIEW


# ============================================================================
# Statistics
# ============================================================================

async def show_statistics_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show statistics menu."""
    await update.message.reply_text(
        messages.MESSAGE_STATISTICS_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_statistics_keyboard()
    )
    return STATISTICS_MENU


async def show_general_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show general bot statistics."""
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
# Invite Management
# ============================================================================

async def show_invite_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show invite management menu."""
    await update.message.reply_text(
        messages.MESSAGE_INVITE_MANAGEMENT_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_invite_management_keyboard()
    )
    return INVITE_MENU


async def show_invite_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show invite statistics."""
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
    """Start the process of issuing invites to a user."""
    await update.message.reply_text(
        messages.MESSAGE_INVITE_ISSUE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_invite_management_keyboard()
    )
    return INVITE_ISSUE_USER


async def receive_invite_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive user ID for invite issuance."""
    text = update.message.text.strip()
    
    # Handle menu buttons
    if text in ["🔙 Админ бота", "🏠 Главное меню", "📋 Все инвайты"]:
        return await admin_menu_handler(update, context)
    
    try:
        user_id = int(text)
    except ValueError:
        await update.message.reply_text(
            messages.MESSAGE_INVALID_INPUT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return INVITE_ISSUE_USER
    
    # Check if user exists
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
    """Receive count and issue invites."""
    text = update.message.text.strip()
    
    # Handle menu buttons
    if text in ["🔙 Админ бота", "🏠 Главное меню", "📋 Все инвайты"]:
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
    
    # Issue invites
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
# Callback Handler
# ============================================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle all inline button callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Navigation callbacks
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
        # Refresh user list via callback
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
    
    # User pagination
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
    
    # User view
    if data.startswith("bot_admin_user_view_"):
        user_id = int(data.replace("bot_admin_user_view_", ""))
        return await show_user_details_callback(query, context, user_id)
    
    # Admin grant/revoke
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
    
    # Issue invites from user view
    if data.startswith("bot_admin_issue_invites_"):
        user_id = int(data.replace("bot_admin_issue_invites_", ""))
        context.user_data['issue_invites_user'] = user_id
        await query.message.reply_text(
            messages.MESSAGE_INVITE_ISSUE_COUNT.format(user_id=user_id),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_invite_management_keyboard()
        )
        return INVITE_ISSUE_COUNT
    
    # Pre-invite callbacks
    if data == "bot_admin_preinvite_menu":
        await query.message.reply_text(
            messages.MESSAGE_PREINVITE_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_preinvite_keyboard()
        )
        return PREINVITE_MENU
    
    if data == "bot_admin_preinvite_list":
        # Refresh list via callback
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
    
    return None


# ============================================================================
# Cancel Handler
# ============================================================================

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel admin conversation."""
    context.user_data.pop('new_preinvite', None)
    context.user_data.pop('issue_invites_user', None)
    
    await update.message.reply_text(
        messages.MESSAGE_OPERATION_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


# ============================================================================
# Conversation Handler Builder
# ============================================================================

def get_admin_conversation_handler() -> ConversationHandler:
    """Build and return the bot admin ConversationHandler."""
    
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
            # User management states
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
            # Pre-invite states
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
            # Statistics states
            STATISTICS_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_callback)
            ],
            # Invite management states
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
        },
        fallbacks=[
            CommandHandler("cancel", cancel_admin),
            MessageHandler(filters.Regex("^🏠 Главное меню$"), cancel_admin)
        ],
        name="bot_admin_panel",
        persistent=False
    )
