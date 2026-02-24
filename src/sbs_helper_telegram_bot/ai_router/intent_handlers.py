"""
intent_handlers.py — обработчики намерений для AI-маршрутизации.

Каждый обработчик отвечает за выполнение действия конкретного модуля
на основе параметров, извлечённых LLM из пользовательского сообщения.
Обработчики вызывают logic/DB-функции модулей напрямую, минуя Telegram-handlers.
"""

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

from src.sbs_helper_telegram_bot.ai_router.messages import (
    escape_markdown_v2,
    format_rag_answer_markdown_v2,
)

logger = logging.getLogger(__name__)

_EDGE_INVISIBLE_CHARS_RE = re.compile(r'^[\s\u200b\u200c\u200d\ufeff]+|[\s\u200b\u200c\u200d\ufeff]+$')


def _normalize_lookup_code(value: Any, to_upper: bool = False) -> str:
    """Нормализовать код поиска, удаляя пробелы и невидимые символы по краям."""
    if value is None:
        return ""

    normalized = _EDGE_INVISIBLE_CHARS_RE.sub("", str(value))
    if to_upper:
        normalized = normalized.upper()

    return normalized


# =============================================
# Базовый класс обработчика
# =============================================

class IntentHandler(ABC):
    """Абстрактный обработчик намерения."""

    @property
    @abstractmethod
    def intent_name(self) -> str:
        """Имя намерения, которое обрабатывает этот handler."""
        ...

    @property
    @abstractmethod
    def module_key(self) -> str:
        """Ключ модуля в MODULE_CONFIG для проверки включённости."""
        ...

    @abstractmethod
    async def execute(self, params: Dict[str, Any], user_id: int) -> str:
        """
        Выполнить действие по намерению.

        Args:
            params: Параметры, извлечённые LLM.
            user_id: Telegram ID пользователя.

        Returns:
            Отформатированный MarkdownV2-ответ для отправки пользователю.
        """
        ...


# =============================================
# UPOS Errors Handler
# =============================================

class UposErrorHandler(IntentHandler):
    """Обработчик поиска ошибок UPOS."""

    @property
    def intent_name(self) -> str:
        return "upos_error_lookup"

    @property
    def module_key(self) -> str:
        return "upos_errors"

    async def execute(self, params: Dict[str, Any], user_id: int) -> str:
        """Найти ошибку UPOS по коду."""
        from src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part import (
            get_error_code_by_code,
            record_error_request,
            record_unknown_code,
        )
        from src.sbs_helper_telegram_bot.upos_error.messages import (
            format_error_code_response,
        )

        error_code = _normalize_lookup_code(params.get("error_code", ""))
        if not error_code:
            return "⚠️ Не указан код ошибки\\. Попробуйте ещё раз\\."

        # Ограничиваем длину
        if len(error_code) > 50:
            error_code = error_code[:50]

        result = get_error_code_by_code(error_code)

        if result:
            record_error_request(user_id, error_code, found=True)
            return format_error_code_response(
                error_code=result["error_code"],
                description=result.get("description", ""),
                suggested_actions=result.get("suggested_actions", ""),
                category_name=result.get("category_name"),
                updated_timestamp=result.get("updated_timestamp"),
            )
        else:
            record_error_request(user_id, error_code, found=False)
            record_unknown_code(error_code)
            escaped_code = escape_markdown_v2(error_code)
            return (
                f"❌ Код ошибки `{escaped_code}` не найден в базе\\.\n\n"
                "Попробуйте другой код или обратитесь к разделу "
                "🔢 *UPOS Ошибки* в меню\\."
            )


# =============================================
# Ticket Validator Handler
# =============================================

class TicketValidatorHandler(IntentHandler):
    """Обработчик валидации заявок."""

    @staticmethod
    def _get_ticket_type_name(ticket_type: Any) -> str:
        """Безопасно получить отображаемое имя типа заявки."""
        return str(
            getattr(ticket_type, "type_name", None)
            or getattr(ticket_type, "name", None)
            or "Неизвестный тип"
        )

    @property
    def intent_name(self) -> str:
        return "ticket_validation"

    @property
    def module_key(self) -> str:
        return "ticket_validator"

    async def execute(self, params: Dict[str, Any], user_id: int) -> str:
        """Провалидировать текст заявки."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import (
            load_all_ticket_types,
            load_rules_from_db,
        )
        from src.sbs_helper_telegram_bot.ticket_validator.validators import (
            detect_ticket_type,
            validate_ticket,
        )

        ticket_text = str(params.get("ticket_text", "")).strip()
        if not ticket_text:
            return "⚠️ Не указан текст заявки для валидации\\."

        try:
            ticket_types = load_all_ticket_types()
            detected_type, _ = detect_ticket_type(ticket_text, ticket_types)

            if not detected_type:
                type_names = [
                    escape_markdown_v2(self._get_ticket_type_name(t))
                    for t in ticket_types
                    if t.active
                ]
                types_list = "\n".join(f"• {name}" for name in type_names)
                return (
                    "⚠️ *Тип заявки не определён*\n\n"
                    "Не удалось определить тип заявки\\. "
                    f"Поддерживаемые типы:\n{types_list}\n\n"
                    "Попробуйте вставить полный текст заявки\\."
                )

            rules = load_rules_from_db(ticket_type_id=detected_type.id)
            result = validate_ticket(ticket_text, rules, detected_ticket_type=detected_type)

            return self._format_result(result, detected_type)

        except Exception as exc:
            logger.error("Ошибка валидации заявки через AI: %s", exc)
            return "❌ Ошибка при валидации заявки\\. Попробуйте через меню *✅ Валидация заявок*\\."

    @staticmethod
    def _format_result(result, detected_type) -> str:
        """Отформатировать результат валидации."""
        type_name = escape_markdown_v2(
            TicketValidatorHandler._get_ticket_type_name(detected_type)
        )
        header = f"📋 *Тип заявки:* {type_name}\n\n"

        if result.is_valid:
            return header + "✅ *Заявка прошла валидацию\\!*"
        else:
            errors = "\n".join(
                f"• {escape_markdown_v2(msg)}" for msg in result.error_messages
            )
            return (
                header + "❌ *Заявка не прошла валидацию*\n\n"
                f"*Ошибки:*\n{errors}"
            )


# =============================================
# KTR Handler
# =============================================

class KtrHandler(IntentHandler):
    """Обработчик поиска кодов КТР."""

    @property
    def intent_name(self) -> str:
        return "ktr_lookup"

    @property
    def module_key(self) -> str:
        return "ktr"

    async def execute(self, params: Dict[str, Any], user_id: int) -> str:
        """Найти код КТР."""
        from src.sbs_helper_telegram_bot.ktr.ktr_bot_part import (
            get_ktr_code_by_code,
            record_ktr_request,
        )
        from src.sbs_helper_telegram_bot.ktr.messages import (
            format_ktr_code_response,
        )

        ktr_code = _normalize_lookup_code(params.get("ktr_code", ""), to_upper=True)
        if not ktr_code:
            return "⚠️ Не указан код КТР\\. Попробуйте ещё раз\\."

        if len(ktr_code) > 50:
            ktr_code = ktr_code[:50]

        result = get_ktr_code_by_code(ktr_code)

        if result:
            record_ktr_request(user_id, ktr_code, found=True)
            return format_ktr_code_response(
                code=result["code"],
                description=result.get("description", ""),
                minutes=result.get("minutes", 0),
                category_name=result.get("category_name"),
                updated_timestamp=result.get("updated_timestamp"),
                date_updated=result.get("date_updated"),
            )
        else:
            record_ktr_request(user_id, ktr_code, found=False)
            escaped = escape_markdown_v2(ktr_code)
            return (
                f"❌ Код КТР `{escaped}` не найден в базе\\.\n\n"
                "Попробуйте другой код или обратитесь к разделу "
                "⏱️ *КТР* в меню\\."
            )


# =============================================
# Certification Handler
# =============================================

class CertificationHandler(IntentHandler):
    """Обработчик запросов по аттестации."""

    @property
    def intent_name(self) -> str:
        return "certification_info"

    @property
    def module_key(self) -> str:
        return "certification"

    async def execute(self, params: Dict[str, Any], user_id: int) -> str:
        """Получить информацию по аттестации."""
        from src.sbs_helper_telegram_bot.certification.certification_logic import (
            get_user_certification_summary,
            get_certification_statistics,
            get_all_categories,
        )

        query_type = str(params.get("query_type", "summary")).strip()

        try:
            if query_type == "stats":
                return self._format_stats()
            elif query_type == "categories":
                return self._format_categories()
            else:
                return self._format_summary(user_id)
        except Exception as exc:
            logger.error("Ошибка получения данных аттестации: %s", exc)
            return "❌ Ошибка при получении данных\\. Попробуйте через меню *📝 Аттестация*\\."

    @staticmethod
    def _format_summary(user_id: int) -> str:
        """Отформатировать сводку пользователя."""
        from src.sbs_helper_telegram_bot.certification.certification_logic import (
            get_user_certification_summary,
        )

        summary = get_user_certification_summary(user_id)
        rank_icon = summary.get("rank_icon", "🔰")
        rank_name = escape_markdown_v2(summary.get("rank_name", "Новичок"))
        points = summary.get("certification_points", 0)
        max_pts = summary.get("max_achievable_points", 0)
        progress = summary.get("overall_progress_percent", 0)
        progress_bar = summary.get("overall_progress_bar", "")
        passed = summary.get("passed_tests_count", 0)

        result = (
            f"📝 *Ваш профиль аттестации*\n\n"
            f"{rank_icon} *Ранг:* {rank_name}\n"
            f"🏆 *Баллы:* {points}/{max_pts}\n"
            f"📊 *Прогресс:* {progress}%\n"
            f"{escape_markdown_v2(progress_bar)}\n"
            f"✅ *Пройдено тестов:* {passed}"
        )

        next_rank = summary.get("next_rank_name")
        if next_rank:
            pts_needed = summary.get("points_to_next_rank", 0)
            next_icon = summary.get("next_rank_icon", "")
            result += (
                f"\n\n➡️ *Следующий ранг:* {next_icon} "
                f"{escape_markdown_v2(next_rank)} "
                f"\\(нужно ещё {pts_needed} баллов\\)"
            )

        return result

    @staticmethod
    def _format_stats() -> str:
        """Отформатировать общую статистику."""
        from src.sbs_helper_telegram_bot.certification.certification_logic import (
            get_certification_statistics,
        )

        stats = get_certification_statistics()
        total_q = stats.get("total_questions", 0)
        total_c = stats.get("total_categories", 0)
        active_c = stats.get("active_categories", 0)

        return (
            f"📊 *Статистика аттестации*\n\n"
            f"📝 *Вопросов:* {total_q}\n"
            f"📁 *Категорий:* {total_c} \\(активных: {active_c}\\)"
        )

    @staticmethod
    def _format_categories() -> str:
        """Отформатировать список категорий."""
        from src.sbs_helper_telegram_bot.certification.certification_logic import (
            get_all_categories,
        )

        categories = get_all_categories(active_only=True)
        if not categories:
            return "📁 Нет активных категорий аттестации\\."

        lines = ["📁 *Категории аттестации:*\n"]
        for cat in categories:
            name = escape_markdown_v2(cat.get("name", ""))
            q_count = cat.get("questions_count", 0)
            lines.append(f"• {name} \\({q_count} вопросов\\)")

        return "\n".join(lines)


# =============================================
# News Handler
# =============================================

class NewsHandler(IntentHandler):
    """Обработчик запросов по новостям."""

    @property
    def intent_name(self) -> str:
        return "news_search"

    @property
    def module_key(self) -> str:
        return "news"

    async def execute(self, params: Dict[str, Any], user_id: int) -> str:
        """Найти или показать новости."""
        from src.sbs_helper_telegram_bot.news.news_logic import (
            search_news,
            get_published_news,
            get_unread_count,
        )

        search_query = str(params.get("search_query", "")).strip()

        try:
            if search_query:
                articles, total = search_news(search_query, page=0, per_page=3)
                if not articles:
                    escaped_q = escape_markdown_v2(search_query)
                    return f"🔍 По запросу «{escaped_q}» новостей не найдено\\."
                return self._format_articles(articles, f"🔍 Результаты поиска \\({total}\\)")
            else:
                # Показать последние новости
                unread = get_unread_count(user_id)
                articles, total = get_published_news(page=0, per_page=3)
                if not articles:
                    return "📰 Новостей пока нет\\."

                header = f"📰 Последние новости \\({total}\\)"
                if unread > 0:
                    header += f" \\| 🔴 Непрочитанных: {unread}"

                return self._format_articles(articles, header)

        except Exception as exc:
            logger.error("Ошибка получения новостей: %s", exc)
            return "❌ Ошибка при получении новостей\\. Попробуйте через меню *📰 Новости*\\."

    @staticmethod
    def _format_articles(articles, header: str) -> str:
        """Отформатировать список статей."""
        lines = [f"*{header}*\n"]

        for article in articles:
            title = escape_markdown_v2(article.get("title", ""))
            emoji = article.get("category_emoji", "📰")
            # Форматируем дату
            pub_ts = article.get("published_timestamp")
            if pub_ts:
                date_str = datetime.fromtimestamp(pub_ts).strftime("%d.%m.%Y")
                escaped_date = escape_markdown_v2(date_str)
            else:
                escaped_date = ""

            lines.append(f"{emoji} *{title}*")
            if escaped_date:
                lines.append(f"  _{escaped_date}_")
            # Краткое содержание (первые 100 символов)
            content = article.get("content", "")
            if content:
                preview = content[:100].replace("\n", " ")
                if len(content) > 100:
                    preview += "..."
                lines.append(f"  {escape_markdown_v2(preview)}")
            lines.append("")

        lines.append("_Подробнее в разделе 📰 Новости_")
        return "\n".join(lines)


# =============================================
# RAG Handler
# =============================================

class RagQaHandler(IntentHandler):
    """Обработчик вопросов к базе знаний документов (RAG)."""

    @property
    def intent_name(self) -> str:
        return "rag_qa"

    @property
    def module_key(self) -> str:
        return "ai_router"

    async def execute(self, params: Dict[str, Any], user_id: int) -> str:
        """Ответить на вопрос по загруженным документам."""
        from src.sbs_helper_telegram_bot.ai_router.rag_service import get_rag_service
        from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings

        if not ai_settings.AI_RAG_ENABLED:
            return "⚠️ Режим базы знаний временно отключён\\."

        question = str(params.get("question", "")).strip()
        if not question:
            return "⚠️ Уточните вопрос по документам, чтобы я смог найти ответ\\."

        try:
            rag_service = get_rag_service()
            answer = await rag_service.answer_question(question, user_id=user_id)
            if not answer:
                return (
                    "📚 В загруженных документах не найден точный ответ\\.\n\n"
                    "Попробуйте переформулировать вопрос или уточнить формулировку\\."
                )

            safe_answer = format_rag_answer_markdown_v2(answer)
            return f"📚 *Ответ по базе знаний*\n\n{safe_answer}"
        except Exception as exc:
            logger.exception(
                "Ошибка RAG-обработчика: user=%s error_type=%s error_repr=%r",
                user_id,
                type(exc).__name__,
                exc,
            )
            return "❌ Не удалось получить ответ из базы знаний\\. Попробуйте позже\\."


# =============================================
# Реестр обработчиков
# =============================================

def get_all_handlers() -> list[IntentHandler]:
    """Получить список всех зарегистрированных обработчиков намерений."""
    return [
        RagQaHandler(),
        UposErrorHandler(),
        TicketValidatorHandler(),
        KtrHandler(),
        CertificationHandler(),
        NewsHandler(),
    ]
