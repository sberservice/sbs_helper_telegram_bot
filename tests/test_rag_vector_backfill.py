"""Тесты CLI-скрипта пакетного backfill векторных индексов RAG."""

import unittest
from unittest.mock import MagicMock, patch

from scripts import rag_vector_backfill


class TestRagVectorBackfillScript(unittest.TestCase):
    """Проверки аргументов и вызова сервиса в rag_vector_backfill.py."""

    @patch("scripts.rag_vector_backfill.RagKnowledgeService")
    @patch("scripts.rag_vector_backfill.logger.info")
    def test_main_passes_target_to_service(self, mock_logger_info, mock_service_cls):
        """CLI передаёт --target в backfill_vector_index."""
        service = MagicMock()
        service.backfill_vector_index.return_value = {
            "documents_total": 1,
            "documents_processed": 1,
            "chunks_indexed": 0,
            "summaries_indexed": 1,
            "errors": 0,
        }
        mock_service_cls.return_value = service

        with patch(
            "sys.argv",
            [
                "rag_vector_backfill.py",
                "--target",
                "summaries",
                "--batch-size",
                "50",
                "--max-documents",
                "10",
            ],
        ):
            rag_vector_backfill.main()

        service.backfill_vector_index.assert_called_once_with(
            batch_size=50,
            source_type=None,
            dry_run=False,
            max_documents=10,
            target="summaries",
        )
        self.assertTrue(any("Backfill vector index завершён" in str(call.args[0]) for call in mock_logger_info.call_args_list))

    @patch("scripts.rag_vector_backfill.logger.error")
    def test_main_rejects_non_positive_batch_size(self, mock_logger_error):
        """CLI завершает работу с ошибкой при некорректном --batch-size."""
        with patch("sys.argv", ["rag_vector_backfill.py", "--batch-size", "0"]):
            with self.assertRaises(SystemExit) as exit_ctx:
                rag_vector_backfill.main()

        self.assertEqual(exit_ctx.exception.code, 1)
        mock_logger_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
