"""
Employee Certification Module - User Bot Part

Telegram handlers for the user-facing certification functionality:
- Starting and taking tests
- Viewing results and history
- Monthly rankings
"""

import logging
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
    context.user_data[settings.TEST_QUESTIONS_KEY] = questions
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
    
    # Build options text
    options_text = f"""
🅰️ {logic.escape_markdown(question['option_a'])}
🅱️ {logic.escape_markdown(question['option_b'])}
©️ {logic.escape_markdown(question['option_c'])}
🇩 {logic.escape_markdown(question['option_d'])}"""
    
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
    is_correct = user_answer.upper() == correct_option.upper()
    
    # Save answer
    logic.save_answer(
        attempt_id=attempt_id,
        question_id=question['id'],
        question_order=current_index + 1,
        user_answer=user_answer.upper(),
        is_correct=is_correct
    )
    
    # Show result
    if is_correct:
        result_text = messages.MESSAGE_ANSWER_CORRECT
    else:
        result_text = messages.MESSAGE_ANSWER_INCORRECT.format(
            correct_option=settings.ANSWER_EMOJIS.get(correct_option, correct_option)
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
    
    # Move to next question
    context.user_data[settings.CURRENT_QUESTION_INDEX_KEY] = current_index + 1
    
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
    
    result_message = message_template.format(
        correct=result['correct_answers'],
        total=result['total_questions'],
        score=result['score_percent'],
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
    """Show user's ranking and statistics."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    user_stats = logic.get_user_stats(update.effective_user.id)
    
    if not user_stats:
        await update.message.reply_text(
            messages.MESSAGE_NO_TESTS_YET,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Get current month rank
    user_rank = logic.get_user_monthly_rank(update.effective_user.id)
    rank_str = str(user_rank['rank']) if user_rank else "—"
    
    # Format last test date
    if user_stats['last_test_timestamp']:
        last_test_date = datetime.fromtimestamp(user_stats['last_test_timestamp']).strftime('%d\\.%m\\.%Y')
    else:
        last_test_date = "—"
    
    message = messages.MESSAGE_MY_RANKING.format(
        rank=rank_str,
        best_score=user_stats['best_score'],
        total_tests=user_stats['total_tests'],
        passed_tests=user_stats['passed_tests'],
        last_test_date=last_test_date,
        last_test_score=user_stats['last_test_score'] or 0
    )
    
    await update.message.reply_text(
        message,
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
            score=attempt['score_percent'],
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
    """Show monthly top ranking."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    now = datetime.now()
    month_name = logic.get_month_name(now.month)
    
    ranking = logic.get_monthly_ranking(limit=10)
    
    if not ranking:
        await update.message.reply_text(
            messages.MESSAGE_EMPTY_TOP,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Format top list
    top_items = []
    for user in ranking:
        name = logic.escape_markdown(user['first_name'])
        if user['last_name']:
            name += f" {logic.escape_markdown(user['last_name'])}"
        
        top_items.append(messages.MESSAGE_TOP_ITEM.format(
            rank=user['rank'],
            name=name,
            score=user['best_score'],
            tests_count=user['tests_count']
        ))
    
    # Get current user's position
    user_rank = logic.get_user_monthly_rank(update.effective_user.id)
    if user_rank and user_rank['rank'] <= 10:
        your_position = ""  # Already in top 10
    elif user_rank:
        your_position = messages.MESSAGE_YOUR_POSITION.format(
            rank=user_rank['rank'],
            score=user_rank['best_score']
        )
    else:
        your_position = messages.MESSAGE_NOT_IN_TOP
    
    message = messages.MESSAGE_MONTHLY_TOP.format(
        month=logic.escape_markdown(month_name),
        top_list="\n".join(top_items),
        your_position=your_position
    )
    
    await update.message.reply_text(
        message,
        parse_mode=constants.ParseMode.MARKDOWN_V2
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
        "🔐 Админ панель",
    ]
    escaped_buttons = [b.replace("(", "\\(").replace(")", "\\)") for b in buttons]
    return "^(" + "|".join(escaped_buttons) + ")$"
