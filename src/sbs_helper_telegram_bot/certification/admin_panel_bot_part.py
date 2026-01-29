"""
Employee Certification Module - Admin Panel

Telegram handlers for admin functionality:
- CRUD operations for categories and questions
- Outdated questions management
- Test settings configuration
"""

import logging
import time
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from typing import Optional

from telegram import Update, constants
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

from src.common.telegram_user import check_if_user_legit, check_if_user_admin
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE, get_main_menu_keyboard

from . import settings
from . import messages
from . import keyboards
from . import certification_logic as logic

logger = logging.getLogger(__name__)

# Conversation states for admin panel
(
    ADMIN_MENU,
    # Category management
    CAT_LIST,
    CAT_VIEW,
    CAT_CREATE_NAME,
    CAT_CREATE_DESC,
    CAT_CREATE_ORDER,
    CAT_EDIT_NAME,
    CAT_EDIT_DESC,
    CAT_CONFIRM_DELETE,
    # Question management
    Q_LIST,
    Q_VIEW,
    Q_CREATE_TEXT,
    Q_CREATE_OPT_A,
    Q_CREATE_OPT_B,
    Q_CREATE_OPT_C,
    Q_CREATE_OPT_D,
    Q_CREATE_CORRECT,
    Q_CREATE_EXPLANATION,
    Q_CREATE_DIFFICULTY,
    Q_CREATE_CATEGORIES,
    Q_CREATE_RELEVANCE,
    Q_EDIT_FIELD,
    Q_EDIT_CATEGORIES,
    Q_CONFIRM_DELETE,
    Q_UPDATE_RELEVANCE,
    # Settings
    SETTINGS_MENU,
    SETTINGS_QUESTIONS_COUNT,
    SETTINGS_TIME_LIMIT,
    SETTINGS_PASSING_SCORE,
    # Outdated questions
    OUTDATED_LIST,
) = range(30)


# ============================================================================
# Entry Point and Main Menu
# ============================================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle admin panel entry."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
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
    """Handle admin menu button presses."""
    text = update.message.text
    
    if text == "❓ Вопросы":
        return await show_questions_list(update, context)
    elif text == "📁 Категории":
        return await show_categories_list(update, context)
    elif text == "⚠️ Устаревшие вопросы":
        return await show_outdated_questions(update, context)
    elif text == "⚙️ Настройки теста":
        return await show_settings(update, context)
    elif text == "📋 Все вопросы":
        # Handle from questions submenu
        return await show_questions_list(update, context)
    elif text == "📋 Все категории":
        # Handle from categories submenu
        return await show_categories_list(update, context)
    elif text == "🔙 Назад":
        # Go back to certification submenu
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
    elif text == "🔙 Админ меню":
        # Go back to admin menu from questions/categories submenu
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    elif text == "🏠 Главное меню":
        is_admin = check_if_user_admin(update.effective_user.id)
        await update.message.reply_text(
            messages.MESSAGE_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard(is_admin=is_admin)
        )
        return ConversationHandler.END
    
    return ADMIN_MENU


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle admin inline button callbacks."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cert_admin_menu":
        await query.message.reply_text(
            messages.MESSAGE_ADMIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    
    if data == "cert_noop":
        return None  # No operation, keep current state
    
    # Category callbacks
    if data == "cert_cat_list":
        return await show_categories_list_callback(update, context)
    
    if data.startswith("cert_cat_view_"):
        cat_id = int(data.replace("cert_cat_view_", ""))
        return await show_category_details(update, context, cat_id)
    
    if data.startswith("cert_cat_toggle_"):
        cat_id = int(data.replace("cert_cat_toggle_", ""))
        return await toggle_category(update, context, cat_id)
    
    if data.startswith("cert_cat_delete_"):
        cat_id = int(data.replace("cert_cat_delete_", ""))
        context.user_data[settings.ADMIN_EDITING_CATEGORY_KEY] = cat_id
        return await confirm_delete_category(update, context, cat_id)
    
    if data.startswith("cert_cat_confirm_delete_"):
        cat_id = int(data.replace("cert_cat_confirm_delete_", ""))
        return await delete_category(update, context, cat_id)
    
    if data.startswith("cert_cat_page_"):
        page = int(data.replace("cert_cat_page_", ""))
        return await show_categories_page(update, context, page)
    
    # Category edit - show edit menu
    if data.startswith("cert_cat_edit_") and not any(
        data.startswith(f"cert_cat_edit_{field}_") 
        for field in ["name", "desc"]
    ):
        cat_id = int(data.replace("cert_cat_edit_", ""))
        context.user_data[settings.ADMIN_EDITING_CATEGORY_KEY] = cat_id
        await query.edit_message_text(
            "✏️ *Редактирование категории*\n\nВыберите поле для редактирования:",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_category_edit_keyboard(cat_id)
        )
        return CAT_EDIT_NAME  # Using this state for category edit
    
    # Category edit - specific field handlers
    if data.startswith("cert_cat_edit_name_"):
        cat_id = int(data.replace("cert_cat_edit_name_", ""))
        context.user_data[settings.ADMIN_EDITING_CATEGORY_KEY] = cat_id
        context.user_data["edit_field"] = "name"
        await query.edit_message_text(
            "📝 Введите новое название категории:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return CAT_EDIT_NAME
    
    if data.startswith("cert_cat_edit_desc_"):
        cat_id = int(data.replace("cert_cat_edit_desc_", ""))
        context.user_data[settings.ADMIN_EDITING_CATEGORY_KEY] = cat_id
        context.user_data["edit_field"] = "description"
        await query.edit_message_text(
            "📄 Введите новое описание \\(или /skip чтобы очистить\\):",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return CAT_EDIT_DESC
    
    if data == "cert_cancel":
        await query.edit_message_text(
            messages.MESSAGE_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    # Question callbacks
    if data == "cert_q_list":
        return await show_questions_list_callback(update, context)
    
    if data.startswith("cert_q_view_"):
        q_id = int(data.replace("cert_q_view_", ""))
        return await show_question_details(update, context, q_id)
    
    if data.startswith("cert_q_toggle_"):
        q_id = int(data.replace("cert_q_toggle_", ""))
        return await toggle_question(update, context, q_id)
    
    if data.startswith("cert_q_delete_"):
        q_id = int(data.replace("cert_q_delete_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        return await confirm_delete_question(update, context, q_id)
    
    if data.startswith("cert_q_confirm_delete_"):
        q_id = int(data.replace("cert_q_confirm_delete_", ""))
        return await delete_question(update, context, q_id)
    
    if data.startswith("cert_q_relevance_"):
        q_id = int(data.replace("cert_q_relevance_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        await query.edit_message_text(
            messages.MESSAGE_CREATE_QUESTION_RELEVANCE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_UPDATE_RELEVANCE
    
    # Question edit - show edit menu
    if data.startswith("cert_q_edit_") and not any(
        data.startswith(f"cert_q_edit_{field}_") 
        for field in ["text", "opt_a", "opt_b", "opt_c", "opt_d", "correct", "expl", "diff", "cats"]
    ):
        q_id = int(data.replace("cert_q_edit_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        await query.edit_message_text(
            "✏️ *Редактирование вопроса*\n\nВыберите поле для редактирования:",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_question_edit_keyboard(q_id)
        )
        return Q_EDIT_FIELD
    
    # Question edit - specific field handlers
    if data.startswith("cert_q_edit_text_"):
        q_id = int(data.replace("cert_q_edit_text_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        context.user_data["edit_field"] = "question_text"
        await query.edit_message_text(
            "📝 Введите новый текст вопроса:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_EDIT_FIELD
    
    if data.startswith("cert_q_edit_opt_a_"):
        q_id = int(data.replace("cert_q_edit_opt_a_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        context.user_data["edit_field"] = "option_a"
        await query.edit_message_text(
            "🅰️ Введите новый текст варианта A:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_EDIT_FIELD
    
    if data.startswith("cert_q_edit_opt_b_"):
        q_id = int(data.replace("cert_q_edit_opt_b_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        context.user_data["edit_field"] = "option_b"
        await query.edit_message_text(
            "🅱️ Введите новый текст варианта B:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_EDIT_FIELD
    
    if data.startswith("cert_q_edit_opt_c_"):
        q_id = int(data.replace("cert_q_edit_opt_c_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        context.user_data["edit_field"] = "option_c"
        await query.edit_message_text(
            "©️ Введите новый текст варианта C:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_EDIT_FIELD
    
    if data.startswith("cert_q_edit_opt_d_"):
        q_id = int(data.replace("cert_q_edit_opt_d_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        context.user_data["edit_field"] = "option_d"
        await query.edit_message_text(
            "🇩 Введите новый текст варианта D:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_EDIT_FIELD
    
    if data.startswith("cert_q_edit_expl_"):
        q_id = int(data.replace("cert_q_edit_expl_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        context.user_data["edit_field"] = "explanation"
        await query.edit_message_text(
            "💡 Введите новое пояснение \\(или /skip чтобы очистить\\):",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_EDIT_FIELD
    
    if data.startswith("cert_q_edit_correct_"):
        q_id = int(data.replace("cert_q_edit_correct_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        context.user_data["edit_field"] = "correct_option"
        await query.edit_message_text(
            "✅ Выберите правильный ответ:",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_correct_answer_keyboard()
        )
        return Q_EDIT_FIELD
    
    if data.startswith("cert_q_edit_diff_"):
        q_id = int(data.replace("cert_q_edit_diff_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        context.user_data["edit_field"] = "difficulty"
        await query.edit_message_text(
            "📊 Выберите уровень сложности:",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_difficulty_keyboard()
        )
        return Q_EDIT_FIELD
    
    if data.startswith("cert_q_edit_cats_"):
        q_id = int(data.replace("cert_q_edit_cats_", ""))
        context.user_data[settings.ADMIN_EDITING_QUESTION_KEY] = q_id
        
        # Get current categories for the question
        question = logic.get_question_by_id(q_id)
        current_cat_ids = [c['id'] for c in question.get('categories', [])] if question else []
        context.user_data['editing_question_categories'] = current_cat_ids
        
        # Get all active categories
        categories = logic.get_all_categories(active_only=True)
        
        await query.edit_message_text(
            "📁 *Редактирование категорий*\n\nВыберите категории для вопроса:",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_category_edit_multiselect_keyboard(categories, current_cat_ids, q_id)
        )
        return Q_EDIT_CATEGORIES
    
    # Question category editing callbacks
    if data.startswith("cert_q_cat_toggle_"):
        cat_id = int(data.replace("cert_q_cat_toggle_", ""))
        return await toggle_question_category(update, context, cat_id)
    
    if data == "cert_q_cat_save":
        return await save_question_categories(update, context)
    
    if data.startswith("cert_q_page_"):
        page = int(data.replace("cert_q_page_", ""))
        return await show_questions_page(update, context, page)
    
    # Outdated questions
    if data == "cert_outdated_update_all":
        return await update_all_outdated(update, context)
    
    # Settings callbacks
    if data == "cert_set_questions":
        await query.edit_message_text(
            messages.MESSAGE_ENTER_QUESTIONS_COUNT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return SETTINGS_QUESTIONS_COUNT
    
    if data == "cert_set_time":
        await query.edit_message_text(
            messages.MESSAGE_ENTER_TIME_LIMIT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return SETTINGS_TIME_LIMIT
    
    if data == "cert_set_score":
        await query.edit_message_text(
            messages.MESSAGE_ENTER_PASSING_SCORE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return SETTINGS_PASSING_SCORE
    
    if data == "cert_set_show_correct":
        # Toggle show_correct_answer setting
        test_settings = logic.get_test_settings()
        new_value = not test_settings['show_correct_answer']
        logic.set_setting(settings.DB_SETTING_SHOW_CORRECT, str(new_value), "Show correct answer after each question")
        
        # Refresh settings display
        test_settings = logic.get_test_settings()
        show_correct_text = "✅ Да" if test_settings['show_correct_answer'] else "❌ Нет"
        obfuscate_text = "✅ Да" if test_settings['obfuscate_names'] else "❌ Нет"
        
        message = messages.MESSAGE_CERTIFICATION_SETTINGS.format(
            questions_count=test_settings['questions_count'],
            time_limit=test_settings['time_limit_minutes'],
            passing_score=test_settings['passing_score_percent'],
            show_correct=show_correct_text,
            obfuscate_names=obfuscate_text
        )
        
        await query.edit_message_text(
            message,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_settings_keyboard(
                test_settings['show_correct_answer'],
                test_settings['obfuscate_names']
            )
        )
        return SETTINGS_MENU
    
    if data == "cert_set_obfuscate":
        # Toggle obfuscate_names setting
        test_settings = logic.get_test_settings()
        new_value = not test_settings['obfuscate_names']
        logic.set_setting(settings.DB_SETTING_OBFUSCATE_NAMES, str(new_value), "Obfuscate names in ranking")
        
        # Refresh settings display
        test_settings = logic.get_test_settings()
        show_correct_text = "✅ Да" if test_settings['show_correct_answer'] else "❌ Нет"
        obfuscate_text = "✅ Да" if test_settings['obfuscate_names'] else "❌ Нет"
        
        message = messages.MESSAGE_CERTIFICATION_SETTINGS.format(
            questions_count=test_settings['questions_count'],
            time_limit=test_settings['time_limit_minutes'],
            passing_score=test_settings['passing_score_percent'],
            show_correct=show_correct_text,
            obfuscate_names=obfuscate_text
        )
        
        await query.edit_message_text(
            message,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_settings_keyboard(
                test_settings['show_correct_answer'],
                test_settings['obfuscate_names']
            )
        )
        return SETTINGS_MENU
    
    # Question creation - correct answer selection
    if data.startswith("cert_correct_"):
        answer = data.replace("cert_correct_", "")
        return await receive_correct_answer(update, context, answer)
    
    # Question creation - difficulty selection
    if data.startswith("cert_diff_"):
        difficulty = data.replace("cert_diff_", "")
        return await receive_difficulty(update, context, difficulty)
    
    # Question creation - category selection
    if data.startswith("cert_catsel_"):
        if data == "cert_catsel_done":
            return await finish_category_selection(update, context)
        cat_id = int(data.replace("cert_catsel_", ""))
        return await toggle_category_selection(update, context, cat_id)
    
    return ADMIN_MENU


# ============================================================================
# Category Management
# ============================================================================

async def show_categories_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show categories list."""
    categories = logic.get_all_categories()
    
    if not categories:
        await update.message.reply_text(
            messages.MESSAGE_NO_CATEGORIES,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_categories_keyboard()
        )
        return CAT_LIST  # Changed from ADMIN_MENU to CAT_LIST
    
    await update.message.reply_text(
        "📁 *Категории тестов*",
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_categories_list_keyboard(categories)
    )
    
    # Also show reply keyboard for add button
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=keyboards.get_admin_categories_keyboard()
    )
    
    return CAT_LIST


async def show_categories_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show categories list (callback version)."""
    query = update.callback_query
    categories = logic.get_all_categories()
    
    if not categories:
        await query.edit_message_text(
            messages.MESSAGE_NO_CATEGORIES,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        # Send reply keyboard
        await query.message.reply_text(
            "Выберите действие:",
            reply_markup=keyboards.get_admin_categories_keyboard()
        )
        return CAT_LIST  # Changed from ADMIN_MENU
    
    await query.edit_message_text(
        "📁 *Категории тестов*",
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_categories_list_keyboard(categories)
    )
    
    # Send reply keyboard
    await query.message.reply_text(
        "Выберите действие:",
        reply_markup=keyboards.get_admin_categories_keyboard()
    )
    
    return CAT_LIST


async def show_categories_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> int:
    """Show specific page of categories list."""
    query = update.callback_query
    categories = logic.get_all_categories()
    
    await query.edit_message_reply_markup(
        reply_markup=keyboards.get_categories_list_keyboard(categories, page=page)
    )
    
    return CAT_LIST


async def show_category_details(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int) -> int:
    """Show category details."""
    query = update.callback_query
    category = logic.get_category_by_id(category_id)
    
    if not category:
        await query.edit_message_text(
            "❌ Категория не найдена",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    status = "✅ Активна" if category['active'] else "❌ Неактивна"
    created_date = datetime.fromtimestamp(category['created_timestamp']).strftime('%d\\.%m\\.%Y')
    
    message = messages.MESSAGE_CATEGORY_DETAILS.format(
        name=logic.escape_markdown(category['name']),
        description=logic.escape_markdown(category['description'] or "—"),
        questions_count=category['questions_count'],
        status=status,
        display_order=category['display_order'],
        created_date=created_date
    )
    
    await query.edit_message_text(
        message,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_category_actions_keyboard(category_id, category['active'])
    )
    
    return CAT_VIEW


async def receive_category_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and save edited category field value."""
    text = update.message.text
    cat_id = context.user_data.get(settings.ADMIN_EDITING_CATEGORY_KEY)
    field = context.user_data.get("edit_field")
    
    if not cat_id or not field:
        await update.message.reply_text(
            "❌ Ошибка: данные редактирования потеряны",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    # Handle /skip for description field
    if field == "description" and text == "/skip":
        text = None
    
    # Update the category field
    success = logic.update_category_field(cat_id, field, text)
    
    if success:
        await update.message.reply_text(
            "✅ *Поле успешно обновлено\\!*",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        # Show category details again
        category = logic.get_category_by_id(cat_id)
        if category:
            status = "✅ Активна" if category['active'] else "❌ Неактивна"
            created_date = datetime.fromtimestamp(category['created_timestamp']).strftime('%d\\.%m\\.%Y')
            
            message = messages.MESSAGE_CATEGORY_DETAILS.format(
                name=logic.escape_markdown(category['name']),
                description=logic.escape_markdown(category['description'] or "—"),
                questions_count=category['questions_count'],
                status=status,
                display_order=category['display_order'],
                created_date=created_date
            )
            
            await update.message.reply_text(
                message,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboards.get_category_actions_keyboard(cat_id, category['active'])
            )
    else:
        await update.message.reply_text(
            "❌ Ошибка сохранения",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    # Clean up
    context.user_data.pop("edit_field", None)
    
    return CAT_VIEW


async def toggle_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int) -> int:
    """Toggle category active status."""
    query = update.callback_query
    
    new_status = logic.toggle_category_active(category_id)
    
    if new_status is None:
        await query.answer("❌ Ошибка", show_alert=True)
        return CAT_VIEW
    
    status_text = "✅ Активна" if new_status else "❌ Неактивна"
    await query.answer(f"Статус изменен: {status_text}")
    
    # Refresh details
    return await show_category_details(update, context, category_id)


async def confirm_delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int) -> int:
    """Show delete confirmation for category."""
    query = update.callback_query
    
    await query.edit_message_text(
        messages.MESSAGE_CONFIRM_DELETE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_confirmation_keyboard(
            f"cert_cat_confirm_delete_{category_id}",
            "cert_cat_list"
        )
    )
    
    return CAT_CONFIRM_DELETE


async def delete_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int) -> int:
    """Delete a category."""
    query = update.callback_query
    
    category = logic.get_category_by_id(category_id)
    success = logic.delete_category(category_id)
    
    if success:
        name = category['name'] if category else "Категория"
        await query.edit_message_text(
            messages.MESSAGE_CATEGORY_DELETED.format(name=logic.escape_markdown(name)),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка удаления",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    return ADMIN_MENU


async def create_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start category creation flow."""
    await update.message.reply_text(
        messages.MESSAGE_CREATE_CATEGORY_NAME,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    context.user_data[settings.ADMIN_NEW_CATEGORY_DATA_KEY] = {}
    
    return CAT_CREATE_NAME


async def receive_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive category name."""
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text(
            "❌ Название слишком короткое\\. Введите минимум 2 символа:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return CAT_CREATE_NAME
    
    context.user_data[settings.ADMIN_NEW_CATEGORY_DATA_KEY]['name'] = name
    
    await update.message.reply_text(
        messages.MESSAGE_CREATE_CATEGORY_DESCRIPTION,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return CAT_CREATE_DESC


async def receive_category_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive category description."""
    text = update.message.text.strip()
    
    if text == "-":
        description = None
    else:
        description = text
    
    context.user_data[settings.ADMIN_NEW_CATEGORY_DATA_KEY]['description'] = description
    
    await update.message.reply_text(
        messages.MESSAGE_CREATE_CATEGORY_ORDER,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return CAT_CREATE_ORDER


async def receive_category_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive category display order and create category."""
    text = update.message.text.strip()
    
    try:
        display_order = int(text)
    except ValueError:
        display_order = 0
    
    cat_data = context.user_data.get(settings.ADMIN_NEW_CATEGORY_DATA_KEY, {})
    
    category_id = logic.create_category(
        name=cat_data.get('name', 'Unnamed'),
        description=cat_data.get('description'),
        display_order=display_order
    )
    
    if category_id:
        await update.message.reply_text(
            messages.MESSAGE_CATEGORY_CREATED.format(name=logic.escape_markdown(cat_data.get('name', ''))),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Ошибка создания категории",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
    
    context.user_data.pop(settings.ADMIN_NEW_CATEGORY_DATA_KEY, None)
    
    return ADMIN_MENU


# ============================================================================
# Question Management
# ============================================================================

async def show_questions_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show questions list."""
    questions = logic.get_all_questions()
    
    if not questions:
        await update.message.reply_text(
            messages.MESSAGE_NO_QUESTIONS_ADMIN,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_questions_keyboard()
        )
        return Q_LIST  # Changed from ADMIN_MENU to Q_LIST
    
    await update.message.reply_text(
        "❓ *Вопросы*",
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_questions_list_keyboard(questions)
    )
    
    # Also show reply keyboard for add/search buttons
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=keyboards.get_admin_questions_keyboard()
    )
    
    return Q_LIST


async def show_questions_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show questions list (callback version)."""
    query = update.callback_query
    questions = logic.get_all_questions()
    
    if not questions:
        await query.edit_message_text(
            messages.MESSAGE_NO_QUESTIONS_ADMIN,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        # Send reply keyboard
        await query.message.reply_text(
            "Выберите действие:",
            reply_markup=keyboards.get_admin_questions_keyboard()
        )
        return Q_LIST  # Already was correct, but ensure consistency
    
    await query.edit_message_text(
        "❓ *Вопросы*",
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_questions_list_keyboard(questions)
    )
    
    # Send reply keyboard
    await query.message.reply_text(
        "Выберите действие:",
        reply_markup=keyboards.get_admin_questions_keyboard()
    )
    
    return Q_LIST


async def show_questions_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> int:
    """Show specific page of questions list."""
    query = update.callback_query
    questions = logic.get_all_questions()
    
    await query.edit_message_reply_markup(
        reply_markup=keyboards.get_questions_list_keyboard(questions, page=page)
    )
    
    return Q_LIST


async def show_question_details(update: Update, context: ContextTypes.DEFAULT_TYPE, question_id: int) -> int:
    """Show question details."""
    query = update.callback_query
    question = logic.get_question_by_id(question_id)
    
    if not question:
        await query.edit_message_text(
            "❌ Вопрос не найден",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    status = "✅ Активен" if question['active'] else "❌ Неактивен"
    difficulty = settings.DIFFICULTY_LABELS.get(question['difficulty'], question['difficulty'])
    
    # Format categories
    if question.get('categories'):
        categories_str = ", ".join(logic.escape_markdown(c['name']) for c in question['categories'])
    else:
        categories_str = "—"
    
    # Format relevance date
    rel_date = question['relevance_date']
    if isinstance(rel_date, str):
        relevance_str = logic.escape_markdown(rel_date)
    else:
        relevance_str = rel_date.strftime('%d\\.%m\\.%Y')
    
    message = messages.MESSAGE_QUESTION_DETAILS.format(
        id=question_id,
        question_text=logic.escape_markdown(question['question_text']),
        option_a=logic.escape_markdown(question['option_a']),
        option_b=logic.escape_markdown(question['option_b']),
        option_c=logic.escape_markdown(question['option_c']),
        option_d=logic.escape_markdown(question['option_d']),
        correct_option=settings.ANSWER_EMOJIS.get(question['correct_option'], question['correct_option']),
        explanation=logic.escape_markdown(question['explanation'] or "—"),
        difficulty=difficulty,
        categories=categories_str,
        relevance_date=relevance_str,
        status=status
    )
    
    await query.edit_message_text(
        message,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_question_actions_keyboard(question_id, question['active'])
    )
    
    return Q_VIEW


async def receive_question_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive and save edited question field value."""
    text = update.message.text
    q_id = context.user_data.get(settings.ADMIN_EDITING_QUESTION_KEY)
    field = context.user_data.get("edit_field")
    
    if not q_id or not field:
        await update.message.reply_text(
            "❌ Ошибка: данные редактирования потеряны",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    # Handle /skip for explanation field
    if field == "explanation" and text == "/skip":
        text = None
    
    # Update the question field
    success = logic.update_question_field(q_id, field, text)
    
    if success:
        await update.message.reply_text(
            "✅ *Поле успешно обновлено\\!*",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        # Show question details again
        question = logic.get_question_by_id(q_id)
        if question:
            status = "✅ Активен" if question['active'] else "❌ Неактивен"
            difficulty = settings.DIFFICULTY_LABELS.get(question['difficulty'], question['difficulty'])
            
            if question.get('categories'):
                categories_str = ", ".join(logic.escape_markdown(c['name']) for c in question['categories'])
            else:
                categories_str = "—"
            
            rel_date = question['relevance_date']
            if isinstance(rel_date, str):
                relevance_str = logic.escape_markdown(rel_date)
            else:
                relevance_str = rel_date.strftime('%d\\.%m\\.%Y')
            
            message = messages.MESSAGE_QUESTION_DETAILS.format(
                id=q_id,
                question_text=logic.escape_markdown(question['question_text']),
                option_a=logic.escape_markdown(question['option_a']),
                option_b=logic.escape_markdown(question['option_b']),
                option_c=logic.escape_markdown(question['option_c']),
                option_d=logic.escape_markdown(question['option_d']),
                correct_option=settings.ANSWER_EMOJIS.get(question['correct_option'], question['correct_option']),
                explanation=logic.escape_markdown(question['explanation'] or "—"),
                difficulty=difficulty,
                categories=categories_str,
                relevance_date=relevance_str,
                status=status
            )
            
            await update.message.reply_text(
                message,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboards.get_question_actions_keyboard(q_id, question['active'])
            )
    else:
        await update.message.reply_text(
            "❌ Ошибка сохранения",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    # Clean up
    context.user_data.pop("edit_field", None)
    
    return Q_VIEW


async def receive_question_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle correct answer or difficulty selection during edit."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    q_id = context.user_data.get(settings.ADMIN_EDITING_QUESTION_KEY)
    field = context.user_data.get("edit_field")
    
    if not q_id or not field:
        await query.edit_message_text(
            "❌ Ошибка: данные редактирования потеряны",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    # Determine the value based on callback
    value = None
    if field == "correct_option" and data.startswith("cert_correct_"):
        value = data.replace("cert_correct_", "")
    elif field == "difficulty" and data.startswith("cert_diff_"):
        value = data.replace("cert_diff_", "")
    
    if value:
        success = logic.update_question_field(q_id, field, value)
        
        if success:
            await query.edit_message_text(
                "✅ *Поле успешно обновлено\\!*",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        else:
            await query.edit_message_text(
                "❌ Ошибка сохранения",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
    
    # Clean up
    context.user_data.pop("edit_field", None)
    
    # Return to question details
    return await show_question_details(update, context, q_id)


async def toggle_question_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int) -> int:
    """Toggle category selection for question being edited."""
    query = update.callback_query
    
    q_id = context.user_data.get(settings.ADMIN_EDITING_QUESTION_KEY)
    selected = context.user_data.get('editing_question_categories', [])
    
    if category_id in selected:
        selected.remove(category_id)
    else:
        selected.append(category_id)
    
    context.user_data['editing_question_categories'] = selected
    
    categories = logic.get_all_categories(active_only=True)
    
    await query.edit_message_reply_markup(
        reply_markup=keyboards.get_category_edit_multiselect_keyboard(categories, selected, q_id)
    )
    
    return Q_EDIT_CATEGORIES


async def save_question_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save updated question categories."""
    query = update.callback_query
    await query.answer()
    
    q_id = context.user_data.get(settings.ADMIN_EDITING_QUESTION_KEY)
    selected = context.user_data.get('editing_question_categories', [])
    
    if not q_id:
        await query.edit_message_text(
            "❌ Ошибка: данные редактирования потеряны",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    success = logic.update_question(q_id, category_ids=selected)
    
    if success:
        await query.edit_message_text(
            "✅ *Категории обновлены\\!*",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка сохранения категорий",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    # Clean up
    context.user_data.pop('editing_question_categories', None)
    
    # Return to question details
    return await show_question_details(update, context, q_id)


async def toggle_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question_id: int) -> int:
    """Toggle question active status."""
    query = update.callback_query
    
    new_status = logic.toggle_question_active(question_id)
    
    if new_status is None:
        await query.answer("❌ Ошибка", show_alert=True)
        return Q_VIEW
    
    status_text = "✅ Активен" if new_status else "❌ Неактивен"
    await query.answer(f"Статус изменен: {status_text}")
    
    return await show_question_details(update, context, question_id)


async def confirm_delete_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question_id: int) -> int:
    """Show delete confirmation for question."""
    query = update.callback_query
    
    await query.edit_message_text(
        messages.MESSAGE_CONFIRM_DELETE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_confirmation_keyboard(
            f"cert_q_confirm_delete_{question_id}",
            "cert_q_list"
        )
    )
    
    return Q_CONFIRM_DELETE


async def delete_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question_id: int) -> int:
    """Delete a question."""
    query = update.callback_query
    
    success = logic.delete_question(question_id)
    
    if success:
        await query.edit_message_text(
            messages.MESSAGE_QUESTION_DELETED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка удаления",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    return ADMIN_MENU


# ============================================================================
# Question Creation Flow
# ============================================================================

async def create_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start question creation flow."""
    await update.message.reply_text(
        messages.MESSAGE_CREATE_QUESTION_TEXT,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY] = {}
    
    return Q_CREATE_TEXT


async def receive_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive question text."""
    text = update.message.text.strip()
    
    if len(text) < 10:
        await update.message.reply_text(
            messages.MESSAGE_QUESTION_TOO_SHORT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_CREATE_TEXT
    
    context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY]['question_text'] = text
    
    await update.message.reply_text(
        messages.MESSAGE_CREATE_QUESTION_OPTION_A,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return Q_CREATE_OPT_A


async def receive_option_a(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive option A."""
    text = update.message.text.strip()
    
    if len(text) < 1:
        await update.message.reply_text(
            messages.MESSAGE_OPTION_TOO_SHORT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_CREATE_OPT_A
    
    context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY]['option_a'] = text
    
    await update.message.reply_text(
        messages.MESSAGE_CREATE_QUESTION_OPTION_B,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return Q_CREATE_OPT_B


async def receive_option_b(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive option B."""
    text = update.message.text.strip()
    
    if len(text) < 1:
        await update.message.reply_text(
            messages.MESSAGE_OPTION_TOO_SHORT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_CREATE_OPT_B
    
    context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY]['option_b'] = text
    
    await update.message.reply_text(
        messages.MESSAGE_CREATE_QUESTION_OPTION_C,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return Q_CREATE_OPT_C


async def receive_option_c(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive option C."""
    text = update.message.text.strip()
    
    if len(text) < 1:
        await update.message.reply_text(
            messages.MESSAGE_OPTION_TOO_SHORT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_CREATE_OPT_C
    
    context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY]['option_c'] = text
    
    await update.message.reply_text(
        messages.MESSAGE_CREATE_QUESTION_OPTION_D,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return Q_CREATE_OPT_D


async def receive_option_d(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive option D."""
    text = update.message.text.strip()
    
    if len(text) < 1:
        await update.message.reply_text(
            messages.MESSAGE_OPTION_TOO_SHORT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_CREATE_OPT_D
    
    context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY]['option_d'] = text
    
    await update.message.reply_text(
        messages.MESSAGE_CREATE_QUESTION_CORRECT,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_correct_answer_keyboard()
    )
    
    return Q_CREATE_CORRECT


async def receive_correct_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, answer: str) -> int:
    """Receive correct answer selection."""
    query = update.callback_query
    
    context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY]['correct_option'] = answer
    
    await query.edit_message_text(
        messages.MESSAGE_CREATE_QUESTION_EXPLANATION,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return Q_CREATE_EXPLANATION


async def receive_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive explanation."""
    text = update.message.text.strip()
    
    if text == "-":
        explanation = None
    else:
        explanation = text
    
    context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY]['explanation'] = explanation
    
    await update.message.reply_text(
        messages.MESSAGE_CREATE_QUESTION_DIFFICULTY,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_difficulty_keyboard()
    )
    
    return Q_CREATE_DIFFICULTY


async def receive_difficulty(update: Update, context: ContextTypes.DEFAULT_TYPE, difficulty: str) -> int:
    """Receive difficulty selection."""
    query = update.callback_query
    
    context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY]['difficulty'] = difficulty
    
    # Get categories for selection
    categories = logic.get_all_categories(active_only=True)
    context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY]['selected_categories'] = []
    
    if categories:
        await query.edit_message_text(
            messages.MESSAGE_CREATE_QUESTION_CATEGORIES,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_category_multiselect_keyboard(categories, [])
        )
        return Q_CREATE_CATEGORIES
    else:
        # No categories, skip to relevance
        await query.edit_message_text(
            messages.MESSAGE_CREATE_QUESTION_RELEVANCE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return Q_CREATE_RELEVANCE


async def toggle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int) -> int:
    """Toggle category selection for new question."""
    query = update.callback_query
    
    selected = context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY].get('selected_categories', [])
    
    if category_id in selected:
        selected.remove(category_id)
    else:
        selected.append(category_id)
    
    context.user_data[settings.ADMIN_NEW_QUESTION_DATA_KEY]['selected_categories'] = selected
    
    categories = logic.get_all_categories(active_only=True)
    
    await query.edit_message_reply_markup(
        reply_markup=keyboards.get_category_multiselect_keyboard(categories, selected)
    )
    
    return Q_CREATE_CATEGORIES


async def finish_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finish category selection and move to relevance date."""
    query = update.callback_query
    
    await query.edit_message_text(
        messages.MESSAGE_CREATE_QUESTION_RELEVANCE,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return Q_CREATE_RELEVANCE


async def receive_relevance_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive relevance date and create question."""
    text = update.message.text.strip()
    
    relevance_date = None
    relevance_months = None
    
    # Try parsing as number of months
    try:
        months = int(text)
        if 1 <= months <= 120:
            relevance_months = months
    except ValueError:
        # Try parsing as date
        try:
            relevance_date = datetime.strptime(text, "%d.%m.%Y").date()
        except ValueError:
            await update.message.reply_text(
                messages.MESSAGE_INVALID_DATE_FORMAT,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return Q_CREATE_RELEVANCE
    
    # Create the question
    q_data = context.user_data.get(settings.ADMIN_NEW_QUESTION_DATA_KEY, {})
    
    question_id = logic.create_question(
        question_text=q_data.get('question_text', ''),
        option_a=q_data.get('option_a', ''),
        option_b=q_data.get('option_b', ''),
        option_c=q_data.get('option_c', ''),
        option_d=q_data.get('option_d', ''),
        correct_option=q_data.get('correct_option', 'A'),
        explanation=q_data.get('explanation'),
        difficulty=q_data.get('difficulty', 'medium'),
        relevance_months=relevance_months,
        relevance_date=relevance_date,
        category_ids=q_data.get('selected_categories', [])
    )
    
    if question_id:
        await update.message.reply_text(
            messages.MESSAGE_QUESTION_CREATED,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Ошибка создания вопроса",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
    
    context.user_data.pop(settings.ADMIN_NEW_QUESTION_DATA_KEY, None)
    
    return ADMIN_MENU


async def receive_relevance_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive new relevance date for existing question."""
    text = update.message.text.strip()
    question_id = context.user_data.get(settings.ADMIN_EDITING_QUESTION_KEY)
    
    if not question_id:
        return ADMIN_MENU
    
    # Try parsing
    try:
        months = int(text)
        if 1 <= months <= 120:
            new_date = date.today() + relativedelta(months=months)
        else:
            raise ValueError("Invalid months")
    except ValueError:
        try:
            new_date = datetime.strptime(text, "%d.%m.%Y").date()
        except ValueError:
            await update.message.reply_text(
                messages.MESSAGE_INVALID_DATE_FORMAT,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return Q_UPDATE_RELEVANCE
    
    success = logic.update_question(question_id, relevance_date=new_date)
    
    if success:
        await update.message.reply_text(
            messages.MESSAGE_RELEVANCE_UPDATED.format(date=new_date.strftime('%d\\.%m\\.%Y')),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Ошибка обновления",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
    
    context.user_data.pop(settings.ADMIN_EDITING_QUESTION_KEY, None)
    
    return ADMIN_MENU


# ============================================================================
# Outdated Questions
# ============================================================================

async def show_outdated_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show list of outdated questions."""
    questions = logic.get_outdated_questions()
    
    if not questions:
        await update.message.reply_text(
            messages.MESSAGE_NO_OUTDATED_QUESTIONS,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    
    await update.message.reply_text(
        f"⚠️ *Устаревшие вопросы* \\({len(questions)}\\)",
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_outdated_questions_keyboard(questions)
    )
    
    return OUTDATED_LIST


async def update_all_outdated(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Update relevance date for all outdated questions."""
    query = update.callback_query
    
    count = logic.update_all_outdated_relevance()
    
    if count > 0:
        await query.edit_message_text(
            f"✅ Обновлено вопросов: {count}",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        await query.edit_message_text(
            "❌ Нет вопросов для обновления",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    return ADMIN_MENU


# ============================================================================
# Settings
# ============================================================================

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show certification settings."""
    test_settings = logic.get_test_settings()
    
    show_correct_text = "✅ Да" if test_settings['show_correct_answer'] else "❌ Нет"
    obfuscate_text = "✅ Да" if test_settings['obfuscate_names'] else "❌ Нет"
    
    message = messages.MESSAGE_CERTIFICATION_SETTINGS.format(
        questions_count=test_settings['questions_count'],
        time_limit=test_settings['time_limit_minutes'],
        passing_score=test_settings['passing_score_percent'],
        show_correct=show_correct_text,
        obfuscate_names=obfuscate_text
    )
    
    await update.message.reply_text(
        message,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_settings_keyboard(
            test_settings['show_correct_answer'],
            test_settings['obfuscate_names']
        )
    )
    
    return SETTINGS_MENU


async def receive_questions_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive new questions count setting."""
    text = update.message.text.strip()
    
    try:
        count = int(text)
        if not 1 <= count <= 100:
            raise ValueError("Invalid range")
    except ValueError:
        await update.message.reply_text(
            messages.MESSAGE_INVALID_NUMBER,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return SETTINGS_QUESTIONS_COUNT
    
    logic.set_setting(settings.DB_SETTING_QUESTIONS_COUNT, count, "Number of questions per test")
    
    await update.message.reply_text(
        messages.MESSAGE_SETTING_UPDATED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_MENU


async def receive_time_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive new time limit setting."""
    text = update.message.text.strip()
    
    try:
        minutes = int(text)
        if not 1 <= minutes <= 120:
            raise ValueError("Invalid range")
    except ValueError:
        await update.message.reply_text(
            messages.MESSAGE_INVALID_NUMBER,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return SETTINGS_TIME_LIMIT
    
    logic.set_setting(settings.DB_SETTING_TIME_LIMIT, minutes, "Time limit in minutes")
    
    await update.message.reply_text(
        messages.MESSAGE_SETTING_UPDATED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_MENU


async def receive_passing_score(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive new passing score setting."""
    text = update.message.text.strip()
    
    try:
        score = int(text)
        if not 1 <= score <= 100:
            raise ValueError("Invalid range")
    except ValueError:
        await update.message.reply_text(
            messages.MESSAGE_INVALID_NUMBER,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return SETTINGS_PASSING_SCORE
    
    logic.set_setting(settings.DB_SETTING_PASSING_SCORE, score, "Passing score percentage")
    
    await update.message.reply_text(
        messages.MESSAGE_SETTING_UPDATED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    
    return ADMIN_MENU


# ============================================================================
# Search
# ============================================================================

async def search_question_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start question search."""
    await update.message.reply_text(
        messages.MESSAGE_SEARCH_QUESTION,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    # Store that we're in search mode
    context.user_data['cert_search_mode'] = True
    
    return Q_LIST


async def search_question_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive search query and show results."""
    if not context.user_data.get('cert_search_mode'):
        return ADMIN_MENU
    
    context.user_data.pop('cert_search_mode', None)
    
    query = update.message.text.strip()
    questions = logic.search_questions(query)
    
    if not questions:
        await update.message.reply_text(
            messages.MESSAGE_NO_SEARCH_RESULTS,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_admin_questions_keyboard()
        )
        return ADMIN_MENU
    
    await update.message.reply_text(
        f"🔍 *Результаты поиска* \\({len(questions)}\\)",
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_questions_list_keyboard(questions)
    )
    
    return Q_LIST


# ============================================================================
# Cancel Handler
# ============================================================================

async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel admin operation."""
    # Clear admin context
    context.user_data.pop(settings.ADMIN_NEW_QUESTION_DATA_KEY, None)
    context.user_data.pop(settings.ADMIN_NEW_CATEGORY_DATA_KEY, None)
    context.user_data.pop(settings.ADMIN_EDITING_QUESTION_KEY, None)
    context.user_data.pop(settings.ADMIN_EDITING_CATEGORY_KEY, None)
    context.user_data.pop('cert_search_mode', None)
    
    is_admin = check_if_user_admin(update.effective_user.id)
    await update.message.reply_text(
        messages.MESSAGE_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard(is_admin=is_admin)
    )
    
    return ConversationHandler.END


async def back_to_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Go back to certification submenu from admin panel."""
    # Clear admin context
    context.user_data.pop(settings.ADMIN_NEW_QUESTION_DATA_KEY, None)
    context.user_data.pop(settings.ADMIN_NEW_CATEGORY_DATA_KEY, None)
    context.user_data.pop(settings.ADMIN_EDITING_QUESTION_KEY, None)
    context.user_data.pop(settings.ADMIN_EDITING_CATEGORY_KEY, None)
    context.user_data.pop('cert_search_mode', None)
    
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


async def back_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Go back to admin menu from questions/categories submenu."""
    # Clear admin context
    context.user_data.pop(settings.ADMIN_NEW_QUESTION_DATA_KEY, None)
    context.user_data.pop(settings.ADMIN_NEW_CATEGORY_DATA_KEY, None)
    context.user_data.pop(settings.ADMIN_EDITING_QUESTION_KEY, None)
    context.user_data.pop(settings.ADMIN_EDITING_CATEGORY_KEY, None)
    context.user_data.pop('cert_search_mode', None)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_admin_menu_keyboard()
    )
    return ADMIN_MENU


# ============================================================================
# Conversation Handler Builder
# ============================================================================

def get_admin_conversation_handler() -> ConversationHandler:
    """
    Build and return the admin conversation handler.
    
    Returns:
        ConversationHandler for admin panel
    """
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^⚙️ Управление$"), admin_command),
        ],
        states={
            ADMIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_"),
            ],
            # Category states
            CAT_LIST: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_"),
                MessageHandler(filters.Regex("^➕ Добавить категорию$"), create_category_start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
            ],
            CAT_VIEW: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_"),
            ],
            CAT_CREATE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_name),
            ],
            CAT_CREATE_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_description),
            ],
            CAT_CREATE_ORDER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_order),
            ],
            CAT_EDIT_NAME: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_cat_edit_"),
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_cat_view_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_edit),
            ],
            CAT_EDIT_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_edit),
            ],
            CAT_CONFIRM_DELETE: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_"),
            ],
            # Question states
            Q_LIST: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_"),
                MessageHandler(filters.Regex("^➕ Добавить вопрос$"), create_question_start),
                MessageHandler(filters.Regex("^🔍 Найти вопрос$"), search_question_start),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
            ],
            Q_VIEW: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_"),
            ],
            Q_EDIT_FIELD: [
                CallbackQueryHandler(receive_question_edit_callback, pattern="^cert_correct_"),
                CallbackQueryHandler(receive_question_edit_callback, pattern="^cert_diff_"),
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_q_view_"),
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_q_edit_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question_edit),
            ],
            Q_CREATE_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question_text),
            ],
            Q_CREATE_OPT_A: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_a),
            ],
            Q_CREATE_OPT_B: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_b),
            ],
            Q_CREATE_OPT_C: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_c),
            ],
            Q_CREATE_OPT_D: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_option_d),
            ],
            Q_CREATE_CORRECT: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_correct_"),
            ],
            Q_CREATE_EXPLANATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_explanation),
            ],
            Q_CREATE_DIFFICULTY: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_diff_"),
            ],
            Q_CREATE_CATEGORIES: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_catsel_"),
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_cancel$"),
            ],
            Q_CREATE_RELEVANCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_relevance_date),
            ],
            Q_EDIT_CATEGORIES: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_q_cat_"),
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_q_view_"),
            ],
            Q_CONFIRM_DELETE: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_"),
            ],
            Q_UPDATE_RELEVANCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_relevance_update),
            ],
            # Settings states
            SETTINGS_MENU: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_"),
            ],
            SETTINGS_QUESTIONS_COUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_questions_count),
            ],
            SETTINGS_TIME_LIMIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time_limit),
            ],
            SETTINGS_PASSING_SCORE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_passing_score),
            ],
            # Outdated questions
            OUTDATED_LIST: [
                CallbackQueryHandler(admin_callback_handler, pattern="^cert_"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_admin),
            MessageHandler(filters.Regex("^🏠 Главное меню$"), cancel_admin),
            MessageHandler(filters.Regex("^🔙 Назад$"), back_to_submenu),
            MessageHandler(filters.Regex("^🔙 Админ меню$"), back_to_admin_menu),
        ],
        name="certification_admin",
        persistent=False,
        allow_reentry=True
    )
