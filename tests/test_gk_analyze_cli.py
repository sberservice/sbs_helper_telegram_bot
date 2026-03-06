"""Тесты CLI-логики scripts/gk_analyze.py."""

import argparse
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "gk_analyze.py"
SPEC = importlib.util.spec_from_file_location("gk_analyze_module_for_tests", SCRIPT_PATH)
GK_ANALYZE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(GK_ANALYZE)


class TestGKAnalyzeCliHelpers(unittest.TestCase):
    """Тесты helper-функций выбора целей анализа."""

    def test_resolve_analysis_targets_all_unprocessed(self):
        """Режим --all-unprocessed собирает только даты с processed=0 по каждой группе."""
        args = argparse.Namespace(
            all_unprocessed=True,
            date=None,
            date_range=None,
        )

        with patch.object(
            GK_ANALYZE.gk_db,
            "get_unprocessed_dates",
            side_effect=[["2026-03-05", "2026-03-06"], []],
        ) as mock_dates:
            targets = GK_ANALYZE._resolve_analysis_targets(args, [-1001, -1002])

        self.assertEqual(targets, [(-1001, "2026-03-05"), (-1001, "2026-03-06")])
        self.assertEqual(mock_dates.call_count, 2)

    def test_resolve_group_ids_from_config(self):
        """Без --group-id берёт группы из конфига."""
        args = argparse.Namespace(group_id=None)

        with patch.object(
            GK_ANALYZE,
            "load_groups_config",
            return_value=[{"id": -1001}, {"id": -1002}],
        ):
            group_ids = GK_ANALYZE._resolve_group_ids(args)

        self.assertEqual(group_ids, [-1001, -1002])


if __name__ == "__main__":
    unittest.main()
