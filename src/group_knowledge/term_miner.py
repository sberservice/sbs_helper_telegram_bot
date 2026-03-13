"""
Майнер терминов и аббревиатур из сообщений Telegram-групп.

Сканирует собранные сообщения через LLM для извлечения:
- Защищённых терминов (short domain-specific tokens, < 6 символов)
- Аббревиатур с расшифровками (acronym → definition)

Результаты сохраняются в gk_terms со статусом 'pending' для
последующей экспертной валидации.
"""

import asyncio
import json
import logging
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import ai_settings
from src.core.ai.llm_provider import get_provider
from src.group_knowledge import database as gk_db

logger = logging.getLogger(__name__)

# Regex для извлечения JSON из markdown code fence (в т.ч. с преамбулой).
_JSON_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)

# Regex для схлопывания внутренних пробелов.
_MULTISPACE_RE = re.compile(r"\s+")

# Символы, считающиеся частью слова при проверке границ термина.
_TERM_WORD_CHARS = "0-9A-Za-zА-Яа-яЁё"


def _build_term_boundary_pattern(term: str) -> re.Pattern[str]:
    """Построить regex для точного совпадения термина по границам токена."""
    escaped_term = re.escape(term)
    return re.compile(
        rf"(?<![{_TERM_WORD_CHARS}]){escaped_term}(?![{_TERM_WORD_CHARS}])",
        re.IGNORECASE,
    )


def _normalize_term(raw: str) -> str:
    """Нормализовать строку термина.

    - Unicode NFKC (каноническое представление).
    - strip + lower.
    - Схлопывание внутренних пробелов.
    - Пустая строка → вернуть "".
    """
    text = unicodedata.normalize("NFKC", raw)
    text = text.strip().lower()
    text = _MULTISPACE_RE.sub(" ", text)
    return text


# Максимальная длина текста сообщений в одном батче для LLM.
_MAX_BATCH_TEXT_LENGTH = 12000

# Промпт для извлечения терминов из батча сообщений.
TERM_EXTRACTION_PROMPT = """Ты — эксперт по технической поддержке оборудования для полевых инженеров.

Проанализируй переписку из чата технической поддержки и найди доменные сокращения и термины.
Примеры: ккт, офд, фн, усн, pos, nfc, sim, гз, чз.

ПРАВИЛА:
- Термины записывай в нижнем регистре.
- Не включай общеупотребительные слова (да, нет, ок, привет, спасибо).
- Не включай имена людей, города, даты.
- Включай только устоявшиеся сокращения, а не случайные слова.
- Если из контекста понятна расшифровка сокращения — укажи её в definition.
- Если расшифровка НЕ ясна из контекста — укажи definition: null.
- confidence — уверенность, что это устоявшийся технический термин (0.0–1.0).
- Не дублируй термины.

СООБЩЕНИЯ:
{messages}

Верни JSON:
{{
    "terms": [
        {{
            "term": "сокращение в нижнем регистре",
            "definition": "расшифровка (если известна, иначе null)",
            "confidence": 0.0-1.0
        }}
    ]
}}

Если терминов не найдено — верни пустой массив terms."""


class TermMiner:
    """
    Майнер терминов и аббревиатур из сообщений групп.

    Сканирует сообщения через LLM и сохраняет найденные термины
    в gk_terms со статусом 'pending'.
    """

    def __init__(self, model_name: Optional[str] = None):
        """
        Инициализация майнера.

        Args:
            model_name: Модель LLM для анализа (по умолчанию из настроек).
        """
        self._model_name = model_name or ai_settings.GK_TERMS_SCAN_MODEL
        self._batch_size = ai_settings.GK_TERMS_SCAN_BATCH_SIZE

    async def scan_group_messages(
        self,
        group_id: int,
        date_from: str,
        date_to: str,
        *,
        progress_callback: Optional[Any] = None,
        scan_batch_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Сканировать сообщения группы за период и извлечь термины.

        Args:
            group_id: ID группы Telegram.
            date_from: Начальная дата (YYYY-MM-DD).
            date_to: Конечная дата (YYYY-MM-DD).
            progress_callback: Опциональный callback для обновления прогресса.
            scan_batch_id: Внешний UUID батча (если не указан — генерируется).

        Returns:
            Словарь с результатами сканирования:
            - scan_batch_id: UUID батча
            - total_messages: число отсканированных сообщений
            - terms_found: число найденных терминов (после дедупликации)
            - terms_new: число вставленных новых терминов
            - terms_updated: число обновлённых существующих терминов
            - terms_skipped: число пропущенных (ранее рассмотренных) терминов
            - errors: список ошибок
        """
        if not scan_batch_id:
            scan_batch_id = str(uuid.uuid4())
        result: Dict[str, Any] = {
            "scan_batch_id": scan_batch_id,
            "group_id": group_id,
            "date_from": date_from,
            "date_to": date_to,
            "total_messages": 0,
            "total_batches": 0,
            "batches_processed": 0,
            "terms_found": 0,
            "terms_new": 0,
            "terms_updated": 0,
            "terms_skipped": 0,
            "errors": [],
            "status": "running",
            "progress": {
                "stage": "started",
                "message": "Сканирование запущено",
                "percent": 0,
                "updated_at": datetime.utcnow().isoformat(),
            },
            "progress_log": [],
        }

        async def _emit_progress(
            stage: str,
            message: str,
            percent: float,
            **extra: Any,
        ) -> None:
            """Обновить прогресс и уведомить callback о текущем этапе."""
            event: Dict[str, Any] = {
                "stage": stage,
                "message": message,
                "percent": max(0.0, min(100.0, float(percent))),
                "updated_at": datetime.utcnow().isoformat(),
            }
            event.update(extra)

            result["progress"] = event
            progress_log = result.get("progress_log") or []
            progress_log.append(event)
            if len(progress_log) > 200:
                progress_log = progress_log[-200:]
            result["progress_log"] = progress_log

            if progress_callback:
                try:
                    callback_result = progress_callback(event)
                    if asyncio.iscoroutine(callback_result):
                        await callback_result
                except Exception as callback_exc:
                    logger.warning(
                        "Ошибка progress_callback при сканировании терминов: %s",
                        callback_exc,
                    )

        logger.info(
            "Начато сканирование терминов: group=%d dates=%s..%s batch_id=%s",
            group_id, date_from, date_to, scan_batch_id,
        )
        await _emit_progress(
            "loading_dates",
            "Загрузка дат с сообщениями",
            5,
            group_id=group_id,
            scan_batch_id=scan_batch_id,
        )

        # Получить все даты с сообщениями в диапазоне.
        all_dates = gk_db.get_message_dates(group_id)
        target_dates = [d for d in all_dates if date_from <= d <= date_to]

        if not target_dates:
            logger.info(
                "Нет сообщений для сканирования: group=%d dates=%s..%s",
                group_id, date_from, date_to,
            )
            result["status"] = "completed"
            await _emit_progress(
                "completed",
                "Нет сообщений в выбранном диапазоне",
                100,
                total_messages=0,
                total_batches=0,
            )
            return result

        # Собрать сообщения из целевых дат поэтапно (экономия памяти):
        # загружаем по одному дню, собираем общее число,
        # формируем батчи постепенно.
        all_messages: List[Any] = []
        await _emit_progress(
            "loading_messages",
            "Загрузка сообщений из БД",
            10,
            target_dates=len(target_dates),
        )
        for date_str in target_dates:
            day_messages = gk_db.get_messages_for_date(group_id, date_str)
            all_messages.extend(day_messages)

        result["total_messages"] = len(all_messages)

        if not all_messages:
            result["status"] = "completed"
            await _emit_progress(
                "completed",
                "Сообщения не найдены",
                100,
                total_messages=0,
                total_batches=0,
            )
            return result

        # Разбить на батчи.
        batches = self._create_message_batches(all_messages)
        result["total_batches"] = len(batches)
        await _emit_progress(
            "batching",
            "Сообщения разбиты на батчи",
            15,
            total_messages=len(all_messages),
            total_batches=len(batches),
        )

        logger.info(
            "Сканирование терминов: messages=%d batches=%d group=%d",
            len(all_messages), len(batches), group_id,
        )

        all_terms: List[Dict[str, Any]] = []

        for batch_idx, batch in enumerate(batches):
            try:
                batch_terms = await self._extract_terms_from_batch(batch, group_id)
                all_terms.extend(batch_terms)
                result["batches_processed"] = batch_idx + 1
                progress_share = (batch_idx + 1) / max(1, len(batches))
                await _emit_progress(
                    "processing_batches",
                    f"Обработан батч {batch_idx + 1}/{len(batches)}",
                    15 + progress_share * 70,
                    batches_processed=batch_idx + 1,
                    total_batches=len(batches),
                    batch_terms_found=len(batch_terms),
                    terms_found_so_far=len(all_terms),
                )
            except Exception as exc:
                error_msg = f"Ошибка батча {batch_idx + 1}/{len(batches)}: {exc}"
                result["errors"].append(error_msg)
                logger.warning(error_msg, exc_info=True)
                await _emit_progress(
                    "processing_batches",
                    error_msg,
                    15 + ((batch_idx + 1) / max(1, len(batches))) * 70,
                    batches_processed=batch_idx + 1,
                    total_batches=len(batches),
                    errors_count=len(result["errors"]),
                )

            # Пауза между LLM-запросами.
            await asyncio.sleep(0.5)

        # Дедупликация найденных терминов.
        deduplicated = self._deduplicate_terms(all_terms)
        result["terms_found"] = len(deduplicated)
        await _emit_progress(
            "deduplicating",
            "Дедупликация найденных терминов",
            90,
            terms_found=result["terms_found"],
        )

        # Сохранение в БД.
        terms_to_store = []
        for term_data in deduplicated:
            terms_to_store.append({
                "group_id": group_id,
                "term": term_data["term"],
                "definition": term_data.get("definition"),
                "source": "llm_discovered",
                "status": "pending",
                "confidence": term_data.get("confidence"),
                "llm_model_used": self._model_name,
                "scan_batch_id": scan_batch_id,
            })

        store_result = gk_db.store_terms_batch(terms_to_store)
        result["terms_new"] = store_result["inserted"]
        result["terms_updated"] = store_result["updated"]
        result["terms_skipped"] = store_result["skipped"]
        result["status"] = "completed"
        await _emit_progress(
            "completed",
            "Сканирование завершено",
            100,
            terms_found=result["terms_found"],
            terms_new=result["terms_new"],
            terms_updated=result["terms_updated"],
            terms_skipped=result["terms_skipped"],
            batches_processed=result["batches_processed"],
            total_batches=result["total_batches"],
            errors_count=len(result["errors"]),
        )

        logger.info(
            "Сканирование терминов завершено: group=%d batch_id=%s "
            "messages=%d terms_found=%d new=%d updated=%d skipped=%d errors=%d",
            group_id, scan_batch_id,
            result["total_messages"], result["terms_found"],
            result["terms_new"], result["terms_updated"],
            result["terms_skipped"], len(result["errors"]),
        )

        return result

    def _create_message_batches(
        self,
        messages: list,
    ) -> List[List[Any]]:
        """Разбить сообщения на батчи для LLM-обработки."""
        batches: List[List[Any]] = []
        current_batch: List[Any] = []
        current_length = 0

        for msg in messages:
            text = msg.full_text.strip()
            if not text:
                continue

            msg_len = len(text)

            if current_batch and (
                len(current_batch) >= self._batch_size
                or current_length + msg_len > _MAX_BATCH_TEXT_LENGTH
            ):
                batches.append(current_batch)
                current_batch = []
                current_length = 0

            current_batch.append(msg)
            current_length += msg_len

        if current_batch:
            batches.append(current_batch)

        return batches

    async def _extract_terms_from_batch(
        self,
        messages: list,
        group_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Извлечь термины из одного батча сообщений через LLM.

        Args:
            messages: Список GroupMessage.
            group_id: ID группы.

        Returns:
            Список словарей с найденными терминами.
        """
        # Форматирование сообщений для промпта.
        formatted_lines = []
        for msg in messages:
            text = msg.full_text.strip()
            if not text:
                continue
            sender = msg.sender_name or f"user_{msg.sender_id}"
            formatted_lines.append(f"[{msg.telegram_message_id}] {sender}: {text}")

        if not formatted_lines:
            return []

        messages_text = "\n".join(formatted_lines)
        if len(messages_text) > _MAX_BATCH_TEXT_LENGTH:
            messages_text = messages_text[:_MAX_BATCH_TEXT_LENGTH]

        prompt = TERM_EXTRACTION_PROMPT.format(messages=messages_text)
        system_prompt = "Ты — помощник для анализа терминологии технической поддержки."

        try:
            provider = get_provider("deepseek")
            raw = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
                purpose="gk_term_mining",
                model_override=self._model_name,
                response_format={"type": "json_object"},
            )

            return self._parse_term_response(raw)

        except Exception as exc:
            logger.warning(
                "Ошибка извлечения терминов из батча (group=%d): %s",
                group_id, exc,
            )
            return []

    @staticmethod
    def _parse_term_response(raw: str) -> List[Dict[str, Any]]:
        """Распарсить JSON-ответ LLM с терминами."""
        if not raw or not raw.strip():
            return []

        text = raw.strip()
        # Извлечь JSON из code fence (даже с преамбулой LLM).
        fence_match = _JSON_CODE_FENCE_RE.search(text)
        if fence_match:
            text = fence_match.group(1).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Ошибка парсинга JSON ответа терминов: %s", exc)
            return []

        terms = parsed.get("terms", [])
        if not isinstance(terms, list):
            return []

        result = []
        for item in terms:
            if not isinstance(item, dict):
                continue

            term = _normalize_term(item.get("term") or "")
            if not term or len(term) > 100:
                continue

            definition = item.get("definition")
            if definition is not None:
                definition = str(definition).strip() or None

            confidence = None
            raw_conf = item.get("confidence")
            if raw_conf is not None:
                try:
                    confidence = max(0.0, min(1.0, float(raw_conf)))
                except (TypeError, ValueError):
                    pass

            result.append({
                "term": term,
                "definition": definition,
                "confidence": confidence,
            })

        return result

    @staticmethod
    def _deduplicate_terms(terms: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Дедупликация терминов по term.

        Правила:
        - Предпочитаем запись с definition перед записью без.
        - При одинаковом наличии definition — предпочитаем запись с более
          высоким confidence.
        - При замене записи всегда сохраняем definition от проигравшей
          записи, если у победителя definition отсутствует.
        """
        seen: Dict[str, Dict[str, Any]] = {}

        for item in terms:
            key = item["term"]
            existing = seen.get(key)

            if existing is None:
                seen[key] = item
                continue

            existing_conf = existing.get("confidence") or 0.0
            new_conf = item.get("confidence") or 0.0

            should_replace = False

            # Предпочитаем запись с definition.
            existing_has_def = bool(existing.get("definition"))
            new_has_def = bool(item.get("definition"))
            if new_has_def and not existing_has_def:
                should_replace = True
            elif existing_has_def and not new_has_def:
                should_replace = False
            elif new_conf > existing_conf:
                should_replace = True

            if should_replace:
                # Сохраняем definition от existing, если новая запись
                # не имеет своего.
                old_def = existing.get("definition")
                seen[key] = item
                if not item.get("definition") and old_def:
                    seen[key]["definition"] = old_def
            else:
                # Обратный случай — обогащаем existing.
                if not existing.get("definition") and item.get("definition"):
                    seen[key]["definition"] = item["definition"]

        return list(seen.values())


# ---------------------------------------------------------------------------
# Пересчёт частоты упоминания терминов в сообщениях группы
# ---------------------------------------------------------------------------


async def recount_term_usage(
    group_id: int,
    *,
    progress_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Пересчитать message_count для всех одобренных терминов с расшифровкой.

    Сканирует тексты сообщений указанной группы и считает, в скольких
    сообщениях каждый термин упоминается (case-insensitive match по
    границам токена, без ложных срабатываний на подстроки).

    Глобальные термины (group_id=0) обновляются ТОЛЬКО при явном вызове
    с group_id=0 (подсчёт по всем группам). При пересчёте для конкретной
    группы глобальные термины НЕ затрагиваются.

    Args:
        group_id: ID группы Telegram.
        progress_callback: Опциональный callback для отслеживания прогресса.

    Returns:
        Словарь с результатами: terms_counted, messages_scanned, updated.
    """
    result: Dict[str, Any] = {
        "group_id": group_id,
        "terms_counted": 0,
        "messages_scanned": 0,
        "updated": 0,
        "status": "running",
        "errors": [],
    }

    async def _emit(stage: str, message: str, percent: float) -> None:
        """Уведомить о прогрессе."""
        if not progress_callback:
            return
        event = {
            "stage": stage,
            "message": message,
            "percent": max(0.0, min(100.0, percent)),
            "updated_at": datetime.utcnow().isoformat(),
        }
        try:
            cb_result = progress_callback(event)
            if asyncio.iscoroutine(cb_result):
                await cb_result
        except Exception:
            pass

    await _emit("loading_terms", "Загрузка терминов", 5)

    # Загрузить термины для пересчёта.
    # Для group_id=0 — только глобальные; для конкретной группы — только групповые.
    if group_id == 0:
        # Глобальный пересчёт: берём только глобальные термины,
        # считаем по ВСЕМ сообщениям (всех групп).
        raw_terms = gk_db.get_terms_for_group(0, has_definition=True)
        terms = [
            t for t in raw_terms
            if t.get("group_id", 0) == 0
        ]
    else:
        # Групповой пересчёт: берём только группо-специфичные термины.
        raw_terms = gk_db.get_terms_for_group(group_id, has_definition=True)
        terms = [
            t for t in raw_terms
            if t.get("group_id", 0) == group_id
        ]

    if not terms:
        result["status"] = "completed"
        await _emit("completed", "Нет терминов для пересчёта", 100)
        return result

    # Построить lookup: term_string_lower -> list of term_ids.
    term_lookup: Dict[str, List[int]] = {}
    for t in terms:
        key = (t.get("term") or "").strip().lower()
        if key:
            term_lookup.setdefault(key, []).append(t["id"])

    term_patterns: Dict[str, re.Pattern[str]] = {
        term_str: _build_term_boundary_pattern(term_str)
        for term_str in term_lookup.keys()
    }

    # Инициализировать счётчики.
    counts: Dict[int, int] = {t["id"]: 0 for t in terms}

    result["terms_counted"] = len(terms)
    await _emit("counting", f"Подсчёт для {len(terms)} терминов", 10)

    # Определить общее количество сообщений.
    if group_id == 0:
        # Для глобальных терминов — считаем по всем группам.
        # Получаем список всех групп с сообщениями.
        all_group_ids = _get_all_group_ids_with_messages()
        total_messages = sum(
            gk_db.get_message_count_for_group(gid) for gid in all_group_ids
        )
    else:
        all_group_ids = [group_id]
        total_messages = gk_db.get_message_count_for_group(group_id)

    if total_messages == 0:
        result["status"] = "completed"
        await _emit("completed", "Нет сообщений для анализа", 100)
        return result

    batch_size = ai_settings.GK_TERMS_RECOUNT_BATCH_SIZE
    messages_processed = 0

    # Сканировать сообщения батчами.
    for scan_group_id in all_group_ids:
        offset = 0
        while True:
            rows = gk_db.get_message_texts_batch(
                scan_group_id, offset=offset, limit=batch_size,
            )
            if not rows:
                break

            for row in rows:
                # Учитываем только текст сообщения (без caption/image_description).
                message_text = row.get("message_text")
                if not message_text:
                    continue

                combined = str(message_text)

                for term_str, term_ids in term_lookup.items():
                    pattern = term_patterns.get(term_str)
                    if pattern and pattern.search(combined):
                        for tid in term_ids:
                            counts[tid] += 1

            messages_processed += len(rows)
            offset += batch_size

            # Обновить прогресс.
            pct = 10 + (messages_processed / max(1, total_messages)) * 80
            await _emit(
                "scanning",
                f"Обработано {messages_processed}/{total_messages} сообщений",
                pct,
            )

            if len(rows) < batch_size:
                break

    result["messages_scanned"] = messages_processed

    # Сохранить результаты в БД.
    await _emit("saving", "Сохранение результатов", 92)
    updated = gk_db.bulk_update_term_message_counts(counts)
    result["updated"] = updated
    result["status"] = "completed"

    logger.info(
        "Пересчёт usage терминов завершён: group=%d terms=%d messages=%d updated=%d",
        group_id, len(terms), messages_processed, updated,
    )
    await _emit(
        "completed",
        f"Пересчёт завершён: {len(terms)} терминов, {messages_processed} сообщений",
        100,
    )
    return result


def _get_all_group_ids_with_messages() -> List[int]:
    """Получить список всех group_id, имеющих сообщения в gk_messages."""
    try:
        from src.common.database import get_db_connection, get_cursor

        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT DISTINCT group_id FROM gk_messages ORDER BY group_id"
                )
                rows = cursor.fetchall() or []
                return [int(r["group_id"]) for r in rows]
    except Exception as exc:
        logger.warning("Не удалось получить список групп: %s", exc)
        return []
