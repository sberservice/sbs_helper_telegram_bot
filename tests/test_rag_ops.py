"""Тесты CLI-утилиты scripts/rag_ops.py."""

import argparse
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import rag_ops


class _FakeCursor:
    """Фейковый курсор БД для unit-тестов."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _query):
        return None

    def fetchone(self):
        return {"cnt": 1}


class _FakeConnection:
    """Фейковое соединение БД для unit-тестов."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestRagOpsScript(unittest.TestCase):
    """Проверки критичных сценариев rag_ops после регрессионных фиксов."""

    def test_cmd_setup_no_longer_requires_config_settings_mysql_attrs(self):
        """setup не падает, даже если в config.settings нет MYSQL_* атрибутов."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            (project_root / ".env").write_text("DEBUG=0\n", encoding="utf-8")
            (project_root / "sql").mkdir(parents=True, exist_ok=True)
            (project_root / "sql" / "ai_rag_setup.sql").write_text("SELECT 1;\n", encoding="utf-8")

            fake_config_module = types.ModuleType("config")
            fake_settings_module = types.ModuleType("config.settings")
            setattr(fake_config_module, "settings", fake_settings_module)

            with patch.dict(
                sys.modules,
                {
                    "config": fake_config_module,
                    "config.settings": fake_settings_module,
                },
            ), patch.object(rag_ops, "_PROJECT_ROOT", project_root), patch.object(
                rag_ops,
                "_RAG_SQL_FILES",
                ["sql/ai_rag_setup.sql"],
            ), patch.object(rag_ops, "_header"), patch.object(rag_ops, "_step"), patch.object(
                rag_ops, "_info"
            ), patch.object(rag_ops, "_ok"), patch.object(rag_ops, "_warn"), patch.object(
                rag_ops, "_err"
            ):
                rc = rag_ops.cmd_setup(argparse.Namespace(apply_sql=False, yes=True))

        self.assertEqual(rc, 0)

    @patch("src.sbs_helper_telegram_bot.ai_router.vector_search.LocalVectorIndex")
    @patch("src.common.database.get_cursor")
    @patch("src.common.database.get_db_connection")
    def test_cmd_health_checks_vector_index_via_local_vector_index(
        self,
        mock_get_db_connection,
        mock_get_cursor,
        mock_local_vector_index,
    ):
        """health использует актуальный LocalVectorIndex для проверки векторного слоя."""
        mock_get_db_connection.return_value = _FakeConnection()
        mock_get_cursor.return_value = _FakeCursor()

        index_instance = MagicMock()
        index_instance.is_ready.return_value = True
        mock_local_vector_index.return_value = index_instance

        with patch.object(rag_ops, "_header"), patch.object(rag_ops, "_step"), patch.object(
            rag_ops, "_ok"
        ) as mock_ok, patch.object(rag_ops, "_warn"), patch.object(rag_ops, "_err"):
            rc = rag_ops.cmd_health(argparse.Namespace())

        self.assertEqual(rc, 0)
        self.assertTrue(any("Qdrant подключён" in call.args[0] for call in mock_ok.call_args_list))
        mock_local_vector_index.assert_called_once()


if __name__ == "__main__":
    unittest.main()
