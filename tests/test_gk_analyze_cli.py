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
            all_unprocessed_except_today=False,
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
            all_unprocessed_except_today=False,
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

    def test_resolve_analysis_targets_all_unprocessed_except_today(self):
        """Режим --all-unprocessed-except-today исключает текущую дату из целей."""
        args = argparse.Namespace(
            all_dates=False,
            all_unprocessed=False,
            all_unprocessed_except_today=True,
            date=None,
            date_range=None,
        )

        with patch.object(
            GK_ANALYZE.gk_db,
            "get_unprocessed_dates",
            side_effect=[["2026-03-09", "2026-03-10"], ["2026-03-10", "2026-03-08"]],
        ) as mock_dates:
            with patch.object(GK_ANALYZE, "datetime") as mock_datetime:
                mock_now = unittest.mock.MagicMock()
                mock_now.strftime.return_value = "2026-03-10"
                mock_datetime.now.return_value = mock_now

                targets = GK_ANALYZE._resolve_analysis_targets(args, [-1001, -1002])

        self.assertEqual(targets, [(-1001, "2026-03-09"), (-1002, "2026-03-08")])
        self.assertEqual(mock_dates.call_count, 2)

    def test_resolve_analysis_targets_rebuild_pairs_excludes_today(self):
        """Режим --all-dates --rebuild-pairs исключает текущую дату из целей."""
        args = argparse.Namespace(
            all_dates=True,
            all_unprocessed=False,
            all_unprocessed_except_today=False,
            date=None,
            date_range=None,
            rebuild_pairs=True,
        )

        with patch.object(
            GK_ANALYZE.gk_db,
            "get_message_dates",
            side_effect=[["2026-03-09", "2026-03-10"], ["2026-03-10", "2026-03-08"]],
        ) as mock_dates:
            with patch.object(GK_ANALYZE, "datetime") as mock_datetime:
                mock_now = unittest.mock.MagicMock()
                mock_now.strftime.return_value = "2026-03-10"
                mock_datetime.now.return_value = mock_now

                targets = GK_ANALYZE._resolve_analysis_targets(args, [-1001, -1002])

        self.assertEqual(targets, [(-1001, "2026-03-09"), (-1002, "2026-03-08")])
        self.assertEqual(mock_dates.call_count, 2)

    def test_run_analysis_rebuild_pairs_deletes_existing_pairs(self):
        """Режим rebuild удаляет старые пары и запускает force_reanalyze по всем датам."""
        args = argparse.Namespace(
            index=False,
            rebuild_vector_index=False,
            group_id=-1001,
            all_dates=True,
            all_unprocessed=False,
            all_unprocessed_except_today=False,
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
                            with patch.object(GK_ANALYZE.gk_db, "get_qa_pairs_count", return_value=0) as mock_count_pairs:
                                with patch.object(GK_ANALYZE, "_cleanup_vector_points", return_value=2) as mock_cleanup:
                                    await GK_ANALYZE.run_analysis(args)
            return mock_dates, mock_pair_ids, mock_delete_pairs, mock_cleanup, mock_count_pairs

        mock_dates, mock_pair_ids, mock_delete_pairs, mock_cleanup, mock_count_pairs = asyncio.run(_run())

        mock_dates.assert_called_once_with(-1001)
        mock_pair_ids.assert_called_once_with(-1001)
        mock_delete_pairs.assert_called_once_with(-1001)
        mock_cleanup.assert_called_once_with([1, 2])
        mock_count_pairs.assert_called_once_with(group_id=-1001, date_str="2026-03-01")
        analyzer.analyze_day.assert_awaited_once_with(
            group_id=-1001,
            date_str="2026-03-01",
            skip_thread=False,
            skip_llm=False,
            force_reanalyze=True,
        )

    def test_run_analysis_all_dates_force_reanalyze_cleans_expert_validations(self):
        """Режим --all-dates --force-reanalyze очищает expert validations по выбранным группам."""
        args = argparse.Namespace(
            index=False,
            rebuild_vector_index=False,
            group_id=-1001,
            all_dates=True,
            all_unprocessed=False,
            all_unprocessed_except_today=False,
            date=None,
            date_range=None,
            skip_thread=False,
            skip_llm=False,
            force_reanalyze=True,
            rebuild_pairs=False,
            no_index=True,
        )

        analyzer = unittest.mock.MagicMock()
        analyzer.analyze_day = unittest.mock.AsyncMock(return_value=unittest.mock.MagicMock(
            thread_pairs_found=0,
            llm_pairs_found=0,
            errors=[],
            total_messages=7,
        ))

        async def _run():
            with patch.object(GK_ANALYZE, "QAAnalyzer", return_value=analyzer):
                with patch.object(GK_ANALYZE.gk_db, "get_message_dates", return_value=["2026-03-01"]) as mock_dates:
                    with patch.object(GK_ANALYZE.gk_db, "delete_expert_validations_by_group", return_value=3) as mock_cleanup_validations:
                        with patch.object(GK_ANALYZE.gk_db, "get_qa_pairs_count", return_value=0):
                            await GK_ANALYZE.run_analysis(args)
            return mock_dates, mock_cleanup_validations

        mock_dates, mock_cleanup_validations = asyncio.run(_run())

        mock_dates.assert_called_once_with(-1001)
        mock_cleanup_validations.assert_called_once_with(-1001)
        analyzer.analyze_day.assert_awaited_once_with(
            group_id=-1001,
            date_str="2026-03-01",
            skip_thread=False,
            skip_llm=False,
            force_reanalyze=True,
        )

    def test_run_analysis_rebuild_vector_index_reindexes_all_approved_pairs(self):
        """Режим --rebuild-vector-index очищает QA-векторы и запускает повторную индексацию."""
        args = argparse.Namespace(
            rebuild_vector_index=True,
            index=False,
            group_id=None,
            all_dates=False,
            all_unprocessed=False,
            all_unprocessed_except_today=False,
            date=None,
            date_range=None,
            skip_thread=False,
            skip_llm=False,
            force_reanalyze=False,
            rebuild_pairs=False,
            no_index=False,
        )

        analyzer = unittest.mock.MagicMock()
        analyzer.index_new_pairs = unittest.mock.AsyncMock(return_value=2)
        pair_1 = argparse.Namespace(id=101)
        pair_2 = argparse.Namespace(id=202)
        pair_duplicate = argparse.Namespace(id=202)

        async def _run():
            with patch.object(GK_ANALYZE, "QAAnalyzer", return_value=analyzer):
                with patch.object(
                    GK_ANALYZE.gk_db,
                    "get_all_approved_qa_pairs",
                    return_value=[pair_1, pair_2, pair_duplicate],
                ):
                    with patch.object(GK_ANALYZE, "_cleanup_vector_points", return_value=2) as mock_cleanup:
                        with patch.object(
                            GK_ANALYZE.gk_db,
                            "reset_qa_pairs_vector_indexed",
                            return_value=2,
                        ) as mock_reset:
                            await GK_ANALYZE.run_analysis(args)
            return mock_cleanup, mock_reset

        mock_cleanup, mock_reset = asyncio.run(_run())

        mock_cleanup.assert_called_once_with([101, 202])
        mock_reset.assert_called_once_with(approved_only=True)
        analyzer.index_new_pairs.assert_awaited_once_with()
        analyzer.analyze_day.assert_not_called()


if __name__ == "__main__":
    unittest.main()
