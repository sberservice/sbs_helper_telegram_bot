"""Утилиты для отбора, дедупликации и ранжирования аббревиатур Group Knowledge."""

from typing import Any, Dict, Iterable


def _to_float(value: Any) -> float:
    """Преобразовать значение к float с безопасным fallback."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    """Преобразовать значение к int с безопасным fallback."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def select_best_acronyms_by_term(
    records: Iterable[Dict[str, Any]],
    *,
    uppercase_key: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """Выбрать по одной лучшей записи на каждую аббревиатуру.

    Приоритет выбора записи:
    1) group-specific (group_id != 0) важнее глобальной (group_id == 0);
    2) выше confidence;
    3) больше id.
    """
    best_by_term: Dict[str, Dict[str, Any]] = {}

    for record in records:
        term = str(record.get("term") or "").strip()
        if not term:
            continue

        dedup_key = term.upper() if uppercase_key else term
        existing = best_by_term.get(dedup_key)
        if existing is None:
            best_by_term[dedup_key] = record
            continue

        existing_group_id = int(existing.get("group_id") or 0)
        current_group_id = int(record.get("group_id") or 0)
        existing_confidence = _to_float(existing.get("confidence"))
        current_confidence = _to_float(record.get("confidence"))

        should_replace = False
        if existing_group_id == 0 and current_group_id != 0:
            should_replace = True
        elif existing_group_id != 0 and current_group_id == 0:
            should_replace = False
        elif current_confidence > existing_confidence:
            should_replace = True
        elif current_confidence == existing_confidence:
            should_replace = int(record.get("id") or 0) > int(existing.get("id") or 0)

        if should_replace:
            best_by_term[dedup_key] = record

    return best_by_term


def sort_acronym_records_for_prompt(records: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Отсортировать записи для секции промпта по приоритету использования.

    Порядок:
    1) message_count по убыванию;
    2) term по алфавиту (детерминизм при равных message_count).
    """
    return sorted(
        list(records),
        key=lambda record: (
            -_to_int(record.get("message_count")),
            str(record.get("term") or "").strip().upper(),
        ),
    )
