"""Стратифицированная выборка документов для тестирования промптов.

Выбирает случайные документы из rag_documents, обеспечивая покрытие
разных размеров (малые, средние, крупные) для репрезентативного теста.
"""

from __future__ import annotations

import logging
import random
from typing import Dict, List

from src.common import database

logger = logging.getLogger(__name__)

# Границы бакетов по количеству чанков
_SMALL_MAX_CHUNKS = 3
_MEDIUM_MAX_CHUNKS = 10

_BUCKET_SMALL = "small"
_BUCKET_MEDIUM = "medium"
_BUCKET_LARGE = "large"


def sample_documents(count: int) -> List[int]:
    """Выбрать стратифицированную выборку документов.

    Документы разбиваются на три бакета по размеру (кол-во чанков):
    - small: 1–3 чанка
    - medium: 4–10 чанков
    - large: 11+ чанков

    Из каждого бакета выбирается пропорциональная доля.
    Если в бакете недостаточно документов — добирается из других.

    Args:
        count: Желаемое количество документов.

    Returns:
        Список document_id.
    """
    safe_count = max(2, min(count, 100))

    # Загружаем все активные не-certification документы с подсчётом чанков
    query = """
        SELECT d.id, COUNT(c.id) AS chunks_count
        FROM rag_documents d
        LEFT JOIN rag_chunks c ON c.document_id = d.id
        WHERE d.status = 'active' AND d.source_type != 'certification'
        GROUP BY d.id
        HAVING chunks_count > 0
        ORDER BY d.id
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query)
            rows = cursor.fetchall() or []

    if not rows:
        logger.warning("Нет активных документов для выборки")
        return []

    total_available = len(rows)
    if total_available <= safe_count:
        logger.info(
            "Доступно документов (%d) <= запрошено (%d), возвращаем все",
            total_available, safe_count,
        )
        return [r["id"] for r in rows]

    # Распределяем по бакетам
    buckets: Dict[str, List[int]] = {
        _BUCKET_SMALL: [],
        _BUCKET_MEDIUM: [],
        _BUCKET_LARGE: [],
    }
    for row in rows:
        cc = row["chunks_count"]
        if cc <= _SMALL_MAX_CHUNKS:
            buckets[_BUCKET_SMALL].append(row["id"])
        elif cc <= _MEDIUM_MAX_CHUNKS:
            buckets[_BUCKET_MEDIUM].append(row["id"])
        else:
            buckets[_BUCKET_LARGE].append(row["id"])

    # Перемешиваем каждый бакет
    for bucket in buckets.values():
        random.shuffle(bucket)

    # Пропорциональное распределение
    result: List[int] = []
    remaining = safe_count

    bucket_names = [_BUCKET_SMALL, _BUCKET_MEDIUM, _BUCKET_LARGE]
    proportions = {name: len(buckets[name]) / total_available for name in bucket_names}

    for name in bucket_names:
        target = max(1, round(proportions[name] * safe_count)) if buckets[name] else 0
        take = min(target, len(buckets[name]), remaining)
        result.extend(buckets[name][:take])
        buckets[name] = buckets[name][take:]
        remaining -= take

    # Добираем оставшееся из всех бакетов
    if remaining > 0:
        pool = []
        for name in bucket_names:
            pool.extend(buckets[name])
        random.shuffle(pool)
        result.extend(pool[:remaining])

    random.shuffle(result)
    logger.info(
        "Выборка документов: запрошено=%d выбрано=%d (из %d доступных)",
        safe_count, len(result), total_available,
    )
    return result[:safe_count]
