"""
Admin Panel Bot Part

Handles admin-only commands for managing validation rules,
ticket types, rule-type associations, and test templates.
"""

import logging
from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, 
    ConversationHandler, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    filters
)

from src.common.telegram_user import check_if_user_legit, check_if_user_admin, update_user_info_from_telegram
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE, MESSAGE_MAIN_MENU, get_main_menu_keyboard

# Import module-specific messages and keyboards
from . import messages
from .keyboards import (
    get_admin_menu_keyboard,
    get_admin_rules_keyboard,
    get_admin_templates_keyboard,
)
from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import (
    load_all_rules,
    load_rule_by_id,
    load_all_ticket_types_admin,
    create_validation_rule,
    update_validation_rule,
    toggle_rule_active,
    delete_validation_rule,
    get_rules_for_ticket_type,
    get_ticket_types_for_rule,
    add_rule_to_ticket_type,
    remove_rule_from_ticket_type,
    test_regex_pattern,
    # Test template functions
    create_test_template,
    update_test_template,
    delete_test_template,
    toggle_test_template_active,
    load_test_template_by_id,
    list_all_test_templates,
    set_template_rule_expectation,
    remove_template_rule_expectation,
    get_template_rule_expectations,
    get_rules_not_in_template,
    run_template_validation_test,
    run_all_template_tests
)

logger = logging.getLogger(__name__)

# Conversation states
(
    ADMIN_MENU,
    CREATE_RULE_NAME,
    CREATE_RULE_TYPE,
    CREATE_RULE_PATTERN,
    CREATE_RULE_ERROR_MSG,
    CREATE_RULE_PRIORITY,
    SELECT_RULE_FOR_ACTION,
    CONFIRM_DELETE,
    EDIT_RULE_FIELD,
    EDIT_RULE_VALUE,
    SELECT_TICKET_TYPE,
    MANAGE_TYPE_RULES,
    SELECT_RULE_FOR_TYPE,
    TEST_REGEX_PATTERN,
    TEST_REGEX_TEXT,
    # Template management states
    TEMPLATES_MENU,
    CREATE_TEMPLATE_NAME,
    CREATE_TEMPLATE_TEXT,
    CREATE_TEMPLATE_DESC,
    CREATE_TEMPLATE_EXPECTED,
    SELECT_TEMPLATE_FOR_ACTION,
    MANAGE_TEMPLATE_RULES,
    SELECT_RULE_FOR_TEMPLATE,
    SELECT_RULE_EXPECTATION,
) = range(24)

# Rule types for selection
RULE_TYPES = ['regex', 'required_field', 'format', 'length', 'custom']


def escape_markdown(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    if text is None:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = str(text).replace(char, f'\\{char}')
    return text


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for /admin command.
    Shows admin menu if user is authorized admin.
    """
    # Check if user is legitimate
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    update_user_info_from_telegram(update.effective_user)
    
    # Check if user is admin
    if not check_if_user_admin(update.effective_user.id):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_NOT_AUTHORIZED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_admin_menu_keyboard()
    )
    return ADMIN_MENU


async def admin_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle admin menu button presses."""
    text = update.message.text
    
    # Re-check admin status
    if not check_if_user_admin(update.effective_user.id):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_NOT_AUTHORIZED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    if text == "📋 Список правил" or text == "📋 Все правила":
        return await show_rules_list(update, context)
    elif text == "➕ Создать правило":
        return await start_create_rule(update, context)
    elif text == "📁 Типы заявок":
        return await show_ticket_types(update, context)
    elif text == "🔬 Тест regex":
        return await start_test_regex(update, context)
    elif text == "🧪 Тест шаблоны":
        return await show_templates_menu(update, context)
    elif text == "📋 Все шаблоны":
        return await show_templates_list(update, context)
    elif text == "➕ Создать шаблон":
        return await start_create_template(update, context)
    elif text == "▶️ Запустить все тесты":
        return await run_all_tests(update, context)
    elif text == "🔙 Админ меню":
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    elif text == "🏠 Главное меню":
        await update.message.reply_text(
            MESSAGE_MAIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_INVALID_INPUT,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU


# ===== RULES LIST =====

async def show_rules_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display list of all validation rules with inline buttons."""
    try:
        rules = load_all_rules(include_inactive=True)
        
        if not rules:
            await update.message.reply_text(
                "📋 *Список правил пуст*\n\nСоздайте первое правило с помощью кнопки ➕",
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_admin_rules_keyboard()
            )
            return ADMIN_MENU
        
        # Build inline keyboard with rules
        keyboard = []
        for rule in rules:
            status = "✅" if rule.active else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {rule.rule_name} (ID:{rule.id})",
                    callback_data=f"rule_view_{rule.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_back")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📋 *Список правил валидации*\n\nВсего правил: {len(rules)}\n\nНажмите на правило для управления:",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup
        )
        return SELECT_RULE_FOR_ACTION
        
    except Exception as e:
        logger.error(f"Error loading rules list: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при загрузке списка правил\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU


async def handle_rule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle inline button callbacks for rule management."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "admin_back":
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    elif data.startswith("rule_view_"):
        rule_id = int(data.replace("rule_view_", ""))
        return await show_rule_details(query, context, rule_id)
    
    elif data.startswith("rule_toggle_"):
        rule_id = int(data.replace("rule_toggle_", ""))
        return await toggle_rule(query, context, rule_id)
    
    elif data.startswith("rule_delete_"):
        rule_id = int(data.replace("rule_delete_", ""))
        return await confirm_delete_rule(query, context, rule_id)
    
    elif data.startswith("rule_confirm_delete_"):
        rule_id = int(data.replace("rule_confirm_delete_", ""))
        return await execute_delete_rule(query, context, rule_id)
    
    elif data == "rule_cancel_delete":
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_OPERATION_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    elif data.startswith("rule_types_"):
        rule_id = int(data.replace("rule_types_", ""))
        return await show_rule_ticket_types(query, context, rule_id)
    
    elif data.startswith("type_view_"):
        type_id = int(data.replace("type_view_", ""))
        return await show_ticket_type_rules(query, context, type_id)
    
    elif data.startswith("type_add_rule_"):
        type_id = int(data.replace("type_add_rule_", ""))
        context.user_data['manage_type_id'] = type_id
        return await show_available_rules_for_type(query, context, type_id)
    
    elif data.startswith("type_remove_rule_"):
        parts = data.replace("type_remove_rule_", "").split("_")
        type_id = int(parts[0])
        rule_id = int(parts[1])
        return await remove_rule_from_type(query, context, type_id, rule_id)
    
    elif data.startswith("add_rule_to_type_"):
        parts = data.replace("add_rule_to_type_", "").split("_")
        type_id = int(parts[0])
        rule_id = int(parts[1])
        return await add_rule_to_type(query, context, type_id, rule_id)
    
    elif data == "types_back":
        return await show_ticket_types_inline(query, context)
    
    return ADMIN_MENU


async def show_rule_details(query, context: ContextTypes.DEFAULT_TYPE, rule_id: int) -> int:
    """Show detailed information about a rule."""
    try:
        rule = load_rule_by_id(rule_id)
        if not rule:
            await query.edit_message_text("❌ Правило не найдено\\.")
            return ADMIN_MENU
        
        # Get ticket types using this rule
        ticket_types = get_ticket_types_for_rule(rule_id)
        types_text = "\n".join([f"• {escape_markdown(t.type_name)}" for t in ticket_types]) if ticket_types else "Не назначено"
        
        status = "✅ Активно" if rule.active else "❌ Неактивно"
        toggle_text = "❌ Отключить" if rule.active else "✅ Включить"
        
        rule_type_value = rule.rule_type.value if hasattr(rule.rule_type, 'value') else rule.rule_type
        
        message = messages.MESSAGE_ADMIN_RULE_DETAILS.format(
            name=escape_markdown(rule.rule_name),
            id=rule.id,
            rule_type=escape_markdown(rule_type_value),
            pattern=escape_markdown(rule.pattern),
            error_message=escape_markdown(rule.error_message),
            priority=rule.priority,
            status=status,
            ticket_types=types_text
        )
        
        keyboard = [
            [
                InlineKeyboardButton(toggle_text, callback_data=f"rule_toggle_{rule_id}"),
                InlineKeyboardButton("🗑️ Удалить", callback_data=f"rule_delete_{rule_id}")
            ],
            [InlineKeyboardButton("📁 Типы заявок", callback_data=f"rule_types_{rule_id}")],
            [InlineKeyboardButton("🔙 К списку правил", callback_data="admin_back")]
        ]
        
        await query.edit_message_text(
            message,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_RULE_FOR_ACTION
        
    except Exception as e:
        logger.error(f"Error showing rule details: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка при загрузке правила\\.")
        return ADMIN_MENU


async def toggle_rule(query, context: ContextTypes.DEFAULT_TYPE, rule_id: int) -> int:
    """Toggle rule active status."""
    try:
        rule = load_rule_by_id(rule_id)
        if not rule:
            await query.edit_message_text("❌ Правило не найдено\\.")
            return ADMIN_MENU
        
        new_status = not rule.active
        success = toggle_rule_active(rule_id, new_status)
        
        if success:
            status_text = "включено" if new_status else "отключено"
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_RULE_TOGGLED.format(
                    name=escape_markdown(rule.rule_name),
                    status=status_text
                ),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        else:
            await query.edit_message_text("❌ Ошибка при обновлении правила\\.")
        
        return ADMIN_MENU
        
    except Exception as e:
        logger.error(f"Error toggling rule: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка при обновлении правила\\.")
        return ADMIN_MENU


async def confirm_delete_rule(query, context: ContextTypes.DEFAULT_TYPE, rule_id: int) -> int:
    """Show confirmation dialog for rule deletion."""
    try:
        rule = load_rule_by_id(rule_id)
        if not rule:
            await query.edit_message_text("❌ Правило не найдено\\.")
            return ADMIN_MENU
        
        ticket_types = get_ticket_types_for_rule(rule_id)
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"rule_confirm_delete_{rule_id}"),
                InlineKeyboardButton("❌ Отмена", callback_data="rule_cancel_delete")
            ]
        ]
        
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_CONFIRM_DELETE.format(
                name=escape_markdown(rule.rule_name),
                count=len(ticket_types)
            ),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CONFIRM_DELETE
        
    except Exception as e:
        logger.error(f"Error confirming delete: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка\\.")
        return ADMIN_MENU


async def execute_delete_rule(query, context: ContextTypes.DEFAULT_TYPE, rule_id: int) -> int:
    """Execute rule deletion."""
    try:
        rule = load_rule_by_id(rule_id)
        if not rule:
            await query.edit_message_text("❌ Правило не найдено\\.")
            return ADMIN_MENU
        
        rule_name = rule.rule_name
        success, deleted_associations = delete_validation_rule(rule_id)
        
        if success:
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_RULE_DELETED.format(
                    name=escape_markdown(rule_name),
                    associations=deleted_associations
                ),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        else:
            await query.edit_message_text("❌ Ошибка при удалении правила\\.")
        
        return ADMIN_MENU
        
    except Exception as e:
        logger.error(f"Error deleting rule: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка при удалении правила\\.")
        return ADMIN_MENU


# ===== CREATE RULE =====

async def start_create_rule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start rule creation wizard."""
    context.user_data['new_rule'] = {}
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_RULE_NAME,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_admin_rules_keyboard()
    )
    return CREATE_RULE_NAME


async def receive_rule_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive rule name from user."""
    text = update.message.text
    
    if text in ["🏠 Главное меню", "🔙 Админ меню"]:
        return await handle_cancel(update, context, text)
    
    if len(text) < 3:
        await update.message.reply_text(
            "❌ Название должно содержать минимум 3 символа\\. Попробуйте снова:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return CREATE_RULE_NAME
    
    context.user_data['new_rule']['name'] = text
    
    # Show rule type selection
    keyboard = []
    for rule_type in RULE_TYPES:
        keyboard.append([InlineKeyboardButton(rule_type, callback_data=f"ruletype_{rule_type}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_create")])
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_RULE_TYPE,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CREATE_RULE_TYPE


async def handle_rule_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle rule type selection callback."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cancel_create":
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_OPERATION_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU
    
    if data.startswith("ruletype_"):
        rule_type = data.replace("ruletype_", "")
        context.user_data['new_rule']['type'] = rule_type
        
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_CREATE_RULE_PATTERN,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return CREATE_RULE_PATTERN
    
    return CREATE_RULE_TYPE


async def receive_rule_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive rule pattern from user."""
    text = update.message.text
    
    if text in ["🏠 Главное меню", "🔙 Админ меню"]:
        return await handle_cancel(update, context, text)
    
    rule_type = context.user_data['new_rule'].get('type', 'regex')
    
    # Validate pattern if it's a regex
    if rule_type == 'regex':
        is_valid, message = test_regex_pattern(text)
        if not is_valid:
            await update.message.reply_text(
                f"❌ Некорректное регулярное выражение: {escape_markdown(message)}\n\nПопробуйте снова:",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return CREATE_RULE_PATTERN
    
    context.user_data['new_rule']['pattern'] = text
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_RULE_ERROR_MSG,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return CREATE_RULE_ERROR_MSG


async def receive_rule_error_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive error message from user."""
    text = update.message.text
    
    if text in ["🏠 Главное меню", "🔙 Админ меню"]:
        return await handle_cancel(update, context, text)
    
    if len(text) < 5:
        await update.message.reply_text(
            "❌ Сообщение должно содержать минимум 5 символов\\. Попробуйте снова:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return CREATE_RULE_ERROR_MSG
    
    context.user_data['new_rule']['error_message'] = text
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_RULE_PRIORITY,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return CREATE_RULE_PRIORITY


async def receive_rule_priority(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive priority and create the rule."""
    text = update.message.text
    
    if text in ["🏠 Главное меню", "🔙 Админ меню"]:
        return await handle_cancel(update, context, text)
    
    try:
        priority = int(text)
        if priority < 0 or priority > 100:
            raise ValueError("Priority out of range")
    except ValueError:
        await update.message.reply_text(
            "❌ Введите число от 0 до 100\\. Попробуйте снова:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return CREATE_RULE_PRIORITY
    
    # Create the rule
    new_rule = context.user_data.get('new_rule', {})
    
    try:
        rule_id = create_validation_rule(
            rule_name=new_rule['name'],
            pattern=new_rule['pattern'],
            rule_type=new_rule['type'],
            error_message=new_rule['error_message'],
            priority=priority
        )
        
        if rule_id:
            await update.message.reply_text(
                messages.MESSAGE_ADMIN_RULE_CREATED.format(name=escape_markdown(new_rule['name'])),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_admin_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Ошибка при создании правила\\.",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        
    except Exception as e:
        logger.error(f"Error creating rule: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при создании правила\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    # Clear user data
    context.user_data.pop('new_rule', None)
    return ADMIN_MENU


# ===== TICKET TYPES =====

async def show_ticket_types(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show list of ticket types for rule management."""
    try:
        ticket_types = load_all_ticket_types_admin(include_inactive=True)
        
        if not ticket_types:
            await update.message.reply_text(
                "📁 *Типы заявок не найдены*",
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_admin_menu_keyboard()
            )
            return ADMIN_MENU
        
        keyboard = []
        for tt in ticket_types:
            status = "✅" if tt.active else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {tt.type_name}",
                    callback_data=f"type_view_{tt.id}"
                )
            ])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_back")])
        
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_SELECT_TICKET_TYPE,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_TICKET_TYPE
        
    except Exception as e:
        logger.error(f"Error loading ticket types: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при загрузке типов заявок\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ADMIN_MENU


async def show_ticket_types_inline(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show ticket types via inline query."""
    try:
        ticket_types = load_all_ticket_types_admin(include_inactive=True)
        
        keyboard = []
        for tt in ticket_types:
            status = "✅" if tt.active else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {tt.type_name}",
                    callback_data=f"type_view_{tt.id}"
                )
            ])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_back")])
        
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_SELECT_TICKET_TYPE,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_TICKET_TYPE
        
    except Exception as e:
        logger.error(f"Error loading ticket types: {e}", exc_info=True)
        return ADMIN_MENU


async def show_ticket_type_rules(query, context: ContextTypes.DEFAULT_TYPE, type_id: int) -> int:
    """Show rules assigned to a ticket type."""
    try:
        ticket_types = load_all_ticket_types_admin(include_inactive=True)
        ticket_type = next((t for t in ticket_types if t.id == type_id), None)
        
        if not ticket_type:
            await query.edit_message_text("❌ Тип заявки не найден\\.")
            return ADMIN_MENU
        
        rules = get_rules_for_ticket_type(type_id)
        
        if rules:
            rules_text = "\n".join([
                f"{'✅' if r.active else '❌'} {escape_markdown(r.rule_name)} \\(ID:{r.id}\\)" 
                for r in rules
            ])
        else:
            rules_text = "Нет назначенных правил"
        
        keyboard = []
        # Add remove buttons for existing rules
        for rule in rules:
            keyboard.append([
                InlineKeyboardButton(
                    f"➖ {rule.rule_name}",
                    callback_data=f"type_remove_rule_{type_id}_{rule.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("➕ Добавить правило", callback_data=f"type_add_rule_{type_id}")])
        keyboard.append([InlineKeyboardButton("🔙 К типам заявок", callback_data="types_back")])
        
        message = messages.MESSAGE_ADMIN_TICKET_TYPE_RULES.format(
            type_name=escape_markdown(ticket_type.type_name),
            rules=rules_text
        )
        
        await query.edit_message_text(
            message,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MANAGE_TYPE_RULES
        
    except Exception as e:
        logger.error(f"Error showing type rules: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка\\.")
        return ADMIN_MENU


async def show_available_rules_for_type(query, context: ContextTypes.DEFAULT_TYPE, type_id: int) -> int:
    """Show available rules to add to a ticket type."""
    try:
        all_rules = load_all_rules(include_inactive=True)
        assigned_rules = get_rules_for_ticket_type(type_id)
        assigned_ids = {r.id for r in assigned_rules}
        
        available_rules = [r for r in all_rules if r.id not in assigned_ids]
        
        if not available_rules:
            await query.answer("Все правила уже добавлены к этому типу", show_alert=True)
            return await show_ticket_type_rules(query, context, type_id)
        
        keyboard = []
        for rule in available_rules:
            keyboard.append([
                InlineKeyboardButton(
                    f"➕ {rule.rule_name}",
                    callback_data=f"add_rule_to_type_{type_id}_{rule.id}"
                )
            ])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"type_view_{type_id}")])
        
        await query.edit_message_text(
            "Выберите правило для добавления:",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_RULE_FOR_TYPE
        
    except Exception as e:
        logger.error(f"Error showing available rules: {e}", exc_info=True)
        return ADMIN_MENU


async def add_rule_to_type(query, context: ContextTypes.DEFAULT_TYPE, type_id: int, rule_id: int) -> int:
    """Add a rule to a ticket type."""
    try:
        success = add_rule_to_ticket_type(rule_id, type_id)
        
        if success:
            rule = load_rule_by_id(rule_id)
            
            await query.answer(
                f"Правило {rule.rule_name if rule else 'ID:'+str(rule_id)} добавлено!",
                show_alert=True
            )
        else:
            await query.answer("Правило уже добавлено", show_alert=True)
        
        return await show_ticket_type_rules(query, context, type_id)
        
    except Exception as e:
        logger.error(f"Error adding rule to type: {e}", exc_info=True)
        await query.answer("Ошибка", show_alert=True)
        return ADMIN_MENU


async def remove_rule_from_type(query, context: ContextTypes.DEFAULT_TYPE, type_id: int, rule_id: int) -> int:
    """Remove a rule from a ticket type."""
    try:
        success = remove_rule_from_ticket_type(rule_id, type_id)
        
        if success:
            await query.answer("Правило удалено из типа", show_alert=True)
        else:
            await query.answer("Ошибка при удалении", show_alert=True)
        
        return await show_ticket_type_rules(query, context, type_id)
        
    except Exception as e:
        logger.error(f"Error removing rule from type: {e}", exc_info=True)
        await query.answer("Ошибка", show_alert=True)
        return ADMIN_MENU


async def show_rule_ticket_types(query, context: ContextTypes.DEFAULT_TYPE, rule_id: int) -> int:
    """Show which ticket types use a specific rule."""
    try:
        rule = load_rule_by_id(rule_id)
        if not rule:
            await query.edit_message_text("❌ Правило не найдено\\.")
            return ADMIN_MENU
        
        assigned_types = get_ticket_types_for_rule(rule_id)
        all_types = load_all_ticket_types_admin(include_inactive=True)
        assigned_ids = {t.id for t in assigned_types}
        
        keyboard = []
        
        # Show assigned types with remove option
        for tt in assigned_types:
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ {tt.type_name} (убрать)",
                    callback_data=f"type_remove_rule_{tt.id}_{rule_id}"
                )
            ])
        
        # Show unassigned types with add option
        for tt in all_types:
            if tt.id not in assigned_ids:
                keyboard.append([
                    InlineKeyboardButton(
                        f"➕ {tt.type_name}",
                        callback_data=f"add_rule_to_type_{tt.id}_{rule_id}"
                    )
                ])
        
        keyboard.append([InlineKeyboardButton("🔙 К правилу", callback_data=f"rule_view_{rule_id}")])
        
        await query.edit_message_text(
            f"📁 *Типы заявок для правила: {escape_markdown(rule.rule_name)}*\n\n"
            f"Назначено типов: {len(assigned_types)}",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MANAGE_TYPE_RULES
        
    except Exception as e:
        logger.error(f"Error showing rule ticket types: {e}", exc_info=True)
        return ADMIN_MENU


# ===== TEST REGEX =====

async def start_test_regex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start regex testing wizard."""
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_TEST_REGEX,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_admin_rules_keyboard()
    )
    return TEST_REGEX_PATTERN


async def receive_test_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive regex pattern for testing."""
    text = update.message.text
    
    if text in ["🏠 Главное меню", "🔙 Админ меню"]:
        return await handle_cancel(update, context, text)
    
    # Validate the pattern first
    is_valid, message = test_regex_pattern(text)
    
    if not is_valid:
        await update.message.reply_text(
            f"❌ {escape_markdown(message)}\n\nВведите корректный паттерн:",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return TEST_REGEX_PATTERN
    
    context.user_data['test_pattern'] = text
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_TEST_REGEX_SAMPLE.format(pattern=escape_markdown(text)),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return TEST_REGEX_TEXT


async def receive_test_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive test text and show results."""
    text = update.message.text
    
    if text in ["🏠 Главное меню", "🔙 Админ меню"]:
        return await handle_cancel(update, context, text)
    
    pattern = context.user_data.get('test_pattern', '')
    
    _, result = test_regex_pattern(pattern, text)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_TEST_REGEX_RESULT.format(
            pattern=escape_markdown(pattern),
            result=escape_markdown(result)
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_admin_menu_keyboard()
    )
    
    context.user_data.pop('test_pattern', None)
    return ADMIN_MENU


# ===== TEST TEMPLATES MANAGEMENT =====

async def show_templates_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display test templates menu."""
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_TEMPLATES_MENU,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_admin_templates_keyboard()
    )
    return TEMPLATES_MENU


async def show_templates_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display list of all test templates with inline buttons."""
    try:
        templates = list_all_test_templates(include_inactive=True)
        
        if not templates:
            await update.message.reply_text(
                messages.MESSAGE_ADMIN_NO_TEMPLATES,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_admin_templates_keyboard()
            )
            return TEMPLATES_MENU
        
        # Build inline keyboard with templates
        keyboard = []
        for template in templates:
            status = "✅" if template['active'] else "❌"
            expected = "✓" if template['expected_result'] == 'pass' else "✗"
            rule_count = template.get('rule_count', 0)
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} [{expected}] {template['template_name']} ({rule_count} правил)",
                    callback_data=f"template_view_{template['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="templates_back")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_TEMPLATES_LIST.format(count=len(templates)),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup
        )
        return SELECT_TEMPLATE_FOR_ACTION
        
    except Exception as e:
        logger.error(f"Error loading templates list: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при загрузке списка шаблонов\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return TEMPLATES_MENU


async def handle_template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle inline button callbacks for template management."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "templates_back":
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_TEMPLATES_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return TEMPLATES_MENU
    
    elif data.startswith("template_view_"):
        template_id = int(data.replace("template_view_", ""))
        return await show_template_details(query, context, template_id)
    
    elif data.startswith("template_toggle_"):
        template_id = int(data.replace("template_toggle_", ""))
        return await toggle_template(query, context, template_id)
    
    elif data.startswith("template_delete_"):
        template_id = int(data.replace("template_delete_", ""))
        return await confirm_delete_template(query, context, template_id)
    
    elif data.startswith("template_confirm_delete_"):
        template_id = int(data.replace("template_confirm_delete_", ""))
        return await execute_delete_template(query, context, template_id)
    
    elif data == "template_cancel_delete":
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_OPERATION_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return TEMPLATES_MENU
    
    elif data.startswith("template_rules_"):
        template_id = int(data.replace("template_rules_", ""))
        return await show_template_rules(query, context, template_id)
    
    elif data.startswith("template_add_rule_"):
        template_id = int(data.replace("template_add_rule_", ""))
        context.user_data['manage_template_id'] = template_id
        return await show_available_rules_for_template(query, context, template_id)
    
    elif data.startswith("template_remove_rule_"):
        parts = data.replace("template_remove_rule_", "").split("_")
        template_id = int(parts[0])
        rule_id = int(parts[1])
        return await remove_rule_from_template(query, context, template_id, rule_id)
    
    elif data.startswith("add_rule_to_template_"):
        parts = data.replace("add_rule_to_template_", "").split("_")
        template_id = int(parts[0])
        rule_id = int(parts[1])
        context.user_data['pending_rule_id'] = rule_id
        context.user_data['manage_template_id'] = template_id
        return await ask_rule_expectation(query, context, template_id, rule_id)
    
    elif data.startswith("set_expectation_"):
        parts = data.replace("set_expectation_", "").split("_")
        template_id = int(parts[0])
        rule_id = int(parts[1])
        expected_pass = parts[2] == "pass"
        return await set_rule_expectation(query, context, template_id, rule_id, expected_pass)
    
    elif data.startswith("template_test_"):
        template_id = int(data.replace("template_test_", ""))
        return await run_single_template_test(query, context, template_id)
    
    return TEMPLATES_MENU


async def show_template_details(query, context: ContextTypes.DEFAULT_TYPE, template_id: int) -> int:
    """Show detailed information about a template."""
    try:
        template = load_test_template_by_id(template_id)
        if not template:
            await query.edit_message_text("❌ Шаблон не найден\\.")
            return TEMPLATES_MENU
        
        # Get rule expectations
        expectations = get_template_rule_expectations(template_id)
        
        rules_list = ""
        if expectations:
            for exp in expectations:
                exp_icon = "✅" if exp['expected_pass'] else "❌"
                rules_list += f"\n{exp_icon} {escape_markdown(exp['rule_name'])}"
        else:
            rules_list = "Не настроены"
        
        status = "✅ Активен" if template['active'] else "❌ Неактивен"
        toggle_text = "❌ Отключить" if template['active'] else "✅ Включить"
        expected_result = "✅ Должен пройти" if template['expected_result'] == 'pass' else "❌ Должен провалиться"
        ticket_type = template['ticket_type_name'] or "Не указан"
        
        message = messages.MESSAGE_ADMIN_TEMPLATE_DETAILS.format(
            name=escape_markdown(template['template_name']),
            id=template['id'],
            description=escape_markdown(template['description'] or 'Нет описания'),
            ticket_type=escape_markdown(ticket_type),
            expected_result=expected_result,
            status=status,
            rule_count=len(expectations),
            rules_list=rules_list
        )
        
        keyboard = [
            [
                InlineKeyboardButton(toggle_text, callback_data=f"template_toggle_{template_id}"),
                InlineKeyboardButton("🗑️ Удалить", callback_data=f"template_delete_{template_id}")
            ],
            [InlineKeyboardButton("📋 Управление правилами", callback_data=f"template_rules_{template_id}")],
            [InlineKeyboardButton("▶️ Запустить тест", callback_data=f"template_test_{template_id}")],
            [InlineKeyboardButton("🔙 К списку шаблонов", callback_data="templates_back")]
        ]
        
        await query.edit_message_text(
            message,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_TEMPLATE_FOR_ACTION
        
    except Exception as e:
        logger.error(f"Error showing template details: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка при загрузке шаблона\\.")
        return TEMPLATES_MENU


async def toggle_template(query, context: ContextTypes.DEFAULT_TYPE, template_id: int) -> int:
    """Toggle template active status."""
    try:
        template = load_test_template_by_id(template_id)
        if not template:
            await query.edit_message_text("❌ Шаблон не найден\\.")
            return TEMPLATES_MENU
        
        new_status = not template['active']
        success = toggle_test_template_active(template_id, new_status)
        
        if success:
            status_text = "включен" if new_status else "отключен"
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_TEMPLATE_TOGGLED.format(
                    name=escape_markdown(template['template_name']),
                    status=status_text
                ),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        else:
            await query.edit_message_text("❌ Ошибка при изменении статуса\\.")
        
        return TEMPLATES_MENU
        
    except Exception as e:
        logger.error(f"Error toggling template: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка при изменении статуса\\.")
        return TEMPLATES_MENU


async def confirm_delete_template(query, context: ContextTypes.DEFAULT_TYPE, template_id: int) -> int:
    """Ask for confirmation before deleting template."""
    try:
        template = load_test_template_by_id(template_id)
        if not template:
            await query.edit_message_text("❌ Шаблон не найден\\.")
            return TEMPLATES_MENU
        
        expectations = get_template_rule_expectations(template_id)
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да, удалить", callback_data=f"template_confirm_delete_{template_id}"),
                InlineKeyboardButton("❌ Отмена", callback_data="template_cancel_delete")
            ]
        ]
        
        await query.edit_message_text(
            f"⚠️ Вы уверены, что хотите удалить шаблон *{escape_markdown(template['template_name'])}*?\n\n"
            f"Это удалит все настроенные ожидания правил \\({len(expectations)} ожиданий\\)\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_TEMPLATE_FOR_ACTION
        
    except Exception as e:
        logger.error(f"Error confirming template delete: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка\\.")
        return TEMPLATES_MENU


async def execute_delete_template(query, context: ContextTypes.DEFAULT_TYPE, template_id: int) -> int:
    """Actually delete the template."""
    try:
        template = load_test_template_by_id(template_id)
        template_name = template['template_name'] if template else "Неизвестный"
        
        success, expectations_count = delete_test_template(template_id)
        
        if success:
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_TEMPLATE_DELETED.format(
                    name=escape_markdown(template_name),
                    expectations=expectations_count
                ),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        else:
            await query.edit_message_text("❌ Ошибка при удалении шаблона\\.")
        
        return TEMPLATES_MENU
        
    except Exception as e:
        logger.error(f"Error deleting template: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка при удалении\\.")
        return TEMPLATES_MENU


async def show_template_rules(query, context: ContextTypes.DEFAULT_TYPE, template_id: int) -> int:
    """Show rules configured for a template with add/remove options."""
    try:
        template = load_test_template_by_id(template_id)
        if not template:
            await query.edit_message_text("❌ Шаблон не найден\\.")
            return TEMPLATES_MENU
        
        expectations = get_template_rule_expectations(template_id)
        
        keyboard = []
        
        if expectations:
            for exp in expectations:
                exp_icon = "✅" if exp['expected_pass'] else "❌"
                keyboard.append([
                    InlineKeyboardButton(
                        f"{exp_icon} {exp['rule_name']} (удалить)",
                        callback_data=f"template_remove_rule_{template_id}_{exp['validation_rule_id']}"
                    )
                ])
        
        keyboard.append([
            InlineKeyboardButton("➕ Добавить правило", callback_data=f"template_add_rule_{template_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 К шаблону", callback_data=f"template_view_{template_id}")
        ])
        
        message = f"📋 *Правила шаблона: {escape_markdown(template['template_name'])}*\n\n"
        if expectations:
            message += f"Настроено правил: {len(expectations)}\n\n"
            message += "✅ \\= правило должно пройти\n❌ \\= правило должно провалиться\n\n"
            message += "Нажмите на правило чтобы удалить:"
        else:
            message += "Правила не настроены\\. Добавьте правила для тестирования\\."
        
        await query.edit_message_text(
            message,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return MANAGE_TEMPLATE_RULES
        
    except Exception as e:
        logger.error(f"Error showing template rules: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка\\.")
        return TEMPLATES_MENU


async def show_available_rules_for_template(query, context: ContextTypes.DEFAULT_TYPE, template_id: int) -> int:
    """Show rules that can be added to a template."""
    try:
        template = load_test_template_by_id(template_id)
        if not template:
            await query.edit_message_text("❌ Шаблон не найден\\.")
            return TEMPLATES_MENU
        
        available_rules = get_rules_not_in_template(template_id)
        
        if not available_rules:
            await query.edit_message_text(
                "Все активные правила уже добавлены к этому шаблону\\.",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return MANAGE_TEMPLATE_RULES
        
        keyboard = []
        for rule in available_rules:
            keyboard.append([
                InlineKeyboardButton(
                    f"{rule.rule_name}",
                    callback_data=f"add_rule_to_template_{template_id}_{rule.id}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("🔙 Назад", callback_data=f"template_rules_{template_id}")
        ])
        
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_ADD_RULE_TO_TEMPLATE.format(
                template_name=escape_markdown(template['template_name'])
            ),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_RULE_FOR_TEMPLATE
        
    except Exception as e:
        logger.error(f"Error showing available rules: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка\\.")
        return TEMPLATES_MENU


async def ask_rule_expectation(query, context: ContextTypes.DEFAULT_TYPE, template_id: int, rule_id: int) -> int:
    """Ask what the expected result should be for this rule."""
    try:
        rule = load_rule_by_id(rule_id)
        if not rule:
            await query.edit_message_text("❌ Правило не найдено\\.")
            return TEMPLATES_MENU
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Должно пройти", callback_data=f"set_expectation_{template_id}_{rule_id}_pass"),
                InlineKeyboardButton("❌ Должно провалиться", callback_data=f"set_expectation_{template_id}_{rule_id}_fail")
            ],
            [InlineKeyboardButton("🔙 Отмена", callback_data=f"template_rules_{template_id}")]
        ]
        
        await query.edit_message_text(
            messages.MESSAGE_ADMIN_SELECT_EXPECTATION.format(rule_name=escape_markdown(rule.rule_name)),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_RULE_EXPECTATION
        
    except Exception as e:
        logger.error(f"Error asking rule expectation: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка\\.")
        return TEMPLATES_MENU


async def set_rule_expectation(query, context: ContextTypes.DEFAULT_TYPE, 
                               template_id: int, rule_id: int, expected_pass: bool) -> int:
    """Set the expected result for a rule on a template."""
    try:
        rule = load_rule_by_id(rule_id)
        rule_name = rule.rule_name if rule else "Неизвестное"
        
        success = set_template_rule_expectation(template_id, rule_id, expected_pass)
        
        if success:
            expectation = "должно пройти" if expected_pass else "должно провалиться"
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_RULE_EXPECTATION_SET.format(
                    rule_name=escape_markdown(rule_name),
                    expectation=expectation
                ),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        else:
            await query.edit_message_text("❌ Ошибка при добавлении правила\\.")
        
        # Clean up
        context.user_data.pop('pending_rule_id', None)
        
        return TEMPLATES_MENU
        
    except Exception as e:
        logger.error(f"Error setting rule expectation: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка\\.")
        return TEMPLATES_MENU


async def remove_rule_from_template(query, context: ContextTypes.DEFAULT_TYPE, 
                                    template_id: int, rule_id: int) -> int:
    """Remove a rule expectation from a template."""
    try:
        rule = load_rule_by_id(rule_id)
        rule_name = rule.rule_name if rule else "Неизвестное"
        
        success = remove_template_rule_expectation(template_id, rule_id)
        
        if success:
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_RULE_EXPECTATION_REMOVED.format(
                    rule_name=escape_markdown(rule_name)
                ),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        else:
            await query.edit_message_text("❌ Ошибка при удалении правила\\.")
        
        return TEMPLATES_MENU
        
    except Exception as e:
        logger.error(f"Error removing rule from template: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка\\.")
        return TEMPLATES_MENU


async def run_single_template_test(query, context: ContextTypes.DEFAULT_TYPE, template_id: int) -> int:
    """Run validation test for a single template."""
    try:
        admin_userid = query.from_user.id
        result = run_template_validation_test(template_id, admin_userid)
        
        if 'error' in result:
            await query.edit_message_text(
                f"⚠️ *Ошибка*: {escape_markdown(result['error'])}",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return TEMPLATES_MENU
        
        if result['overall_pass']:
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_TEST_RESULT_PASS.format(
                    template_name=escape_markdown(result['template_name']),
                    passed=result['rules_passed_as_expected'],
                    total=result['total_rules_tested']
                ),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        else:
            # Build mismatches list
            mismatches = ""
            for detail in result['details']:
                if not detail['matches_expectation']:
                    expected = "пройти" if detail['expected_pass'] else "провалиться"
                    actual = "прошло" if detail['actual_pass'] else "провалилось"
                    mismatches += f"\n• {escape_markdown(detail['rule_name'])}: ожидалось {expected}, {actual}"
            
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_TEST_RESULT_FAIL.format(
                    template_name=escape_markdown(result['template_name']),
                    passed=result['rules_passed_as_expected'],
                    failed=result['rules_failed_unexpectedly'],
                    total=result['total_rules_tested'],
                    mismatches=mismatches
                ),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        
        return TEMPLATES_MENU
        
    except Exception as e:
        logger.error(f"Error running template test: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка при запуске теста\\.")
        return TEMPLATES_MENU


async def run_all_tests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Run all template validation tests."""
    try:
        admin_userid = update.effective_user.id
        
        # Send "running" message
        await update.message.reply_text(
            "🧪 *Запуск всех тестов\\.\\.\\.*",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        
        results = run_all_template_tests(admin_userid)
        
        if not results['results']:
            await update.message.reply_text(
                messages.MESSAGE_ADMIN_NO_TEMPLATES,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_admin_templates_keyboard()
            )
            return TEMPLATES_MENU
        
        # Format results
        passed = results['templates_passed']
        failed = results['templates_failed']
        total = results['total_templates']
        
        if failed == 0:
            status_emoji = "✅"
            status_text = "Все тесты пройдены\\!"
        else:
            status_emoji = "❌"
            status_text = f"Провалено тестов: {failed}"
        
        response = f"{status_emoji} *Результаты тестирования*\n\n"
        response += f"📊 Всего шаблонов: {total}\n"
        response += f"✅ Пройдено: {passed}\n"
        response += f"❌ Провалено: {failed}\n\n"
        response += f"*{status_text}*\n\n"
        
        # Add details for each template
        response += "*Детали:*\n"
        for r in results['results']:
            template_name = escape_markdown(r['template_name'])
            if 'error' in r:
                response += f"⚠️ {template_name}: {escape_markdown(r['error'])}\n"
            elif r['overall_pass']:
                response += f"✅ {template_name}: {r['rules_passed']}/{r['rules_passed'] + r['rules_failed']} правил\n"
            else:
                response += f"❌ {template_name}: {r['rules_passed']}/{r['rules_passed'] + r['rules_failed']} правил \\({r['rules_failed']} провалено\\)\n"
        
        await update.message.reply_text(
            response,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_admin_templates_keyboard()
        )
        return TEMPLATES_MENU
        
    except Exception as e:
        logger.error(f"Error running all tests: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при запуске тестов\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return TEMPLATES_MENU


# ===== CREATE TEMPLATE =====

async def start_create_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the template creation process."""
    context.user_data['new_template'] = {}
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_TEMPLATE_NAME,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_admin_templates_keyboard()
    )
    return CREATE_TEMPLATE_NAME


async def receive_template_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive template name."""
    text = update.message.text
    
    if text in ["🏠 Главное меню", "🔙 Админ меню"]:
        return await handle_cancel(update, context, text)
    
    context.user_data['new_template']['name'] = text
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_TEMPLATE_TEXT,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return CREATE_TEMPLATE_TEXT


async def receive_template_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive template text (sample ticket)."""
    text = update.message.text
    
    if text in ["🏠 Главное меню", "🔙 Админ меню"]:
        return await handle_cancel(update, context, text)
    
    context.user_data['new_template']['text'] = text
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_TEMPLATE_DESC,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return CREATE_TEMPLATE_DESC


async def receive_template_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive template description."""
    text = update.message.text
    
    if text in ["🏠 Главное меню", "🔙 Админ меню"]:
        return await handle_cancel(update, context, text)
    
    context.user_data['new_template']['description'] = text
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Должен пройти (pass)", callback_data="template_expected_pass"),
            InlineKeyboardButton("❌ Должен провалиться (fail)", callback_data="template_expected_fail")
        ]
    ]
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_CREATE_TEMPLATE_EXPECTED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CREATE_TEMPLATE_EXPECTED


async def handle_template_expected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle expected result selection for new template."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    expected_result = 'pass' if data == "template_expected_pass" else 'fail'
    
    # Create the template
    template_data = context.user_data.get('new_template', {})
    
    try:
        template_id = create_test_template(
            template_name=template_data.get('name', ''),
            template_text=template_data.get('text', ''),
            description=template_data.get('description', ''),
            expected_result=expected_result
        )
        
        if template_id:
            await query.edit_message_text(
                messages.MESSAGE_ADMIN_TEMPLATE_CREATED.format(
                    name=escape_markdown(template_data.get('name', ''))
                ),
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        else:
            await query.edit_message_text("❌ Ошибка при создании шаблона\\.")
        
    except Exception as e:
        logger.error(f"Error creating template: {e}", exc_info=True)
        await query.edit_message_text("❌ Ошибка при создании шаблона\\.")
    
    context.user_data.pop('new_template', None)
    return TEMPLATES_MENU


# ===== CANCEL AND HELPERS =====

async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> int:
    """Handle cancel/navigation buttons during conversation."""
    # Clear any ongoing operation data
    context.user_data.pop('new_rule', None)
    context.user_data.pop('test_pattern', None)
    context.user_data.pop('manage_type_id', None)
    context.user_data.pop('new_template', None)
    context.user_data.pop('manage_template_id', None)
    
    if text == "🏠 Главное меню":
        await update.message.reply_text(
            MESSAGE_MAIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    elif text == "🔙 Админ меню":
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_MENU,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_admin_menu_keyboard()
        )
        return ADMIN_MENU
    
    return ADMIN_MENU


async def cancel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel admin conversation."""
    context.user_data.pop('new_rule', None)
    context.user_data.pop('test_pattern', None)
    context.user_data.pop('manage_type_id', None)
    context.user_data.pop('new_template', None)
    context.user_data.pop('manage_template_id', None)
    
    await update.message.reply_text(
        messages.MESSAGE_ADMIN_OPERATION_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END


# Build the conversation handler
def get_admin_conversation_handler() -> ConversationHandler:
    """Build and return the admin panel ConversationHandler."""
    
    # Common handler for menu buttons that can be pressed in any state
    menu_buttons_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler)
    
    return ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin_command),
            MessageHandler(filters.Regex("^🔐 Админ панель$"), admin_command),
            MessageHandler(filters.Regex("^🧪 Тест шаблонов$"), show_templates_menu_from_submenu)
        ],
        states={
            ADMIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_rule_callback)
            ],
            CREATE_RULE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rule_name)
            ],
            CREATE_RULE_TYPE: [
                CallbackQueryHandler(handle_rule_type_callback),
                menu_buttons_handler  # Allow menu navigation
            ],
            CREATE_RULE_PATTERN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rule_pattern)
            ],
            CREATE_RULE_ERROR_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rule_error_msg)
            ],
            CREATE_RULE_PRIORITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rule_priority)
            ],
            SELECT_RULE_FOR_ACTION: [
                CallbackQueryHandler(handle_rule_callback),
                menu_buttons_handler  # Allow menu navigation
            ],
            CONFIRM_DELETE: [
                CallbackQueryHandler(handle_rule_callback),
                menu_buttons_handler  # Allow menu navigation
            ],
            SELECT_TICKET_TYPE: [
                CallbackQueryHandler(handle_rule_callback),
                menu_buttons_handler  # Allow menu navigation
            ],
            MANAGE_TYPE_RULES: [
                CallbackQueryHandler(handle_rule_callback),
                menu_buttons_handler  # Allow menu navigation
            ],
            SELECT_RULE_FOR_TYPE: [
                CallbackQueryHandler(handle_rule_callback),
                menu_buttons_handler  # Allow menu navigation
            ],
            TEST_REGEX_PATTERN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_test_pattern)
            ],
            TEST_REGEX_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_test_text)
            ],
            # Template management states
            TEMPLATES_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_handler),
                CallbackQueryHandler(handle_template_callback)
            ],
            CREATE_TEMPLATE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_template_name)
            ],
            CREATE_TEMPLATE_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_template_text)
            ],
            CREATE_TEMPLATE_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_template_desc)
            ],
            CREATE_TEMPLATE_EXPECTED: [
                CallbackQueryHandler(handle_template_expected_callback),
                menu_buttons_handler  # Allow menu navigation
            ],
            SELECT_TEMPLATE_FOR_ACTION: [
                CallbackQueryHandler(handle_template_callback),
                menu_buttons_handler  # Allow menu navigation
            ],
            MANAGE_TEMPLATE_RULES: [
                CallbackQueryHandler(handle_template_callback),
                menu_buttons_handler  # Allow menu navigation
            ],
            SELECT_RULE_FOR_TEMPLATE: [
                CallbackQueryHandler(handle_template_callback),
                menu_buttons_handler  # Allow menu navigation
            ],
            SELECT_RULE_EXPECTATION: [
                CallbackQueryHandler(handle_template_callback),
                menu_buttons_handler  # Allow menu navigation
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_admin),
            MessageHandler(filters.Regex("^🏠 Главное меню$"), cancel_admin)
        ],
        name="admin_panel",
        persistent=False
    )


async def show_templates_menu_from_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for test templates from validator submenu."""
    # Check if user is admin
    if not check_if_user_admin(update.effective_user.id):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_NOT_AUTHORIZED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    return await show_templates_menu(update, context)
