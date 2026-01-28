"""
Employee Certification Module Keyboards

Telegram keyboard builders for the certification module.
"""

from typing import List, Optional
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from . import settings


def get_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build certification submenu keyboard for regular users.
    
    Returns:
        ReplyKeyboardMarkup for certification submenu
    """
    return ReplyKeyboardMarkup(
        settings.SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build certification submenu keyboard with admin panel button.
    
    Returns:
        ReplyKeyboardMarkup for admin certification submenu
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Build admin panel main menu keyboard.
    
    Returns:
        ReplyKeyboardMarkup for admin menu
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_questions_keyboard() -> ReplyKeyboardMarkup:
    """
    Build admin questions management keyboard.
    
    Returns:
        ReplyKeyboardMarkup for questions management
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_QUESTIONS_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_categories_keyboard() -> ReplyKeyboardMarkup:
    """
    Build admin categories management keyboard.
    
    Returns:
        ReplyKeyboardMarkup for categories management
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_CATEGORIES_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_category_selection_keyboard(categories: List[dict], include_all: bool = True) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for category selection before starting a test.
    
    Args:
        categories: List of category dicts with 'id' and 'name'
        include_all: Whether to include "All categories" option
        
    Returns:
        InlineKeyboardMarkup for category selection
    """
    keyboard = []
    
    if include_all:
        keyboard.append([
            InlineKeyboardButton("📋 Полный тест (все категории)", callback_data="cert_start_all")
        ])
    
    for category in categories:
        keyboard.append([
            InlineKeyboardButton(
                f"📁 {category['name']}",
                callback_data=f"cert_start_cat_{category['id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("❌ Отмена", callback_data="cert_cancel")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_answer_keyboard() -> InlineKeyboardMarkup:
    """
    Build inline keyboard for answering a question.
    
    Returns:
        InlineKeyboardMarkup with answer options A, B, C, D
    """
    keyboard = [
        [
            InlineKeyboardButton("🅰️ A", callback_data="cert_answer_A"),
            InlineKeyboardButton("🅱️ B", callback_data="cert_answer_B"),
        ],
        [
            InlineKeyboardButton("©️ C", callback_data="cert_answer_C"),
            InlineKeyboardButton("🇩 D", callback_data="cert_answer_D"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_test_control_keyboard() -> InlineKeyboardMarkup:
    """
    Build inline keyboard with test control buttons.
    
    Returns:
        InlineKeyboardMarkup with cancel test option
    """
    keyboard = [
        [InlineKeyboardButton("❌ Завершить тест", callback_data="cert_cancel_test")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_next_question_keyboard() -> InlineKeyboardMarkup:
    """
    Build inline keyboard to proceed to next question.
    
    Returns:
        InlineKeyboardMarkup with next question button
    """
    keyboard = [
        [InlineKeyboardButton("➡️ Следующий вопрос", callback_data="cert_next_question")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_confirmation_keyboard(confirm_data: str, cancel_data: str = "cert_cancel") -> InlineKeyboardMarkup:
    """
    Build inline keyboard for confirmation dialogs.
    
    Args:
        confirm_data: Callback data for confirm button
        cancel_data: Callback data for cancel button
        
    Returns:
        InlineKeyboardMarkup with confirm/cancel buttons
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data=confirm_data),
            InlineKeyboardButton("❌ Нет", callback_data=cancel_data),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# ============================================================================
# Admin Keyboards
# ============================================================================

def get_categories_list_keyboard(categories: List[dict], page: int = 1, per_page: int = 10) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for categories list with pagination.
    
    Args:
        categories: List of category dicts
        page: Current page number
        per_page: Items per page
        
    Returns:
        InlineKeyboardMarkup for categories list
    """
    keyboard = []
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_categories = categories[start_idx:end_idx]
    
    for cat in page_categories:
        status = "✅" if cat.get('active', True) else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {cat['name']}",
                callback_data=f"cert_cat_view_{cat['id']}"
            )
        ])
    
    # Pagination
    nav_buttons = []
    total_pages = (len(categories) + per_page - 1) // per_page
    
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"cert_cat_page_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"cert_cat_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="cert_admin_menu")])
    
    return InlineKeyboardMarkup(keyboard)


def get_category_actions_keyboard(category_id: int, is_active: bool) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for category actions.
    
    Args:
        category_id: Category ID
        is_active: Current active status
        
    Returns:
        InlineKeyboardMarkup with category actions
    """
    toggle_text = "❌ Деактивировать" if is_active else "✅ Активировать"
    toggle_data = f"cert_cat_toggle_{category_id}"
    
    keyboard = [
        [
            InlineKeyboardButton("✏️ Редактировать", callback_data=f"cert_cat_edit_{category_id}"),
            InlineKeyboardButton(toggle_text, callback_data=toggle_data),
        ],
        [
            InlineKeyboardButton("🗑 Удалить", callback_data=f"cert_cat_delete_{category_id}"),
        ],
        [
            InlineKeyboardButton("🔙 К списку", callback_data="cert_cat_list"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_category_edit_keyboard(category_id: int) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for selecting which category field to edit.
    
    Args:
        category_id: Category ID
        
    Returns:
        InlineKeyboardMarkup with field edit options
    """
    keyboard = [
        [
            InlineKeyboardButton("📝 Название", callback_data=f"cert_cat_edit_name_{category_id}"),
        ],
        [
            InlineKeyboardButton("📄 Описание", callback_data=f"cert_cat_edit_desc_{category_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data=f"cert_cat_view_{category_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_questions_list_keyboard(questions: List[dict], page: int = 1, per_page: int = 8) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for questions list with pagination.
    
    Args:
        questions: List of question dicts
        page: Current page number
        per_page: Items per page
        
    Returns:
        InlineKeyboardMarkup for questions list
    """
    keyboard = []
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_questions = questions[start_idx:end_idx]
    
    for q in page_questions:
        status = "✅" if q.get('active', True) else "❌"
        difficulty_emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(q.get('difficulty', 'medium'), "🟡")
        text_preview = q['question_text'][:30] + "..." if len(q['question_text']) > 30 else q['question_text']
        keyboard.append([
            InlineKeyboardButton(
                f"{status}{difficulty_emoji} {text_preview}",
                callback_data=f"cert_q_view_{q['id']}"
            )
        ])
    
    # Pagination
    nav_buttons = []
    total_pages = (len(questions) + per_page - 1) // per_page
    
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f"cert_q_page_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="cert_noop"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f"cert_q_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="cert_admin_menu")])
    
    return InlineKeyboardMarkup(keyboard)


def get_question_actions_keyboard(question_id: int, is_active: bool) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for question actions.
    
    Args:
        question_id: Question ID
        is_active: Current active status
        
    Returns:
        InlineKeyboardMarkup with question actions
    """
    toggle_text = "❌ Деактивировать" if is_active else "✅ Активировать"
    
    keyboard = [
        [
            InlineKeyboardButton("✏️ Редактировать", callback_data=f"cert_q_edit_{question_id}"),
            InlineKeyboardButton(toggle_text, callback_data=f"cert_q_toggle_{question_id}"),
        ],
        [
            InlineKeyboardButton("📅 Обновить дату", callback_data=f"cert_q_relevance_{question_id}"),
            InlineKeyboardButton("🗑 Удалить", callback_data=f"cert_q_delete_{question_id}"),
        ],
        [
            InlineKeyboardButton("🔙 К списку", callback_data="cert_q_list"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_question_edit_keyboard(question_id: int) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for selecting which question field to edit.
    
    Args:
        question_id: Question ID
        
    Returns:
        InlineKeyboardMarkup with field edit options
    """
    keyboard = [
        [
            InlineKeyboardButton("📝 Текст вопроса", callback_data=f"cert_q_edit_text_{question_id}"),
        ],
        [
            InlineKeyboardButton("🅰️ Вариант A", callback_data=f"cert_q_edit_opt_a_{question_id}"),
            InlineKeyboardButton("🅱️ Вариант B", callback_data=f"cert_q_edit_opt_b_{question_id}"),
        ],
        [
            InlineKeyboardButton("©️ Вариант C", callback_data=f"cert_q_edit_opt_c_{question_id}"),
            InlineKeyboardButton("🇩 Вариант D", callback_data=f"cert_q_edit_opt_d_{question_id}"),
        ],
        [
            InlineKeyboardButton("✅ Правильный ответ", callback_data=f"cert_q_edit_correct_{question_id}"),
            InlineKeyboardButton("💡 Пояснение", callback_data=f"cert_q_edit_expl_{question_id}"),
        ],
        [
            InlineKeyboardButton("📊 Сложность", callback_data=f"cert_q_edit_diff_{question_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data=f"cert_q_view_{question_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_difficulty_keyboard() -> InlineKeyboardMarkup:
    """
    Build inline keyboard for difficulty selection.
    
    Returns:
        InlineKeyboardMarkup with difficulty options
    """
    keyboard = [
        [
            InlineKeyboardButton("🟢 Легкий", callback_data="cert_diff_easy"),
            InlineKeyboardButton("🟡 Средний", callback_data="cert_diff_medium"),
            InlineKeyboardButton("🔴 Сложный", callback_data="cert_diff_hard"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_correct_answer_keyboard() -> InlineKeyboardMarkup:
    """
    Build inline keyboard for selecting correct answer.
    
    Returns:
        InlineKeyboardMarkup with answer options
    """
    keyboard = [
        [
            InlineKeyboardButton("🅰️ A", callback_data="cert_correct_A"),
            InlineKeyboardButton("🅱️ B", callback_data="cert_correct_B"),
            InlineKeyboardButton("©️ C", callback_data="cert_correct_C"),
            InlineKeyboardButton("🇩 D", callback_data="cert_correct_D"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_category_multiselect_keyboard(
    categories: List[dict], 
    selected_ids: Optional[List[int]] = None
) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for multi-selecting categories.
    
    Args:
        categories: List of category dicts
        selected_ids: List of already selected category IDs
        
    Returns:
        InlineKeyboardMarkup for category multi-selection
    """
    selected_ids = selected_ids or []
    keyboard = []
    
    for cat in categories:
        is_selected = cat['id'] in selected_ids
        prefix = "✅ " if is_selected else "⬜️ "
        keyboard.append([
            InlineKeyboardButton(
                f"{prefix}{cat['name']}",
                callback_data=f"cert_catsel_{cat['id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("✅ Готово", callback_data="cert_catsel_done"),
        InlineKeyboardButton("❌ Отмена", callback_data="cert_cancel"),
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_outdated_questions_keyboard(questions: List[dict]) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for outdated questions management.
    
    Args:
        questions: List of outdated question dicts
        
    Returns:
        InlineKeyboardMarkup for outdated questions
    """
    keyboard = []
    
    for q in questions[:10]:  # Limit to 10 items
        text_preview = q['question_text'][:25] + "..." if len(q['question_text']) > 25 else q['question_text']
        keyboard.append([
            InlineKeyboardButton(
                f"⚠️ {text_preview}",
                callback_data=f"cert_q_view_{q['id']}"
            )
        ])
    
    if questions:
        keyboard.append([
            InlineKeyboardButton("🔄 Обновить все", callback_data="cert_outdated_update_all")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="cert_admin_menu")])
    
    return InlineKeyboardMarkup(keyboard)


def get_settings_keyboard(show_correct: bool = True) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for certification settings.
    
    Args:
        show_correct: Current value of show_correct_answer setting
    
    Returns:
        InlineKeyboardMarkup for settings
    """
    show_correct_text = "✅ Показывать ответ" if show_correct else "❌ Показывать ответ"
    keyboard = [
        [InlineKeyboardButton("📋 Кол-во вопросов", callback_data="cert_set_questions")],
        [InlineKeyboardButton("⏱ Время на тест", callback_data="cert_set_time")],
        [InlineKeyboardButton("🎯 Проходной балл", callback_data="cert_set_score")],
        [InlineKeyboardButton(f"👁 {show_correct_text}", callback_data="cert_set_show_correct")],
        [InlineKeyboardButton("🔙 Назад", callback_data="cert_admin_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_history_pagination_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """
    Build inline keyboard for history pagination.
    
    Args:
        page: Current page
        total_pages: Total pages
        
    Returns:
        InlineKeyboardMarkup for pagination
    """
    keyboard = []
    nav_buttons = []
    
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"cert_hist_page_{page-1}"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"cert_hist_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    return InlineKeyboardMarkup(keyboard) if keyboard else None
