"""
Gamification Admin Panel Bot Part

Admin handlers for the gamification system:
- View user profiles
- Configure score values
- View all achievements
- System statistics
"""

import logging

from telegram import Update, constants
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

from src.common.telegram_user import check_if_user_admin
from src.common.messages import get_main_menu_keyboard

from . import settings
from . import messages
from . import keyboards
from . import gamification_logic
from .gamification_bot_part import return_to_submenu, return_to_main_menu

logger = logging.getLogger(__name__)


# ===== ENTRY POINT =====

async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for admin panel."""
    user = update.effective_user
    
    if not check_if_user_admin(user.id):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_NOT_AUTHORIZED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_SUBMENU
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_MENU,
        reply_markup=keyboards.get_admin_menu_keyboard(),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_ADMIN_MENU


# ===== PROFILE SEARCH =====

async def admin_find_profile_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show prompt for finding user profile."""
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_ENTER_USERID,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_ADMIN_FIND_PROFILE


async def admin_find_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle profile search input."""
    query_text = update.message.text.strip()
    
    # Try to parse as userid first
    try:
        userid = int(query_text)
        profile = gamification_logic.get_user_profile(userid)
        
        if profile:
            await _show_admin_profile(update.message, profile)
            return settings.STATE_ADMIN_VIEW_PROFILE
    except ValueError:
        pass
    
    # Search by name
    users = gamification_logic.search_users(query_text)
    
    if not users:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_USER_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_MENU
    
    if len(users) == 1:
        profile = gamification_logic.get_user_profile(users[0]['userid'])
        if profile:
            await _show_admin_profile(update.message, profile)
            return settings.STATE_ADMIN_VIEW_PROFILE
    
    # Multiple results
    await update.message.reply_text(
        messages.MESSAGE_SEARCH_RESULTS_HEADER,
        reply_markup=keyboards.get_search_results_keyboard(users),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_ADMIN_FIND_PROFILE


async def _show_admin_profile(message, profile: dict) -> None:
    """Display profile for admin viewing."""
    text = messages.format_profile_message(
        first_name=profile['first_name'],
        last_name=profile['last_name'],
        total_score=profile['total_score'],
        rank_name=profile['rank_name'],
        rank_icon=profile['rank_icon'],
        next_rank_name=profile['next_rank_name'],
        next_rank_threshold=profile['next_rank_threshold'],
        total_achievements=profile['total_achievements'],
        max_achievements=profile['max_achievements'],
        achievements_by_level=profile['achievements_by_level']
    )
    
    # Add admin info
    text += f"\n\n_ID: {profile['userid']}_"
    if profile.get('username'):
        text += f"\n_Username: @{messages._escape_md(profile['username'])}_"
    
    await message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )


async def admin_view_profile_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle profile selection from search results."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    try:
        userid = int(callback_data.split('_')[-1])
    except (ValueError, IndexError):
        return settings.STATE_ADMIN_FIND_PROFILE
    
    profile = gamification_logic.get_user_profile(userid)
    
    if not profile:
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_USER_NOT_FOUND,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_MENU
    
    text = messages.format_profile_message(
        first_name=profile['first_name'],
        last_name=profile['last_name'],
        total_score=profile['total_score'],
        rank_name=profile['rank_name'],
        rank_icon=profile['rank_icon'],
        next_rank_name=profile['next_rank_name'],
        next_rank_threshold=profile['next_rank_threshold'],
        total_achievements=profile['total_achievements'],
        max_achievements=profile['max_achievements'],
        achievements_by_level=profile['achievements_by_level']
    )
    
    text += f"\n\n_ID: {profile['userid']}_"
    if profile.get('username'):
        text += f"\n_Username: @{messages._escape_md(profile['username'])}_"
    
    await query.edit_message_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_ADMIN_VIEW_PROFILE


# ===== SCORE CONFIGURATION =====

async def admin_score_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show score configuration settings."""
    configs = gamification_logic.get_all_score_configs()
    
    if not configs:
        await update.message.reply_text(
            "📋 Нет настроек очков\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_MENU
    
    # Build message
    text = messages.MESSAGE_ADMIN_SCORE_SETTINGS_HEADER
    for config in configs:
        text += messages.MESSAGE_ADMIN_SCORE_CONFIG_ITEM.format(
            module=messages._escape_md(config['module']),
            action=messages._escape_md(config['action']),
            points=config['points'],
            description=messages._escape_md(config.get('description') or '-')
        )
    
    keyboard = keyboards.get_admin_score_config_keyboard(configs)
    
    await update.message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_ADMIN_SCORE_SETTINGS


async def admin_edit_score_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle score config edit selection."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    try:
        config_id = int(callback_data.split('_')[-1])
    except (ValueError, IndexError):
        return settings.STATE_ADMIN_SCORE_SETTINGS
    
    config = gamification_logic.get_score_config_by_id(config_id)
    
    if not config:
        await query.edit_message_text(
            "❌ Настройка не найдена\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_SCORE_SETTINGS
    
    context.user_data[settings.CONTEXT_ADMIN_EDITING_CONFIG] = config_id
    
    await query.edit_message_text(
        messages.MESSAGE_ADMIN_ENTER_NEW_POINTS.format(
            module=messages._escape_md(config['module']),
            action=messages._escape_md(config['action'])
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_ADMIN_EDIT_SCORE


async def admin_save_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save updated score value."""
    text = update.message.text.strip()
    
    try:
        points = int(text)
    except ValueError:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_INVALID_POINTS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_EDIT_SCORE
    
    config_id = context.user_data.get(settings.CONTEXT_ADMIN_EDITING_CONFIG)
    
    if not config_id:
        return settings.STATE_ADMIN_MENU
    
    success = gamification_logic.update_score_config(config_id, points)
    
    if success:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_SCORE_UPDATED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            "❌ Ошибка сохранения\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    # Return to score settings
    return await admin_score_settings(update, context)


# ===== ALL ACHIEVEMENTS =====

async def admin_all_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show all achievements with unlock counts."""
    achievements = gamification_logic.get_achievements_with_unlock_counts()
    
    if not achievements:
        await update.message.reply_text(
            "📋 Нет достижений в системе\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_ADMIN_MENU
    
    text = messages.MESSAGE_ADMIN_ALL_ACHIEVEMENTS_HEADER
    
    for ach in achievements:
        text += messages.format_admin_achievement_item(
            code=ach['code'],
            module=ach['module'],
            name=ach['name'],
            icon=ach['icon'],
            threshold_bronze=ach['threshold_bronze'],
            threshold_silver=ach['threshold_silver'],
            threshold_gold=ach['threshold_gold'],
            unlocked_count=ach.get('unlocked_count', 0)
        )
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_ADMIN_MENU


# ===== STATISTICS =====

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show system statistics."""
    stats = gamification_logic.get_system_stats()
    
    text = messages.format_admin_stats(
        total_users=stats['total_users'],
        active_users_7d=stats['active_users_7d'],
        total_achievements_unlocked=stats['total_achievements_unlocked'],
        total_score_awarded=stats['total_score_awarded'],
        top_scorers=stats['top_scorers']
    )
    
    await update.message.reply_text(
        text,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_ADMIN_MENU


# ===== OBFUSCATION SETTINGS =====

async def admin_obfuscate_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggle name obfuscation setting in rankings."""
    current_value = gamification_logic.get_obfuscate_names()
    new_value = not current_value
    
    gamification_logic.set_setting(
        settings.DB_SETTING_OBFUSCATE_NAMES,
        str(new_value).lower(),
        "Скрывать имена в рейтинге"
    )
    
    status = "✅ включено" if new_value else "❌ выключено"
    await update.message.reply_text(
        f"🔒 *Скрытие имён в рейтинге:* {status}",
        reply_markup=keyboards.get_admin_menu_keyboard(),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_ADMIN_MENU


# ===== NAVIGATION =====

async def admin_back_to_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return to gamification submenu from admin."""
    return await return_to_submenu(update, context)


# ===== CONVERSATION HANDLER =====

def get_gamification_admin_handler() -> ConversationHandler:
    """Build and return the admin conversation handler."""
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(f"^{settings.BUTTON_ADMIN_PANEL}$"),
                admin_entry
            ),
        ],
        states={
            settings.STATE_ADMIN_MENU: [
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_ADMIN_FIND_PROFILE}$"),
                    admin_find_profile_prompt
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_ADMIN_SCORE_SETTINGS}$"),
                    admin_score_settings
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_ADMIN_ALL_ACHIEVEMENTS}$"),
                    admin_all_achievements
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_ADMIN_STATS}$"),
                    admin_stats
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_ADMIN_OBFUSCATE}$"),
                    admin_obfuscate_toggle
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_BACK_TO_PROFILE}$"),
                    admin_back_to_profile
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                    return_to_main_menu
                ),
            ],
            settings.STATE_ADMIN_FIND_PROFILE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    admin_find_profile
                ),
                CallbackQueryHandler(
                    admin_view_profile_callback,
                    pattern=f"^{settings.CALLBACK_PREFIX_PROFILE}_view_"
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_BACK_TO_PROFILE}$"),
                    admin_back_to_profile
                ),
            ],
            settings.STATE_ADMIN_VIEW_PROFILE: [
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_ADMIN_FIND_PROFILE}$"),
                    admin_find_profile_prompt
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_BACK_TO_PROFILE}$"),
                    admin_back_to_profile
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                    return_to_main_menu
                ),
            ],
            settings.STATE_ADMIN_SCORE_SETTINGS: [
                CallbackQueryHandler(
                    admin_edit_score_callback,
                    pattern=f"^{settings.CALLBACK_PREFIX_ADMIN}_edit_score_"
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_BACK_TO_PROFILE}$"),
                    admin_back_to_profile
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                    return_to_main_menu
                ),
            ],
            settings.STATE_ADMIN_EDIT_SCORE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    admin_save_score
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_BACK_TO_PROFILE}$"),
                    admin_back_to_profile
                ),
            ],
        },
        fallbacks=[
            MessageHandler(
                filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                return_to_main_menu
            ),
            CommandHandler("cancel", return_to_main_menu),
        ],
        map_to_parent={
            settings.STATE_SUBMENU: ConversationHandler.END,
            ConversationHandler.END: ConversationHandler.END,
        },
        name="gamification_admin_handler",
        persistent=False
    )
