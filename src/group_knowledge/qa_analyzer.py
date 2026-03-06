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
from typing import Dict, List, Optional, Tuple

from config import ai_settings
from src.core.ai.llm_provider import get_provider
from src.group_knowledge import database as gk_db
from src.group_knowledge.models import AnalysisResult, GroupMessage, QAPair
from src.group_knowledge.settings import GK_IGNORED_SENDER_IDS

logger = logging.getLogger(__name__)

# Эвристика для расширения thread-контекста соседними последовательными сообщениями
# участников цепочки, даже если они не связаны Telegram reply-to.
THREAD_NEARBY_WINDOW_SECONDS = 180
THREAD_MAX_NEARBY_MESSAGES = 20
THREAD_OVERLAP_RATIO_THRESHOLD = 0.60

# Промпт для валидации и очистки thread-based цепочек
THREAD_VALIDATION_PROMPT = """Ты — эксперт по технической поддержке оборудования и ПО для полевых инженеров.

Тебе дана цепочка сообщений из чата технической поддержки.
Цепочка может содержать:
- исходный вопрос,
- уточняющие вопросы,
- промежуточные ответы,
- финальное решение,
- благодарность после решения.

ИСХОДНЫЙ ВОПРОС:
{question}

ЦЕПОЧКА СООБЩЕНИЙ:
{thread_context}
КОНТЕКСТ ЗАКОНЧЕН.
ОПРЕДЕЛИ:
1. Найди в цепочке полезный технический вопрос с решением.
2. Если все хорошо — is_valid_qa=true.
3. Игнорируй благодарности, приветствия, шутки и служебные реплики.
4. Если решение собрано из нескольких сообщений, объедини их в один качественный ответ.
5. По возможности укажи ID сообщения, где содержится финальное или наиболее полезное решение.
6. confidence - уровень уверенности модели, в том, что вопрос извлечен правильно, а не частично, общими словами без предмета обсуждения, вопрос имеет смысл и имеет полезное решение (0.0-1.0).
7. Оставляй аббревиатуры неизменными. ГЗ означает Горячая замена.
Верни JSON:
{{
    "is_valid_qa": true/false,
    "confidence": 0.0-1.0,
    "clean_question": "переформулированный вопрос. Если есть изображение, включи в вопрос суть проблемы из блока Изображение, добавь отдельный блок в начале [ИЗОБРАЖЕНИЕ].",
    "clean_answer": "итоговый ответ/решение",
    "answer_message_id": 123
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
        self._model_name = model_name or ai_settings.GK_ANALYSIS_MODEL
        self._batch_size = ai_settings.GK_ANALYSIS_BATCH_SIZE

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
            if force_reanalyze:
                logger.info(
                    "Нет сообщений для переанализа: group=%d date=%s",
                    group_id,
                    date_str,
                )
            else:
                logger.info(
                    "Нет новых необработанных сообщений для анализа: group=%d date=%s",
                    group_id,
                    date_str,
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
        if not skip_llm:
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

    async def _extract_thread_pairs(
        self,
        messages: List[GroupMessage],
    ) -> List[QAPair]:
        """
        Извлечь Q&A пары по reply-to связям и цепочкам обсуждения.

        Строит reply-деревья и пытается получить итоговую Q&A-пару
        из всей цепочки обсуждения, а не только из одного прямого ответа.
        """
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
            question_text = root_msg.full_text.strip()

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

            try:
                validated = await self._validate_thread_chain(root_msg, thread_messages)
                if not validated:
                    continue

                clean_question, clean_answer, confidence, answer_message_tg_id = validated
                answer_message = None
                if answer_message_tg_id is not None:
                    answer_message = msg_index.get(answer_message_tg_id)
                if answer_message is None:
                    answer_message = self._find_last_meaningful_message(
                        thread_messages,
                        question_sender_id=root_msg.sender_id,
                    )

                stored_question = self._enrich_question_with_image_gist(
                    clean_question,
                    root_msg,
                )
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
                    question_message_id=root_msg.id,
                    answer_message_id=answer_message.id if answer_message else None,
                    group_id=root_msg.group_id,
                    extraction_type="thread_reply",
                    confidence=confidence,
                    llm_model_used=self._model_name,
                )
                pair_id = gk_db.store_qa_pair(pair)
                pair.id = pair_id
                pairs.append(pair)
                seen_root_ids.add(root_msg.telegram_message_id)

                logger.debug(
                    "Thread chain pair saved: root_msg=%d messages=%d conf=%.2f",
                    root_msg.telegram_message_id,
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
    ) -> Optional[Tuple[str, str, float, Optional[int]]]:
        """
        Валидировать и очистить цепочку Q&A через LLM.

        Returns:
            Кортеж (clean_question, clean_answer, confidence, answer_message_id) или None.
        """
        provider = get_provider("deepseek")
        thread_context = self._format_thread_context(thread_messages)
        prompt = THREAD_VALIDATION_PROMPT.format(
            question=root_message.full_text[:2000],
            thread_context=thread_context[:6000],
        )

        try:
            raw = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="Ты — помощник для анализа пар вопрос-ответ.",
                purpose="gk_validation",
                model_override=self._model_name,
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

            if not clean_q or not clean_a:
                return None

            return clean_q, clean_a, confidence, answer_message_id
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
        clean_q, clean_a, confidence, _answer_message_id = validated
        return clean_q, clean_a, confidence

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
            )
            added_count = len(collected) - base_count
            if added_count > 0:
                logger.info(
                    "Найдены дополнительные последовательные сообщения: root_msg=%d added=%d total=%d",
                    root_message.telegram_message_id,
                    added_count,
                    len(collected),
                )

        collected.sort(key=lambda item: (item.message_date, item.telegram_message_id))
        return collected

    @staticmethod
    def _append_nearby_sequential_messages(
        collected: List[GroupMessage],
        all_messages: List[GroupMessage],
        visited_ids: set,
    ) -> List[GroupMessage]:
        """Добавить соседние по времени сообщения участников цепочки без reply-связи."""
        participant_ids = {msg.sender_id for msg in collected if msg.sender_id}
        if not participant_ids:
            return collected

        ordered_messages = sorted(
            all_messages,
            key=lambda item: (item.message_date, item.telegram_message_id),
        )

        min_ts = min((msg.message_date for msg in collected), default=0)
        max_ts = max((msg.message_date for msg in collected), default=0)

        nearby_added = 0
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

                collected.append(msg)
                visited_ids.add(msg.telegram_message_id)
                nearby_added += 1
                min_ts = min(min_ts, msg.message_date)
                max_ts = max(max_ts, msg.message_date)
                changed = True

        return collected

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
            lines.append(
                f"[{msg.telegram_message_id} @ {timestamp}{reply_hint}] {sender}: {text[:700]}"
            )
        return "\n".join(lines)

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
        base_question = (question_text or source_message.full_text or "").strip()
        if not base_question:
            return ""

        image_gist = (source_message.image_description or "").strip()
        if not image_gist:
            return base_question

        normalized_question = " ".join(base_question.lower().split())
        normalized_gist = " ".join(image_gist.lower().split())
        if normalized_gist and normalized_gist in normalized_question:
            return base_question

        return f"{base_question}\n[Суть по изображению: {image_gist[:1200]}]"

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
        all_messages: List[GroupMessage],
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
                question_hint = ""
                if msg.is_question is True:
                    confidence = msg.question_confidence if msg.question_confidence is not None else 0.0
                    question_hint = f" [QUESTION_HINT conf={confidence:.2f}]"
                elif msg.is_question is False:
                    confidence = msg.question_confidence if msg.question_confidence is not None else 0.0
                    question_hint = f" [NOT_QUESTION_HINT conf={confidence:.2f}]"

                msg_lines.append(
                    f"[{msg.telegram_message_id}]{question_hint} {sender}: {text[:500]}"
                )

        if len(msg_lines) < 2:
            return []

        messages_text = "\n".join(msg_lines)
        prompt = LLM_INFERENCE_PROMPT.format(messages=messages_text)

        provider = get_provider("deepseek")

        try:
            raw = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="Ты — аналитик технической поддержки.",
                purpose="gk_inference",
                model_override=self._model_name,
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
                    q_msg = None
                    if q_msg_id and q_msg_id in msg_index:
                        q_msg = msg_index[q_msg_id]
                        q_db_id = msg_index[q_msg_id].id
                    if a_msg_id and a_msg_id in msg_index:
                        a_db_id = msg_index[a_msg_id].id

                    stored_question = self._enrich_question_with_image_gist(
                        q_text,
                        q_msg if q_msg is not None else GroupMessage(message_text=q_text),
                    )
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

            indexed_count = 0
            for pair in pairs:
                if not pair.id:
                    continue

                # Текст для эмбеддинга: вопрос + ответ
                embed_text = f"Вопрос: {pair.question_text}\nОтвет: {pair.answer_text}"

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
