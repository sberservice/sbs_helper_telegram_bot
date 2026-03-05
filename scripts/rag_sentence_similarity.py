#!/usr/bin/env python3
"""CLI-утилита для сравнения похожести двух предложений в RAG-тестах.

Поддерживает два режима:
  - Одноразовый (legacy): python rag_sentence_similarity.py --sentence-a ... --sentence-b ...
  - Интерактивный REPL:   python rag_sentence_similarity.py --interactive
                           python rag_sentence_similarity.py -i
"""

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _run() -> int:
    """Определить режим запуска и делегировать в нужный модуль."""
    # Если передан флаг --interactive / -i — запустить REPL,
    # иначе — обычный одноразовый CLI.
    interactive = "--interactive" in sys.argv or "-i" in sys.argv
    if interactive:
        # Убрать флаг из argv, чтобы argparse внутри REPL не споткнулся
        filtered_argv = [
            arg for arg in sys.argv[1:]
            if arg not in ("--interactive", "-i")
        ]
        from src.sbs_helper_telegram_bot.ai_router.rag_similarity_interactive import (
            main as interactive_main,
        )
        return interactive_main(filtered_argv)

    from src.sbs_helper_telegram_bot.ai_router.rag_similarity import main
    return main()


if __name__ == "__main__":
    raise SystemExit(_run())
