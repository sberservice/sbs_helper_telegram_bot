"""
Клавиатуры модуля аттестации сотрудников

Сборщики Telegram-клавиатур для модуля аттестации.
"""

from typing import List, Optional
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from . import settings


def get_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Сформировать клавиатуру подменю аттестации для обычных пользователей.
    
    Возвращает:
        ReplyKeyboardMarkup для подменю аттестации
    """
    return ReplyKeyboardMarkup(
        settings.SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_submenu_keyboard() -> ReplyKeyboardMarkup:
    """
    Сформировать клавиатуру подменю аттестации с кнопкой админ-панели.
    
    Возвращает:
        ReplyKeyboardMarkup для админского подменю аттестации
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_SUBMENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Сформировать клавиатуру главного меню админ-панели.
    
    Возвращает:
        ReplyKeyboardMarkup для меню администратора
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_MENU_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_questions_keyboard() -> ReplyKeyboardMarkup:
    """
    Сформировать клавиатуру управления вопросами для администратора.
    
    Возвращает:
        ReplyKeyboardMarkup для управления вопросами
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_QUESTIONS_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_admin_categories_keyboard() -> ReplyKeyboardMarkup:
    """
    Сформировать клавиатуру управления категориями для администратора.
    
    Возвращает:
        ReplyKeyboardMarkup для управления категориями
    """
    return ReplyKeyboardMarkup(
        settings.ADMIN_CATEGORIES_BUTTONS,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_category_selection_keyboard(categories: List[dict], include_all: bool = True) -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру выбора категории перед тестом.
    
    Аргументы:
        categories: Список словарей категорий с полями 'id' и 'name'
        include_all: Добавлять ли пункт «Все категории»
        
    Возвращает:
        InlineKeyboardMarkup для выбора категории
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


def get_learning_category_selection_keyboard(
    categories: List[dict],
    include_all: bool = True
) -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру выбора категории перед началом обучения.
    
    Аргументы:
        categories: Список словарей категорий с полями 'id' и 'name'
        include_all: Добавлять ли пункт «Все категории»
        
    Возвращает:
        InlineKeyboardMarkup для выбора категории в обучении
    """
    keyboard = []
    
    if include_all:
        keyboard.append([
            InlineKeyboardButton("📚 Все категории", callback_data="cert_learn_all")
        ])
    
    for category in categories:
        keyboard.append([
            InlineKeyboardButton(
                f"📁 {category['name']}",
                callback_data=f"cert_learn_cat_{category['id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("❌ Отмена", callback_data="cert_learn_cancel")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_learning_difficulty_keyboard() -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру выбора сложности для обучения.
    
    Возвращает:
        InlineKeyboardMarkup для выбора сложности
    """
    keyboard = [
        [
            InlineKeyboardButton("🟢 Легкий", callback_data="cert_learn_diff_easy"),
            InlineKeyboardButton("🟡 Средний", callback_data="cert_learn_diff_medium"),
        ],
        [
            InlineKeyboardButton("🔴 Сложный", callback_data="cert_learn_diff_hard"),
        ],
        [
            InlineKeyboardButton("📚 Любой", callback_data="cert_learn_diff_all"),
        ],
        [
            InlineKeyboardButton("❌ Отмена", callback_data="cert_learn_diff_cancel"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_answer_keyboard() -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру для ответа на вопрос.
    
    Возвращает:
        InlineKeyboardMarkup с вариантами ответов A, B, C, D
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


def get_learning_answer_keyboard() -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру для ответа в режиме обучения.
    
    Возвращает:
        InlineKeyboardMarkup с вариантами A, B, C, D и кнопкой отмены
    """
    keyboard = [
        [
            InlineKeyboardButton("🅰️ A", callback_data="cert_learn_answer_A"),
            InlineKeyboardButton("🅱️ B", callback_data="cert_learn_answer_B"),
        ],
        [
            InlineKeyboardButton("©️ C", callback_data="cert_learn_answer_C"),
            InlineKeyboardButton("🇩 D", callback_data="cert_learn_answer_D"),
        ],
        [
            InlineKeyboardButton("❌ Завершить обучение", callback_data="cert_learn_cancel_session")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_test_control_keyboard() -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру управления тестом.
    
    Возвращает:
        InlineKeyboardMarkup с кнопкой отмены теста
    """
    keyboard = [
        [InlineKeyboardButton("❌ Завершить тест", callback_data="cert_cancel_test")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_next_question_keyboard() -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру перехода к следующему вопросу.
    
    Возвращает:
        InlineKeyboardMarkup с кнопкой следующего вопроса
    """
    keyboard = [
        [InlineKeyboardButton("➡️ Следующий вопрос", callback_data="cert_next_question")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_learning_next_question_keyboard() -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру перехода к следующему учебному вопросу.
    
    Возвращает:
        InlineKeyboardMarkup с кнопкой следующего вопроса
    """
    keyboard = [
        [InlineKeyboardButton("➡️ Следующий вопрос", callback_data="cert_learn_next_question")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_confirmation_keyboard(confirm_data: str, cancel_data: str = "cert_cancel") -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру для диалогов подтверждения.
    
    Аргументы:
        confirm_data: Callback data для кнопки подтверждения
        cancel_data: Callback data для кнопки отмены
        
    Возвращает:
        InlineKeyboardMarkup с кнопками подтверждения/отмены
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data=confirm_data),
            InlineKeyboardButton("❌ Нет", callback_data=cancel_data),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_top_category_selector_keyboard(categories: List[dict]) -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру выбора категории для просмотра топа месяца.
    
    Аргументы:
        categories: Список словарей категорий с полями 'id' и 'name'
        
    Возвращает:
        InlineKeyboardMarkup для выбора категории топа
    """
    keyboard = []
    
    # Общий рейтинг
    keyboard.append([
        InlineKeyboardButton("📊 Общий рейтинг", callback_data="cert_top_all")
    ])
    
    # Отдельные категории
    for category in categories:
        keyboard.append([
            InlineKeyboardButton(
                f"📁 {category['name']}",
                callback_data=f"cert_top_cat_{category['id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("🔙 Назад", callback_data="cert_top_back")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_top_back_keyboard() -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру с кнопкой возврата для топа.
    
    Возвращает:
        InlineKeyboardMarkup с возвратом к выбору категории
    """
    keyboard = [
        [InlineKeyboardButton("🔙 К выбору категории", callback_data="cert_top_select")]
    ]
    return InlineKeyboardMarkup(keyboard)


# ============================================================================
# Клавиатуры администратора
# ============================================================================

def get_categories_list_keyboard(categories: List[dict], page: int = 1, per_page: int = 10) -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру списка категорий с пагинацией.
    
    Аргументы:
        categories: Список словарей категорий
        page: Номер текущей страницы
        per_page: Количество элементов на странице
        
    Возвращает:
        InlineKeyboardMarkup для списка категорий
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
    
    # Пагинация
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
    Сформировать inline-клавиатуру действий с категорией.
    
    Аргументы:
        category_id: ID категории
        is_active: Текущий статус активности
        
    Возвращает:
        InlineKeyboardMarkup с действиями категории
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
    Сформировать inline-клавиатуру выбора поля категории для редактирования.
    
    Аргументы:
        category_id: ID категории
        
    Возвращает:
        InlineKeyboardMarkup с вариантами редактирования полей
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
    Сформировать inline-клавиатуру списка вопросов с пагинацией.
    
    Аргументы:
        questions: Список словарей вопросов
        page: Номер текущей страницы
        per_page: Количество элементов на странице
        
    Возвращает:
        InlineKeyboardMarkup для списка вопросов
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
    
    # Пагинация
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
    Сформировать inline-клавиатуру действий с вопросом.
    
    Аргументы:
        question_id: ID вопроса
        is_active: Текущий статус активности
        
    Возвращает:
        InlineKeyboardMarkup с действиями вопроса
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
    Сформировать inline-клавиатуру выбора поля вопроса для редактирования.
    
    Аргументы:
        question_id: ID вопроса
        
    Возвращает:
        InlineKeyboardMarkup с вариантами редактирования полей
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
            InlineKeyboardButton("📁 Категории", callback_data=f"cert_q_edit_cats_{question_id}"),
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data=f"cert_q_view_{question_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_difficulty_keyboard() -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру выбора сложности.
    
    Возвращает:
        InlineKeyboardMarkup с вариантами сложности
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
    Сформировать inline-клавиатуру выбора правильного ответа.
    
    Возвращает:
        InlineKeyboardMarkup с вариантами ответов
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
    Сформировать inline-клавиатуру множественного выбора категорий.
    
    Аргументы:
        categories: Список словарей категорий
        selected_ids: Список уже выбранных ID категорий
        
    Возвращает:
        InlineKeyboardMarkup для множественного выбора категорий
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


def get_category_edit_multiselect_keyboard(
    categories: List[dict], 
    selected_ids: Optional[List[int]] = None,
    question_id: int = None
) -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру редактирования категорий вопроса.
    
    Аргументы:
        categories: Список словарей категорий
        selected_ids: Список уже выбранных ID категорий
        question_id: ID редактируемого вопроса
        
    Возвращает:
        InlineKeyboardMarkup для множественного выбора категорий при редактировании
    """
    selected_ids = selected_ids or []
    keyboard = []
    
    for cat in categories:
        is_selected = cat['id'] in selected_ids
        prefix = "✅ " if is_selected else "⬜️ "
        keyboard.append([
            InlineKeyboardButton(
                f"{prefix}{cat['name']}",
                callback_data=f"cert_q_cat_toggle_{cat['id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton("✅ Сохранить", callback_data="cert_q_cat_save"),
        InlineKeyboardButton("❌ Отмена", callback_data=f"cert_q_view_{question_id}" if question_id else "cert_cancel"),
    ])
    
    return InlineKeyboardMarkup(keyboard)


def get_outdated_questions_keyboard(questions: List[dict]) -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру управления устаревшими вопросами.
    
    Аргументы:
        questions: Список словарей устаревших вопросов
        
    Возвращает:
        InlineKeyboardMarkup для устаревших вопросов
    """
    keyboard = []
    
    for q in questions[:10]:  # Ограничить до 10 элементов
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


def get_settings_keyboard(show_correct: bool = True, obfuscate_names: bool = False) -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру настроек аттестации.
    
    Аргументы:
        show_correct: Текущее значение настройки show_correct_answer
        obfuscate_names: Текущее значение настройки obfuscate_names
    
    Возвращает:
        InlineKeyboardMarkup для настроек
    """
    show_correct_text = "✅ Показывать ответ" if show_correct else "❌ Показывать ответ"
    obfuscate_text = "✅ Скрывать имена" if obfuscate_names else "❌ Скрывать имена"
    keyboard = [
        [InlineKeyboardButton("📋 Кол-во вопросов", callback_data="cert_set_questions")],
        [InlineKeyboardButton("⏱ Время на тест", callback_data="cert_set_time")],
        [InlineKeyboardButton("🎯 Проходной балл", callback_data="cert_set_score")],
        [InlineKeyboardButton(f"👁 {show_correct_text}", callback_data="cert_set_show_correct")],
        [InlineKeyboardButton(f"🔒 {obfuscate_text}", callback_data="cert_set_obfuscate")],
        [InlineKeyboardButton("🔙 Назад", callback_data="cert_admin_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_history_pagination_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """
    Сформировать inline-клавиатуру пагинации истории.
    
    Аргументы:
        page: Текущая страница
        total_pages: Общее число страниц
        
    Возвращает:
        InlineKeyboardMarkup для пагинации
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
