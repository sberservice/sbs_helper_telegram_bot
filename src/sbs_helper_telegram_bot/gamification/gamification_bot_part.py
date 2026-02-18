"""
Часть бота для геймификации.

Основные обработчики системы достижений/геймификации.
Обрабатывает просмотр профиля, достижения и навигацию по рейтингам.
"""

import logging
import math
from typing import Optional

from telegram import Update, constants
from telegram.error import BadRequest
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

from src.common.telegram_user import check_if_user_legit, check_if_user_admin, get_unauthorized_message
from src.common.messages import get_main_menu_message, get_main_menu_keyboard

from . import settings
from . import messages
from . import keyboards
from . import gamification_logic
from src.sbs_helper_telegram_bot.certification import certification_logic

logger = logging.getLogger(__name__)


# ===== ТОЧКА ВХОДА =====

async def gamification_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Точка входа в модуль геймификации."""
    user = update.effective_user
    
    if not check_if_user_legit(user.id):
        await update.message.reply_text(get_unauthorized_message(user.id))
        return ConversationHandler.END
    
    # Убеждаемся, что у пользователя есть запись итогов
    gamification_logic.ensure_user_totals_exist(user.id)
    
    # Выбираем клавиатуру с учётом статуса администратора
    is_admin = check_if_user_admin(user.id)
    keyboard = keyboards.get_admin_submenu_keyboard() if is_admin else keyboards.get_submenu_keyboard()

    profile_message = _get_profile_message(user.id)
    if not profile_message:
        await update.message.reply_text(
            "❌ Профиль не найден\.",
            reply_markup=keyboard,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_SUBMENU

    await update.message.reply_text(
        profile_message,
        reply_markup=keyboard,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_SUBMENU


# ===== ОБРАБОТЧИКИ ПРОФИЛЯ =====

async def show_my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать профиль текущего пользователя."""
    user = update.effective_user

    message = _get_profile_message(user.id)
    if not message:
        await update.message.reply_text(
            "❌ Профиль не найден\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_SUBMENU
    
    await update.message.reply_text(
        message,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_SUBMENU


async def show_other_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать профиль другого пользователя (из рейтинга)."""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем идентификатор пользователя из callback-данных
    callback_data = query.data
    try:
        userid = int(callback_data.split('_')[-1])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка загрузки профиля\\.")
        return settings.STATE_VIEW_RANKINGS
    
    context.user_data[settings.CONTEXT_VIEW_USERID] = userid
    
    profile = gamification_logic.get_user_profile(userid)
    
    if not profile:
        await query.edit_message_text(
            "❌ Профиль не найден\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_VIEW_RANKINGS
    
    obfuscate = gamification_logic.get_obfuscate_names()
    cert_summary = certification_logic.get_user_certification_summary(userid)
    
    message = messages.format_other_user_profile_message(
        first_name=profile['first_name'],
        last_name=profile['last_name'],
        total_score=profile['total_score'],
        rank_name=profile['rank_name'],
        rank_icon=profile['rank_icon'],
        total_achievements=profile['total_achievements'],
        achievements_by_level=profile['achievements_by_level'],
        obfuscate=obfuscate,
        certification_rank_name=cert_summary.get('rank_name'),
        certification_rank_icon=cert_summary.get('rank_icon'),
        certification_points=cert_summary.get('certification_points'),
        passed_tests_count=cert_summary.get('passed_tests_count'),
        passed_categories_count=cert_summary.get('passed_categories_count'),
    )
    
    await query.edit_message_text(
        message,
        reply_markup=keyboards.get_user_profile_keyboard(from_ranking=True),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_VIEW_USER_PROFILE


# ===== ОБРАБОТЧИКИ ДОСТИЖЕНИЙ =====

async def show_my_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать достижения текущего пользователя."""
    user = update.effective_user
    
    # Сбрасываем фильтры
    context.user_data[settings.CONTEXT_MODULE_FILTER] = None
    context.user_data[settings.CONTEXT_CURRENT_PAGE] = 1
    
    await _display_achievements(update.message, user.id, context)
    
    return settings.STATE_VIEW_ACHIEVEMENTS


async def _display_achievements(
    message_or_query,
    userid: int,
    context: ContextTypes.DEFAULT_TYPE,
    edit: bool = False
) -> None:
    """Показать список достижений с пагинацией."""
    module_filter = context.user_data.get(settings.CONTEXT_MODULE_FILTER)
    page = context.user_data.get(settings.CONTEXT_CURRENT_PAGE, 1)
    
    # Получаем достижения с прогрессом
    achievements = gamification_logic.get_user_achievements_with_progress(userid, module_filter)
    
    if not achievements:
        text = messages.MESSAGE_ACHIEVEMENTS_EMPTY
        keyboard = None
    else:
        # Пагинация
        per_page = settings.ACHIEVEMENTS_PER_PAGE
        total_pages = math.ceil(len(achievements) / per_page)
        page = min(page, total_pages)
        
        start_idx = (page - 1) * per_page
        page_achievements = achievements[start_idx:start_idx + per_page]
        
        # Формируем сообщение
        unlocked = gamification_logic.get_user_unlocked_achievements_count(userid)
        total = gamification_logic.get_total_achievements_count()
        
        if module_filter:
            header = messages.MESSAGE_MODULE_ACHIEVEMENTS_HEADER.format(
                module=messages._escape_md(module_filter),
                unlocked=unlocked,
                total=total
            )
        else:
            header = messages.MESSAGE_ACHIEVEMENTS_HEADER.format(
                unlocked=unlocked,
                total=total
            )
        
        cards = []
        for ach in page_achievements:
            card = messages.format_achievement_card(
                name=ach['name'],
                description=ach['description'],
                icon=ach['icon'],
                current_count=ach['current_count'],
                threshold_bronze=ach['threshold_bronze'],
                threshold_silver=ach['threshold_silver'],
                threshold_gold=ach['threshold_gold'],
                unlocked_level=ach['unlocked_level']
            )
            cards.append(card)
        
        text = header + "\n".join(cards)
        
        # Получаем список модулей для кнопок фильтра
        modules = gamification_logic.get_achievement_modules()
        keyboard = keyboards.get_achievements_keyboard(
            modules=modules,
            selected_module=module_filter,
            page=page,
            total_pages=total_pages
        )
    
    if edit and hasattr(message_or_query, 'edit_message_text'):
        try:
            await message_or_query.edit_message_text(
                text,
                reply_markup=keyboard,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        except BadRequest as e:
            # Игнорируем ошибку Telegram о неизменённом сообщении
            if "Message is not modified" not in str(e):
                raise
    else:
        await message_or_query.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )


async def handle_achievement_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать колбэки достижений (фильтр, пагинация)."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user = update.effective_user
    
    if "_filter_" in callback_data:
        # Фильтр по модулю
        filter_value = callback_data.split("_filter_")[-1]
        if filter_value == "all":
            context.user_data[settings.CONTEXT_MODULE_FILTER] = None
        else:
            context.user_data[settings.CONTEXT_MODULE_FILTER] = filter_value
        context.user_data[settings.CONTEXT_CURRENT_PAGE] = 1
        
    elif "_page_" in callback_data:
        # Пагинация
        try:
            page = int(callback_data.split("_page_")[-1])
            context.user_data[settings.CONTEXT_CURRENT_PAGE] = page
        except ValueError:
            pass
    
    elif "_module_" in callback_data:
        # Кнопка достижений модуля, пришедшая из других модулей
        module_name = callback_data.split("_module_")[-1]
        context.user_data[settings.CONTEXT_MODULE_FILTER] = module_name
        context.user_data[settings.CONTEXT_CURRENT_PAGE] = 1
    
    await _display_achievements(query, user.id, context, edit=True)
    
    return settings.STATE_VIEW_ACHIEVEMENTS


# ===== ОБРАБОТЧИКИ РЕЙТИНГОВ =====

async def show_rankings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать выбор типа рейтинга."""
    await update.message.reply_text(
        messages.MESSAGE_RANKINGS_MENU,
        reply_markup=keyboards.get_rankings_type_keyboard(),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_VIEW_RANKINGS


async def handle_ranking_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать выбор типа рейтинга."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if "_type_" in callback_data:
        ranking_type = callback_data.split("_type_")[-1]
        context.user_data[settings.CONTEXT_RANKING_TYPE] = ranking_type
        
        await query.edit_message_text(
            messages.MESSAGE_RANKINGS_MENU,
            reply_markup=keyboards.get_rankings_period_keyboard(ranking_type),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    elif callback_data.endswith("_back"):
        await query.edit_message_text(
            messages.MESSAGE_RANKINGS_MENU,
            reply_markup=keyboards.get_rankings_type_keyboard(),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    return settings.STATE_VIEW_RANKINGS


async def handle_ranking_period_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать выбор периода и показать рейтинг."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user = update.effective_user
    
    # Разбор колбэка: gf_period_{type}_{period}
    parts = callback_data.split("_")
    if len(parts) >= 4:
        ranking_type = parts[2]
        period = parts[3]
    else:
        return settings.STATE_VIEW_RANKINGS
    
    context.user_data[settings.CONTEXT_RANKING_TYPE] = ranking_type
    context.user_data[settings.CONTEXT_RANKING_PERIOD] = period
    context.user_data[settings.CONTEXT_CURRENT_PAGE] = 1
    
    await _display_rankings(query, user.id, context, edit=True)
    
    return settings.STATE_VIEW_RANKINGS


async def handle_ranking_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать пагинацию рейтинга."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user = update.effective_user
    
    # Разбор колбэка: gf_page_{type}_{period}_{page}
    parts = callback_data.split("_")
    if len(parts) >= 5:
        ranking_type = parts[2]
        period = parts[3]
        page = int(parts[4])
        
        context.user_data[settings.CONTEXT_RANKING_TYPE] = ranking_type
        context.user_data[settings.CONTEXT_RANKING_PERIOD] = period
        context.user_data[settings.CONTEXT_CURRENT_PAGE] = page
    
    await _display_rankings(query, user.id, context, edit=True)
    
    return settings.STATE_VIEW_RANKINGS


async def _display_rankings(
    query,
    current_userid: int,
    context: ContextTypes.DEFAULT_TYPE,
    edit: bool = True
) -> None:
    """Показать список рейтинга."""
    ranking_type = context.user_data.get(settings.CONTEXT_RANKING_TYPE, settings.RANKING_TYPE_SCORE)
    period = context.user_data.get(settings.CONTEXT_RANKING_PERIOD, settings.RANKING_PERIOD_ALL_TIME)
    page = context.user_data.get(settings.CONTEXT_CURRENT_PAGE, 1)
    
    per_page = settings.RANKINGS_PER_PAGE
    
    # Получаем данные рейтинга
    if ranking_type == settings.RANKING_TYPE_SCORE:
        entries, total = gamification_logic.get_score_ranking(period, page, per_page)
        header = messages.MESSAGE_RANKING_SCORE_HEADER.format(
            period=messages._escape_md(messages.get_period_display_name(period))
        )
    else:
        entries, total = gamification_logic.get_achievements_ranking(period, page, per_page)
        header = messages.MESSAGE_RANKING_ACHIEVEMENTS_HEADER.format(
            period=messages._escape_md(messages.get_period_display_name(period))
        )
    
    total_pages = max(1, math.ceil(total / per_page))
    
    # Получаем позицию пользователя, если её нет в видимом списке
    user_rank = gamification_logic.get_user_rank(current_userid, ranking_type, period)
    
    obfuscate = gamification_logic.get_obfuscate_names()
    
    # Форматируем список рейтинга
    ranking_text = messages.format_ranking_list(
        entries=entries,
        ranking_type=ranking_type,
        current_userid=current_userid,
        page=page,
        total_pages=total_pages,
        user_rank=user_rank,
        obfuscate=obfuscate
    )
    
    text = header + ranking_text
    
    keyboard = keyboards.get_ranking_list_keyboard(
        ranking_type=ranking_type,
        period=period,
        page=page,
        total_pages=total_pages,
        entries=entries,
        obfuscate=obfuscate
    )
    
    if edit:
        try:
            await query.edit_message_text(
                text,
                reply_markup=keyboard,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        except BadRequest as e:
            # Игнорируем ошибку Telegram о неизменённом сообщении
            if "Message is not modified" not in str(e):
                raise
    else:
        await query.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )


async def handle_ranking_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать кнопку поиска в рейтингах."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        messages.MESSAGE_SEARCH_ENTER_QUERY,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_SEARCH_USER


async def handle_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать поисковый запрос пользователя."""
    query_text = update.message.text.strip()
    
    if not query_text:
        await update.message.reply_text(
            messages.MESSAGE_SEARCH_ENTER_QUERY,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_SEARCH_USER
    
    users = gamification_logic.search_users(query_text)
    
    if not users:
        await update.message.reply_text(
            messages.MESSAGE_SEARCH_NO_RESULTS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_VIEW_RANKINGS
    
    await update.message.reply_text(
        messages.MESSAGE_SEARCH_RESULTS_HEADER,
        reply_markup=keyboards.get_search_results_keyboard(users),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_VIEW_RANKINGS


async def handle_ranking_return(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вернуться к рейтингу из профиля или поиска."""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    await _display_rankings(query, user.id, context, edit=True)
    
    return settings.STATE_VIEW_RANKINGS


# ===== НАВИГАЦИЯ =====

async def return_to_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вернуться в подменю геймификации."""
    user = update.effective_user

    is_admin = check_if_user_admin(user.id)
    keyboard = keyboards.get_admin_submenu_keyboard() if is_admin else keyboards.get_submenu_keyboard()

    profile_message = _get_profile_message(user.id)
    if not profile_message:
        await update.message.reply_text(
            "❌ Профиль не найден\.",
            reply_markup=keyboard,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return settings.STATE_SUBMENU

    await update.message.reply_text(
        profile_message,
        reply_markup=keyboard,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return settings.STATE_SUBMENU


async def return_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вернуться в главное меню бота."""
    user = update.effective_user
    is_admin = check_if_user_admin(user.id)
    await update.message.reply_text(
        get_main_menu_message(user.id, user.first_name),
        reply_markup=get_main_menu_keyboard(is_admin=is_admin),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ConversationHandler.END


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать команду /cancel."""
    return await return_to_main_menu(update, context)


# ===== ОБРАБОТЧИК ДИАЛОГА =====

def get_gamification_user_handler() -> ConversationHandler:
    """Собрать и вернуть ConversationHandler для пользователя."""
    return ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(f"^{settings.MENU_BUTTON_TEXT}$"),
                gamification_entry
            ),
        ],
        states={
            settings.STATE_SUBMENU: [
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MY_PROFILE}$"),
                    show_my_profile
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MY_ACHIEVEMENTS}$"),
                    show_my_achievements
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_RANKINGS}$"),
                    show_rankings_menu
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                    return_to_main_menu
                ),
            ],
            settings.STATE_VIEW_ACHIEVEMENTS: [
                CallbackQueryHandler(
                    handle_achievement_callback,
                    pattern=f"^{settings.CALLBACK_PREFIX_ACHIEVEMENT}_"
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MY_PROFILE}$"),
                    show_my_profile
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_RANKINGS}$"),
                    show_rankings_menu
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                    return_to_main_menu
                ),
            ],
            settings.STATE_VIEW_RANKINGS: [
                CallbackQueryHandler(
                    handle_ranking_type_selection,
                    pattern=f"^{settings.CALLBACK_PREFIX_RANKING}_"
                ),
                CallbackQueryHandler(
                    handle_ranking_period_selection,
                    pattern=f"^{settings.CALLBACK_PREFIX_PERIOD}_"
                ),
                CallbackQueryHandler(
                    handle_ranking_page,
                    pattern=f"^{settings.CALLBACK_PREFIX_PAGE}_"
                ),
                CallbackQueryHandler(
                    show_other_user_profile,
                    pattern=f"^{settings.CALLBACK_PREFIX_PROFILE}_view_"
                ),
                CallbackQueryHandler(
                    handle_ranking_search,
                    pattern=f"^{settings.CALLBACK_PREFIX_RANKING}_search$"
                ),
                CallbackQueryHandler(
                    handle_ranking_return,
                    pattern=f"^{settings.CALLBACK_PREFIX_RANKING}_return$"
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_RANKINGS}$"),
                    show_rankings_menu
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MY_PROFILE}$"),
                    show_my_profile
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MY_ACHIEVEMENTS}$"),
                    show_my_achievements
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                    return_to_main_menu
                ),
            ],
            settings.STATE_VIEW_USER_PROFILE: [
                CallbackQueryHandler(
                    handle_ranking_return,
                    pattern=f"^{settings.CALLBACK_PREFIX_RANKING}_return$"
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_BACK_TO_RANKING}$"),
                    show_rankings_menu
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_RANKINGS}$"),
                    show_rankings_menu
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                    return_to_main_menu
                ),
            ],
            settings.STATE_SEARCH_USER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    handle_search_query
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_RANKINGS}$"),
                    show_rankings_menu
                ),
                MessageHandler(
                    filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                    return_to_main_menu
                ),
            ],
        },
        fallbacks=[
            MessageHandler(
                filters.Regex(f"^{settings.BUTTON_MAIN_MENU}$"),
                return_to_main_menu
            ),
            CommandHandler("cancel", cancel_handler),
            CommandHandler("reset", return_to_main_menu),
            CommandHandler("menu", return_to_main_menu),
        ],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END,
        },
        name="gamification_user_handler",
        persistent=False
    )


def _get_profile_message(userid: int) -> Optional[str]:
    """Сформировать сообщение профиля пользователя."""
    profile = gamification_logic.get_user_profile(userid)
    cert_summary = certification_logic.get_user_certification_summary(userid)

    if not profile:
        return None

    return messages.format_profile_message(
        first_name=profile['first_name'],
        last_name=profile['last_name'],
        total_score=profile['total_score'],
        rank_name=profile['rank_name'],
        rank_icon=profile['rank_icon'],
        next_rank_name=profile['next_rank_name'],
        next_rank_threshold=profile['next_rank_threshold'],
        total_achievements=profile['total_achievements'],
        max_achievements=profile['max_achievements'],
        achievements_by_level=profile['achievements_by_level'],
        certification_rank_name=cert_summary.get('rank_name'),
        certification_rank_icon=cert_summary.get('rank_icon'),
        certification_points=cert_summary.get('certification_points'),
        passed_tests_count=cert_summary.get('passed_tests_count'),
        passed_categories_count=cert_summary.get('passed_categories_count'),
        certification_next_rank_name=cert_summary.get('next_rank_name'),
        certification_points_to_next=cert_summary.get('points_to_next_rank'),
    )
