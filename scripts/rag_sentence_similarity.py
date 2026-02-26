#!/usr/bin/env python3
"""CLI-утилита для сравнения похожести двух предложений в RAG-тестах."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def _bootstrap_project_root() -> None:
    """Добавить корень проекта в sys.path для прямого запуска скрипта."""
    project_root = Path(__file__).resolve().parents[1]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


_bootstrap_project_root()

from src.sbs_helper_telegram_bot.ai_router.rag_similarity import main


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


if __name__ == "__main__":
    raise SystemExit(main())
