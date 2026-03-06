"""Тесты CLI-утилиты scripts/gk_delete_group_data.py."""

import argparse
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "gk_delete_group_data.py"
SPEC = importlib.util.spec_from_file_location("gk_delete_group_data_module_for_tests", SCRIPT_PATH)
GK_DELETE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(GK_DELETE)


class TestGKDeleteGroupDataCli(unittest.TestCase):
    """Тесты helper-функций удаления данных группы."""

    def test_cleanup_vector_points_calls_delete_for_each_pair(self):
        """Удаление векторов вызывается для каждого pair_id."""
        mock_index = MagicMock()
        mock_index.delete_document_points.side_effect = [1, 1, 0]

        with patch.object(GK_DELETE, "LocalVectorIndex", return_value=mock_index):
            deleted = GK_DELETE._cleanup_vector_points([10, 11, 12])

        self.assertEqual(deleted, 2)
        self.assertEqual(mock_index.delete_document_points.call_count, 3)

    def test_dry_run_without_yes_does_not_delete(self):
        """Без --yes утилита делает только dry-run статистику."""
        args = argparse.Namespace(group_id=-1001, interactive=False, yes=False, no_vector_cleanup=False)

        with patch.object(GK_DELETE.argparse.ArgumentParser, "parse_args", return_value=args):
            with patch.object(
                GK_DELETE.gk_db,
                "delete_group_data",
                return_value={
                    "group_id": -1001,
                    "messages_found": 1,
                    "qa_pairs_found": 2,
                    "responder_logs_found": 0,
                    "image_queue_found": 0,
                },
            ) as mock_delete:
                with patch.object(GK_DELETE.gk_db, "get_qa_pair_ids_by_group") as mock_get_pairs:
                    GK_DELETE.main()

        mock_delete.assert_called_once_with(-1001, dry_run=True)
        mock_get_pairs.assert_not_called()

    def test_select_group_interactively_returns_selected_group(self):
        """Интерактивное меню возвращает выбранный group_id."""
        groups = [
            {"group_id": -1001, "group_title": "Group 1", "message_count": 10},
            {"group_id": -1002, "group_title": "Group 2", "message_count": 20},
        ]

        with patch.object(GK_DELETE.gk_db, "get_collected_groups", return_value=groups):
            with patch("builtins.input", return_value="2"):
                selected = GK_DELETE._select_group_interactively()

        self.assertEqual(selected, -1002)

    def test_main_interactive_mode_deletes_after_yes_confirmation(self):
        """В интерактивном режиме удаление выполняется после подтверждения yes."""
        args = argparse.Namespace(group_id=None, interactive=True, yes=False, no_vector_cleanup=False)

        with patch.object(GK_DELETE.argparse.ArgumentParser, "parse_args", return_value=args):
            with patch.object(GK_DELETE, "_select_group_interactively", return_value=-1005):
                with patch.object(GK_DELETE, "_confirm_interactively", return_value=True):
                    with patch.object(
                        GK_DELETE.gk_db,
                        "delete_group_data",
                        side_effect=[
                            {
                                "group_id": -1005,
                                "messages_found": 3,
                                "qa_pairs_found": 2,
                                "responder_logs_found": 1,
                                "image_queue_found": 1,
                            },
                            {
                                "group_id": -1005,
                                "messages_deleted": 3,
                                "qa_pairs_deleted": 2,
                                "responder_logs_deleted": 1,
                                "image_queue_deleted": 1,
                            },
                        ],
                    ) as mock_delete:
                        with patch.object(GK_DELETE.gk_db, "get_qa_pair_ids_by_group", return_value=[21, 22]) as mock_pairs:
                            with patch.object(GK_DELETE, "_cleanup_vector_points", return_value=2) as mock_cleanup:
                                GK_DELETE.main()

        self.assertEqual(mock_delete.call_count, 2)
        mock_delete.assert_any_call(-1005, dry_run=True)
        mock_delete.assert_any_call(-1005, dry_run=False)
        mock_pairs.assert_called_once_with(-1005)
        mock_cleanup.assert_called_once_with([21, 22])


if __name__ == "__main__":
    unittest.main()
