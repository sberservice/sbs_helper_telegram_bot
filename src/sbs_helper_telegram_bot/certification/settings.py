"""
Employee Certification Module Settings

Module-specific configuration settings for employee certification and testing.
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU

# Module metadata
MODULE_NAME: Final[str] = "Аттестация сотрудников"
MODULE_DESCRIPTION: Final[str] = "Тестирование знаний сотрудников с рейтингом и историей"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

# Main menu button for this module
MENU_BUTTON_TEXT: Final[str] = "📝 Аттестация"

# Default test configuration
DEFAULT_QUESTIONS_COUNT: Final[int] = 20
DEFAULT_TIME_LIMIT_MINUTES: Final[int] = 15
DEFAULT_PASSING_SCORE_PERCENT: Final[int] = 80
DEFAULT_RELEVANCE_MONTHS: Final[int] = 6  # Questions become outdated after this many months

# Submenu button configuration for regular users
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📝 Начать тест"],
    ["🎓 Режим обучения"],
    ["📊 Мой рейтинг", "📜 История тестов"],
    ["🏆 Топ месяца"],
    [COMMON_BUTTON_MAIN_MENU]
]

# Admin submenu (includes admin panel button)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    ["📝 Начать тест"],
    ["🎓 Режим обучения"],
    ["📊 Мой рейтинг", "📜 История тестов"],
    ["🏆 Топ месяца"],
    ["⚙️ Управление", COMMON_BUTTON_MAIN_MENU]
]

# Admin panel menu buttons
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["❓ Вопросы", "📁 Категории"],
    ["⚠️ Устаревшие вопросы", "📊 Статистика"],
    ["⚙️ Настройки теста"],
    ["🔙 Назад", COMMON_BUTTON_MAIN_MENU]
]

# Admin questions management submenu
ADMIN_QUESTIONS_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все вопросы", "➕ Добавить вопрос"],
    ["🔍 Найти вопрос", "📂 Без категории"],
    ["🔙 Админ меню", COMMON_BUTTON_MAIN_MENU]
]

# Admin categories management submenu
ADMIN_CATEGORIES_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все категории", "➕ Добавить категорию"],
    ["🔙 Админ меню", COMMON_BUTTON_MAIN_MENU]
]

# User data keys for context storage
TEST_IN_PROGRESS_KEY: Final[str] = 'certification_test_in_progress'
CURRENT_ATTEMPT_ID_KEY: Final[str] = 'certification_current_attempt_id'
CURRENT_QUESTION_INDEX_KEY: Final[str] = 'certification_current_question_index'
TEST_QUESTIONS_KEY: Final[str] = 'certification_test_questions'
TEST_START_TIME_KEY: Final[str] = 'certification_test_start_time'
SELECTED_CATEGORY_KEY: Final[str] = 'certification_selected_category'

# Learning mode user data keys
LEARNING_IN_PROGRESS_KEY: Final[str] = 'certification_learning_in_progress'
LEARNING_QUESTIONS_KEY: Final[str] = 'certification_learning_questions'
LEARNING_CURRENT_QUESTION_INDEX_KEY: Final[str] = 'certification_learning_current_question_index'
LEARNING_SELECTED_CATEGORY_KEY: Final[str] = 'certification_learning_selected_category'
LEARNING_CORRECT_COUNT_KEY: Final[str] = 'certification_learning_correct_count'

# Admin context keys
ADMIN_EDITING_QUESTION_KEY: Final[str] = 'certification_admin_editing_question'
ADMIN_EDITING_CATEGORY_KEY: Final[str] = 'certification_admin_editing_category'
ADMIN_NEW_QUESTION_DATA_KEY: Final[str] = 'certification_admin_new_question_data'
ADMIN_NEW_CATEGORY_DATA_KEY: Final[str] = 'certification_admin_new_category_data'

# Difficulty labels for display
DIFFICULTY_LABELS: Final[dict] = {
    'easy': '🟢 Легкий',
    'medium': '🟡 Средний',
    'hard': '🔴 Сложный'
}

# Answer option labels
ANSWER_OPTIONS: Final[List[str]] = ['A', 'B', 'C', 'D']
ANSWER_EMOJIS: Final[dict] = {
    'A': '🅰️',
    'B': '🅱️',
    'C': '©️',
    'D': '🇩'
}

# Database setting keys
DB_SETTING_QUESTIONS_COUNT: Final[str] = 'questions_count'
DB_SETTING_TIME_LIMIT: Final[str] = 'time_limit_minutes'
DB_SETTING_PASSING_SCORE: Final[str] = 'passing_score_percent'
DB_SETTING_SHOW_CORRECT: Final[str] = 'show_correct_answer'
DB_SETTING_OBFUSCATE_NAMES: Final[str] = 'obfuscate_names'

# Default values
DEFAULT_SHOW_CORRECT: Final[bool] = True
DEFAULT_OBFUSCATE_NAMES: Final[bool] = False
