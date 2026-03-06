#!/usr/bin/env python3
"""
gk_analyze — CLI утилита запуска анализа Q&A-пар.

Анализирует собранные сообщения за указанный день или диапазон дат,
извлекает пары вопрос-ответ и индексирует их в Qdrant.

Режимы:
    python scripts/gk_analyze.py --date 2024-01-15                — один день
    python scripts/gk_analyze.py --date-range 2024-01-10 2024-01-15 — диапазон
    python scripts/gk_analyze.py --all-unprocessed                — все даты с необработанными сообщениями
    python scripts/gk_analyze.py --date 2024-01-15 --group-id -100123456
    python scripts/gk_analyze.py --index                          — проиндексировать новые пары
    python scripts/gk_analyze.py --date 2024-01-15 --force-reanalyze — переанализировать все сообщения за день
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Корень проекта для импортов
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.group_knowledge import database as gk_db
from src.group_knowledge.message_collector import load_groups_config
from src.group_knowledge.qa_analyzer import QAAnalyzer

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GK_ANALYZE] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gk_analyze")


def _resolve_group_ids(args: argparse.Namespace) -> list[int]:
    """Определить список групп для анализа на основе аргументов CLI."""
    if args.group_id:
        return [args.group_id]

    groups = load_groups_config()
    if not groups:
        logger.error(
            "Нет настроенных групп. Запустите: python scripts/gk_collector.py --manage-groups"
        )
        return []
    return [g["id"] for g in groups]


def _resolve_analysis_targets(
    args: argparse.Namespace,
    group_ids: list[int],
) -> list[tuple[int, str]]:
    """Определить пары (group_id, date_str), которые нужно проанализировать."""
    if args.all_unprocessed:
        targets: list[tuple[int, str]] = []
        for gid in group_ids:
            unprocessed_dates = gk_db.get_unprocessed_dates(gid)
            if not unprocessed_dates:
                continue
            for date_str in unprocessed_dates:
                targets.append((gid, date_str))
        return targets

    dates = []
    if args.date:
        dates = [args.date]
    elif args.date_range:
        start_date = datetime.strptime(args.date_range[0], "%Y-%m-%d")
        end_date = datetime.strptime(args.date_range[1], "%Y-%m-%d")
        current = start_date
        while current <= end_date:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
    else:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        dates = [yesterday]
        logger.info("Дата не указана, используется вчерашний день: %s", yesterday)

    return [(gid, date_str) for date_str in dates for gid in group_ids]


async def run_analysis(args: argparse.Namespace) -> None:
    """
    Запустить анализ Q&A-пар.

    Args:
        args: Аргументы командной строки.
    """
    analyzer = QAAnalyzer()

    # Режим индексации
    if args.index:
        logger.info("Запуск индексации новых Q&A-пар...")
        count = await analyzer.index_new_pairs()
        logger.info("Проиндексировано: %d пар", count)
        return

    group_ids = _resolve_group_ids(args)
    if not group_ids:
        return

    targets = _resolve_analysis_targets(args, group_ids)
    if not targets:
        logger.info("Нет необработанных сообщений для анализа по выбранным параметрам.")
        return

    logger.info(
        "Анализ: целей=%d группы=%s force_reanalyze=%s all_unprocessed=%s",
        len(targets),
        sorted(set(group_ids)),
        args.force_reanalyze,
        args.all_unprocessed,
    )

    # Статистика
    total_thread = 0
    total_llm = 0
    total_errors = 0

    for gid, date_str in targets:
        logger.info("=" * 60)
        logger.info("Анализ: group=%d date=%s", gid, date_str)

        result = await analyzer.analyze_day(
            group_id=gid,
            date_str=date_str,
            skip_thread=args.skip_thread,
            skip_llm=args.skip_llm,
            force_reanalyze=args.force_reanalyze,
        )

        total_thread += result.thread_pairs_found
        total_llm += result.llm_pairs_found
        total_errors += len(result.errors)

        logger.info(
            "Результат: messages=%d thread=%d llm=%d errors=%d",
            result.total_messages,
            result.thread_pairs_found,
            result.llm_pairs_found,
            len(result.errors),
        )

        for err in result.errors:
            logger.warning("  Ошибка: %s", err)

    logger.info("=" * 60)
    logger.info(
        "ИТОГО: thread=%d llm=%d ошибок=%d",
        total_thread, total_llm, total_errors,
    )

    # Автоматическая индексация если есть новые пары
    if not args.no_index and (total_thread + total_llm) > 0:
        logger.info("Автоматическая индексация новых пар...")
        indexed = await analyzer.index_new_pairs()
        logger.info("Проиндексировано: %d пар", indexed)


def main() -> None:
    """Точка входа."""
    parser = argparse.ArgumentParser(
        description="GK Analyze — анализ и извлечение Q&A-пар",
        allow_abbrev=False,
    )
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        "--date",
        type=str,
        help="Дата для анализа в формате YYYY-MM-DD",
    )
    date_group.add_argument(
        "--date-range",
        type=str,
        nargs=2,
        metavar=("START", "END"),
        help="Диапазон дат: START END (формат YYYY-MM-DD)",
    )
    date_group.add_argument(
        "--all-unprocessed",
        action="store_true",
        help="Проанализировать все даты, где есть сообщения processed=0",
    )
    parser.add_argument(
        "--group-id",
        type=int,
        help="ID конкретной группы для анализа",
    )
    parser.add_argument(
        "--index",
        action="store_true",
        help="Только проиндексировать новые Q&A-пары в Qdrant",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Не индексировать пары автоматически после анализа",
    )
    parser.add_argument(
        "--skip-thread",
        action="store_true",
        help="Пропустить thread-based извлечение",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Пропустить LLM-inferred извлечение",
    )
    parser.add_argument(
        "--force-reanalyze",
        action="store_true",
        help="Принудительно переанализировать все сообщения за дату, включая уже processed",
    )
    args = parser.parse_args()

    if args.all_unprocessed and args.force_reanalyze:
        parser.error("--all-unprocessed нельзя использовать вместе с --force-reanalyze")

    asyncio.run(run_analysis(args))


if __name__ == "__main__":
    main()
