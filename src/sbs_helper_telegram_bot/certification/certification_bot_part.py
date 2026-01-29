"""
Employee Certification Module - User Bot Part

Telegram handlers for the user-facing certification functionality:
- Starting and taking tests
- Viewing results and history
- Monthly rankings
"""

import logging
import random
import time
from datetime import datetime
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
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE

from . import settings
from . import messages
from . import keyboards
from . import certification_logic as logic

logger = logging.getLogger(__name__)

# Conversation states
(
    SELECTING_CATEGORY,
    ANSWERING_QUESTION,
    VIEWING_RESULT,
) = range(3)


def obfuscate_name(name: str) -> str:
    """
    Obfuscate a name by keeping only the first letter and replacing rest with dots.
    
    Args:
        name: The name to obfuscate (e.g., "Иван")
        
    Returns:
        Obfuscated name (e.g., "И...")
    """
    if not name:
        return ""
    return f"{name[0]}\\.\\.\\."


def shuffle_question_options(question: dict) -> dict:
    """
    Shuffle the answer options for a question and track the mapping.
    
    Args:
        question: Question dict with option_a, option_b, option_c, option_d, correct_option
        
    Returns:
        Question dict with shuffled_options list and option_mapping dict
    """
    # Create list of (original_letter, option_text) tuples
    options = [
        ('A', question['option_a']),
        ('B', question['option_b']),
        ('C', question['option_c']),
        ('D', question['option_d']),
    ]
    
    # Shuffle the options
    random.shuffle(options)
    
    # Create mapping: displayed_letter -> original_letter
    # e.g., if original B is now shown as A, mapping['A'] = 'B'
    display_letters = ['A', 'B', 'C', 'D']
    option_mapping = {}  # displayed -> original
    shuffled_options = []  # list of option texts in display order
    
    for i, (original_letter, option_text) in enumerate(options):
        display_letter = display_letters[i]
        option_mapping[display_letter] = original_letter
        shuffled_options.append(option_text)
    
    # Store in question
    question['shuffled_options'] = shuffled_options
    question['option_mapping'] = option_mapping
    
    return question


# ============================================================================
# Entry Points and Navigation
# ============================================================================

async def certification_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show certification submenu."""
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


async def start_test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle 'Start Test' button - show category selection."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    # Cancel any existing in-progress attempts
    logic.cancel_user_attempts(update.effective_user.id)
    
    # Check if there are any questions
    questions_count = logic.get_questions_count()
    if questions_count == 0:
        await update.message.reply_text(
            messages.MESSAGE_NO_QUESTIONS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Get test settings
    test_settings = logic.get_test_settings()
    
    # Get active categories
    categories = logic.get_all_categories(active_only=True)
    
    # Show test intro with category selection
    intro_text = messages.MESSAGE_TEST_INTRO.format(
        questions_count=test_settings['questions_count'],
        time_limit=test_settings['time_limit_minutes'],
        passing_score=test_settings['passing_score_percent']
    )
    
    await update.message.reply_text(
        intro_text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_category_selection_keyboard(categories)
    )
    
    return SELECTING_CATEGORY


async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle category selection callback."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cert_cancel":
        await query.edit_message_text(
            messages.MESSAGE_TEST_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    category_id = None
    if data == "cert_start_all":
        category_id = None
    elif data.startswith("cert_start_cat_"):
        category_id = int(data.replace("cert_start_cat_", ""))
    else:
        return SELECTING_CATEGORY
    
    # Get test settings
    test_settings = logic.get_test_settings()
    questions_count = test_settings['questions_count']
    time_limit_minutes = test_settings['time_limit_minutes']
    time_limit_seconds = time_limit_minutes * 60
    passing_score = test_settings['passing_score_percent']
    
    # Get random questions
    questions = logic.get_random_questions(questions_count, category_id)
    
    if not questions:
        await query.edit_message_text(
            messages.MESSAGE_NO_QUESTIONS_IN_CATEGORY,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Create test attempt
    attempt_id = logic.create_test_attempt(
        userid=update.effective_user.id,
        total_questions=len(questions),
        time_limit_seconds=time_limit_seconds,
        category_id=category_id
    )
    
    if not attempt_id:
        await query.edit_message_text(
            "❌ Ошибка создания теста\\. Попробуйте позже\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Store test data in context
    context.user_data[settings.CURRENT_ATTEMPT_ID_KEY] = attempt_id
    # Shuffle options for each question
    shuffled_questions = [shuffle_question_options(q) for q in questions]
    context.user_data[settings.TEST_QUESTIONS_KEY] = shuffled_questions
    context.user_data[settings.CURRENT_QUESTION_INDEX_KEY] = 0
    context.user_data[settings.TEST_START_TIME_KEY] = time.time()
    context.user_data[settings.SELECTED_CATEGORY_KEY] = category_id
    context.user_data[settings.TEST_IN_PROGRESS_KEY] = True
    
    # Show test started message
    await query.edit_message_text(
        messages.MESSAGE_TEST_STARTED.format(
            total_questions=len(questions),
            time_limit=time_limit_minutes,
            passing_score=passing_score
        ),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    # Send first question
    await send_question(update, context, is_callback=True)
    
    return ANSWERING_QUESTION


async def send_question(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    is_callback: bool = False
) -> None:
    """Send current question to user."""
    questions = context.user_data.get(settings.TEST_QUESTIONS_KEY, [])
    current_index = context.user_data.get(settings.CURRENT_QUESTION_INDEX_KEY, 0)
    start_time = context.user_data.get(settings.TEST_START_TIME_KEY, time.time())
    attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
    
    if current_index >= len(questions):
        # Test completed
        await finish_test(update, context, is_callback=is_callback)
        return
    
    # Check time
    attempt = logic.get_attempt_by_id(attempt_id)
    if attempt:
        elapsed = time.time() - start_time
        remaining = attempt['time_limit_seconds'] - int(elapsed)
        
        if remaining <= 0:
            # Time expired
            await finish_test(update, context, status='expired', is_callback=is_callback)
            return
        
        time_remaining_str = logic.format_time_remaining(remaining)
    else:
        time_remaining_str = "--:--"
    
    question = questions[current_index]
    
    # Format question text
    question_text = logic.escape_markdown(question['question_text'])
    
    # Build options text using shuffled options
    shuffled = question.get('shuffled_options', [
        question['option_a'], question['option_b'], 
        question['option_c'], question['option_d']
    ])
    options_text = f"""
🅰️ {logic.escape_markdown(shuffled[0])}
🅱️ {logic.escape_markdown(shuffled[1])}
©️ {logic.escape_markdown(shuffled[2])}
🇩 {logic.escape_markdown(shuffled[3])}"""
    
    full_message = messages.MESSAGE_QUESTION_TEMPLATE.format(
        current=current_index + 1,
        total=len(questions),
        question_text=question_text,
        time_remaining=time_remaining_str
    ) + options_text
    
    # Add time warning if needed
    if attempt and (attempt['time_limit_seconds'] - int(time.time() - start_time)) < 120:
        full_message = messages.MESSAGE_TIME_WARNING + "\n\n" + full_message
    
    if is_callback:
        await update.effective_chat.send_message(
            full_message,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_answer_keyboard()
        )
    else:
        await update.message.reply_text(
            full_message,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_answer_keyboard()
        )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle user's answer to a question."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cert_cancel_test":
        # Cancel test
        attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
        if attempt_id:
            logic.complete_test_attempt(attempt_id, status='cancelled')
        
        # Clear context
        clear_test_context(context)
        
        await query.edit_message_text(
            messages.MESSAGE_TEST_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    if not data.startswith("cert_answer_"):
        return ANSWERING_QUESTION
    
    user_answer = data.replace("cert_answer_", "")
    
    # Check time first
    start_time = context.user_data.get(settings.TEST_START_TIME_KEY, time.time())
    attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
    attempt = logic.get_attempt_by_id(attempt_id)
    
    if attempt:
        elapsed = time.time() - start_time
        if elapsed > attempt['time_limit_seconds']:
            await finish_test(update, context, status='expired', is_callback=True)
            return ConversationHandler.END
    
    # Get current question
    questions = context.user_data.get(settings.TEST_QUESTIONS_KEY, [])
    current_index = context.user_data.get(settings.CURRENT_QUESTION_INDEX_KEY, 0)
    
    if current_index >= len(questions):
        await finish_test(update, context, is_callback=True)
        return ConversationHandler.END
    
    question = questions[current_index]
    correct_option = question['correct_option']
    
    # Map user's displayed answer to original option letter
    option_mapping = question.get('option_mapping', {'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D'})
    original_answer = option_mapping.get(user_answer.upper(), user_answer.upper())
    is_correct = original_answer == correct_option.upper()
    
    # Find which displayed letter corresponds to the correct answer
    # (reverse mapping: original -> displayed)
    displayed_correct = user_answer.upper()  # default
    for displayed, original in option_mapping.items():
        if original == correct_option.upper():
            displayed_correct = displayed
            break
    
    # Save answer (save the original letter for consistency)
    logic.save_answer(
        attempt_id=attempt_id,
        question_id=question['id'],
        question_order=current_index + 1,
        user_answer=original_answer,
        is_correct=is_correct
    )
    
    # Check if we should show correct answer
    test_settings = logic.get_test_settings()
    show_correct = test_settings.get('show_correct_answer', True)
    
    # Move to next question
    context.user_data[settings.CURRENT_QUESTION_INDEX_KEY] = current_index + 1
    
    # Show result or proceed automatically
    if show_correct:
        if is_correct:
            result_text = messages.MESSAGE_ANSWER_CORRECT
        else:
            # Show the displayed letter of the correct answer
            result_text = messages.MESSAGE_ANSWER_INCORRECT.format(
                correct_option=settings.ANSWER_EMOJIS.get(displayed_correct, displayed_correct)
            )
        
        # Add explanation if available
        if question.get('explanation'):
            result_text = messages.MESSAGE_ANSWER_WITH_EXPLANATION.format(
                result=result_text,
                explanation=logic.escape_markdown(question['explanation'])
            )
        
        await query.edit_message_text(
            result_text,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_next_question_keyboard()
        )
        
        return ANSWERING_QUESTION
    else:
        # Auto-proceed to next question without showing result
        new_index = context.user_data.get(settings.CURRENT_QUESTION_INDEX_KEY, 0)
        questions = context.user_data.get(settings.TEST_QUESTIONS_KEY, [])
        
        if new_index >= len(questions):
            # Test finished
            await query.edit_message_text(
                "⏳ Завершаем тест\\.\\.\\.",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            await finish_test(update, context, is_callback=True)
            return ConversationHandler.END
        
        # Delete the old message and send next question
        await query.edit_message_text(
            "⏳ Следующий вопрос\\.\\.\\.",
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        await send_question(update, context, is_callback=True)
        return ANSWERING_QUESTION


async def handle_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle 'Next question' button."""
    query = update.callback_query
    await query.answer()
    
    if query.data != "cert_next_question":
        return ANSWERING_QUESTION
    
    # Check if test is still in progress
    if not context.user_data.get(settings.TEST_IN_PROGRESS_KEY):
        return ConversationHandler.END
    
    questions = context.user_data.get(settings.TEST_QUESTIONS_KEY, [])
    current_index = context.user_data.get(settings.CURRENT_QUESTION_INDEX_KEY, 0)
    
    if current_index >= len(questions):
        await finish_test(update, context, is_callback=True)
        return ConversationHandler.END
    
    await send_question(update, context, is_callback=True)
    return ANSWERING_QUESTION


async def finish_test(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    status: str = 'completed',
    is_callback: bool = False
) -> int:
    """Finish test and show results."""
    attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
    
    if not attempt_id:
        return ConversationHandler.END
    
    # Complete the attempt
    result = logic.complete_test_attempt(attempt_id, status=status)
    
    if not result:
        return ConversationHandler.END
    
    # Format time spent
    time_spent_str = logic.format_time_spent(result['time_spent_seconds'])
    
    # Get rank info
    rank_info = ""
    if result['passed']:
        user_rank = logic.get_user_monthly_rank(update.effective_user.id)
        if user_rank:
            rank_info = messages.MESSAGE_RANK_INFO.format(rank=user_rank['rank'])
        else:
            rank_info = messages.MESSAGE_NO_RANK_YET
    else:
        rank_info = messages.MESSAGE_NO_RANK_YET
    
    # Format status
    if status == 'expired':
        status_text = "⏰ Время истекло"
        message_template = messages.MESSAGE_TIME_EXPIRED
    else:
        status_text = messages.MESSAGE_TEST_PASSED if result['passed'] else messages.MESSAGE_TEST_FAILED
        message_template = messages.MESSAGE_TEST_COMPLETED
    
    # Format score - use integer if whole number, otherwise escape the decimal point
    score = result['score_percent']
    if score == int(score):
        score_str = str(int(score))
    else:
        score_str = str(score).replace('.', '\\.')
    
    result_message = message_template.format(
        correct=result['correct_answers'],
        total=result['total_questions'],
        score=score_str,
        time_spent=time_spent_str,
        status=status_text,
        rank_info=rank_info
    )
    
    # Clear context
    clear_test_context(context)
    
    if is_callback:
        await update.effective_chat.send_message(
            result_message,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            result_message,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    
    return ConversationHandler.END


def clear_test_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear test-related data from context."""
    keys_to_clear = [
        settings.CURRENT_ATTEMPT_ID_KEY,
        settings.TEST_QUESTIONS_KEY,
        settings.CURRENT_QUESTION_INDEX_KEY,
        settings.TEST_START_TIME_KEY,
        settings.SELECTED_CATEGORY_KEY,
        settings.TEST_IN_PROGRESS_KEY,
    ]
    for key in keys_to_clear:
        context.user_data.pop(key, None)


# ============================================================================
# Rankings and History
# ============================================================================

async def show_my_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's ranking and statistics per category for current month."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    now = datetime.now()
    month_name = logic.get_month_name(now.month)
    
    # Get categories where user has tests this month
    user_categories = logic.get_user_categories_this_month(update.effective_user.id)
    
    if not user_categories:
        await update.message.reply_text(
            messages.MESSAGE_NO_TESTS_THIS_MONTH.format(month=logic.escape_markdown(month_name)),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Build message with per-category ratings
    message_parts = [messages.MESSAGE_MY_RANKING_HEADER.format(month=logic.escape_markdown(month_name))]
    
    # Get overall stats for last test info
    user_stats = logic.get_user_stats(update.effective_user.id)
    
    # Add combined rating first (if user has any passed tests)
    combined_rank = logic.get_user_monthly_rank(update.effective_user.id)
    if combined_rank:
        message_parts.append(messages.MESSAGE_MY_RANKING_ALL_ITEM.format(
            rank=combined_rank['rank'],
            best_score=int(combined_rank['best_score']),
            tests_count=combined_rank['tests_count']
        ))
    
    # Add each category's rating
    for cat_info in user_categories:
        # Skip if this is a "full test" (category_id is None) - already shown in combined
        if cat_info['category_id'] is None:
            continue
        
        category_name = cat_info['category_name'] or "Все категории"
        rank = cat_info.get('rank', '—')
        
        message_parts.append(messages.MESSAGE_MY_RANKING_CATEGORY_ITEM.format(
            category=logic.escape_markdown(category_name),
            rank=rank if rank else '—',
            best_score=int(cat_info['best_score']) if cat_info['best_score'] else 0,
            tests_count=cat_info['tests_count']
        ))
    
    # Add footer with last test info
    if user_stats and user_stats['last_test_timestamp']:
        last_test_date = datetime.fromtimestamp(user_stats['last_test_timestamp']).strftime('%d\\.%m\\.%Y')
        message_parts.append(messages.MESSAGE_MY_RANKING_FOOTER.format(
            last_test_date=last_test_date,
            last_test_score=int(user_stats['last_test_score']) if user_stats['last_test_score'] else 0
        ))
    
    await update.message.reply_text(
        "".join(message_parts),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )


async def show_test_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's test history."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    history = logic.get_user_test_history(update.effective_user.id, limit=10)
    
    if not history:
        await update.message.reply_text(
            messages.MESSAGE_NO_HISTORY,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Format history list
    history_items = []
    for i, attempt in enumerate(history, 1):
        date_str = datetime.fromtimestamp(attempt['completed_timestamp']).strftime('%d\\.%m\\.%Y')
        status = "✅" if attempt['passed'] else "❌"
        category = logic.escape_markdown(attempt['category_name']) if attempt['category_name'] else "Все"
        
        history_items.append(messages.MESSAGE_HISTORY_ITEM.format(
            num=i,
            date=date_str,
            score=int(attempt['score_percent']),
            status=status,
            category=category
        ))
    
    message = messages.MESSAGE_TEST_HISTORY.format(
        count=len(history),
        history_list="\n".join(history_items)
    )
    
    await update.message.reply_text(
        message,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )


async def show_monthly_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show category selector for monthly top ranking."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    now = datetime.now()
    month_name = logic.get_month_name(now.month)
    
    # Get active categories
    categories = logic.get_all_categories(active_only=True)
    
    await update.message.reply_text(
        messages.MESSAGE_SELECT_TOP_CATEGORY.format(month=logic.escape_markdown(month_name)),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_top_category_selector_keyboard(categories)
    )


async def handle_top_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback for top category selection."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cert_top_back":
        # Just close the message
        await query.message.delete()
        return
    
    if data == "cert_top_select":
        # Show category selector again
        now = datetime.now()
        month_name = logic.get_month_name(now.month)
        categories = logic.get_all_categories(active_only=True)
        
        await query.edit_message_text(
            messages.MESSAGE_SELECT_TOP_CATEGORY.format(month=logic.escape_markdown(month_name)),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_top_category_selector_keyboard(categories)
        )
        return
    
    # Determine category filter
    category_id = None
    category_name = None
    is_combined = False
    
    if data == "cert_top_all":
        category_id = None
        is_combined = True
    elif data.startswith("cert_top_cat_"):
        category_id = int(data.replace("cert_top_cat_", ""))
        category = logic.get_category_by_id(category_id)
        category_name = category['name'] if category else "Unknown"
    else:
        return
    
    now = datetime.now()
    month_name = logic.get_month_name(now.month)
    
    # Get ranking for the selected category
    ranking = logic.get_monthly_ranking_by_category(category_id=category_id, limit=10)
    
    if not ranking:
        if is_combined:
            await query.edit_message_text(
                messages.MESSAGE_EMPTY_TOP_ALL,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboards.get_top_back_keyboard()
            )
        else:
            await query.edit_message_text(
                messages.MESSAGE_EMPTY_TOP_CATEGORY.format(category=logic.escape_markdown(category_name)),
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                reply_markup=keyboards.get_top_back_keyboard()
            )
        return
    
    # Check if names should be obfuscated
    test_settings = logic.get_test_settings()
    should_obfuscate = test_settings.get('obfuscate_names', False)
    
    # Format top list
    top_items = []
    for user in ranking:
        if should_obfuscate:
            name = obfuscate_name(user['first_name'])
            if user['last_name']:
                name += f" {obfuscate_name(user['last_name'])}"
        else:
            name = logic.escape_markdown(user['first_name'])
            if user['last_name']:
                name += f" {logic.escape_markdown(user['last_name'])}"
        
        top_items.append(messages.MESSAGE_TOP_ITEM.format(
            rank=user['rank'],
            name=name,
            score=int(user['best_score']),
            tests_count=user['tests_count']
        ))
    
    # Get current user's position
    user_rank = logic.get_user_monthly_rank_by_category(
        update.effective_user.id, 
        category_id=category_id
    )
    
    if user_rank and user_rank['rank'] <= 10:
        your_position = ""  # Already in top 10
    elif user_rank:
        your_position = messages.MESSAGE_YOUR_POSITION.format(
            rank=user_rank['rank'],
            score=int(user_rank['best_score'])
        )
    else:
        your_position = messages.MESSAGE_NOT_IN_TOP
    
    # Use appropriate message template
    if is_combined:
        message = messages.MESSAGE_MONTHLY_TOP_ALL.format(
            month=logic.escape_markdown(month_name),
            top_list="\n".join(top_items),
            your_position=your_position
        )
    else:
        message = messages.MESSAGE_MONTHLY_TOP_CATEGORY.format(
            month=logic.escape_markdown(month_name),
            category=logic.escape_markdown(category_name),
            top_list="\n".join(top_items),
            your_position=your_position
        )
    
    await query.edit_message_text(
        message,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_top_back_keyboard()
    )


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show certification help."""
    await update.message.reply_text(
        messages.MESSAGE_HELP,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )


# ============================================================================
# Cancel and Fallback Handlers
# ============================================================================

async def cancel_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current test."""
    attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
    
    if attempt_id:
        logic.complete_test_attempt(attempt_id, status='cancelled')
    
    clear_test_context(context)
    
    await update.message.reply_text(
        messages.MESSAGE_TEST_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ConversationHandler.END


async def cancel_on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel test when user navigates to menu."""
    attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
    
    if attempt_id:
        logic.complete_test_attempt(attempt_id, status='cancelled')
    
    clear_test_context(context)
    
    return ConversationHandler.END


# ============================================================================
# Conversation Handler Builder
# ============================================================================

def get_user_conversation_handler() -> ConversationHandler:
    """
    Build and return the user conversation handler for certification.
    
    Returns:
        ConversationHandler for certification test flow
    """
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📝 Начать тест$"), start_test_command),
        ],
        states={
            SELECTING_CATEGORY: [
                CallbackQueryHandler(handle_category_selection, pattern="^cert_"),
            ],
            ANSWERING_QUESTION: [
                CallbackQueryHandler(handle_answer, pattern="^cert_answer_"),
                CallbackQueryHandler(handle_answer, pattern="^cert_cancel_test$"),
                CallbackQueryHandler(handle_next_question, pattern="^cert_next_question$"),
            ],
            VIEWING_RESULT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, certification_submenu),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_test),
            MessageHandler(filters.Regex("^🏠 Главное меню$"), cancel_on_menu),
            MessageHandler(filters.COMMAND, cancel_on_menu),
        ],
        name="certification_test",
        persistent=False,
        allow_reentry=True
    )


def get_menu_button_regex_pattern() -> str:
    """
    Get regex pattern for all menu buttons that should exit the conversation.
    
    Returns:
        Regex pattern string
    """
    buttons = [
        "🏠 Главное меню",
        "📊 Мой рейтинг",
        "📜 История тестов",
        "🏆 Топ месяца",
        "⚙️ Управление",
    ]
    escaped_buttons = [b.replace("(", "\\(").replace(")", "\\)") for b in buttons]
    return "^(" + "|".join(escaped_buttons) + ")$"
