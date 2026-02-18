"""
Сообщения модуля геймификации.

Все пользовательские сообщения для системы достижений/геймификации.
Сообщения используют формат Telegram MarkdownV2 там, где это нужно.
"""
# pylint: disable=line-too-long
# Примечание: двойные обратные слэши нужны для экранирования MarkdownV2

from typing import Optional, Dict, List
from . import settings


# ===== ПОДМЕНЮ =====

MESSAGE_SUBMENU = "🏆 *Достижения*\n\nВаш цифровой профиль, достижения и рейтинги\\.\n\nВыберите действие из меню:"


# ===== СООБЩЕНИЯ ПРОФИЛЯ =====

def format_profile_message(
    first_name: str,
    last_name: Optional[str],
    total_score: int,
    rank_name: str,
    rank_icon: str,
    next_rank_name: Optional[str],
    next_rank_threshold: Optional[int],
    total_achievements: int,
    max_achievements: int,
    achievements_by_level: Dict[int, int],
    certification_rank_name: Optional[str] = None,
    certification_rank_icon: Optional[str] = None,
    certification_points: Optional[int] = None,
    passed_tests_count: Optional[int] = None,
    passed_categories_count: Optional[int] = None,
    certification_next_rank_name: Optional[str] = None,
    certification_points_to_next: Optional[int] = None,
) -> str:
    """
    Сформировать сообщение профиля пользователя.
    
    Args:
        first_name: имя пользователя.
        last_name: фамилия пользователя (опционально).
        total_score: суммарные очки.
        rank_name: название текущего ранга.
        rank_icon: эмодзи текущего ранга.
        next_rank_name: следующий ранг (None, если уже максимальный).
        next_rank_threshold: очков нужно до следующего ранга.
        total_achievements: всего разблокированных уровней достижений.
        max_achievements: максимальное возможное число уровней достижений.
        achievements_by_level: словарь уровень -> количество.
    
    Returns:
        Сообщение, готовое для MarkdownV2.
    """
    # Экранируем спецсимволы для MarkdownV2
    name = _escape_md(first_name)
    if last_name:
        name += f" {_escape_md(last_name)}"
    
    # Прогресс до следующего ранга
    display_rank_name = certification_rank_name or rank_name
    display_rank_icon = certification_rank_icon or rank_icon

    if certification_next_rank_name and certification_points_to_next is not None:
        progress_text = f"\n📈 До «{_escape_md(certification_next_rank_name)}»: *{certification_points_to_next}* балл\(ов\)"
    elif next_rank_name and next_rank_threshold:
        progress_text = f"\n📈 До «{_escape_md(next_rank_name)}»: *{next_rank_threshold - total_score}* очков"
    else:
        progress_text = "\n🎉 *Максимальный ранг достигнут\\!*"
    
    # Разбивка по достижениям
    bronze = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_BRONZE, 0)
    silver = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_SILVER, 0)
    gold = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_GOLD, 0)
    
    certification_block = ""
    if certification_points is not None:
        certification_block = (
            f"\n\n📝 *Аттестация*\n"
            f"{display_rank_icon} Ранг: *{_escape_md(display_rank_name)}*\n"
            f"📈 Баллы: *{certification_points}*\n"
            f"✅ Пройдено тестов: *{passed_tests_count or 0}*\n"
            f"📚 Освоено категорий: *{passed_categories_count or 0}*"
            f"{progress_text}"
        )

    return (
        f"👤 *Профиль: {name}*\n"
        f"{'─' * 20}\n\n"
        f"💎 Очки: *{total_score}*"
        f"\n\n"
        f"🎖️ *Достижения: {total_achievements}/{max_achievements}*\n"
        f"   🥉 Бронза: {bronze}\n"
        f"   🥈 Серебро: {silver}\n"
        f"   🥇 Золото: {gold}"
        f"{certification_block}"
    )


def format_other_user_profile_message(
    first_name: str,
    last_name: Optional[str],
    total_score: int,
    rank_name: str,
    rank_icon: str,
    total_achievements: int,
    achievements_by_level: Dict[int, int],
    obfuscate: bool = False,
    certification_rank_name: Optional[str] = None,
    certification_rank_icon: Optional[str] = None,
    certification_points: Optional[int] = None,
    passed_tests_count: Optional[int] = None,
    passed_categories_count: Optional[int] = None,
) -> str:
    """
    Сформировать профиль другого пользователя (просмотр из рейтинга).
    
    Args:
        first_name: имя пользователя.
        last_name: фамилия пользователя (опционально).
        total_score: суммарные очки.
        rank_name: название текущего ранга.
        rank_icon: эмодзи текущего ранга.
        total_achievements: всего разблокированных уровней достижений.
        achievements_by_level: словарь уровень -> количество.
        obfuscate: скрывать ли полное имя.
    
    Returns:
        Сообщение, готовое для MarkdownV2.
    """
    if obfuscate:
        name = _obfuscate_name(first_name, last_name)
    else:
        name = _escape_md(first_name)
        if last_name:
            name += f" {_escape_md(last_name)}"
    
    # Разбивка по достижениям
    bronze = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_BRONZE, 0)
    silver = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_SILVER, 0)
    gold = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_GOLD, 0)
    
    display_rank_name = certification_rank_name or rank_name
    display_rank_icon = certification_rank_icon or rank_icon

    certification_block = ""
    if certification_points is not None:
        certification_block = (
            f"\n📝 *Аттестация*\n"
            f"{display_rank_icon} Ранг: *{_escape_md(display_rank_name)}*\n"
            f"📈 Баллы: *{certification_points}*\n"
            f"✅ Пройдено тестов: *{passed_tests_count or 0}*\n"
            f"📚 Освоено категорий: *{passed_categories_count or 0}*"
        )

    return (
        f"👤 *Профиль: {name}*\n"
        f"{'─' * 20}\n\n"
        f"💎 Очки: *{total_score}*\n\n"
        f"🎖️ *Достижения: {total_achievements}*\n"
        f"   🥉 Бронза: {bronze}\n"
        f"   🥈 Серебро: {silver}\n"
        f"   🥇 Золото: {gold}"
        f"{certification_block}"
    )


# ===== СООБЩЕНИЯ ДОСТИЖЕНИЙ =====

MESSAGE_ACHIEVEMENTS_HEADER = "🎖️ *Мои достижения*\n\nВсего разблокировано: *{unlocked}* из *{total}*\n\n"

MESSAGE_ACHIEVEMENTS_EMPTY = "🎖️ *Мои достижения*\n\nУ вас пока нет достижений\\.\n\nПродолжайте использовать бота, чтобы получить первые награды\\!"

MESSAGE_MODULE_ACHIEVEMENTS_HEADER = "🎖️ *Достижения модуля {module}*\n\nРазблокировано: *{unlocked}* из *{total}*\n\n"


def format_achievement_card(
    name: str,
    description: str,
    icon: str,
    current_count: int,
    threshold_bronze: int,
    threshold_silver: int,
    threshold_gold: int,
    unlocked_level: int  # 0 = нет, 1 = бронза, 2 = серебро, 3 = золото
) -> str:
    """
    Сформатировать карточку достижения.
    
    Args:
        name: название достижения.
        description: описание достижения.
        icon: эмодзи достижения.
        current_count: текущий прогресс.
        threshold_bronze: порог бронзового уровня.
        threshold_silver: порог серебряного уровня.
        threshold_gold: порог золотого уровня.
        unlocked_level: максимальный разблокированный уровень (0-3).
    
    Returns:
        Отформатированная карточка достижения.
    """
    # Индикаторы уровней
    bronze_check = "🥉" if unlocked_level >= 1 else "⬜"
    silver_check = "🥈" if unlocked_level >= 2 else "⬜"
    gold_check = "🥇" if unlocked_level >= 3 else "⬜"
    
    # Текст прогресса
    if unlocked_level >= 3:
        progress = "✅ Полностью разблокировано"
    elif unlocked_level >= 2:
        progress = f"Прогресс: {current_count}/{threshold_gold}"
    elif unlocked_level >= 1:
        progress = f"Прогресс: {current_count}/{threshold_silver}"
    else:
        progress = f"Прогресс: {current_count}/{threshold_bronze}"
    
    return (
        f"{icon} *{_escape_md(name)}*\n"
        f"_{_escape_md(description)}_\n"
        f"{bronze_check} {silver_check} {gold_check} \\| {_escape_md(progress)}\n"
    )


def format_achievement_unlocked_notification(
    achievement_name: str,
    achievement_icon: str,
    level: int,
    level_name: str,
    level_icon: str
) -> str:
    """
    Сформатировать уведомление о разблокировке достижения.
    """
    return (
        f"🎉 *Новое достижение\\!*\n\n"
        f"{achievement_icon} *{_escape_md(achievement_name)}*\n"
        f"Уровень: {level_icon} {_escape_md(level_name)}"
    )


# ===== СООБЩЕНИЯ РЕЙТИНГОВ =====

MESSAGE_RANKINGS_MENU = "📊 *Рейтинги*\n\nВыберите тип рейтинга и период:"

MESSAGE_RANKING_SCORE_HEADER = "📊 *Рейтинг по очкам*\n_{period}_\n\n"

MESSAGE_RANKING_ACHIEVEMENTS_HEADER = "🎖️ *Рейтинг по достижениям*\n_{period}_\n\n"


def format_ranking_list(
    entries: List[Dict],
    ranking_type: str,
    current_userid: int,
    page: int,
    total_pages: int,
    user_rank: Optional[Dict] = None,
    obfuscate: bool = False
) -> str:
    """
    Сформатировать список рейтинга с пагинацией.
    
    Args:
        entries: список записей рейтинга.
        ranking_type: "score" или "achievements".
        current_userid: ID текущего пользователя (для подсветки).
        page: текущая страница.
        total_pages: всего страниц.
        user_rank: информация о месте пользователя, если не видно в списке.
        obfuscate: скрывать ли полные имена.
    
    Returns:
        Отформатированный список рейтинга.
    """
    if not entries:
        return "📊 *Рейтинг пуст*\n\nПока никто не набрал очков\\."
    
    lines = []
    for entry in entries:
        rank = entry.get('rank', 0)
        userid = entry.get('userid')
        first_name = entry.get('first_name', 'Unknown')
        last_name = entry.get('last_name')
        
        if obfuscate:
            name = _obfuscate_name(first_name, last_name)
        else:
            name = _escape_md(first_name)
            if last_name:
                name += f" {_escape_md(last_name[:1])}\\."
        
        if ranking_type == settings.RANKING_TYPE_SCORE:
            value = entry.get('total_score', 0)
            value_text = f"{value} очков"
        else:
            value = entry.get('total_achievements', 0)
            value_text = f"{value} достижений"
        
        # Медали для топ-3
        if rank == 1:
            medal = "🥇"
        elif rank == 2:
            medal = "🥈"
        elif rank == 3:
            medal = "🥉"
        else:
            medal = f"{rank}\\."
        
        # Подсветить текущего пользователя
        if userid == current_userid:
            lines.append(f"*{medal} {name}* — *{_escape_md(value_text)}* 👈")
        else:
            lines.append(f"{medal} {name} — {_escape_md(value_text)}")
    
    result = "\n".join(lines)
    
    # Добавить позицию пользователя, если её нет в видимом списке
    if user_rank and user_rank.get('rank'):
        user_in_list = any(e.get('userid') == current_userid for e in entries)
        if not user_in_list:
            ur = user_rank
            if ranking_type == settings.RANKING_TYPE_SCORE:
                value_text = f"{ur.get('total_score', 0)} очков"
            else:
                value_text = f"{ur.get('total_achievements', 0)} достижений"
            result += f"\n\n{'─' * 15}\n*Ваша позиция: {ur.get('rank')}* — {_escape_md(value_text)}"
    
    # Информация о пагинации
    if total_pages > 1:
        result += f"\n\n_Страница {page}/{total_pages}_"
    
    return result


def get_period_display_name(period: str) -> str:
    """Вернуть человекочитаемое название периода."""
    if period == settings.RANKING_PERIOD_MONTHLY:
        return "За месяц"
    elif period == settings.RANKING_PERIOD_YEARLY:
        return "За год"
    else:
        return "За всё время"


# ===== СООБЩЕНИЯ ДЛЯ АДМИНА =====

MESSAGE_ADMIN_MENU = "🔐 *Админ\\-панель геймификации*\n\nВыберите действие из меню:"

MESSAGE_ADMIN_NOT_AUTHORIZED = "⛔ У вас нет прав администратора\\."

MESSAGE_ADMIN_ENTER_USERID = "🔍 *Поиск профиля*\n\nВведите Telegram ID или имя пользователя:"

MESSAGE_ADMIN_USER_NOT_FOUND = "❌ Пользователь не найден\\."

MESSAGE_ADMIN_SCORE_SETTINGS_HEADER = "⚙️ *Настройки начисления очков*\n\n"

MESSAGE_ADMIN_SCORE_CONFIG_ITEM = "• *{module}* — {action}: *{points}* очков\n  _{description}_\n"

MESSAGE_ADMIN_ENTER_NEW_POINTS = "✏️ *Редактирование*\n\n{module} — {action}\n\nВведите новое количество очков:"

MESSAGE_ADMIN_SCORE_UPDATED = "✅ Настройки обновлены\\!"

MESSAGE_ADMIN_INVALID_POINTS = "⚠️ Введите корректное целое число\\."


def format_admin_stats(
    total_users: int,
    active_users_7d: int,
    total_achievements_unlocked: int,
    total_score_awarded: int,
    top_scorers: List[Dict]
) -> str:
    """Сформировать сообщение со статистикой для админа."""
    top_lines = []
    for i, scorer in enumerate(top_scorers[:5], 1):
        name = _escape_md(scorer.get('first_name', 'Unknown'))
        score = scorer.get('total_score', 0)
        top_lines.append(f"{i}\\. {name} — {score} очков")
    
    top_text = "\n".join(top_lines) if top_lines else "_Нет данных_"
    
    return (
        f"📈 *Статистика геймификации*\n\n"
        f"👥 Всего пользователей: *{total_users}*\n"
        f"📊 Активных за 7 дней: *{active_users_7d}*\n"
        f"🎖️ Достижений разблокировано: *{total_achievements_unlocked}*\n"
        f"💎 Очков начислено всего: *{total_score_awarded}*\n\n"
        f"*Топ\\-5 по очкам:*\n{top_text}"
    )


MESSAGE_ADMIN_ALL_ACHIEVEMENTS_HEADER = "📋 *Все достижения системы*\n\n"


def format_admin_achievement_item(
    code: str,
    module: str,
    name: str,
    icon: str,
    threshold_bronze: int,
    threshold_silver: int,
    threshold_gold: int,
    unlocked_count: int
) -> str:
    """Сформировать элемент достижения для админского просмотра."""
    return (
        f"{icon} *{_escape_md(name)}* \\[{_escape_md(module)}\\]\n"
        f"   Код: `{_escape_md(code)}`\n"
        f"   Уровни: {threshold_bronze}/{threshold_silver}/{threshold_gold}\n"
        f"   Разблокировано: {unlocked_count} раз\n\n"
    )


# ===== СООБЩЕНИЯ ПОИСКА =====

MESSAGE_SEARCH_ENTER_QUERY = "🔍 *Поиск пользователя*\n\nВведите имя или часть имени:"

MESSAGE_SEARCH_RESULTS_HEADER = "🔍 *Результаты поиска:*\n\n"

MESSAGE_SEARCH_NO_RESULTS = "❌ Пользователи не найдены\\."


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

def _escape_md(text: str) -> str:
    """
    Экранировать спецсимволы для Telegram MarkdownV2.
    
    Args:
        text: исходный текст для экранирования.
        
    Returns:
        Экранированный текст, безопасный для MarkdownV2.
    """
    if not text:
        return ""
    
    # Символы, требующие экранирования в MarkdownV2
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    result = str(text)
    for char in special_chars:
        result = result.replace(char, f'\\{char}')
    
    return result


def _obfuscate_name(first_name: str, last_name: Optional[str]) -> str:
    """
    Скрыть имя пользователя для приватности в рейтингах.
    Показывает первую букву и точки для оставшихся символов.
    
    Args:
        first_name: имя пользователя.
        last_name: фамилия пользователя (опционально).
    
    Returns:
        Скрытое имя, например "И... П.....".
    """
    if not first_name:
        return ""
    
    # Имя: первая буква + точки для оставшихся символов
    first_dots = "\\." * (len(first_name) - 1)
    obfuscated = _escape_md(first_name[0]) + first_dots
    
    # Фамилия: первая буква + точки для оставшихся символов
    if last_name:
        last_dots = "\\." * (len(last_name) - 1)
        obfuscated += f" {_escape_md(last_name[0])}{last_dots}"
    
    return obfuscated
