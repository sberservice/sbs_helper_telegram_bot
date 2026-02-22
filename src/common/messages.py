"""
Общие сообщения

Содержит только действительно общие сообщения, используемые во всём боте,
не относящиеся к конкретным модулям.

Сообщения конкретных модулей должны находиться в их messages.py.
"""
# pylint: disable=line-too-long

from typing import Optional
from datetime import datetime

from src.common.constants.sync import SYNC_INTERVAL_HOURS
from src.common.health_check import get_tax_health_status_lines

# Приветственные и авторизационные сообщения
MESSAGE_WELCOME = "👋 *Рады видеть вас в боте\-помощнике инженера СберСервис\!*\n\nВозможности:\n• ✅ Проверка заявок по правилам\n• 📸 Обработка скриншотов карты из Спринта\n• 🔢 Поиск кодов ошибок UPOS и подсказок\n• 📝 Аттестация и рейтинг\n• 📰 Новости и важные объявления\n\n📚 *GitHub:* https://github\.com/sberservice/sbs\_helper\_telegram\_bot"
MESSAGE_PLEASE_ENTER_INVITE = "Пожалуйста, введите ваш инвайт.\nЕго можно попросить у другого пользователя этого бота, если он введет команду /invite или выберет её из меню."

# Сообщения, связанные с инвайтами
MESSAGE_AVAILABLE_INVITES = "Доступные инвайты:"
MESSAGE_NO_INVITES = "У вас нет доступных инвайтов."
MESSAGE_WELCOME_SHORT = "Добро пожаловать!"
MESSAGE_WELCOME_PRE_INVITED = "🎉 Добро пожаловать! Вы были заранее добавлены в список пользователей бота."
MESSAGE_INVITE_ISSUED = "Вам выдан инвайт. Вы можете им поделиться: {invite}"
MESSAGE_INVITE_ALREADY_USED = "Данный инвайт уже был использован. Пожалуйста, введите другой инвайт."
MESSAGE_NO_ADMIN_RIGHTS = "⛔ У вас нет прав администратора\\."

# Сообщение о выключенной инвайт-системе
def get_invite_system_disabled_message() -> str:
    """
    Получить сообщение о выключенной инвайт-системе с динамическим интервалом синхронизации.

    Returns:
        Отформатированное сообщение с актуальным интервалом синхронизации из настроек.
    """
    if SYNC_INTERVAL_HOURS == 24:
        interval_text = "ежедневно"
    elif SYNC_INTERVAL_HOURS < 24:
        interval_text = f"каждые {SYNC_INTERVAL_HOURS} час(а/ов)"
    else:
        days = round(SYNC_INTERVAL_HOURS / 24)
        interval_text = f"каждые {days} дня/дней"
    
    return f"""⚠️ В настоящий момент доступ к боту имеют только участники группы Telegram "Техподдержка POS СБС".

Если стали участником этой группы, ждите, список участников обновляется {interval_text}."""

# Сохраняем обратную совместимость — используем результат функции как константу
MESSAGE_INVITE_SYSTEM_DISABLED = get_invite_system_disabled_message()

# Описания команд бота
COMMAND_DESC_START = "Начать работу с ботом"
COMMAND_DESC_MENU = "Показать главное меню"
COMMAND_DESC_HELP = "Показать справку"

# Подписи главного меню
BUTTON_MAIN_MENU_TEXT = "Главное меню"
BUTTON_MAIN_MENU_ICON = "🏠"
BUTTON_MAIN_MENU = f"{BUTTON_MAIN_MENU_ICON} {BUTTON_MAIN_MENU_TEXT}"

# Сообщения главного меню
MESSAGE_MAIN_MENU = f"{BUTTON_MAIN_MENU_ICON} *{BUTTON_MAIN_MENU_TEXT}*\n\nВыберите действие из меню:"
MESSAGE_UNRECOGNIZED_INPUT = "🤔 Не понял вашу команду\\.\n\n*Используйте:*\n• Кнопки меню ниже\n• Команда /menu\n• Или /help для справки"
SECTION_DIVIDER_THIN = "────────────"


def _escape_markdown_v2(text: str) -> str:
    """
    Экранировать специальные символы для Telegram MarkdownV2.

    Сначала экранируются обратные слэши, затем спецсимволы.
    Это гарантирует корректную обработку текста, содержащего
    обратные слэши.

    Args:
        text: Текст для экранирования.

    Returns:
        Экранированный текст.
    """
    # Сначала экранируем обратные слэши
    text = text.replace('\\', '\\\\')
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def _format_main_menu_message(
    display_name: str,
    certification_points: int,
    rank_name: str,
    rank_icon: str,
    passed_categories_count: int,
    max_achievable_points: int,
    overall_progress_percent: int,
    overall_progress_bar: str,
    next_rank_name: Optional[str],
    points_to_next_rank: Optional[int],
    expired_categories_count: int,
) -> str:
    safe_name = _escape_markdown_v2(display_name)
    safe_rank = _escape_markdown_v2(rank_name)
    safe_next = _escape_markdown_v2(next_rank_name) if next_rank_name else None
    safe_progress_bar = _escape_markdown_v2(overall_progress_bar)

    latest_preview = _get_latest_news_preview_text()

    message = (
        f"{BUTTON_MAIN_MENU_ICON} *{BUTTON_MAIN_MENU_TEXT}*\n\n"
        f"С возвращением, *{safe_name}*\\!\n\n"
        f"{rank_icon} *Аттестационный ранг:* *{safe_rank}*\n"
        f"📊 *Прогресс аттестации:* {safe_progress_bar} {overall_progress_percent}% {certification_points}/{max_achievable_points}\n"
        f"📚 *Освоено категорий:* {passed_categories_count}"
    )

    if expired_categories_count > 0:
        message += (
            "\n⚠️ *Важно:* Есть истекшие результаты по категориям "
            f"\(*{expired_categories_count}*\)\. "
            "Аттестационный ранг может снизиться\."
        )

    if points_to_next_rank is not None and safe_next:
        remaining = max(points_to_next_rank, 0)
        message += f"\n🎯 *До ранга* *{safe_next}*: ещё *{remaining}* балл\(ов\)"

    if latest_preview:
        message += f"\n\n{SECTION_DIVIDER_THIN}" + latest_preview

    health_text = _get_tax_health_status_text()
    if health_text:
        message += f"\n\n{SECTION_DIVIDER_THIN}\n\n{health_text}"

    message += "\n\nВыберите действие из меню:"
    return message


def get_main_menu_message(user_id: int, first_name: Optional[str] = None) -> str:
    """
    Сформировать персонализированное сообщение главного меню по данным аттестации.

    Args:
        user_id: Telegram ID пользователя.
        first_name: Имя пользователя для приветствия по умолчанию.

    Returns:
        Персонализированное сообщение главного меню (MarkdownV2) или сообщение по умолчанию при ошибке.
    """
    display_name = first_name or "коллега"
    try:
        from src.sbs_helper_telegram_bot.certification import certification_logic

        cert_summary = certification_logic.get_user_certification_summary(user_id)

        return _format_main_menu_message(
            display_name=display_name,
            certification_points=cert_summary.get('certification_points', 0),
            rank_name=cert_summary.get('rank_name', 'Новичок'),
            rank_icon=cert_summary.get('rank_icon', '🌱'),
            passed_categories_count=cert_summary.get('passed_categories_count', 0),
            max_achievable_points=int(cert_summary.get('max_achievable_points') or max(int(cert_summary.get('certification_points', 0) or 0), 1)),
            overall_progress_percent=int(cert_summary.get('overall_progress_percent') or 0),
            overall_progress_bar=cert_summary.get('overall_progress_bar', '[□□□□□□□□□□]'),
            next_rank_name=cert_summary.get('next_rank_name'),
            points_to_next_rank=cert_summary.get('points_to_next_rank'),
            expired_categories_count=int(cert_summary.get('expired_categories_count') or 0),
        )
    except Exception:
        return MESSAGE_MAIN_MENU


def _get_latest_news_preview_text() -> Optional[str]:
    """
    Получить превью последней новости для главного меню.

    Returns:
        Строка превью или None, если новостей нет.
    """
    try:
        from src.sbs_helper_telegram_bot.news import news_logic

        articles, _ = news_logic.get_published_news(page=0, per_page=1, include_expired=False)
        if not articles:
            return None

        article = articles[0]
        title = _escape_markdown_v2(article.get('title', 'Без названия'))
        published_ts = article.get('published_timestamp', 0)
        if published_ts:
            published_date = datetime.fromtimestamp(published_ts).strftime('%d.%m.%Y')
            published_date = _escape_markdown_v2(published_date)
        else:
            published_date = _escape_markdown_v2("без даты")

        content = article.get('content', '')
        if len(content) > 200:
            content = content[:197] + "..."
        content = _escape_markdown_v2(content)

        category_emoji = article.get('category_emoji', '📰')

        preview = (
            "\n\n📰 *Последняя новость*\n"
            f"{category_emoji} *{title}*\n"
            f"_{published_date}_\n"
            f"{content}"
        )
        return preview
    except Exception:
        return None


def _get_tax_health_status_text() -> Optional[str]:
    """
    Получить текст статуса налоговой для главного меню.

    Returns:
        Экранированный текст статуса или None при ошибке.
    """
    try:
        lines = get_tax_health_status_lines()
        if not lines:
            return None
        return "\n".join(lines)
    except Exception:
        return None

# Сообщение справки — обзор всех модулей
MESSAGE_MAIN_HELP = """❓ *Помощь*

*Модули бота:*

*✅ Валидация заявок*
Проверяет заявки на соответствие требованиям \\(функционал не окончательный, происходит наполнение правилами\\)\\.

*📸 Обработка скриншота*
Обрабатывает скриншоты карт\\. Отправьте изображение как файл \\(не фото\\), и бот выполнит необходимую обработку\\.

*🔢 UPOS Ошибки*
Поиск кодов ошибок системы UPOS с подробными описаниями и рекомендациями по устранению\\.

*📝 Аттестация*
Прохождение тестирования для проверки знаний по различным категориям\\. Система рейтингов и история попыток\\.

*⏱️ КТР \\(Коэффициент Трудозатрат\\)*
Поиск кодов КТР и получение информации о нормативном времени выполнения работ в минутах\\.

*📬 Обратная связь*
Отправка отзывов, предложений и вопросов команде поддержки с возможностью получения ответов\\.

*🎫 Мои инвайты*
Показывает ваши доступные инвайт\\-коды, которыми вы можете поделиться с другими пользователями для предоставления доступа к боту\\.

*Основные команды бота:*
• `/start` \\- начать работу с ботом
• `/menu` \\- показать главное меню
• `/reset` \\- сбросить состояние и вернуться в главное меню
• `/help` \\- показать эту справку

💡 *Совет:* Если кнопки бота перестали работать или вы застряли в каком\\-то состоянии, используйте команду `/reset` для возврата в главное меню\\.

📚 *GitHub:* https://github\\.com/sberservice/sbs\\_helper\\_telegram\\_bot"""

# Сообщение меню настроек
MESSAGE_SETTINGS_MENU = "⚙️ *Настройки*\n\nВыберите действие из меню:"

# Сообщение меню модулей
MESSAGE_MODULES_MENU = "⚡ *Функции бота*\n\nВыберите модуль:"

# Подписи кнопок главного меню
BUTTON_MODULES = "⚡ Начать работу"
BUTTON_SETTINGS = "⚙️ Настройки"
BUTTON_MY_INVITES = "🎫 Мои инвайты"
BUTTON_HELP = "❓ Помощь"
BUTTON_BOT_ADMIN = "🛠️ Админ бота"
BUTTON_PROFILE = "🏆 Достижения"

# Кнопки модулей — устарели, теперь загружаются из bot_settings.MODULE_CONFIG
# Эти константы оставлены для обратной совместимости, но не используются при генерации клавиатуры
BUTTON_VALIDATE_TICKET = "✅ Валидация заявок"
BUTTON_SCREENSHOT = "📸 Обработать скриншот"
BUTTON_UPOS_ERRORS = "🔢 UPOS Ошибки"
BUTTON_CERTIFICATION = "📝 Аттестация"
BUTTON_KTR = "⏱️ КТР"
BUTTON_FEEDBACK = "📬 Обратная связь"
BUTTON_NEWS = "📰 Новости"


def get_main_menu_keyboard(is_admin: bool = False):
    """
    Собрать клавиатуру главного меню с кнопками модулей и настроек.
    Для администраторов включает кнопку админки.

    Args:
        is_admin: Является ли пользователь администратором.

    Returns:
        ReplyKeyboardMarkup для главного меню.
    """
    from telegram import ReplyKeyboardMarkup
    
    if is_admin:
        buttons = [
            [BUTTON_MODULES, BUTTON_PROFILE],
            [BUTTON_NEWS, BUTTON_SETTINGS],
            [BUTTON_BOT_ADMIN]
        ]
    else:
        buttons = [
            [BUTTON_MODULES, BUTTON_PROFILE],
            [BUTTON_NEWS, BUTTON_SETTINGS]
        ]
    
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_settings_menu_keyboard():
    """
    Собрать клавиатуру меню настроек с инвайтами, справкой и возвратом в главное меню.

    Returns:
        ReplyKeyboardMarkup для меню настроек.
    """
    from telegram import ReplyKeyboardMarkup
    
    buttons = [
        [BUTTON_MY_INVITES, BUTTON_HELP],
        [BUTTON_MAIN_MENU]
    ]
    
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )


def get_modules_menu_keyboard():
    """
    Собрать клавиатуру меню модулей со всеми доступными модулями бота.
    Показывает только включённые модули в заданном порядке.

    Конфигурация модулей (порядок, подписи, колонки) берётся из
    bot_settings.MODULE_CONFIG. Чтобы изменить порядок или добавить новый модуль,
    обновите список MODULE_CONFIG в src/common/bot_settings.py.

    Returns:
        ReplyKeyboardMarkup для меню модулей.
    """
    from telegram import ReplyKeyboardMarkup
    from src.common import bot_settings
    
    # Получаем включённые модули, видимые в меню, в заданном порядке
    modules = bot_settings.get_modules_config(
        enabled_only=True,
        visible_in_modules_menu_only=True,
    )
    
    # Динамически собираем строки кнопок по настройке columns
    buttons = []
    current_row = []
    
    for module in modules:
        button_label = module['button_label']
        columns = module.get('columns', 2)  # По умолчанию 2 колонки
        
        # Добавляем кнопку в текущую строку
        current_row.append(button_label)
        
        # Если строка заполнена (по настройке columns), начинаем новую
        if len(current_row) >= columns:
            buttons.append(current_row)
            current_row = []
    
    # Добавляем оставшиеся кнопки в последнюю строку
    if current_row:
        buttons.append(current_row)
    
    # Всегда добавляем кнопку главного меню внизу
    buttons.append([BUTTON_MAIN_MENU])
    
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True
    )
