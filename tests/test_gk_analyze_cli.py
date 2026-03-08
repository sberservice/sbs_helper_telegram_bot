"""Тесты CLI-логики scripts/gk_analyze.py."""

import argparse
import asyncio
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

    def test_resolve_analysis_targets_all_dates(self):
        """Режим --all-dates собирает все даты с сообщениями по каждой группе."""
        args = argparse.Namespace(
            all_dates=True,
            all_unprocessed=False,
            date=None,
            date_range=None,
        )

        with patch.object(
            GK_ANALYZE.gk_db,
            "get_message_dates",
            side_effect=[["2026-03-01", "2026-03-02"], ["2026-03-05"]],
        ) as mock_dates:
            targets = GK_ANALYZE._resolve_analysis_targets(args, [-1001, -1002])

        self.assertEqual(
            targets,
            [
                (-1001, "2026-03-01"),
                (-1001, "2026-03-02"),
                (-1002, "2026-03-05"),
            ],
        )
        self.assertEqual(mock_dates.call_count, 2)

    def test_resolve_analysis_targets_all_unprocessed(self):
        """Режим --all-unprocessed собирает только даты с processed=0 по каждой группе."""
        args = argparse.Namespace(
            all_dates=False,
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

    def test_run_analysis_rebuild_pairs_deletes_existing_pairs(self):
        """Режим rebuild удаляет старые пары и запускает force_reanalyze по всем датам."""
        args = argparse.Namespace(
            index=False,
            group_id=-1001,
            all_dates=True,
            all_unprocessed=False,
            date=None,
            date_range=None,
            skip_thread=False,
            skip_llm=False,
            force_reanalyze=False,
            rebuild_pairs=True,
            no_index=True,
        )

        analyzer = unittest.mock.MagicMock()
        analyzer.analyze_day = unittest.mock.AsyncMock(return_value=unittest.mock.MagicMock(
            thread_pairs_found=0,
            llm_pairs_found=0,
            errors=[],
            total_messages=10,
        ))

        async def _run():
            with patch.object(GK_ANALYZE, "QAAnalyzer", return_value=analyzer):
                with patch.object(GK_ANALYZE.gk_db, "get_message_dates", return_value=["2026-03-01"]) as mock_dates:
                    with patch.object(GK_ANALYZE.gk_db, "get_qa_pair_ids_by_group", return_value=[1, 2]) as mock_pair_ids:
                        with patch.object(GK_ANALYZE.gk_db, "delete_qa_pairs_by_group", return_value=2) as mock_delete_pairs:
                            with patch.object(GK_ANALYZE, "_cleanup_vector_points", return_value=2) as mock_cleanup:
                                await GK_ANALYZE.run_analysis(args)
            return mock_dates, mock_pair_ids, mock_delete_pairs, mock_cleanup

        mock_dates, mock_pair_ids, mock_delete_pairs, mock_cleanup = asyncio.run(_run())

        mock_dates.assert_called_once_with(-1001)
        mock_pair_ids.assert_called_once_with(-1001)
        mock_delete_pairs.assert_called_once_with(-1001)
        mock_cleanup.assert_called_once_with([1, 2])
        analyzer.analyze_day.assert_awaited_once_with(
            group_id=-1001,
            date_str="2026-03-01",
            skip_thread=False,
            skip_llm=False,
            force_reanalyze=True,
        )


if __name__ == "__main__":
    unittest.main()
