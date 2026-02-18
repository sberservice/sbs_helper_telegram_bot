"""
Модуль аттестации сотрудников — пользовательская часть

Telegram-хендлеры для пользовательского функционала аттестации:
- Запуск и прохождение тестов
- Просмотр результатов и истории
- Ежемесячные рейтинги
"""

import logging
import random
import time
import re
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

from config.settings import DEBUG
from src.common.telegram_user import check_if_user_legit, check_if_user_admin
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE
from src.sbs_helper_telegram_bot.gamification.events import emit_event

from . import settings
from . import messages
from . import keyboards
from . import certification_logic as logic

logger = logging.getLogger(__name__)

# Состояния диалога
(
    SELECTING_CATEGORY,
    ANSWERING_QUESTION,
    VIEWING_RESULT,
    SELECTING_LEARNING_DIFFICULTY,
    SELECTING_LEARNING_CATEGORY,
    LEARNING_ANSWERING_QUESTION,
) = range(6)


def obfuscate_name(name: str) -> str:
    """
    Скрыть имя, оставив только первую букву и заменив остальное точками.
    
    Аргументы:
        name: Имя для скрытия (например, "Иван")
        
    Возвращает:
        Скрытое имя (например, "И...")
    """
    if not name:
        return ""
    return f"{name[0]}\\.\\.\\."


def shuffle_question_options(question: dict) -> dict:
    """
    Перемешать варианты ответа и сохранить отображение.
    
    Аргументы:
        question: Словарь вопроса с option_a, option_b, option_c, option_d, correct_option
        
    Возвращает:
        Словарь вопроса с shuffled_options и option_mapping
    """
    # Сформировать список пар (исходная буква, текст варианта)
    options = [
        ('A', question['option_a']),
        ('B', question['option_b']),
        ('C', question['option_c']),
        ('D', question['option_d']),
    ]
    
    # Перемешать варианты
    random.shuffle(options)
    
    # Создать отображение: показанная буква -> исходная буква
    # Например, если исходный B показан как A, то mapping['A'] = 'B'
    display_letters = ['A', 'B', 'C', 'D']
    option_mapping = {}  # отображаемая -> исходная
    shuffled_options = []  # список текстов вариантов в порядке показа
    
    for i, (original_letter, option_text) in enumerate(options):
        display_letter = display_letters[i]
        option_mapping[display_letter] = original_letter
        shuffled_options.append(option_text)
    
    # Сохранить в вопросе
    question['shuffled_options'] = shuffled_options
    question['option_mapping'] = option_mapping
    
    return question


# ============================================================================
# Точки входа и навигация
# ============================================================================

async def certification_submenu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показать подменю аттестации."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    if check_if_user_admin(update.effective_user.id):
        keyboard = keyboards.get_admin_submenu_keyboard()
    else:
        keyboard = keyboards.get_submenu_keyboard()
    
    # Получить статистику для подменю
    stats = logic.get_certification_statistics()
    questions_count = int(stats.get('total_questions', 0) or 0)
    categories_count = int(stats.get('active_categories', 0) or 0)
    cert_summary = logic.get_user_certification_summary(update.effective_user.id)

    rank_icon = cert_summary.get('rank_icon', '🌱')
    rank_name = logic.escape_markdown(str(cert_summary.get('rank_name', 'Новичок')))
    progress_bar = logic.escape_markdown(str(cert_summary.get('overall_progress_bar', '[□□□□□□□□□□]')))
    progress_percent = int(cert_summary.get('overall_progress_percent') or 0)
    certification_points = int(cert_summary.get('certification_points') or 0)
    max_achievable_points = int(cert_summary.get('max_achievable_points') or 0)
    
    if questions_count > 0 or categories_count > 0:
        submenu_text = messages.get_submenu_message(
            questions_count=questions_count,
            categories_count=categories_count,
            rank_icon=rank_icon,
            rank_name=rank_name,
            progress_bar=progress_bar,
            progress_percent=progress_percent,
            certification_points=certification_points,
            max_achievable_points=max_achievable_points,
        )
    else:
        submenu_text = messages.get_submenu_message(
            questions_count=questions_count,
            categories_count=categories_count,
            rank_icon=rank_icon,
            rank_name=rank_name,
            progress_bar=progress_bar,
            progress_percent=progress_percent,
            certification_points=certification_points,
            max_achievable_points=max_achievable_points,
        )
    
    await update.message.reply_text(
        submenu_text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboard
    )
    return ConversationHandler.END


async def start_test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать кнопку «Начать тест» и показать выбор категории."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END
    
    # Отменить все текущие попытки
    logic.cancel_user_attempts(update.effective_user.id)
    clear_learning_context(context)
    
    # Проверить наличие вопросов
    questions_count = logic.get_questions_count()
    if questions_count == 0:
        await update.message.reply_text(
            messages.MESSAGE_NO_QUESTIONS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Получить настройки теста
    test_settings = logic.get_test_settings()
    
    # Получить активные категории
    categories = logic.get_all_categories(active_only=True)
    
    # Показать вступление к тесту и выбор категории
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


async def start_learning_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать кнопку «Режим обучения» и показать выбор сложности."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return ConversationHandler.END

    # Отменить все текущие попытки
    logic.cancel_user_attempts(update.effective_user.id)
    clear_test_context(context)
    clear_learning_context(context)

    # Проверить наличие вопросов
    questions_count = logic.get_questions_count()
    if questions_count == 0:
        await update.message.reply_text(
            messages.MESSAGE_NO_QUESTIONS,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END

    await update.message.reply_text(
        messages.MESSAGE_LEARNING_SELECT_DIFFICULTY,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_learning_difficulty_keyboard()
    )

    return SELECTING_LEARNING_DIFFICULTY


async def handle_learning_difficulty_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать выбор сложности в режиме обучения."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "cert_learn_diff_cancel":
        await query.edit_message_text(
            messages.MESSAGE_LEARNING_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END

    difficulty = None
    if data == "cert_learn_diff_all":
        difficulty = None
    elif data.startswith("cert_learn_diff_"):
        difficulty = data.replace("cert_learn_diff_", "")
    else:
        return SELECTING_LEARNING_DIFFICULTY

    context.user_data[settings.LEARNING_SELECTED_DIFFICULTY_KEY] = difficulty

    # Получить настройки теста (количество вопросов)
    test_settings = logic.get_test_settings()
    categories = logic.get_all_categories(active_only=True)

    intro_text = messages.MESSAGE_LEARNING_INTRO.format(
        questions_count=test_settings['questions_count']
    )

    await query.edit_message_text(
        intro_text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_learning_category_selection_keyboard(categories)
    )

    return SELECTING_LEARNING_CATEGORY


async def handle_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать выбор категории для теста."""
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
    
    # Получить настройки теста
    test_settings = logic.get_test_settings()
    questions_count = test_settings['questions_count']
    time_limit_minutes = test_settings['time_limit_minutes']
    time_limit_seconds = time_limit_minutes * 60
    passing_score = test_settings['passing_score_percent']
    
    # Получить вопросы с целевым балансом сложности 33/33/33
    question_set = logic.build_fair_test_questions(questions_count, category_id)
    questions = question_set.get('questions', [])
    
    if not questions:
        await query.edit_message_text(
            messages.MESSAGE_NO_QUESTIONS_IN_CATEGORY,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    # Создать попытку теста
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
    
    # Сохранить данные теста в контексте
    context.user_data[settings.CURRENT_ATTEMPT_ID_KEY] = attempt_id
    # Перемешать варианты ответа для каждого вопроса
    shuffled_questions = [shuffle_question_options(q) for q in questions]
    context.user_data[settings.TEST_QUESTIONS_KEY] = shuffled_questions
    context.user_data[settings.CURRENT_QUESTION_INDEX_KEY] = 0
    context.user_data[settings.TEST_START_TIME_KEY] = time.time()
    context.user_data[settings.SELECTED_CATEGORY_KEY] = category_id
    context.user_data[settings.TEST_IN_PROGRESS_KEY] = True
    
    # Показать сообщение о старте теста
    start_lines = [
        messages.MESSAGE_TEST_STARTED.format(
            total_questions=len(questions),
            time_limit=time_limit_minutes,
            passing_score=passing_score
        ),
    ]

    is_admin_debug = check_if_user_admin(update.effective_user.id) and DEBUG
    if is_admin_debug:
        target_distribution = question_set.get('target_distribution', {})
        actual_distribution = question_set.get('actual_distribution', {})
        start_lines.extend([
            messages.MESSAGE_TEST_DIFFICULTY_TARGET.format(
                easy=target_distribution.get('easy', 0),
                medium=target_distribution.get('medium', 0),
                hard=target_distribution.get('hard', 0),
            ),
            messages.MESSAGE_TEST_DIFFICULTY_ACTUAL.format(
                easy=actual_distribution.get('easy', 0),
                medium=actual_distribution.get('medium', 0),
                hard=actual_distribution.get('hard', 0),
            ),
        ])

        if question_set.get('fallback_used'):
            start_lines.append(messages.MESSAGE_TEST_DIFFICULTY_FALLBACK)

    await query.edit_message_text(
        "\n\n".join(start_lines),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    # Отправить первый вопрос
    await send_question(update, context, is_callback=True)
    
    return ANSWERING_QUESTION


async def handle_learning_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать выбор категории для обучения."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "cert_learn_cancel":
        await query.edit_message_text(
            messages.MESSAGE_LEARNING_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END

    category_id = None
    if data == "cert_learn_all":
        category_id = None
    elif data.startswith("cert_learn_cat_"):
        category_id = int(data.replace("cert_learn_cat_", ""))
    else:
        return SELECTING_LEARNING_CATEGORY

    test_settings = logic.get_test_settings()
    questions_count = test_settings['questions_count']

    difficulty = context.user_data.get(settings.LEARNING_SELECTED_DIFFICULTY_KEY)
    questions = logic.get_random_questions(
        questions_count,
        category_id,
        difficulty=difficulty
    )

    if not questions:
        await query.edit_message_text(
            messages.MESSAGE_NO_QUESTIONS_IN_CATEGORY,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END

    # Сохранить данные обучения в контексте
    shuffled_questions = [shuffle_question_options(q) for q in questions]
    context.user_data[settings.LEARNING_QUESTIONS_KEY] = shuffled_questions
    context.user_data[settings.LEARNING_CURRENT_QUESTION_INDEX_KEY] = 0
    context.user_data[settings.LEARNING_SELECTED_CATEGORY_KEY] = category_id
    context.user_data[settings.LEARNING_IN_PROGRESS_KEY] = True
    context.user_data[settings.LEARNING_CORRECT_COUNT_KEY] = 0

    await query.edit_message_text(
        messages.MESSAGE_LEARNING_STARTED.format(total_questions=len(questions)),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )

    await send_learning_question(update, context, is_callback=True)

    return LEARNING_ANSWERING_QUESTION


async def send_question(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    is_callback: bool = False
) -> None:
    """Отправить пользователю текущий вопрос теста."""
    questions = context.user_data.get(settings.TEST_QUESTIONS_KEY, [])
    current_index = context.user_data.get(settings.CURRENT_QUESTION_INDEX_KEY, 0)
    start_time = context.user_data.get(settings.TEST_START_TIME_KEY, time.time())
    attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
    
    if current_index >= len(questions):
        # Тест завершён
        await finish_test(update, context, is_callback=is_callback)
        return
    
    # Проверить время
    attempt = logic.get_attempt_by_id(attempt_id)
    if attempt:
        elapsed = time.time() - start_time
        remaining = attempt['time_limit_seconds'] - int(elapsed)
        
        if remaining <= 0:
            # Время истекло
            await finish_test(update, context, status='expired', is_callback=is_callback)
            return
        
        time_remaining_str = logic.format_time_remaining(remaining)
    else:
        time_remaining_str = "--:--"
    
    question = questions[current_index]
    
    # Подготовить текст вопроса
    question_text = logic.escape_markdown(question['question_text'])
    
    # Сформировать текст вариантов с учётом перемешивания
    shuffled = question.get('shuffled_options', [
        question['option_a'], question['option_b'], 
        question['option_c'], question['option_d']
    ])
    options_text = f"""🅰️ {logic.escape_markdown(shuffled[0])}

🅱️ {logic.escape_markdown(shuffled[1])}

©️ {logic.escape_markdown(shuffled[2])}

🇩 {logic.escape_markdown(shuffled[3])}"""
    
    full_message = messages.MESSAGE_QUESTION_TEMPLATE.format(
        current=current_index + 1,
        total=len(questions),
        question_text=question_text,
        options=options_text,
        time_remaining=time_remaining_str
    )
    
    # Добавить предупреждение о времени при необходимости
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


async def send_learning_question(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    is_callback: bool = False
) -> None:
    """Отправить пользователю текущий вопрос обучения."""
    questions = context.user_data.get(settings.LEARNING_QUESTIONS_KEY, [])
    current_index = context.user_data.get(settings.LEARNING_CURRENT_QUESTION_INDEX_KEY, 0)

    if current_index >= len(questions):
        await finish_learning(update, context, is_callback=is_callback)
        return

    question = questions[current_index]

    question_text = logic.escape_markdown(question['question_text'])

    shuffled = question.get('shuffled_options', [
        question['option_a'], question['option_b'],
        question['option_c'], question['option_d']
    ])
    options_text = f"""🅰️ {logic.escape_markdown(shuffled[0])}

🅱️ {logic.escape_markdown(shuffled[1])}

©️ {logic.escape_markdown(shuffled[2])}

🇩 {logic.escape_markdown(shuffled[3])}"""

    full_message = messages.MESSAGE_LEARNING_QUESTION_TEMPLATE.format(
        current=current_index + 1,
        total=len(questions),
        question_text=question_text,
        options=options_text
    )

    if is_callback:
        await update.effective_chat.send_message(
            full_message,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_learning_answer_keyboard()
        )
    else:
        await update.message.reply_text(
            full_message,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_learning_answer_keyboard()
        )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ответ пользователя на вопрос теста."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cert_cancel_test":
        # Отменить тест
        attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
        if attempt_id:
            logic.complete_test_attempt(attempt_id, status='cancelled')
        
        # Очистить контекст
        clear_test_context(context)
        
        await query.edit_message_text(
            messages.MESSAGE_TEST_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END
    
    if not data.startswith("cert_answer_"):
        return ANSWERING_QUESTION


    user_answer = data.replace("cert_answer_", "")
    
    # Сначала проверить время
    start_time = context.user_data.get(settings.TEST_START_TIME_KEY, time.time())
    attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
    attempt = logic.get_attempt_by_id(attempt_id)
    
    if attempt:
        elapsed = time.time() - start_time
        if elapsed > attempt['time_limit_seconds']:
            await finish_test(update, context, status='expired', is_callback=True)
            return ConversationHandler.END
    
    # Получить текущий вопрос
    questions = context.user_data.get(settings.TEST_QUESTIONS_KEY, [])
    current_index = context.user_data.get(settings.CURRENT_QUESTION_INDEX_KEY, 0)
    
    if current_index >= len(questions):
        await finish_test(update, context, is_callback=True)
        return ConversationHandler.END
    
    question = questions[current_index]
    correct_option = question['correct_option']
    
    # Преобразовать выбранную букву в исходную
    option_mapping = question.get('option_mapping', {'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D'})
    original_answer = option_mapping.get(user_answer.upper(), user_answer.upper())
    is_correct = original_answer == correct_option.upper()
    
    # Найти отображаемую букву правильного ответа
    # (обратное отображение: исходная -> отображаемая)
    displayed_correct = user_answer.upper()  # по умолчанию
    for displayed, original in option_mapping.items():
        if original == correct_option.upper():
            displayed_correct = displayed
            break
    
    # Сохранить ответ (исходную букву для согласованности)
    logic.save_answer(
        attempt_id=attempt_id,
        question_id=question['id'],
        question_order=current_index + 1,
        user_answer=original_answer,
        is_correct=is_correct
    )
    
    # Нужно ли показывать правильный ответ
    test_settings = logic.get_test_settings()
    show_correct = test_settings.get('show_correct_answer', True)
    
    # Перейти к следующему вопросу
    context.user_data[settings.CURRENT_QUESTION_INDEX_KEY] = current_index + 1
    
    # Показать результат или перейти автоматически
    if show_correct:
        if is_correct:
            result_text = messages.MESSAGE_ANSWER_CORRECT
        else:
            # Показать отображаемую букву правильного ответа
            result_text = messages.MESSAGE_ANSWER_INCORRECT.format(
                correct_option=settings.ANSWER_EMOJIS.get(displayed_correct, displayed_correct)
            )
        
        # Добавить пояснение при наличии
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
        # Перейти к следующему вопросу без показа результата
        new_index = context.user_data.get(settings.CURRENT_QUESTION_INDEX_KEY, 0)
        questions = context.user_data.get(settings.TEST_QUESTIONS_KEY, [])
        
        if new_index >= len(questions):
            # Тест завершён
            await query.edit_message_text(
                "⏳ Завершаем тест\\.\\.\\.",
                parse_mode=constants.ParseMode.MARKDOWN_V2
            )
            await finish_test(update, context, is_callback=True)
            return ConversationHandler.END
        
        # Отправить следующий вопрос и удалить старое сообщение
        await send_question(update, context, is_callback=True)
        try:
            await query.message.delete()
        except Exception:
            pass  # Игнорировать, если сообщение нельзя удалить
        return ANSWERING_QUESTION


async def handle_learning_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать ответ пользователя в режиме обучения."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "cert_learn_cancel_session":
        clear_learning_context(context)
        await query.edit_message_text(
            messages.MESSAGE_LEARNING_CANCELLED,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return ConversationHandler.END

    if not data.startswith("cert_learn_answer_"):
        return LEARNING_ANSWERING_QUESTION

    user_answer = data.replace("cert_learn_answer_", "")

    questions = context.user_data.get(settings.LEARNING_QUESTIONS_KEY, [])
    current_index = context.user_data.get(settings.LEARNING_CURRENT_QUESTION_INDEX_KEY, 0)

    if current_index >= len(questions):
        await finish_learning(update, context, is_callback=True)
        return ConversationHandler.END

    question = questions[current_index]
    correct_option = question['correct_option']

    option_mapping = question.get('option_mapping', {'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D'})
    original_answer = option_mapping.get(user_answer.upper(), user_answer.upper())
    is_correct = original_answer == correct_option.upper()

    displayed_correct = user_answer.upper()
    for displayed, original in option_mapping.items():
        if original == correct_option.upper():
            displayed_correct = displayed
            break

    if is_correct:
        result_text = messages.MESSAGE_LEARNING_ANSWER_CORRECT
    else:
        result_text = messages.MESSAGE_LEARNING_ANSWER_INCORRECT

    display_letters = ['A', 'B', 'C', 'D']
    correct_index = display_letters.index(displayed_correct) if displayed_correct in display_letters else 0
    shuffled = question.get('shuffled_options', [
        question['option_a'], question['option_b'],
        question['option_c'], question['option_d']
    ])
    correct_text = logic.escape_markdown(shuffled[correct_index])
    correct_answer = (
        f"{settings.ANSWER_EMOJIS.get(displayed_correct, displayed_correct)} {correct_text}"
    )

    user_answer_line = ""
    if not is_correct:
        user_index = display_letters.index(user_answer.upper()) if user_answer.upper() in display_letters else 0
        user_text = logic.escape_markdown(shuffled[user_index])
        user_answer_display = (
            f"{settings.ANSWER_EMOJIS.get(user_answer.upper(), user_answer.upper())} {user_text}"
        )
        user_answer_line = f"\n\n❌ *Ваш ответ:* {user_answer_display}"

    comment = question.get('explanation')
    comment_text = logic.escape_markdown(comment) if comment else "—"

    feedback_text = messages.MESSAGE_LEARNING_ANSWER_FEEDBACK.format(
        result=result_text,
        correct_answer=correct_answer,
        user_answer_line=user_answer_line,
        comment=comment_text
    )

    context.user_data[settings.LEARNING_CURRENT_QUESTION_INDEX_KEY] = current_index + 1
    if is_correct:
        context.user_data[settings.LEARNING_CORRECT_COUNT_KEY] = (
            context.user_data.get(settings.LEARNING_CORRECT_COUNT_KEY, 0) + 1
        )

    emit_event(
        "certification.learning_answered",
        update.effective_user.id,
        data={
            'question_id': question['id'],
            'is_correct': is_correct,
            'category_id': context.user_data.get(settings.LEARNING_SELECTED_CATEGORY_KEY),
        }
    )

    await query.edit_message_text(
        feedback_text,
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_learning_next_question_keyboard()
    )

    return LEARNING_ANSWERING_QUESTION


async def handle_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать кнопку «Следующий вопрос» в тесте."""
    query = update.callback_query
    await query.answer()
    
    if query.data != "cert_next_question":
        return ANSWERING_QUESTION
    
    # Проверить, что тест ещё идёт
    if not context.user_data.get(settings.TEST_IN_PROGRESS_KEY):
        return ConversationHandler.END
    
    questions = context.user_data.get(settings.TEST_QUESTIONS_KEY, [])
    current_index = context.user_data.get(settings.CURRENT_QUESTION_INDEX_KEY, 0)
    
    if current_index >= len(questions):
        await finish_test(update, context, is_callback=True)
        return ConversationHandler.END
    
    await send_question(update, context, is_callback=True)
    return ANSWERING_QUESTION


async def handle_learning_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработать кнопку «Следующий вопрос» в обучении."""
    query = update.callback_query
    await query.answer()

    if query.data != "cert_learn_next_question":
        return LEARNING_ANSWERING_QUESTION

    if not context.user_data.get(settings.LEARNING_IN_PROGRESS_KEY):
        return ConversationHandler.END

    questions = context.user_data.get(settings.LEARNING_QUESTIONS_KEY, [])
    current_index = context.user_data.get(settings.LEARNING_CURRENT_QUESTION_INDEX_KEY, 0)

    if current_index >= len(questions):
        await finish_learning(update, context, is_callback=True)
        return ConversationHandler.END

    await send_learning_question(update, context, is_callback=True)
    try:
        await query.message.delete()
    except Exception:
        pass
    return LEARNING_ANSWERING_QUESTION


async def finish_test(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    status: str = 'completed',
    is_callback: bool = False
) -> int:
    """Завершить тест и показать результат."""
    attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
    
    if not attempt_id:
        return ConversationHandler.END
    
    user_id = update.effective_user.id

    # Завершить попытку
    result = logic.complete_test_attempt(attempt_id, status=status)
    
    if not result:
        return ConversationHandler.END
    
    # Сформировать строку времени
    time_spent_str = logic.format_time_spent(result['time_spent_seconds'])
    
    # Получить информацию о месте в рейтинге
    rank_info = ""
    if result['passed']:
        user_rank = logic.get_user_monthly_rank(update.effective_user.id)
        if user_rank:
            rank_info = messages.MESSAGE_RANK_INFO.format(rank=user_rank['rank'])
        else:
            rank_info = messages.MESSAGE_NO_RANK_YET
    else:
        rank_info = messages.MESSAGE_NO_RANK_YET
    
    # Сформировать статус
    if status == 'expired':
        status_text = "⏰ Время истекло"
        message_template = messages.MESSAGE_TIME_EXPIRED
    else:
        status_text = messages.MESSAGE_TEST_PASSED if result['passed'] else messages.MESSAGE_TEST_FAILED
        message_template = messages.MESSAGE_TEST_COMPLETED
    
    # Сформировать результат: целое без дробной части, иначе экранировать точку
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
    
    # Отправить события геймификации
    attempt = logic.get_attempt_by_id(attempt_id)

    if attempt and attempt.get('category_id') is not None:
        result_message += "\n\n" + messages.MESSAGE_CATEGORY_RESULT_VALIDITY_INFO.format(
            days=settings.CATEGORY_RESULT_VALIDITY_DAYS
        )
        if result['passed'] and status == 'completed':
            expiry_timestamp = logic.get_category_result_expiry_timestamp(result.get('completed_timestamp'))
            if expiry_timestamp:
                expiry_date = datetime.fromtimestamp(expiry_timestamp).strftime('%d\\.%m\\.%Y')
                result_message += "\n" + messages.MESSAGE_CATEGORY_RESULT_EXPIRES_AT.format(
                    expiry_date=expiry_date
                )

    event_data = {
        'attempt_id': attempt_id,
        'status': status,
        'passed': result['passed'],
        'score_percent': result['score_percent'],
        'correct_answers': result['correct_answers'],
        'total_questions': result['total_questions'],
        'category_id': attempt.get('category_id') if attempt else None,
    }
    emit_event("certification.test_completed", user_id, data=event_data)
    if result['passed'] and status == 'completed':
        emit_event("certification.test_passed", user_id, data=event_data)

    # Очистить контекст
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


async def finish_learning(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    is_callback: bool = False
) -> int:
    """Завершить обучение и показать итог."""
    questions = context.user_data.get(settings.LEARNING_QUESTIONS_KEY, [])
    correct_count = context.user_data.get(settings.LEARNING_CORRECT_COUNT_KEY, 0)
    total_count = len(questions)

    emit_event(
        "certification.learning_completed",
        update.effective_user.id,
        data={
            'total_questions': total_count,
            'correct_answers': correct_count,
            'category_id': context.user_data.get(settings.LEARNING_SELECTED_CATEGORY_KEY),
        }
    )

    message_text = messages.MESSAGE_LEARNING_COMPLETED.format(
        total=total_count,
        correct=correct_count
    )

    clear_learning_context(context)

    if is_callback:
        await update.effective_chat.send_message(
            message_text,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            message_text,
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )

    return ConversationHandler.END


def clear_test_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очистить данные теста из контекста."""
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


def clear_learning_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очистить данные обучения из контекста."""
    keys_to_clear = [
        settings.LEARNING_QUESTIONS_KEY,
        settings.LEARNING_CURRENT_QUESTION_INDEX_KEY,
        settings.LEARNING_SELECTED_CATEGORY_KEY,
        settings.LEARNING_SELECTED_DIFFICULTY_KEY,
        settings.LEARNING_IN_PROGRESS_KEY,
        settings.LEARNING_CORRECT_COUNT_KEY,
    ]
    for key in keys_to_clear:
        context.user_data.pop(key, None)


# ============================================================================
# Рейтинги и история
# ============================================================================

async def show_my_ranking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать рейтинг пользователя и статистику по категориям за месяц."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    now = datetime.now()
    month_name = logic.get_month_name(now.month)
    
    # Получить категории, где пользователь проходил тесты в этом месяце
    user_categories = logic.get_user_categories_this_month(update.effective_user.id)
    cert_summary = logic.get_user_certification_summary(update.effective_user.id)
    
    if not user_categories:
        await update.message.reply_text(
            messages.MESSAGE_NO_TESTS_THIS_MONTH.format(month=logic.escape_markdown(month_name)),
            parse_mode=constants.ParseMode.MARKDOWN_V2
        )
        return
    
    # Сформировать сообщение с рейтингами по категориям
    message_parts = [messages.MESSAGE_MY_RANKING_HEADER.format(month=logic.escape_markdown(month_name))]

    rank_name = logic.escape_markdown(str(cert_summary.get('rank_name', 'Новичок')))
    rank_icon = cert_summary.get('rank_icon', '🌱')
    certification_points = int(cert_summary.get('certification_points') or 0)
    max_achievable_points = int(cert_summary.get('max_achievable_points') or 0)
    overall_progress_percent = int(cert_summary.get('overall_progress_percent') or 0)
    overall_progress_bar = cert_summary.get('overall_progress_bar', logic.build_progress_bar(0))

    cert_progress_lines = [
        messages.MESSAGE_CERT_PROGRESS_HEADER,
        messages.MESSAGE_CERT_PROGRESS_LINE.format(
            rank_icon=rank_icon,
            rank_name=rank_name,
        ),
        messages.MESSAGE_CERT_PROGRESS_POINTS_LINE.format(
            points=certification_points,
            max_points=max_achievable_points,
        ),
        messages.MESSAGE_CERT_PROGRESS_BAR_LINE.format(
            progress_bar=overall_progress_bar,
            progress_percent=overall_progress_percent,
        ),
    ]

    next_rank_name = cert_summary.get('next_rank_name')
    points_to_next_rank = cert_summary.get('points_to_next_rank')
    if next_rank_name and points_to_next_rank is not None:
        cert_progress_lines.append(
            messages.MESSAGE_CERT_PROGRESS_NEXT_STEP_LINE.format(
                next_rank_icon=cert_summary.get('next_rank_icon', '🏅'),
                next_rank_name=logic.escape_markdown(str(next_rank_name)),
                points_to_next=int(points_to_next_rank),
            )
        )
    else:
        cert_progress_lines.append(messages.MESSAGE_CERT_PROGRESS_ULTIMATE_LINE)

    message_parts.append("\n" + "\n".join(cert_progress_lines))
    
    # Получить общую статистику для данных последнего теста
    user_stats = logic.get_user_stats(update.effective_user.id)
    
    # Добавить общий рейтинг (если есть успешные тесты)
    combined_rank = logic.get_user_monthly_rank(update.effective_user.id)
    if combined_rank:
        message_parts.append(messages.MESSAGE_MY_RANKING_ALL_ITEM.format(
            rank=combined_rank['rank'],
            best_score=int(combined_rank['best_score']),
            tests_count=combined_rank['tests_count']
        ))
    
    # Добавить рейтинг по каждой категории
    for cat_info in user_categories:
        # Пропустить полный тест (category_id=None) — он уже в общем рейтинге
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

    expiry_lines = [
        messages.MESSAGE_CATEGORY_RESULT_POLICY_LINE.format(
            days=settings.CATEGORY_RESULT_VALIDITY_DAYS
        )
    ]
    
    nearest_expiry_timestamp = cert_summary.get('nearest_category_expiry_timestamp')
    if nearest_expiry_timestamp:
        nearest_expiry_date = datetime.fromtimestamp(nearest_expiry_timestamp).strftime('%d\\.%m\\.%Y')
        expiry_lines.append(
            messages.MESSAGE_CATEGORY_RESULT_NEAREST_EXPIRY_LINE.format(
                expiry_date=nearest_expiry_date
            )
        )

    expiring_soon_count = int(cert_summary.get('expiring_soon_categories_count') or 0)
    if expiring_soon_count > 0:
        expiry_lines.append(
            messages.MESSAGE_CATEGORY_RESULT_EXPIRING_SOON_LINE.format(
                warning_days=settings.CATEGORY_RESULT_EXPIRY_WARNING_DAYS,
                count=expiring_soon_count,
            )
        )

    expired_count = int(cert_summary.get('expired_categories_count') or 0)
    if expired_count > 0:
        expiry_lines.append(
            messages.MESSAGE_CATEGORY_RESULT_EXPIRED_LINE.format(
                count=expired_count
            )
        )

    message_parts.append("\n\n⏳ *Срок действия результатов по категориям:*\n" + "\n".join(expiry_lines))

    rank_ladder = logic.get_certification_rank_ladder()
    rank_scale_lines = [messages.MESSAGE_RANK_SCALE_HEADER]
    for rank_data in rank_ladder:
        rank_scale_lines.append(
            messages.MESSAGE_RANK_SCALE_ITEM.format(
                icon=rank_data.get('icon', '🏅'),
                name=logic.escape_markdown(str(rank_data.get('name', ''))),
                min_points=int(rank_data.get('min_points', 0)),
            )
        )
    message_parts.append("\n\n" + "\n".join(rank_scale_lines))

    if expired_count > 0:
        message_parts.append(
            "\n" + messages.MESSAGE_RANK_DROP_WARNING.format(count=expired_count)
        )
    
    await update.message.reply_text(
        "".join(message_parts),
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )


async def show_test_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать историю тестов пользователя."""
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
    
    # Сформировать список истории
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
    """Показать выбор категории для ТОПа месяца."""
    if not check_if_user_legit(update.effective_user.id):
        await update.message.reply_text(MESSAGE_PLEASE_ENTER_INVITE)
        return
    
    now = datetime.now()
    month_name = logic.get_month_name(now.month)
    
    # Получить активные категории
    categories = logic.get_all_categories(active_only=True)
    
    await update.message.reply_text(
        messages.MESSAGE_SELECT_TOP_CATEGORY.format(month=logic.escape_markdown(month_name)),
        parse_mode=constants.ParseMode.MARKDOWN_V2,
        reply_markup=keyboards.get_top_category_selector_keyboard(categories)
    )


async def handle_top_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработать выбор категории для ТОПа месяца."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cert_top_back":
        # Просто закрыть сообщение
        await query.message.delete()
        return
    
    if data == "cert_top_select":
        # Показать выбор категории снова
        now = datetime.now()
        month_name = logic.get_month_name(now.month)
        categories = logic.get_all_categories(active_only=True)
        
        await query.edit_message_text(
            messages.MESSAGE_SELECT_TOP_CATEGORY.format(month=logic.escape_markdown(month_name)),
            parse_mode=constants.ParseMode.MARKDOWN_V2,
            reply_markup=keyboards.get_top_category_selector_keyboard(categories)
        )
        return
    
    # Определить фильтр по категории
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
    
    # Получить рейтинг для выбранной категории
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
    
    # Проверить, нужно ли скрывать имена
    test_settings = logic.get_test_settings()
    should_obfuscate = test_settings.get('obfuscate_names', False)
    
    # Сформировать список ТОПа
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
    
    # Получить позицию текущего пользователя
    user_rank = logic.get_user_monthly_rank_by_category(
        update.effective_user.id, 
        category_id=category_id
    )
    
    if user_rank and user_rank['rank'] <= 10:
        your_position = ""  # Уже в ТОП-10
    elif user_rank:
        your_position = messages.MESSAGE_YOUR_POSITION.format(
            rank=user_rank['rank'],
            score=int(user_rank['best_score'])
        )
    else:
        your_position = messages.MESSAGE_NOT_IN_TOP
    
    # Использовать подходящий шаблон сообщения
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
    """Показать справку по модулю аттестации."""
    await update.message.reply_text(
        messages.MESSAGE_HELP,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )


# ============================================================================
# Отмена и обработчики выхода
# ============================================================================

async def cancel_test(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменить текущий тест."""
    attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
    
    if attempt_id:
        logic.complete_test_attempt(attempt_id, status='cancelled')
    
    clear_test_context(context)
    clear_learning_context(context)
    
    await update.message.reply_text(
        messages.MESSAGE_TEST_CANCELLED,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    
    return ConversationHandler.END


async def cancel_on_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменить тест при переходе в меню."""
    attempt_id = context.user_data.get(settings.CURRENT_ATTEMPT_ID_KEY)
    
    if attempt_id:
        logic.complete_test_attempt(attempt_id, status='cancelled')
    
    clear_test_context(context)
    clear_learning_context(context)
    
    return ConversationHandler.END


# ============================================================================
# Сборка ConversationHandler
# ============================================================================

def get_user_conversation_handler() -> ConversationHandler:
    """
    Создать и вернуть пользовательский ConversationHandler для аттестации.
    
    Возвращает:
        ConversationHandler для тестирования
    """
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_START_TEST)}$"), start_test_command),
            MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_LEARNING_MODE)}$"), start_learning_command),
        ],
        states={
            SELECTING_CATEGORY: [
                CallbackQueryHandler(handle_category_selection, pattern="^cert_start_|^cert_cancel$"),
            ],
            ANSWERING_QUESTION: [
                CallbackQueryHandler(handle_answer, pattern="^cert_answer_"),
                CallbackQueryHandler(handle_answer, pattern="^cert_cancel_test$"),
                CallbackQueryHandler(handle_next_question, pattern="^cert_next_question$"),
            ],
            SELECTING_LEARNING_DIFFICULTY: [
                CallbackQueryHandler(handle_learning_difficulty_selection, pattern="^cert_learn_diff_"),
            ],
            SELECTING_LEARNING_CATEGORY: [
                CallbackQueryHandler(handle_learning_category_selection, pattern="^cert_learn_|^cert_learn_cancel$"),
            ],
            LEARNING_ANSWERING_QUESTION: [
                CallbackQueryHandler(handle_learning_answer, pattern="^cert_learn_answer_"),
                CallbackQueryHandler(handle_learning_answer, pattern="^cert_learn_cancel_session$"),
                CallbackQueryHandler(handle_learning_next_question, pattern="^cert_learn_next_question$"),
            ],
            VIEWING_RESULT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, certification_submenu),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_test),
            CommandHandler("reset", cancel_on_menu),
            CommandHandler("menu", cancel_on_menu),
            MessageHandler(filters.Regex(f"^{re.escape(settings.BUTTON_MAIN_MENU)}$"), cancel_on_menu),
            MessageHandler(filters.COMMAND, cancel_on_menu),
        ],
        name="certification_test",
        persistent=False,
        allow_reentry=True
    )


def get_menu_button_regex_pattern() -> str:
    """
    Получить regex-паттерн для кнопок меню, завершающих диалог.
    
    Возвращает:
        Строка regex-паттерна
    """
    buttons = [
        settings.BUTTON_MAIN_MENU,
        settings.BUTTON_MY_RANKING,
        settings.BUTTON_TEST_HISTORY,
        settings.BUTTON_MONTHLY_TOP,
        settings.BUTTON_LEARNING_MODE,
        settings.BUTTON_ADMIN_PANEL,
    ]
    escaped_buttons = [b.replace("(", "\\(").replace(")", "\\)") for b in buttons]
    return "^(" + "|".join(escaped_buttons) + ")$"
