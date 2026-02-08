"""
Ticket Validator Bot Handlers

Telegram bot handlers for ticket validation functionality.
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram import constants
import logging

from src.common.telegram_user import check_if_user_legit, check_if_user_admin, update_user_info_from_telegram
from src.common.messages import (
    MESSAGE_PLEASE_ENTER_INVITE,
    BUTTON_MODULES,
    BUTTON_SETTINGS,
    BUTTON_UPOS_ERRORS,
    BUTTON_SCREENSHOT,
    BUTTON_MY_INVITES,
    BUTTON_HELP,
)

# Import module-specific messages, settings, and keyboards
from . import messages
from . import settings
from .keyboards import get_submenu_keyboard, get_admin_submenu_keyboard
from .validation_rules import (
    load_rules_from_db,
    load_all_ticket_types,
    run_all_template_tests
)
from .validators import validate_ticket, detect_ticket_type

# Import settings for menu button patterns
from . import settings as validator_settings

# Set up logging
logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_TICKET = 1

# Debug mode key from settings
DEBUG_MODE_KEY = settings.DEBUG_MODE_KEY


async def validate_ticket_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start ticket validation conversation.
    Handler for /validate command.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        Next conversation state
    """
    # Check if user is authorized
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(
            MESSAGE_PLEASE_ENTER_INVITE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Update user info
    update_user_info_from_telegram(update.effective_user)
    
    # Ask for ticket text
    await update.message.reply_text(
        messages.MESSAGE_SEND_TICKET,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return WAITING_FOR_TICKET


async def process_ticket_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process and validate submitted ticket text.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        ConversationHandler.END to finish conversation
    """
    ticket_text = update.message.text
    user_id = update.effective_user.id
    
    # Debug mode is automatically enabled for all admins
    is_admin = check_if_user_admin(user_id)
    debug_enabled = is_admin
    
    # Load ticket types and detect which type this ticket is
    try:
        ticket_types = load_all_ticket_types()
        detected_type, debug_info = detect_ticket_type(
            ticket_text, 
            ticket_types, 
            debug=True  # Always get debug info to check for ambiguity
        ) if ticket_types else (None, None)
        
        # Send debug info first if enabled
        if debug_enabled and debug_info:
            debug_message = format_debug_info_for_telegram(debug_info)
            await update.message.reply_text(
                debug_message,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        
        # Check for ambiguous detection (multiple types with same score)
        if debug_info and debug_info.has_ambiguity:
            ambiguous_names = ", ".join([_escape_md(tt.type_name) for tt in debug_info.ambiguous_types])
            warning_message = messages.MESSAGE_AMBIGUOUS_TYPE_WARNING.format(
                types=ambiguous_names,
                detected_type=_escape_md(detected_type.type_name)
            )
            await update.message.reply_text(
                warning_message,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
        
        # Check if ticket type was detected
        if not detected_type:
            # Build list of supported ticket types
            supported_types = "\n".join([
                f"• _{_escape_md(tt.type_name)}_"
                for tt in ticket_types
            ]) if ticket_types else messages.MESSAGE_NO_TICKET_TYPES
            
            error_message = messages.MESSAGE_TYPE_NOT_DETECTED.format(types=supported_types)
            
            await update.message.reply_text(
                error_message,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ConversationHandler.END
        
        # Load validation rules for detected type
        rules = load_rules_from_db(ticket_type_id=detected_type.id)
        
        if not rules:
            await update.message.reply_text(
                messages.MESSAGE_NO_RULES_CONFIGURED,
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            return ConversationHandler.END
        
        # Validate the ticket
        result = validate_ticket(ticket_text, rules, detected_ticket_type=detected_type)
        
        # Determine which keyboard to show based on admin status
        reply_keyboard = get_admin_submenu_keyboard() if is_admin else get_submenu_keyboard()
        
        # Send response to user
        if result.is_valid:
            # Format list of passed rules
            passed_rules_text = ""
            if result.passed_rules:
                passed_rules_formatted = "\n".join([
                    f"  ✓ {_escape_md(rule_name)}"
                    for rule_name in result.passed_rules
                ])
                passed_rules_text = f"\n\n📋 *Пройденные проверки:*\n{passed_rules_formatted}"
            
            response = f"✅ *Заявка прошла валидацию\\!*\n\n🎫 Тип заявки: _{_escape_md(detected_type.type_name)}_{passed_rules_text}"
            await update.message.reply_text(
                response,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=reply_keyboard
            )
        else:
            # Format error messages - properly escape all special characters for MarkdownV2
            errors_formatted = "\n".join([
                f"• {_escape_md(msg)}"
                for msg in result.error_messages
            ])
            
            response = messages.MESSAGE_VALIDATION_FAILED.format(errors=errors_formatted)
            # Add detected ticket type to error message
            response = response.replace("*Заявка не прошла валидацию*", 
                                      f"*Заявка не прошла валидацию*\n\n🎫 Тип заявки: _{_escape_md(detected_type.type_name)}_")
            await update.message.reply_text(
                response,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=reply_keyboard
            )
        
    except Exception as e:
        logger.error(f"Error validating ticket: {e}", exc_info=True)
        await update.message.reply_text(
            messages.MESSAGE_VALIDATION_ERROR,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


async def run_test_templates_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Run all validation tests for test templates.
    Admin-only command for testing validation rules.
    
    Args:
        update: Telegram update object
        context: Telegram context
    """
    user_id = update.effective_user.id
    
    # Check if user is authorized
    if not check_if_user_legit(user_id):
        await update.message.reply_text(
            MESSAGE_PLEASE_ENTER_INVITE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Check if user is admin
    if not check_if_user_admin(user_id):
        await update.message.reply_text(
            messages.MESSAGE_ADMIN_NOT_AUTHORIZED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Update user info
    update_user_info_from_telegram(update.effective_user)
    
    try:
        # Send "running tests" message
        await update.message.reply_text(
            messages.MESSAGE_RUNNING_TESTS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        
        # Run all tests
        results = run_all_template_tests(user_id)
        
        if not results['results']:
            await update.message.reply_text(
                messages.MESSAGE_NO_TEST_TEMPLATES,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=get_admin_submenu_keyboard()
            )
            return
        
        # Format results
        passed = results['templates_passed']
        failed = results['templates_failed']
        total = results['total_templates']
        
        if failed == 0:
            status_emoji = "✅"
            status_text = messages.MESSAGE_ADMIN_ALL_TESTS_PASSED
        else:
            status_emoji = "❌"
            status_text = messages.MESSAGE_ADMIN_TESTS_FAILED.format(count=failed)
        
        response = f"{status_emoji} *Результаты тестирования*\n\n"
        response += f"📊 Всего шаблонов: {total}\n"
        response += f"✅ Пройдено: {passed}\n"
        response += f"❌ Провалено: {failed}\n\n"
        response += f"*{status_text}*\n\n"
        
        # Add details for each template
        response += "*Детали:*\n"
        for r in results['results']:
            template_name = _escape_md(r['template_name'])
            if 'error' in r:
                response += f"⚠️ {template_name}: {_escape_md(r['error'])}\n"
            elif r['overall_pass']:
                response += f"✅ {template_name}: {r['rules_passed']}/{r['rules_passed'] + r['rules_failed']} правил\n"
            else:
                response += f"❌ {template_name}: {r['rules_passed']}/{r['rules_passed'] + r['rules_failed']} правил \\({r['rules_failed']} провалено\\)\n"
        
        await update.message.reply_text(
            response,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=get_admin_submenu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error running template tests: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Ошибка при запуске тестов\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show validation help information.
    Handler for /help_validate command.
    
    Args:
        update: Telegram update object
        context: Telegram context
    """
    # Check if user is authorized
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(
            MESSAGE_PLEASE_ENTER_INVITE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Update user info
    update_user_info_from_telegram(update.effective_user)
    
    await update.message.reply_text(
        messages.get_validation_help_message(),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )


async def cancel_validation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel validation conversation.
    Handler for /cancel command during validation.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        ConversationHandler.END
    """
    await update.message.reply_text(
        messages.MESSAGE_VALIDATION_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return ConversationHandler.END


async def cancel_validation_on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel validation conversation when a menu button is pressed.
    Notifies the user and returns END to exit conversation.
    
    Args:
        update: Telegram update object
        context: Telegram context
        
    Returns:
        ConversationHandler.END
    """
    await update.message.reply_text(
        messages.MESSAGE_VALIDATION_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return ConversationHandler.END


async def toggle_debug_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Toggle debug mode for ticket type detection.
    Only available for admin users.
    
    Args:
        update: Telegram update object
        context: Telegram context
    """
    user_id = update.effective_user.id
    
    # Check if user is authorized
    if not check_if_user_legit(user_id):
        await update.message.reply_text(
            MESSAGE_PLEASE_ENTER_INVITE,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Check if user is admin
    if not check_if_user_admin(user_id):
        await update.message.reply_text(
            messages.MESSAGE_DEBUG_MODE_NOT_ADMIN,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Toggle debug mode
    current_state = context.user_data.get(DEBUG_MODE_KEY, False)
    new_state = not current_state
    context.user_data[DEBUG_MODE_KEY] = new_state
    
    if new_state:
        await update.message.reply_text(
            messages.MESSAGE_DEBUG_MODE_ENABLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            messages.MESSAGE_DEBUG_MODE_DISABLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )


def format_debug_info_for_telegram(debug_info) -> str:
    """
    Format DetectionDebugInfo for Telegram message.
    
    Args:
        debug_info: DetectionDebugInfo object
        
    Returns:
        Formatted string safe for MarkdownV2
    """
    lines = []
    lines.append("🔍 *DEBUG: Определение типа заявки*")
    lines.append("")
    
    if debug_info.detected_type:
        lines.append(f"✅ *Определён тип:* {_escape_md(debug_info.detected_type.type_name)}")
    else:
        lines.append("❌ *Тип не определён*")
    
    lines.append(f"📊 Оценено типов: {debug_info.total_types_evaluated}")
    lines.append("")
    lines.append("*Результаты по типам:*")
    
    # Sort by score descending
    sorted_scores = sorted(debug_info.all_scores, key=lambda x: x.total_score, reverse=True)
    
    for score_info in sorted_scores:
        type_name = _escape_md(score_info.ticket_type.type_name)
        # Escape decimal points and minus signs in numeric values
        total_score_str = str(score_info.total_score).replace('.', '\\.').replace('-', '\\-')
        match_pct_str = f"{score_info.match_percentage:.1f}".replace('.', '\\.')
        
        lines.append("")
        lines.append(f"📋 *{type_name}*")
        lines.append(f"   Счёт: {total_score_str}")
        lines.append(f"   Совпало: {score_info.matched_keywords_count}/{score_info.total_keywords_count} \\({match_pct_str}%\\)")
        
        if score_info.keyword_matches:
            lines.append("   Ключевые слова:")
            for match in score_info.keyword_matches[:5]:  # Limit to 5 keywords to avoid too long messages
                keyword = _escape_md(match.keyword)
                weight_str = str(match.weight).replace('.', '\\.')
                score_str = str(match.weighted_score).replace('.', '\\.').replace('-', '\\-')
                # Use different indicator for negative keywords
                indicator = "⊖" if match.is_negative else "⊕"
                lines.append(f"     {indicator} '{keyword}': {match.count}x \\(вес: {weight_str}, счёт: {score_str}\\)")
            if len(score_info.keyword_matches) > 5:
                lines.append(f"     _\\.\\.\\.и ещё {len(score_info.keyword_matches) - 5}_")
    
    return "\n".join(lines)


def _escape_md(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    if text is None:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = str(text).replace(char, f'\\{char}')
    return text


def get_menu_button_regex_pattern() -> str:
    """
    Get regex pattern matching all menu buttons from this module.
    Used to create fallback handlers for ConversationHandler.
    
    Returns:
        Regex pattern string matching all module menu buttons
    """
    import re
    # Collect all buttons from all menu configurations
    all_buttons = set()
    
    for button_row in validator_settings.SUBMENU_BUTTONS:
        all_buttons.update(button_row)
    for button_row in validator_settings.ADMIN_SUBMENU_BUTTONS:
        all_buttons.update(button_row)
    for button_row in validator_settings.ADMIN_MENU_BUTTONS:
        all_buttons.update(button_row)
    for button_row in validator_settings.ADMIN_RULES_BUTTONS:
        all_buttons.update(button_row)
    for button_row in validator_settings.ADMIN_TEMPLATES_BUTTONS:
        all_buttons.update(button_row)
    
    # Add main menu navigation buttons that should also exit the conversation
    all_buttons.add(BUTTON_MODULES)
    all_buttons.add(BUTTON_SETTINGS)
    all_buttons.add(BUTTON_UPOS_ERRORS)
    all_buttons.add(BUTTON_SCREENSHOT)
    all_buttons.add(BUTTON_MY_INVITES)
    all_buttons.add(BUTTON_HELP)
    
    # Remove the validation button itself as it shouldn't cancel itself
    all_buttons.discard(validator_settings.BUTTON_VALIDATE_TICKET)
    
    # Escape special regex characters in button texts
    escaped_buttons = [re.escape(btn) for btn in all_buttons]
    
    # Create pattern matching any of the buttons
    return "^(" + "|".join(escaped_buttons) + ")$"
