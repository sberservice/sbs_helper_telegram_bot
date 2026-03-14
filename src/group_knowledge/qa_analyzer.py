"""
Анализатор Q&A-пар из собранных сообщений групп.

Извлекает пары вопрос-ответ двумя способами:
1. Thread-based: по reply-to связям в Telegram.
2. LLM-inferred: через анализ контекста всех сообщений дня LLM-моделью.

Также индексирует извлечённые пары в Qdrant для векторного поиска.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from config import ai_settings
from src.core.ai.llm_provider import get_provider, is_provider_registered
from src.group_knowledge.acronyms import (
    select_best_acronyms_by_term,
    sort_acronym_records_for_prompt,
)
from src.group_knowledge import database as gk_db
from src.group_knowledge.models import AnalysisResult, GroupMessage, QAPair
from src.group_knowledge.rag_text import enrich_question_for_rag
from src.group_knowledge.settings import GK_IGNORED_SENDER_IDS

logger = logging.getLogger(__name__)

# Эвристика для расширения thread-контекста соседними последовательными сообщениями
# участников цепочки, даже если они не связаны Telegram reply-to.
THREAD_NEARBY_WINDOW_SECONDS = 180
THREAD_MAX_NEARBY_MESSAGES = 20
THREAD_OVERLAP_RATIO_THRESHOLD = 0.60
THREAD_QUESTION_FRAGMENT_MAX_GAP_SECONDS = 120
THREAD_QUESTION_FRAGMENT_MAX_MESSAGES = 3
THREAD_QUESTION_HINT_CONFIDENCE_DECIMALS = 2
THREAD_LOG_MESSAGE_TEXT_LIMIT = 160
THREAD_LOG_CHAIN_PREVIEW_LIMIT = 2000
# Максимальное число кросс-дневных сообщений, для которых выводятся детальные логи.
THREAD_CROSS_DAY_LOG_LIMIT = 10
#№8. Если у сообщения есть QUESTION_HINT с confidence >= {question_confidence_threshold}, считай это сильным сигналом, что именно это сообщение является техническим вопросом цепочки.
# Промпт для валидации и очистки thread-based цепочек
THREAD_VALIDATION_PROMPT = """Ты — эксперт по технической поддержке оборудования и ПО для полевых инженеров.

Тебе дана цепочка сообщений из чата технической и организационной поддержки.
Цепочка может содержать:
- исходный вопрос,
- уточняющие вопросы,
- промежуточные ответы,
- финальное решение,
- благодарность после решения.

ВОЗМОЖНЫЕ АББРЕВИАТУРЫ:
{acronyms_section}

ИСХОДНЫЙ ВОПРОС:
{question}

ЦЕПОЧКА СООБЩЕНИЙ:
{thread_context}
КОНТЕКСТ ЗАКОНЧЕН.
ОПРЕДЕЛИ:
1. Найди в цепочке полезный вопрос с решением.
2. Если все хорошо — is_valid_qa=true.
3. Игнорируй благодарности, приветствия, шутки и служебные реплики.
4.1. Если вопрос собран из нескольких сообщений от одного пользователя, объедини их в один вопрос.
4.2. Прочитай предыдущие сообщения человека, который задал вопрос и подумай, не являются ли эти сообщения частью вопроса.
4.3. Если решение собрано из нескольких сообщений, объедини их в один качественный ответ, предпочитай информацию не от человека, который задал вопрос, а от других пользователей. Не включай в решение серийные и заводские номера, только общую информацию. Если в ответе есть ссылка, дай её.
5. По возможности укажи ID сообщения, где содержится финальное или наиболее полезное решение.
6. confidence - уровень уверенности модели, в том, что вопрос извлечен правильно, а не частично, с явным предметом обсуждения, что вопрос имеет смысл и имеет полезное решение, которое пригодится другим людям в будущем (0.0-1.0). Длина вопроса и ответа не влияет на расчет confidence, кроме односложных ответов. Наличие аббревиатур не виляет на расчет confidence.
7. НЕ ПЫТАЙСЯ РАСШИФРОВАТЬ АББРЕВИАТУРЫ, ЕСЛИ НЕ УВЕРЕН.
8. Если у сообщения есть QUESTION_HINT с confidence >= {question_confidence_threshold}, считай что это сообщение является вопросом пусть даже без вопросительного знака.
9. Если вопрос или ответ или связанные сообщения в цепочке, отвечают на ситуацию на данный момент (не работает какой-то сервис, или введено временное правило), или указывают о длительности процесса на данный момент, то укажи дату в ответе и сильно снизь confidence.
10. НЕ указывай в ответе серийные номера или номера заявок.

Верни JSON:
{{
    "is_valid_qa": true/false,
    "confidence": 0.0-1.0,
    "clean_question": "переформулированный вопрос, создай блок [ВОПРОС]. Если есть изображение, включи в вопрос суть проблемы из блока Изображение, добавь отдельный блок в начале [ИЗОБРАЖЕНИЕ], перед блоком [ВОПРОС].",
    "clean_answer": "итоговый ответ/решение",
    "answer_message_id": 123,
    "confidence_reason": "Укажи почему ты вернул именно такой confidence",
    "fullness": "подробность ответа: 0.0-1.0"
}}

Если это не техническая цепочка с решением — верни is_valid_qa: false."""

# Промпт для LLM-инференса Q&A пар из дня переписки
LLM_INFERENCE_PROMPT = """Ты — эксперт по технической поддержке. Проанализируй переписку в технической группе поддержки.

Найди пары вопрос-ответ, где:
- Один пользователь задаёт технический вопрос
- Другой пользователь отвечает на этот вопрос
- Пары НЕ связаны через reply (ответ на сообщение), но семантически являются парой Q&A

Сообщения за день (формат: [ID] Имя: текст):
{messages}

Верни JSON-массив найденных пар:
{{
    "pairs": [
        {{
            "question_msg_id": 123,
            "answer_msg_id": 456,
            "question": "Переформулированный вопрос",
            "answer": "Переформулированный ответ",
            "confidence": 0.8
        }}
    ]
}}

Если пар не найдено — верни пустой массив pairs. Ищи только технические вопросы и ответы, пропускай разговоры, шутки, приветствия."""


class QAAnalyzer:
    """
    Анализатор Q&A пар из собранных сообщений.

    Выполняет два этапа анализа:
    1. Thread-based — извлечение по reply-to связям.
    2. LLM-inferred — поиск неявных пар через LLM.
    """

    def __init__(self, model_name: Optional[str] = None):
        """
        Инициализация анализатора.

        Args:
            model_name: Модель для анализа (по умолчанию из настроек).
        """
        self._provider_name = ai_settings.get_active_gk_text_provider()
        self._model_name = model_name or ai_settings.get_active_gk_analysis_model()
        self._batch_size = ai_settings.GK_ANALYSIS_BATCH_SIZE
        self._question_confidence_threshold = (
            ai_settings.get_active_gk_analysis_question_confidence_threshold()
        )
        # Кэш секции аббревиатур по group_id.
        self._acronyms_cache: Dict[int, Tuple[str, float]] = {}

    def _get_provider(self):
        """Вернуть активный LLM-провайдер для задач анализатора GK."""
        provider_name = str(self._provider_name or "").strip()
        if provider_name and is_provider_registered(provider_name):
            return get_provider(provider_name)

        if provider_name:
            logger.warning(
                "GK QAAnalyzer: провайдер '%s' не зарегистрирован, используем deepseek",
                provider_name,
            )
        return get_provider("deepseek")

    async def analyze_day(
        self,
        group_id: int,
        date_str: str,
        skip_thread: bool = False,
        skip_llm: bool = False,
        force_reanalyze: bool = False,
    ) -> AnalysisResult:
        """
        Проанализировать сообщения за один день.

        Args:
            group_id: ID группы.
            date_str: Дата в формате YYYY-MM-DD.
            skip_thread: Пропустить thread-based анализ.
            skip_llm: Пропустить LLM-inferred анализ.
            force_reanalyze: Принудительно переанализировать сообщения, даже если processed=1.

        Returns:
            Результат анализа.
        """
        result = AnalysisResult(
            date=date_str,
            group_id=group_id,
        )

        # По умолчанию анализируем только новые (ещё не обработанные) сообщения,
        # чтобы повторный запуск не пересоздавал уже извлечённые Q&A пары.
        if force_reanalyze:
            messages = gk_db.get_messages_for_date(group_id, date_str)
        else:
            messages = gk_db.get_unprocessed_messages(group_id, date_str)

        ignored_sender_ids = set(GK_IGNORED_SENDER_IDS)
        if ignored_sender_ids:
            ignored_count = sum(1 for msg in messages if msg.sender_id in ignored_sender_ids)
            if ignored_count:
                logger.info(
                    "Исключены сообщения игнорируемых отправителей: group=%d date=%s count=%d senders=%s",
                    group_id,
                    date_str,
                    ignored_count,
                    sorted(ignored_sender_ids),
                )
            messages = [msg for msg in messages if msg.sender_id not in ignored_sender_ids]

        result.total_messages = len(messages)

        if not messages:
            total_messages_for_day = 0
            if not force_reanalyze:
                total_messages_for_day = len(gk_db.get_messages_for_date(group_id, date_str))
                result.total_messages = total_messages_for_day

            if force_reanalyze:
                logger.info(
                    "Нет сообщений для переанализа: group=%d date=%s total_messages=%d",
                    group_id,
                    date_str,
                    result.total_messages,
                )
            else:
                logger.info(
                    "Нет новых необработанных сообщений для анализа: group=%d date=%s total_messages=%d",
                    group_id,
                    date_str,
                    total_messages_for_day,
                )
            return result

        logger.info(
            "Начат анализ: group=%d date=%s messages=%d",
            group_id, date_str, len(messages),
        )

        # Фаза 1: Thread-based
        if not skip_thread:
            try:
                thread_pairs = await self._extract_thread_pairs(messages)
                result.thread_pairs_found = len(thread_pairs)
                logger.info(
                    "Thread-based: найдено %d пар (group=%d date=%s)",
                    len(thread_pairs), group_id, date_str,
                )
            except Exception as exc:
                error_msg = f"Ошибка thread-based анализа: {exc}"
                result.errors.append(error_msg)
                logger.error(error_msg, exc_info=True)

        # Фаза 2: LLM-inferred
        llm_generation_enabled = ai_settings.get_active_gk_generate_llm_inferred_qa_pairs()
        if not skip_llm and llm_generation_enabled:
            try:
                llm_pairs = await self._extract_llm_inferred_pairs(messages, group_id)
                result.llm_pairs_found = len(llm_pairs)
                logger.info(
                    "LLM-inferred: найдено %d пар (group=%d date=%s)",
                    len(llm_pairs), group_id, date_str,
                )
            except Exception as exc:
                error_msg = f"Ошибка LLM-inferred анализа: {exc}"
                result.errors.append(error_msg)
                logger.error(error_msg, exc_info=True)
        elif skip_llm:
            logger.info(
                "LLM-inferred фаза пропущена флагом --skip-llm: group=%d date=%s",
                group_id,
                date_str,
            )
        else:
            logger.info(
                "LLM-inferred генерация отключена настройкой GK_GENERATE_LLM_INFERRED_QA_PAIRS: group=%d date=%s",
                group_id,
                date_str,
            )

        # Отметить сообщения как обработанные
        msg_ids = [m.id for m in messages if m.id is not None]
        if msg_ids:
            gk_db.mark_messages_processed(msg_ids)

        logger.info(
            "Анализ завершён: group=%d date=%s thread=%d llm=%d errors=%d",
            group_id, date_str,
            result.thread_pairs_found,
            result.llm_pairs_found,
            len(result.errors),
        )

        return result

    # -------------------------------------------------------------------
    # Построение секции аббревиатур для промпта
    # -------------------------------------------------------------------

    # Хардкод-fallback на случай недоступности БД.
    _ACRONYMS_FALLBACK = (
        "ГЗ означает Горячая замена. Техобнул означает технологическое обнуление. "
        "ЧЗ означает Честный Знак. УЗ означает удаленная загрузка. "
        "ЦА - Центральный Аппарат. ЦК - Центр Компетенций. "
        "СБС - СберСервис. РМ - Региональный Менеджер. "
        "ТСТ - торгово-сервисная точка. "
        "ФИАС - Федеральная информационная адресная система."
    )

    def _build_acronyms_section(self, group_id: int) -> str:
        """Построить текст секции ВОЗМОЖНЫЕ АББРЕВИАТУРЫ из БД.

        Загружает только approved-термины с расшифровкой (глобальные + групповые),
        отбирает те, у которых высокий confidence (>= GK_ACRONYMS_MIN_CONFIDENCE)
        ИЛИ подтверждённые экспертом (expert_status='approved'),
        и кэширует результат с TTL = GK_TERMS_CACHE_TTL_SECONDS.

        Глобальные термины (group_id=0) включаются всегда.
        Группо-специфичные термины ранжируются по message_count DESC
        и ограничиваются лимитом GK_ACRONYMS_MAX_PROMPT_TERMS.

        Если БД недоступна, возвращается хардкод-fallback.
        """
        import time as _time

        now = _time.time()
        cached = self._acronyms_cache.get(group_id)
        ttl = ai_settings.GK_TERMS_CACHE_TTL_SECONDS
        if cached is not None:
            text, ts = cached
            if (now - ts) < ttl:
                return text

        try:
            min_confidence = float(getattr(ai_settings, "GK_ACRONYMS_MIN_CONFIDENCE", 0.9))
            max_group_terms = int(getattr(ai_settings, "GK_ACRONYMS_MAX_PROMPT_TERMS", 50))
            get_runtime_max_terms = getattr(ai_settings, "get_active_gk_acronyms_max_prompt_terms", None)
            if callable(get_runtime_max_terms):
                try:
                    runtime_value = get_runtime_max_terms()
                    if isinstance(runtime_value, (int, float, str)):
                        max_group_terms = int(runtime_value)
                except (TypeError, ValueError):
                    pass

            acronyms = gk_db.get_terms_for_group(
                group_id if group_id else 0,
                has_definition=True,
            )
            logger.info(
                "Загружено аббревиатур из БД для group_id=%d: total=%d",
                group_id, len(acronyms))
            if acronyms:
                # Разделить на глобальные и группо-специфичные.
                global_eligible: List[Dict[str, Any]] = []
                group_eligible: List[Dict[str, Any]] = []

                for a in acronyms:
                    term = str(a.get("term", "") or "").strip()
                    definition = str(a.get("definition") or "").strip()
                    if not term or not definition:
                        continue

                    # Термин, подтверждённый экспертом, проходит без проверки confidence.
                    expert_approved = a.get("expert_status") == "approved"

                    if not expert_approved:
                        confidence_raw = a.get("confidence")
                        confidence = None
                        if confidence_raw is not None:
                            try:
                                confidence = float(confidence_raw)
                            except (TypeError, ValueError):
                                confidence = None
                        if confidence is None or confidence < min_confidence:
                            continue

                    if int(a.get("group_id") or 0) == 0:
                        global_eligible.append(a)
                    else:
                        group_eligible.append(a)

                # Группо-специфичные: ранжировать по message_count DESC,
                # ограничить лимитом.
                group_eligible.sort(
                    key=lambda x: int(x.get("message_count") or 0),
                    reverse=True,
                )
                if len(group_eligible) > max_group_terms:
                    logger.info(
                        "Обрезка группо-специфичных аббревиатур: %d → %d (group_id=%d)",
                        len(group_eligible), max_group_terms, group_id,
                    )
                    group_eligible = group_eligible[:max_group_terms]

                # Объединить глобальные + top-N группо-специфичных.
                all_eligible = global_eligible + group_eligible
                best_by_term = select_best_acronyms_by_term(
                    all_eligible,
                    uppercase_key=True,
                )

                parts = []
                for selected in sort_acronym_records_for_prompt(best_by_term.values()):
                    term = str(selected.get("term", "") or "").strip().upper()
                    definition = str(selected.get("definition") or "").strip()
                    if term and definition:
                        parts.append(f"{term} - {definition}.")
                if parts:
                    text = " ".join(parts)
                    self._acronyms_cache[group_id] = (text, now)
                    return text
        except Exception:
            logger.debug("Не удалось загрузить аббревиатуры из БД, используется fallback")

        return self._ACRONYMS_FALLBACK

    def build_acronyms_section(self, group_id: int) -> str:
        """Публичная обёртка для получения секции аббревиатур промпта."""
        return self._build_acronyms_section(group_id)

    def _enrich_with_cross_day_context(
        self,
        messages: List[GroupMessage],
    ) -> List[GroupMessage]:
        """
        Обогатить набор сообщений кросс-дневным контекстом.

        Итеративно загружает из БД:
        - родительские сообщения (reply_to_message_id → parent), отсутствующие в наборе;
        - ответы (reply_to) на сообщения набора, отправленные в другие дни.

        Это позволяет строить полные цепочки обсуждений, пересекающие границы
        календарных дней (вопрос в день N, ответ в день N+k).

        Args:
            messages: Исходные сообщения текущего дня.

        Returns:
            Расширенный список сообщений (исходные + кросс-дневные).
        """
        if not messages:
            return messages

        group_ids = {msg.group_id for msg in messages if msg.group_id}
        if len(group_ids) != 1:
            logger.warning(
                "Кросс-дневное обогащение: ожидается 1 группа, получено %d — пропуск",
                len(group_ids),
            )
            return messages
        group_id = group_ids.pop()

        max_depth = ai_settings.GK_ANALYSIS_CROSS_DAY_MAX_DEPTH
        max_days = ai_settings.GK_ANALYSIS_CROSS_DAY_MAX_DAYS

        # Минимальный timestamp для ограничения глубины поиска.
        min_ts = min(msg.message_date for msg in messages)
        min_allowed_ts = min_ts - max_days * 86400

        # Рабочее множество: telegram_message_id → GroupMessage.
        working: Dict[int, GroupMessage] = {
            msg.telegram_message_id: msg for msg in messages
        }
        cross_day_total = 0

        for depth in range(max_depth):
            new_messages: List[GroupMessage] = []

            # --- Вверх: загрузить родительские сообщения, отсутствующие в наборе ---
            missing_parent_ids = [
                msg.reply_to_message_id
                for msg in working.values()
                if msg.reply_to_message_id and msg.reply_to_message_id not in working
            ]
            if missing_parent_ids:
                parents = gk_db.get_messages_by_telegram_ids(group_id, missing_parent_ids)
                for parent in parents:
                    if parent.telegram_message_id not in working:
                        new_messages.append(parent)

            # --- Вниз: загрузить ответы на сообщения набора из других дней ---
            current_tg_ids = list(working.keys())
            if current_tg_ids:
                replies = gk_db.get_replies_to_telegram_messages(
                    group_id, current_tg_ids, min_timestamp=min_allowed_ts,
                )
                for reply in replies:
                    if reply.telegram_message_id not in working:
                        new_messages.append(reply)

            if not new_messages:
                logger.debug(
                    "Кросс-дневное обогащение: depth=%d — новых сообщений не найдено, остановка",
                    depth,
                )
                break

            for msg in new_messages:
                working[msg.telegram_message_id] = msg
            cross_day_total += len(new_messages)

            log_details = "; ".join(
                f"tg_id={m.telegram_message_id} reply_to={m.reply_to_message_id}"
                for m in new_messages[:THREAD_CROSS_DAY_LOG_LIMIT]
            )
            suffix = (
                f" (и ещё {len(new_messages) - THREAD_CROSS_DAY_LOG_LIMIT})"
                if len(new_messages) > THREAD_CROSS_DAY_LOG_LIMIT
                else ""
            )
            logger.info(
                "Кросс-дневное обогащение: depth=%d found=%d group=%d [%s%s]",
                depth, len(new_messages), group_id, log_details, suffix,
            )

        if cross_day_total > 0:
            logger.info(
                "Кросс-дневное обогащение завершено: group=%d total_added=%d working_set=%d",
                group_id, cross_day_total, len(working),
            )

        # Вернуть в том же порядке: сначала исходные, затем новые.
        enriched = list(working.values())
        enriched.sort(key=lambda m: (m.message_date, m.telegram_message_id))
        return enriched

    async def _extract_thread_pairs(
        self,
        messages: List[GroupMessage],
    ) -> List[QAPair]:
        """
        Извлечь Q&A пары по reply-to связям и цепочкам обсуждения.

        Строит reply-деревья и пытается получить итоговую Q&A-пару
        из всей цепочки обсуждения, а не только из одного прямого ответа.
        """
        # Кросс-дневное обогащение: подгрузить ответы/родителей из других дней.
        if ai_settings.GK_ANALYSIS_CROSS_DAY_ENRICHMENT:
            messages = self._enrich_with_cross_day_context(messages)

        msg_index = {msg.telegram_message_id: msg for msg in messages}
        children_index = self._build_reply_children_index(messages)
        thread_roots = self._find_thread_roots(messages, msg_index, children_index)

        pairs: List[QAPair] = []
        seen_root_ids = set()
        candidates = []

        for root_msg in thread_roots:
            if root_msg.telegram_message_id in seen_root_ids:
                continue

            thread_messages = self._collect_thread_messages(
                root_msg,
                children_index,
                all_messages=messages,
            )
            question_message = self._select_chain_question_message(root_msg, thread_messages)
            question_text = question_message.full_text.strip()

            if not question_text or len(thread_messages) < 2:
                continue
            if len({msg.sender_id for msg in thread_messages if msg.sender_id}) < 2:
                continue

            candidates.append(
                {
                    "root": root_msg,
                    "thread_messages": thread_messages,
                    "message_ids": {
                        msg.telegram_message_id
                        for msg in thread_messages
                        if msg.telegram_message_id is not None
                    },
                }
            )

        selected_candidates = self._merge_overlapping_candidates(candidates)

        for candidate in selected_candidates:
            root_msg = candidate["root"]
            thread_messages = candidate["thread_messages"]
            question_message = self._select_chain_question_message(root_msg, thread_messages)

            try:
                validated = await self._validate_thread_chain(question_message, thread_messages)
                if not validated:
                    continue

                llm_request_payload = None
                confidence_reason = None
                fullness = None
                if len(validated) >= 7:
                    (
                        clean_question,
                        clean_answer,
                        confidence,
                        answer_message_tg_id,
                        llm_request_payload,
                        confidence_reason,
                        fullness,
                    ) = validated
                elif len(validated) >= 5:
                    clean_question, clean_answer, confidence, answer_message_tg_id, llm_request_payload = validated
                else:
                    clean_question, clean_answer, confidence, answer_message_tg_id = validated
                answer_message = None
                if answer_message_tg_id is not None:
                    answer_message = msg_index.get(answer_message_tg_id)
                if answer_message is None:
                    answer_message = self._find_last_meaningful_message(
                        thread_messages,
                        question_sender_id=question_message.sender_id,
                    )

                stored_question = (clean_question or "").strip()
                clean_answer = (clean_answer or "").strip()
                if not stored_question.strip() or not clean_answer:
                    logger.debug(
                        "Пропуск thread-пары из-за пустого вопроса/ответа: root_msg=%d",
                        root_msg.telegram_message_id,
                    )
                    continue

                pair = QAPair(
                    question_text=stored_question,
                    answer_text=clean_answer,
                    question_message_id=question_message.id,
                    answer_message_id=answer_message.id if answer_message else None,
                    group_id=question_message.group_id,
                    extraction_type="thread_reply",
                    confidence=confidence,
                    confidence_reason=confidence_reason,
                    fullness=fullness,
                    llm_model_used=self._model_name,
                    llm_request_payload=llm_request_payload,
                )
                pair_id = gk_db.store_qa_pair(pair)
                pair.id = pair_id
                pairs.append(pair)
                seen_root_ids.add(root_msg.telegram_message_id)
                chain_preview = self._format_thread_chain_log_preview(thread_messages)

                logger.info(
                    "Создана thread Q&A-пара: pair_id=%s root_msg=%d question_msg=%d answer_msg=%s messages=%d conf=%.2f chain=%s",
                    pair.id,
                    root_msg.telegram_message_id,
                    question_message.telegram_message_id,
                    answer_message.telegram_message_id if answer_message else None,
                    len(thread_messages),
                    confidence,
                    chain_preview,
                )

                logger.debug(
                    "Thread chain pair saved: root_msg=%d question_msg=%d messages=%d conf=%.2f",
                    root_msg.telegram_message_id,
                    question_message.telegram_message_id,
                    len(thread_messages),
                    confidence,
                )
            except Exception as exc:
                logger.warning(
                    "Ошибка валидации thread цепочки: root=%d error=%s",
                    root_msg.telegram_message_id,
                    exc,
                )

            # Пауза между LLM-запросами
            await asyncio.sleep(0.5)

        return pairs

    def _merge_overlapping_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """Объединить сильно пересекающиеся кандидаты цепочек в одну общую цепочку."""
        if not candidates:
            return []

        ordered_candidates = sorted(
            candidates,
            key=lambda item: (
                -len(item["thread_messages"]),
                item["root"].message_date,
                item["root"].telegram_message_id,
            ),
        )

        selected: List[Dict] = []
        for candidate in ordered_candidates:
            candidate_ids = candidate["message_ids"]
            if not candidate_ids:
                continue

            overlap_indexes = []
            for index, winner in enumerate(selected):
                winner_ids = winner["message_ids"]
                overlap_ratio = self._calculate_overlap_ratio(candidate_ids, winner_ids)
                if overlap_ratio >= THREAD_OVERLAP_RATIO_THRESHOLD:
                    overlap_indexes.append((index, overlap_ratio))

            if not overlap_indexes:
                selected.append(candidate)
                continue

            primary_index, primary_overlap = overlap_indexes[0]
            merged_candidate = self._merge_chain_candidates(selected[primary_index], candidate)
            selected[primary_index] = merged_candidate
            logger.info(
                "Объединение пересекающихся цепочек: base_root_msg=%d merged_root_msg=%d overlap=%.2f merged_messages=%d",
                selected[primary_index]["root"].telegram_message_id,
                candidate["root"].telegram_message_id,
                primary_overlap,
                len(selected[primary_index]["thread_messages"]),
            )

            for overlap_index, overlap_ratio in sorted(overlap_indexes[1:], reverse=True):
                merged_candidate = self._merge_chain_candidates(
                    selected[primary_index],
                    selected[overlap_index],
                )
                selected[primary_index] = merged_candidate
                logger.info(
                    "Объединение пересекающихся цепочек: base_root_msg=%d merged_root_msg=%d overlap=%.2f merged_messages=%d",
                    selected[primary_index]["root"].telegram_message_id,
                    selected[overlap_index]["root"].telegram_message_id,
                    overlap_ratio,
                    len(selected[primary_index]["thread_messages"]),
                )
                selected.pop(overlap_index)

        return sorted(
            selected,
            key=lambda item: (
                item["root"].message_date,
                item["root"].telegram_message_id,
            ),
        )

    @staticmethod
    def _merge_chain_candidates(base_candidate: Dict, extra_candidate: Dict) -> Dict:
        """Слить два кандидата цепочек в один, сохраняя детерминированный root."""
        by_message_id = {
            msg.telegram_message_id: msg
            for msg in base_candidate["thread_messages"]
            if msg.telegram_message_id is not None
        }
        for msg in extra_candidate["thread_messages"]:
            if msg.telegram_message_id is None:
                continue
            by_message_id[msg.telegram_message_id] = msg

        merged_messages = sorted(
            by_message_id.values(),
            key=lambda item: (item.message_date, item.telegram_message_id),
        )

        base_root = base_candidate["root"]
        extra_root = extra_candidate["root"]
        merged_root = min(
            [base_root, extra_root],
            key=lambda item: (item.message_date, item.telegram_message_id),
        )

        return {
            "root": merged_root,
            "thread_messages": merged_messages,
            "message_ids": set(by_message_id.keys()),
        }

    @staticmethod
    def _calculate_overlap_ratio(first_ids: set, second_ids: set) -> float:
        """Рассчитать долю пересечения относительно меньшей цепочки."""
        if not first_ids or not second_ids:
            return 0.0

        intersection_size = len(first_ids & second_ids)
        min_size = min(len(first_ids), len(second_ids))
        if min_size == 0:
            return 0.0
        return intersection_size / min_size

    async def _validate_thread_chain(
        self,
        root_message: GroupMessage,
        thread_messages: List[GroupMessage],
    ) -> Optional[Tuple[str, str, float, Optional[int], Optional[str], Optional[str], Optional[float]]]:
        """
        Валидировать и очистить цепочку Q&A через LLM.

        Returns:
            Кортеж (clean_question, clean_answer, confidence, answer_message_id,
            llm_request_payload, confidence_reason, fullness) или None.
        """
        provider = self._get_provider()
        thread_context = self._format_thread_context(thread_messages)
        acronyms_section = self._build_acronyms_section(
            getattr(root_message, "group_id", 0) or 0
        )
        prompt = THREAD_VALIDATION_PROMPT.format(
            question=root_message.full_text[:2000],
            thread_context=thread_context[:6000],
            question_confidence_threshold=f"{self._question_confidence_threshold:.2f}",
            acronyms_section=acronyms_section,
        )
        system_prompt = "Ты — помощник для анализа пар вопрос-ответ."
        request_payload = self._build_llm_request_payload(
            prompt=prompt,
            system_prompt=system_prompt,
            purpose="gk_validation",
        )

        try:
            temperature = max(0.0, min(2.0, float(ai_settings.get_active_gk_analysis_temperature())))
            raw = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
                purpose="gk_validation",
                model_override=self._model_name,
                temperature_override=temperature,
                response_format={"type": "json_object"},
            )

            parsed = self._parse_json_response(raw)
            if not parsed:
                return None

            if not parsed.get("is_valid_qa", False):
                return None

            clean_q = parsed.get("clean_question", root_message.full_text)
            clean_a = parsed.get("clean_answer", "")
            clean_q = (clean_q or "").strip()
            clean_a = (clean_a or "").strip()
            confidence = float(parsed.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            answer_message_id = parsed.get("answer_message_id")
            confidence_reason_raw = parsed.get("confidence_reason")
            confidence_reason = None
            if confidence_reason_raw is not None:
                confidence_reason = str(confidence_reason_raw).strip() or None

            fullness_raw = parsed.get("fullness")
            fullness: Optional[float] = None
            if fullness_raw is not None:
                try:
                    fullness = float(fullness_raw)
                    fullness = max(0.0, min(1.0, fullness))
                except (TypeError, ValueError):
                    fullness = None

            if not clean_q or not clean_a:
                return None

            return (
                clean_q,
                clean_a,
                confidence,
                answer_message_id,
                request_payload,
                confidence_reason,
                fullness,
            )
        except Exception as exc:
            logger.warning("Ошибка LLM-валидации thread-цепочки: %s", exc)
            return None

    async def _validate_qa_pair(
        self,
        question: str,
        answer: str,
    ) -> Optional[Tuple[str, str, float]]:
        """Совместимость со старыми тестами прямой пары вопрос-ответ."""
        root_message = GroupMessage(message_text=question)
        answer_message = GroupMessage(message_text=answer, reply_to_message_id=1)
        validated = await self._validate_thread_chain(root_message, [root_message, answer_message])
        if not validated:
            return None
        if len(validated) >= 7:
            clean_q, clean_a, confidence, _answer_message_id, _llm_request_payload, _confidence_reason, _fullness = validated
        elif len(validated) >= 5:
            clean_q, clean_a, confidence, _answer_message_id, _llm_request_payload = validated
        else:
            clean_q, clean_a, confidence, _answer_message_id = validated
        return clean_q, clean_a, confidence

    def _build_llm_request_payload(
        self,
        *,
        prompt: str,
        system_prompt: str,
        purpose: str,
    ) -> str:
        """Собрать JSON-представление запроса к LLM для отладки."""
        payload: Dict[str, Any] = {
            "system_prompt": system_prompt,
            "messages": [{"role": "user", "content": prompt}],
            "purpose": purpose,
            "model_override": self._model_name,
            "response_format": {"type": "json_object"},
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def _build_reply_children_index(
        messages: List[GroupMessage],
    ) -> Dict[int, List[GroupMessage]]:
        """Построить индекс дочерних reply-сообщений по telegram_message_id родителя."""
        children: Dict[int, List[GroupMessage]] = {}
        for msg in messages:
            if not msg.reply_to_message_id:
                continue
            children.setdefault(msg.reply_to_message_id, []).append(msg)

        for child_list in children.values():
            child_list.sort(key=lambda item: (item.message_date, item.telegram_message_id))
        return children

    @staticmethod
    def _find_thread_roots(
        messages: List[GroupMessage],
        msg_index: Dict[int, GroupMessage],
        children_index: Dict[int, List[GroupMessage]],
    ) -> List[GroupMessage]:
        """Найти корневые сообщения обсуждений, имеющих reply-цепочки."""
        roots: Dict[int, GroupMessage] = {}
        for msg in messages:
            if msg.telegram_message_id not in children_index:
                continue

            current = msg
            visited = set()
            while current.reply_to_message_id and current.reply_to_message_id in msg_index:
                if current.telegram_message_id in visited:
                    break
                visited.add(current.telegram_message_id)
                current = msg_index[current.reply_to_message_id]
            roots[current.telegram_message_id] = current

        return sorted(
            roots.values(),
            key=lambda item: (item.message_date, item.telegram_message_id),
        )

    def _collect_thread_messages(
        self,
        root_message: GroupMessage,
        children_index: Dict[int, List[GroupMessage]],
        all_messages: Optional[List[GroupMessage]] = None,
    ) -> List[GroupMessage]:
        """
        Собрать сообщения одной цепочки обсуждения начиная с reply-корня.

        Помимо явной reply-ветки, добавляет соседние по времени сообщения
        от тех же участников, чтобы покрыть часть обсуждения без reply-связей.
        """
        collected: List[GroupMessage] = []
        queue = [root_message]
        visited = set()

        while queue:
            current = queue.pop(0)
            if current.telegram_message_id in visited:
                continue
            visited.add(current.telegram_message_id)
            collected.append(current)
            queue.extend(children_index.get(current.telegram_message_id, []))

        if all_messages:
            base_count = len(collected)
            collected = self._append_nearby_sequential_messages(
                collected=collected,
                all_messages=all_messages,
                visited_ids=visited,
                question_confidence_threshold=self._question_confidence_threshold,
            )
            nearby_added_count = len(collected) - base_count
            descendants_base_count = len(collected)
            collected = self._expand_with_reply_descendants(
                collected=collected,
                children_index=children_index,
                visited_ids=visited,
            )
            descendants_added_count = len(collected) - descendants_base_count
            added_count = nearby_added_count + descendants_added_count
            if added_count > 0:
                logger.info(
                    "Найдены дополнительные сообщения в цепочке: root_msg=%d nearby_added=%d descendants_added=%d total=%d",
                    root_message.telegram_message_id,
                    nearby_added_count,
                    descendants_added_count,
                    len(collected),
                )

        collected.sort(key=lambda item: (item.message_date, item.telegram_message_id))
        return collected

    @staticmethod
    def _append_nearby_sequential_messages(
        collected: List[GroupMessage],
        all_messages: List[GroupMessage],
        visited_ids: set,
        question_confidence_threshold: float = 0.90,
    ) -> List[GroupMessage]:
        """
        Добавить соседние по времени сообщения участников цепочки без reply-связи.

        Фильтры:
        - Пропускать сообщения, классифицированные как самостоятельные вопросы
          (is_question=True, confidence >= порог) — они являются корнями своих обсуждений.
        - Пропускать сообщения, у которых reply_to указывает на сообщение, не входящее
          в текущую цепочку — они принадлежат другим обсуждениям.
        """
        participant_ids = {msg.sender_id for msg in collected if msg.sender_id}
        if not participant_ids:
            return collected

        root_sender_id = collected[0].sender_id if collected else None
        hard_question_fragments_added = 0

        ordered_messages = sorted(
            all_messages,
            key=lambda item: (item.message_date, item.telegram_message_id),
        )

        min_ts = min((msg.message_date for msg in collected), default=0)
        max_ts = max((msg.message_date for msg in collected), default=0)

        nearby_added = 0
        skipped_questions = 0
        skipped_foreign_replies = 0
        changed = True
        while changed and nearby_added < THREAD_MAX_NEARBY_MESSAGES:
            changed = False
            window_start = min_ts - THREAD_NEARBY_WINDOW_SECONDS
            window_end = max_ts + THREAD_NEARBY_WINDOW_SECONDS

            for msg in ordered_messages:
                if nearby_added >= THREAD_MAX_NEARBY_MESSAGES:
                    break
                if msg.telegram_message_id in visited_ids:
                    continue
                if not msg.sender_id or msg.sender_id not in participant_ids:
                    continue
                if msg.message_date < window_start or msg.message_date > window_end:
                    continue
                if not msg.full_text.strip():
                    continue

                # Пропустить сообщения, классифицированные как самостоятельные вопросы:
                # такие сообщения — корни собственных обсуждений.
                is_hard_question = (
                    msg.is_question is True
                    and msg.question_confidence is not None
                    and msg.question_confidence >= question_confidence_threshold
                )
                if is_hard_question:
                    can_attach_question_fragment = (
                        root_sender_id is not None
                        and msg.sender_id == root_sender_id
                        and hard_question_fragments_added < THREAD_QUESTION_FRAGMENT_MAX_MESSAGES
                        and QAAnalyzer._is_message_within_fragment_gap(
                            msg,
                            collected,
                            max_gap_seconds=THREAD_QUESTION_FRAGMENT_MAX_GAP_SECONDS,
                        )
                    )
                    if not can_attach_question_fragment:
                        skipped_questions += 1
                        continue

                # Пропустить сообщения, являющиеся ответами на сообщения из другой цепочки.
                if (
                    msg.reply_to_message_id is not None
                    and msg.reply_to_message_id not in visited_ids
                ):
                    skipped_foreign_replies += 1
                    continue

                collected.append(msg)
                visited_ids.add(msg.telegram_message_id)
                nearby_added += 1
                if is_hard_question:
                    hard_question_fragments_added += 1
                min_ts = min(min_ts, msg.message_date)
                max_ts = max(max_ts, msg.message_date)
                changed = True

        if skipped_questions or skipped_foreign_replies:
            logger.debug(
                "Фильтрация nearby-сообщений: skipped_questions=%d skipped_foreign_replies=%d",
                skipped_questions,
                skipped_foreign_replies,
            )

        return collected

    @staticmethod
    def _is_message_within_fragment_gap(
        candidate: GroupMessage,
        collected: List[GroupMessage],
        max_gap_seconds: int,
    ) -> bool:
        """Проверить, что сообщение находится близко к уже собранным сообщениям того же автора."""
        same_sender_dates = [
            msg.message_date
            for msg in collected
            if msg.sender_id == candidate.sender_id
        ]
        if not same_sender_dates:
            return False

        nearest_gap = min(abs(candidate.message_date - ts) for ts in same_sender_dates)
        return nearest_gap <= max_gap_seconds

    @staticmethod
    def _expand_with_reply_descendants(
        collected: List[GroupMessage],
        children_index: Dict[int, List[GroupMessage]],
        visited_ids: set,
    ) -> List[GroupMessage]:
        """Добрать reply-потомков для сообщений, добавленных через nearby-расширение."""
        by_tg_id = {
            msg.telegram_message_id: msg
            for msg in collected
            if msg.telegram_message_id is not None
        }
        queue = list(by_tg_id.keys())

        while queue:
            parent_tg_id = queue.pop(0)
            for child in children_index.get(parent_tg_id, []):
                child_tg_id = child.telegram_message_id
                if child_tg_id in visited_ids:
                    continue
                visited_ids.add(child_tg_id)
                by_tg_id[child_tg_id] = child
                queue.append(child_tg_id)

        return list(by_tg_id.values())

    def _select_chain_question_message(
        self,
        root_message: GroupMessage,
        thread_messages: List[GroupMessage],
    ) -> GroupMessage:
        """Выбрать сообщение, которое следует считать вопросом цепочки."""
        ordered_messages = sorted(
            thread_messages,
            key=lambda item: (item.message_date, item.telegram_message_id),
        )

        for msg in ordered_messages:
            if self._is_message_hard_question(msg) and msg.full_text.strip():
                return msg

        return root_message

    def _is_message_hard_question(self, message: GroupMessage) -> bool:
        """Считать ли сообщение явным вопросом по сохранённой LLM-классификации."""
        if message.is_question is not True:
            return False

        confidence = message.question_confidence
        if confidence is None:
            return False

        return confidence >= self._question_confidence_threshold

    @staticmethod
    def _format_question_hint(message: GroupMessage) -> str:
        """Сформировать подсказку о question-классификации сообщения для LLM."""
        if message.is_question is True:
            confidence = message.question_confidence if message.question_confidence is not None else 0.0
            return f" [QUESTION_HINT conf={confidence:.{THREAD_QUESTION_HINT_CONFIDENCE_DECIMALS}f}]"
#        if message.is_question is False:
#            confidence = message.question_confidence if message.question_confidence is not None else 0.0
#            return f" [NOT_QUESTION_HINT conf={confidence:.{THREAD_QUESTION_HINT_CONFIDENCE_DECIMALS}f}]"
        return ""

    @staticmethod
    def _format_thread_context(thread_messages: List[GroupMessage]) -> str:
        """Подготовить цепочку сообщений в компактный текстовый контекст для LLM."""
        lines = []
        for msg in thread_messages:
            text = msg.full_text.strip()
            if not text:
                continue
            sender = msg.sender_name or f"User_{msg.sender_id}"
            timestamp = QAAnalyzer._format_message_timestamp(msg.message_date)
            reply_hint = (
                f" -> reply_to:{msg.reply_to_message_id}"
                if msg.reply_to_message_id
                else ""
            )
            question_hint = QAAnalyzer._format_question_hint(msg)
            lines.append(
                f"[{msg.telegram_message_id} @ {timestamp}{reply_hint}]{question_hint} {sender}: {text[:700]}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_thread_chain_log_preview(thread_messages: List[GroupMessage]) -> str:
        """Подготовить укороченный preview цепочки сообщений для логов."""
        parts = []
        for msg in thread_messages:
            text = QAAnalyzer._normalize_message_for_log(msg.full_text)
            if not text:
                continue

            sender = msg.sender_name or f"User_{msg.sender_id}"
            truncated_text = text[:THREAD_LOG_MESSAGE_TEXT_LIMIT]
            if len(text) > THREAD_LOG_MESSAGE_TEXT_LIMIT:
                truncated_text += "…"
            parts.append(
                f"[{msg.telegram_message_id}] {sender}: {truncated_text}"
            )

        preview = " | ".join(parts)
        if len(preview) > THREAD_LOG_CHAIN_PREVIEW_LIMIT:
            return preview[: THREAD_LOG_CHAIN_PREVIEW_LIMIT - 1] + "…"
        return preview

    @staticmethod
    def _normalize_message_for_log(text: str) -> str:
        """Нормализовать переносы и лишние пробелы перед выводом в лог."""
        return " ".join((text or "").split())

    @staticmethod
    def _format_message_timestamp(message_date: int) -> str:
        """Преобразовать UNIX timestamp сообщения в читаемый UTC-формат."""
        if not message_date:
            return "unknown_time"
        try:
            return datetime.fromtimestamp(message_date, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
        except (OverflowError, OSError, ValueError):
            return "unknown_time"

    @staticmethod
    def _enrich_question_with_image_gist(question_text: str, source_message: GroupMessage) -> str:
        """Добавить в вопрос краткую суть проблемы с изображения, если она ещё не отражена."""
        return enrich_question_for_rag(
            question_text=question_text,
            source_message=source_message,
            enabled=True,
        )

    @staticmethod
    def _is_gratitude_message(text: str) -> bool:
        """Похоже ли сообщение на благодарность без новой полезной информации."""
        normalized = (text or "").strip().lower()
        if not normalized:
            return True
        gratitude_markers = (
            "спасибо",
            "благодарю",
            "thanks",
            "thank you",
            "всё получилось",
            "все получилось",
            "заработало",
            "помогло",
            "ок, спасибо",
        )
        return any(marker in normalized for marker in gratitude_markers)

    def _find_last_meaningful_message(
        self,
        thread_messages: List[GroupMessage],
        question_sender_id: int,
    ) -> Optional[GroupMessage]:
        """Найти последнее содержательное сообщение с решением в цепочке."""
        for msg in reversed(thread_messages[1:]):
            text = msg.full_text.strip()
            if not text:
                continue
            if self._is_gratitude_message(text):
                continue
            if msg.sender_id == question_sender_id and len(thread_messages) > 2:
                continue
            return msg
        return thread_messages[-1] if len(thread_messages) > 1 else None

    async def _extract_llm_inferred_pairs(
        self,
        messages: List[GroupMessage],
        group_id: int,
    ) -> List[QAPair]:
        """
        Найти неявные Q&A пары через LLM-анализ контекста.

        Отправляет батчи сообщений в LLM для обнаружения пар,
        не связанных через reply-to.
        """
        if not ai_settings.get_active_gk_generate_llm_inferred_qa_pairs():
            logger.info(
                "Пропуск LLM-inferred extraction: настройка GK_GENERATE_LLM_INFERRED_QA_PAIRS=0 (group=%d)",
                group_id,
            )
            return []

        # Собрать ID сообщений, которые уже являются thread-парами
        thread_msg_ids = set()
        for msg in messages:
            if msg.reply_to_message_id:
                thread_msg_ids.add(msg.telegram_message_id)
                thread_msg_ids.add(msg.reply_to_message_id)

        # Фильтровать: убрать уже обработанные в thread-парах
        remaining = [m for m in messages if m.telegram_message_id not in thread_msg_ids]

        if len(remaining) < 2:
            return []

        pairs: List[QAPair] = []

        # Разбить на батчи
        for i in range(0, len(remaining), self._batch_size):
            batch = remaining[i : i + self._batch_size]
            try:
                batch_pairs = await self._analyze_batch_for_pairs(batch, group_id, messages)
                pairs.extend(batch_pairs)
            except Exception as exc:
                logger.warning(
                    "Ошибка анализа батча %d-%d: %s",
                    i, i + len(batch), exc,
                )

            # Пауза между батчами
            if i + self._batch_size < len(remaining):
                await asyncio.sleep(1.0)

        return pairs

    async def _analyze_batch_for_pairs(
        self,
        batch: List[GroupMessage],
        group_id: int,
        _all_messages: List[GroupMessage],
    ) -> List[QAPair]:
        """
        Проанализировать батч сообщений для поиска Q&A пар через LLM.

        Args:
            batch: Батч сообщений для анализа.
            group_id: ID группы.
            all_messages: Все сообщения за день (для индексации по ID).

        Returns:
            Список найденных QAPair.
        """
        # Подготовить текст сообщений для LLM
        msg_lines = []
        msg_index: Dict[int, GroupMessage] = {}
        for msg in batch:
            msg_index[msg.telegram_message_id] = msg
            text = msg.full_text.strip()
            if text:
                sender = msg.sender_name or f"User_{msg.sender_id}"
                question_hint = self._format_question_hint(msg)

                msg_lines.append(
                    f"[{msg.telegram_message_id}]{question_hint} {sender}: {text[:500]}"
                )

        if len(msg_lines) < 2:
            return []

        messages_text = "\n".join(msg_lines)
        prompt = LLM_INFERENCE_PROMPT.format(messages=messages_text)

        provider = self._get_provider()
        system_prompt = "Ты — аналитик технической поддержки."
        request_payload = self._build_llm_request_payload(
            prompt=prompt,
            system_prompt=system_prompt,
            purpose="gk_inference",
        )

        try:
            temperature = max(0.0, min(2.0, float(ai_settings.get_active_gk_analysis_temperature())))
            raw = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
                purpose="gk_inference",
                model_override=self._model_name,
                temperature_override=temperature,
                response_format={"type": "json_object"},
            )

            parsed = self._parse_json_response(raw)
            if not parsed:
                return []

            raw_pairs = parsed.get("pairs", [])
            if not isinstance(raw_pairs, list):
                return []

            pairs: List[QAPair] = []
            for raw_pair in raw_pairs:
                try:
                    q_text = (raw_pair.get("question", "") or "").strip()
                    a_text = (raw_pair.get("answer", "") or "").strip()
                    confidence = float(raw_pair.get("confidence", 0.5))

                    if not q_text or not a_text:
                        continue

                    q_msg_id = raw_pair.get("question_msg_id")
                    a_msg_id = raw_pair.get("answer_msg_id")

                    # Найти DB-ID для сообщений
                    q_db_id = None
                    a_db_id = None
                    if q_msg_id and q_msg_id in msg_index:
                        q_db_id = msg_index[q_msg_id].id
                    if a_msg_id and a_msg_id in msg_index:
                        a_db_id = msg_index[a_msg_id].id

                    stored_question = (q_text or "").strip()
                    if not stored_question.strip() or not a_text:
                        continue

                    pair = QAPair(
                        question_text=stored_question,
                        answer_text=a_text,
                        question_message_id=q_db_id,
                        answer_message_id=a_db_id,
                        group_id=group_id,
                        extraction_type="llm_inferred",
                        confidence=max(0.0, min(1.0, confidence)),
                        llm_model_used=self._model_name,
                        llm_request_payload=request_payload,
                    )
                    pair_id = gk_db.store_qa_pair(pair)
                    pair.id = pair_id
                    pairs.append(pair)
                except Exception as exc:
                    logger.warning("Ошибка парсинга LLM-пары: %s", exc)

            return pairs
        except Exception as exc:
            logger.error("Ошибка LLM-инференса Q&A: %s", exc, exc_info=True)
            return []

    async def index_new_pairs(self) -> int:
        """
        Проиндексировать новые Q&A пары в Qdrant.

        Returns:
            Число проиндексированных пар.
        """
        pairs = gk_db.get_unindexed_qa_pairs()
        if not pairs:
            logger.info("Нет новых пар для индексации")
            return 0

        logger.info("Индексация %d новых Q&A пар", len(pairs))

        try:
            from src.core.ai.vector_search import LocalVectorIndex, LocalEmbeddingProvider

            embedding_provider = LocalEmbeddingProvider()
            collection_name = ai_settings.GK_QA_VECTOR_COLLECTION
            vector_index = LocalVectorIndex(chunk_collection_name=collection_name)

            question_message_ids = [
                int(pair.question_message_id)
                for pair in pairs
                if pair.question_message_id is not None
            ]
            question_messages_by_id: Dict[int, GroupMessage] = {}
            if question_message_ids:
                question_messages_by_id = gk_db.get_messages_by_ids(question_message_ids)

            indexed_count = 0
            total_pairs = len(pairs)
            started_at = time.time()
            for index, pair in enumerate(pairs, start=1):
                try:
                    if not pair.id:
                        continue

                    source_message = None
                    if pair.question_message_id is not None:
                        source_message = question_messages_by_id.get(int(pair.question_message_id))

                    rag_question_text = enrich_question_for_rag(
                        question_text=pair.question_text,
                        source_message=source_message,
                        enabled=ai_settings.GK_RAG_IMAGE_GIST_ENABLED,
                    )
                    if not rag_question_text:
                        rag_question_text = (pair.question_text or "").strip()

                    # Текст для эмбеддинга: вопрос + ответ
                    embed_text = f"Вопрос: {rag_question_text}\nОтвет: {pair.answer_text}"

                    try:
                        embedding = embedding_provider.encode(embed_text)
                        if not embedding:
                            logger.warning(
                                "Не удалось получить эмбеддинг для пары %d",
                                pair.id,
                            )
                            continue

                        upserted = vector_index.upsert_chunks(
                            chunks=[{
                                "document_id": pair.id,
                                "chunk_index": 0,
                                "filename": f"gk_qa_pair_{pair.id}",
                                "chunk_text": embed_text,
                                "status": "active",
                            }],
                            embeddings=[embedding],
                        )
                        if upserted <= 0:
                            logger.warning(
                                "Qdrant не принял вектор для пары %d",
                                pair.id,
                            )
                            continue

                        gk_db.mark_qa_pair_indexed(pair.id)
                        indexed_count += 1
                    except Exception as exc:
                        logger.warning(
                            "Ошибка индексации пары %d: %s", pair.id, exc,
                        )
                finally:
                    if total_pairs and (index == 1 or index % 25 == 0 or index == total_pairs):
                        elapsed = max(time.time() - started_at, 1e-6)
                        rate = index / elapsed
                        remaining_items = max(total_pairs - index, 0)
                        eta_seconds = remaining_items / rate if rate > 0 else 0.0
                        eta_h = int(max(0, eta_seconds)) // 3600
                        eta_m = (int(max(0, eta_seconds)) % 3600) // 60
                        eta_s = int(max(0, eta_seconds)) % 60
                        expected_finish_str = datetime.fromtimestamp(
                            time.time() + eta_seconds
                        ).strftime("%Y-%m-%d %H:%M:%S")
                        logger.info(
                            "Индексация QA-пар: %d/%d (%.1f%%), успешных=%d, ETA=%02d:%02d:%02d, ожидаемое завершение=%s",
                            index,
                            total_pairs,
                            (index / total_pairs) * 100.0,
                            indexed_count,
                            eta_h,
                            eta_m,
                            eta_s,
                            expected_finish_str,
                        )

            logger.info("Проиндексировано пар: %d / %d", indexed_count, len(pairs))
            return indexed_count
        except ImportError as exc:
            logger.error("Vector search не доступен: %s", exc)
            return 0
        except Exception as exc:
            logger.error("Ошибка индексации: %s", exc, exc_info=True)
            return 0

    @staticmethod
    def _parse_json_response(raw: str) -> Optional[Dict]:
        """
        Извлечь JSON из ответа LLM.

        Обрабатывает случаи markdown code-блоков и частичных ответов.
        """
        if not raw or not raw.strip():
            return None

        text = raw.strip()

        # Убрать markdown code-блок
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1])
            else:
                text = text.strip("`").strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Найти первый {..} в тексте
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    pass

        logger.warning("Не удалось распарсить JSON из LLM: %s", raw[:200])
        return None
