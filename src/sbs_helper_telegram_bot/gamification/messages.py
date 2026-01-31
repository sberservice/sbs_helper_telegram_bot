"""
Gamification Module Messages

All user-facing messages for the gamification/achievement system.
Messages use Telegram MarkdownV2 format where needed.
"""
# pylint: disable=line-too-long
# Note: Double backslashes are intentional for Telegram MarkdownV2 escaping

from typing import Optional, Dict, List
from . import settings


# ===== SUBMENU =====

MESSAGE_SUBMENU = "🏆 *Геймификация*\n\nВаш цифровой профиль, достижения и рейтинги\\.\n\nВыберите действие:"


# ===== PROFILE MESSAGES =====

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
    achievements_by_level: Dict[int, int]
) -> str:
    """
    Build user profile message.
    
    Args:
        first_name: User's first name
        last_name: User's last name (optional)
        total_score: Total score points
        rank_name: Current rank name
        rank_icon: Current rank emoji
        next_rank_name: Next rank name (None if max rank)
        next_rank_threshold: Points needed for next rank
        total_achievements: Total achievement levels unlocked
        max_achievements: Maximum possible achievement levels
        achievements_by_level: Dict of level -> count
    
    Returns:
        Formatted message for MarkdownV2
    """
    # Escape special characters for MarkdownV2
    name = _escape_md(first_name)
    if last_name:
        name += f" {_escape_md(last_name)}"
    
    # Progress to next rank
    if next_rank_name and next_rank_threshold:
        progress_text = f"\n📈 До «{_escape_md(next_rank_name)}»: *{next_rank_threshold - total_score}* очков"
    else:
        progress_text = "\n🎉 *Максимальный ранг достигнут\\!*"
    
    # Achievement breakdown
    bronze = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_BRONZE, 0)
    silver = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_SILVER, 0)
    gold = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_GOLD, 0)
    
    return (
        f"👤 *Профиль: {name}*\n"
        f"{'─' * 20}\n\n"
        f"{rank_icon} Ранг: *{_escape_md(rank_name)}*\n"
        f"💎 Очки: *{total_score}*"
        f"{progress_text}\n\n"
        f"🎖️ *Достижения: {total_achievements}/{max_achievements}*\n"
        f"   🥉 Бронза: {bronze}\n"
        f"   🥈 Серебро: {silver}\n"
        f"   🥇 Золото: {gold}"
    )


def format_other_user_profile_message(
    first_name: str,
    last_name: Optional[str],
    total_score: int,
    rank_name: str,
    rank_icon: str,
    total_achievements: int,
    achievements_by_level: Dict[int, int],
    obfuscate: bool = False
) -> str:
    """
    Build another user's profile message (for viewing from rankings).
    
    Args:
        first_name: User's first name
        last_name: User's last name (optional)
        total_score: Total score points
        rank_name: Current rank name
        rank_icon: Current rank emoji
        total_achievements: Total achievement levels unlocked
        achievements_by_level: Dict of level -> count
        obfuscate: Whether to hide full name
    
    Returns:
        Formatted message for MarkdownV2
    """
    if obfuscate:
        name = _obfuscate_name(first_name, last_name)
    else:
        name = _escape_md(first_name)
        if last_name:
            name += f" {_escape_md(last_name)}"
    
    # Achievement breakdown
    bronze = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_BRONZE, 0)
    silver = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_SILVER, 0)
    gold = achievements_by_level.get(settings.ACHIEVEMENT_LEVEL_GOLD, 0)
    
    return (
        f"👤 *Профиль: {name}*\n"
        f"{'─' * 20}\n\n"
        f"{rank_icon} Ранг: *{_escape_md(rank_name)}*\n"
        f"💎 Очки: *{total_score}*\n\n"
        f"🎖️ *Достижения: {total_achievements}*\n"
        f"   🥉 Бронза: {bronze}\n"
        f"   🥈 Серебро: {silver}\n"
        f"   🥇 Золото: {gold}"
    )


# ===== ACHIEVEMENT MESSAGES =====

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
    unlocked_level: int  # 0 = none, 1 = bronze, 2 = silver, 3 = gold
) -> str:
    """
    Format a single achievement card.
    
    Args:
        name: Achievement name
        description: Achievement description
        icon: Achievement emoji icon
        current_count: Current progress count
        threshold_bronze: Bronze level threshold
        threshold_silver: Silver level threshold
        threshold_gold: Gold level threshold
        unlocked_level: Highest unlocked level (0-3)
    
    Returns:
        Formatted achievement card
    """
    # Level indicators
    bronze_check = "🥉" if unlocked_level >= 1 else "⬜"
    silver_check = "🥈" if unlocked_level >= 2 else "⬜"
    gold_check = "🥇" if unlocked_level >= 3 else "⬜"
    
    # Progress text
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
    Format achievement unlock notification.
    """
    return (
        f"🎉 *Новое достижение\\!*\n\n"
        f"{achievement_icon} *{_escape_md(achievement_name)}*\n"
        f"Уровень: {level_icon} {_escape_md(level_name)}"
    )


# ===== RANKING MESSAGES =====

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
    Format ranking list with pagination.
    
    Args:
        entries: List of ranking entries
        ranking_type: 'score' or 'achievements'
        current_userid: Current user's ID (to highlight)
        page: Current page
        total_pages: Total pages
        user_rank: Current user's rank info if not in visible list
        obfuscate: Whether to hide full names
    
    Returns:
        Formatted ranking list
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
        
        # Rank medal for top 3
        if rank == 1:
            medal = "🥇"
        elif rank == 2:
            medal = "🥈"
        elif rank == 3:
            medal = "🥉"
        else:
            medal = f"{rank}\\."
        
        # Highlight current user
        if userid == current_userid:
            lines.append(f"*{medal} {name}* — *{_escape_md(value_text)}* 👈")
        else:
            lines.append(f"{medal} {name} — {_escape_md(value_text)}")
    
    result = "\n".join(lines)
    
    # Add user's rank if not in visible list
    if user_rank and user_rank.get('rank'):
        user_in_list = any(e.get('userid') == current_userid for e in entries)
        if not user_in_list:
            ur = user_rank
            if ranking_type == settings.RANKING_TYPE_SCORE:
                value_text = f"{ur.get('total_score', 0)} очков"
            else:
                value_text = f"{ur.get('total_achievements', 0)} достижений"
            result += f"\n\n{'─' * 15}\n*Ваша позиция: {ur.get('rank')}* — {_escape_md(value_text)}"
    
    # Pagination info
    if total_pages > 1:
        result += f"\n\n_Страница {page}/{total_pages}_"
    
    return result


def get_period_display_name(period: str) -> str:
    """Get human-readable period name."""
    if period == settings.RANKING_PERIOD_MONTHLY:
        return "За месяц"
    elif period == settings.RANKING_PERIOD_YEARLY:
        return "За год"
    else:
        return "За всё время"


# ===== ADMIN MESSAGES =====

MESSAGE_ADMIN_MENU = "🔐 *Админ\\-панель геймификации*\n\nВыберите действие:"

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
    """Format admin statistics message."""
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
    """Format achievement item for admin view."""
    return (
        f"{icon} *{_escape_md(name)}* \\[{_escape_md(module)}\\]\n"
        f"   Код: `{_escape_md(code)}`\n"
        f"   Уровни: {threshold_bronze}/{threshold_silver}/{threshold_gold}\n"
        f"   Разблокировано: {unlocked_count} раз\n\n"
    )


# ===== SEARCH MESSAGES =====

MESSAGE_SEARCH_ENTER_QUERY = "🔍 *Поиск пользователя*\n\nВведите имя или часть имени:"

MESSAGE_SEARCH_RESULTS_HEADER = "🔍 *Результаты поиска:*\n\n"

MESSAGE_SEARCH_NO_RESULTS = "❌ Пользователи не найдены\\."


# ===== HELPER FUNCTIONS =====

def _escape_md(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.
    
    Args:
        text: Raw text to escape
        
    Returns:
        Escaped text safe for MarkdownV2
    """
    if not text:
        return ""
    
    # Characters that need escaping in MarkdownV2
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    result = str(text)
    for char in special_chars:
        result = result.replace(char, f'\\{char}')
    
    return result


def _obfuscate_name(first_name: str, last_name: Optional[str]) -> str:
    """
    Obfuscate user name for privacy in rankings.
    Shows first letter + asterisks.
    
    Args:
        first_name: User's first name
        last_name: User's last name (optional)
    
    Returns:
        Obfuscated name like "И*** П."
    """
    if not first_name:
        return "Аноним"
    
    # First name: first letter + asterisks
    obfuscated = _escape_md(first_name[0]) + "\\*\\*\\*"
    
    # Last name: just first letter with dot
    if last_name:
        obfuscated += f" {_escape_md(last_name[0])}\\."
    
    return obfuscated
