"""
Настройки модуля аттестации сотрудников

Конфигурационные параметры модуля аттестации и тестирования.
"""

from typing import Final, List

from src.common.messages import BUTTON_MAIN_MENU as COMMON_BUTTON_MAIN_MENU

# Метаданные модуля
MODULE_NAME: Final[str] = "Аттестация сотрудников"
MODULE_DESCRIPTION: Final[str] = "Тестирование знаний сотрудников с рейтингом и историей"
MODULE_VERSION: Final[str] = "1.0.0"
MODULE_AUTHOR: Final[str] = "SberService"

# Кнопка главного меню для этого модуля
MENU_BUTTON_TEXT: Final[str] = "📝 Аттестация"

# Тексты кнопок
BUTTON_START_TEST: Final[str] = "📝 Начать тест"
BUTTON_LEARNING_MODE: Final[str] = "🎓 Режим обучения"
BUTTON_MY_RANKING: Final[str] = "📊 Мой рейтинг"
BUTTON_TEST_HISTORY: Final[str] = "📜 История тестов"
BUTTON_MONTHLY_TOP: Final[str] = "🏆 Топ месяца"
BUTTON_ADMIN_PANEL: Final[str] = "⚙️ Управление"
BUTTON_MAIN_MENU: Final[str] = COMMON_BUTTON_MAIN_MENU

# Конфигурация теста по умолчанию
DEFAULT_QUESTIONS_COUNT: Final[int] = 20
DEFAULT_TIME_LIMIT_MINUTES: Final[int] = 15
DEFAULT_PASSING_SCORE_PERCENT: Final[int] = 80
DEFAULT_RELEVANCE_MONTHS: Final[int] = 6  # Вопросы становятся неактуальными спустя это число месяцев
CATEGORY_RESULT_VALIDITY_DAYS: Final[int] = 30  # Срок действия результата по категории
CATEGORY_RESULT_EXPIRY_WARNING_DAYS: Final[int] = 7  # Порог предупреждения о скором истечении

# Конфигурация кнопок подменю для пользователей
SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_START_TEST,BUTTON_LEARNING_MODE],
    [BUTTON_MY_RANKING, BUTTON_TEST_HISTORY],
    [BUTTON_MONTHLY_TOP],
    [BUTTON_MAIN_MENU]
]

# Подменю администратора (включает кнопку админ-панели)
ADMIN_SUBMENU_BUTTONS: Final[List[List[str]]] = [
    [BUTTON_START_TEST,BUTTON_LEARNING_MODE],
    [BUTTON_MY_RANKING, BUTTON_TEST_HISTORY],
    [BUTTON_MONTHLY_TOP],
    [BUTTON_ADMIN_PANEL, BUTTON_MAIN_MENU]
]

# Кнопки меню админ-панели
ADMIN_MENU_BUTTONS: Final[List[List[str]]] = [
    ["❓ Вопросы", "📁 Категории"],
    ["⚠️ Устаревшие вопросы", "📊 Статистика"],
    ["⚙️ Настройки теста"],
    ["🔙 Назад", COMMON_BUTTON_MAIN_MENU]
]

# Подменю управления вопросами
ADMIN_QUESTIONS_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все вопросы", "➕ Добавить вопрос"],
    ["🔍 Найти вопрос", "📂 Без категории"],
    ["🔙 Админ меню", COMMON_BUTTON_MAIN_MENU]
]

# Подменю управления категориями
ADMIN_CATEGORIES_BUTTONS: Final[List[List[str]]] = [
    ["📋 Все категории", "➕ Добавить категорию"],
    ["🔙 Админ меню", COMMON_BUTTON_MAIN_MENU]
]

# Ключи user_data для хранения состояния
TEST_IN_PROGRESS_KEY: Final[str] = 'certification_test_in_progress'
CURRENT_ATTEMPT_ID_KEY: Final[str] = 'certification_current_attempt_id'
CURRENT_QUESTION_INDEX_KEY: Final[str] = 'certification_current_question_index'
TEST_QUESTIONS_KEY: Final[str] = 'certification_test_questions'
TEST_START_TIME_KEY: Final[str] = 'certification_test_start_time'
SELECTED_CATEGORY_KEY: Final[str] = 'certification_selected_category'

# Ключи user_data для режима обучения
LEARNING_IN_PROGRESS_KEY: Final[str] = 'certification_learning_in_progress'
LEARNING_QUESTIONS_KEY: Final[str] = 'certification_learning_questions'
LEARNING_CURRENT_QUESTION_INDEX_KEY: Final[str] = 'certification_learning_current_question_index'
LEARNING_SELECTED_CATEGORY_KEY: Final[str] = 'certification_learning_selected_category'
LEARNING_CORRECT_COUNT_KEY: Final[str] = 'certification_learning_correct_count'
LEARNING_SELECTED_DIFFICULTY_KEY: Final[str] = 'certification_learning_selected_difficulty'

# Ключи контекста администратора
ADMIN_EDITING_QUESTION_KEY: Final[str] = 'certification_admin_editing_question'
ADMIN_EDITING_CATEGORY_KEY: Final[str] = 'certification_admin_editing_category'
ADMIN_NEW_QUESTION_DATA_KEY: Final[str] = 'certification_admin_new_question_data'
ADMIN_NEW_CATEGORY_DATA_KEY: Final[str] = 'certification_admin_new_category_data'

# Метки сложности для отображения
DIFFICULTY_LABELS: Final[dict] = {
    'easy': '🟢 Легкий',
    'medium': '🟡 Средний',
    'hard': '🔴 Сложный'
}

# Метки вариантов ответа
ANSWER_OPTIONS: Final[List[str]] = ['A', 'B', 'C', 'D']
ANSWER_EMOJIS: Final[dict] = {
    'A': '🅰️',
    'B': '🅱️',
    'C': '©️',
    'D': '🇩'
}

# Ключи настроек в БД
DB_SETTING_QUESTIONS_COUNT: Final[str] = 'questions_count'
DB_SETTING_TIME_LIMIT: Final[str] = 'time_limit_minutes'
DB_SETTING_PASSING_SCORE: Final[str] = 'passing_score_percent'
DB_SETTING_SHOW_CORRECT: Final[str] = 'show_correct_answer'
DB_SETTING_OBFUSCATE_NAMES: Final[str] = 'obfuscate_names'

# Значения по умолчанию
DEFAULT_SHOW_CORRECT: Final[bool] = True
DEFAULT_OBFUSCATE_NAMES: Final[bool] = False
