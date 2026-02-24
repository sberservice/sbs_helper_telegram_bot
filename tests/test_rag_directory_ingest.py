"""Тесты скрипта синхронизации директории документов с RAG."""

import hashlib
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.rag_directory_ingest import (
    _acquire_single_instance_lock,
    _build_lock_file_path,
    _release_single_instance_lock,
    run_ingest_cycle,
)


class FakeRagService:
    """Простой тестовый double для RagKnowledgeService."""

    def __init__(self, existing_documents=None):
        self._existing_documents = existing_documents or []
        self.deleted_calls = []
        self.ingest_calls = []

    def list_documents_by_source(self, source_type, source_url_prefix=None):
        _ = source_type
        _ = source_url_prefix
        return list(self._existing_documents)

    def is_supported_file(self, filename):
        return filename.lower().endswith((".txt", ".md", ".pdf", ".docx", ".html", ".htm"))

    def delete_document(self, document_id, updated_by, hard_delete=False):
        self.deleted_calls.append(
            {
                "document_id": document_id,
                "updated_by": updated_by,
                "hard_delete": hard_delete,
            }
        )
        return True

    def ingest_document_from_bytes(self, filename, payload, uploaded_by, source_type="telegram", source_url=None):
        self.ingest_calls.append(
            {
                "filename": filename,
                "payload": payload,
                "uploaded_by": uploaded_by,
                "source_type": source_type,
                "source_url": source_url,
            }
        )
        return {"document_id": 123, "chunks_count": 5, "is_duplicate": 0}


class TestRagDirectoryIngestScript(unittest.TestCase):
    """Проверки поведения скрипта синхронизации директории."""

    def test_run_ingest_cycle_ingests_new_supported_file(self):
        """Новый поддерживаемый файл загружается в RAG."""
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            file_path = directory / "kb.txt"
            file_path.write_text("hello", encoding="utf-8")

            service = FakeRagService(existing_documents=[])
            stats = run_ingest_cycle(
                directory=directory,
                recursive=True,
                dry_run=False,
                force_update=False,
                uploaded_by=42,
                service=service,
            )

        self.assertEqual(stats["scanned_files"], 1)
        self.assertEqual(stats["supported_files"], 1)
        self.assertEqual(stats["ingested"], 1)
        self.assertEqual(stats["purged"], 0)
        self.assertEqual(len(service.ingest_calls), 1)

    def test_run_ingest_cycle_purges_removed_files(self):
        """Отсутствующие в директории файлы удаляются через purge."""
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            missing_url = (directory / "old.txt").resolve().as_posix()
            service = FakeRagService(
                existing_documents=[
                    {
                        "id": 50,
                        "source_url": missing_url,
                        "status": "active",
                        "content_hash": "old",
                    }
                ]
            )

            stats = run_ingest_cycle(
                directory=directory,
                recursive=True,
                dry_run=False,
                force_update=False,
                uploaded_by=9,
                service=service,
            )

        self.assertEqual(stats["purged"], 1)
        self.assertEqual(len(service.deleted_calls), 1)
        self.assertTrue(service.deleted_calls[0]["hard_delete"])

    def test_run_ingest_cycle_purges_old_version_before_ingest(self):
        """При изменении файла старая версия purge-ится перед новой загрузкой."""
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            file_path = directory / "doc.txt"
            file_path.write_text("new content", encoding="utf-8")
            source_url = file_path.resolve().as_posix()
            old_hash = hashlib.sha256(b"old content").hexdigest()

            service = FakeRagService(
                existing_documents=[
                    {
                        "id": 10,
                        "source_url": source_url,
                        "status": "active",
                        "content_hash": old_hash,
                    }
                ]
            )

            stats = run_ingest_cycle(
                directory=directory,
                recursive=True,
                dry_run=False,
                force_update=False,
                uploaded_by=77,
                service=service,
            )

        self.assertEqual(stats["purged"], 1)
        self.assertEqual(stats["ingested"], 1)
        self.assertEqual(len(service.deleted_calls), 1)
        self.assertEqual(len(service.ingest_calls), 1)

    def test_run_ingest_cycle_dry_run_does_not_mutate(self):
        """В dry-run режиме не выполняются purge и ingestion."""
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            file_path = directory / "doc.txt"
            file_path.write_text("content", encoding="utf-8")
            source_url = file_path.resolve().as_posix()

            service = FakeRagService(
                existing_documents=[
                    {
                        "id": 10,
                        "source_url": source_url,
                        "status": "active",
                        "content_hash": "outdated-hash",
                    },
                    {
                        "id": 11,
                        "source_url": (directory / "removed.txt").resolve().as_posix(),
                        "status": "active",
                        "content_hash": "removed-hash",
                    },
                ]
            )

            stats = run_ingest_cycle(
                directory=directory,
                recursive=True,
                dry_run=True,
                force_update=False,
                uploaded_by=11,
                service=service,
            )

        self.assertEqual(stats["ingested"], 1)
        self.assertEqual(stats["purged"], 2)
        self.assertEqual(len(service.deleted_calls), 0)
        self.assertEqual(len(service.ingest_calls), 0)

    def test_run_ingest_cycle_force_update_reingests_unchanged_file(self):
        """При force_update неизменённый файл purge-ится и загружается заново."""
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            file_path = directory / "doc.txt"
            file_path.write_text("same content", encoding="utf-8")
            source_url = file_path.resolve().as_posix()
            same_hash = hashlib.sha256(b"same content").hexdigest()

            service = FakeRagService(
                existing_documents=[
                    {
                        "id": 20,
                        "source_url": source_url,
                        "status": "active",
                        "content_hash": same_hash,
                    }
                ]
            )

            stats = run_ingest_cycle(
                directory=directory,
                recursive=True,
                dry_run=False,
                force_update=True,
                uploaded_by=55,
                service=service,
            )

        self.assertEqual(stats["unchanged"], 0)
        self.assertEqual(stats["purged"], 1)
        self.assertEqual(stats["ingested"], 1)
        self.assertEqual(len(service.deleted_calls), 1)
        self.assertEqual(len(service.ingest_calls), 1)

    def test_cli_help_works_outside_project_directory(self):
        """CLI-скрипт должен запускаться напрямую из любой текущей директории."""
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "rag_directory_ingest.py"

        with TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(script_path), "--help"],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--directory", result.stdout)
        self.assertIn("--force-update", result.stdout)

    def test_single_instance_lock_blocks_second_acquire(self):
        """Второй запуск для той же директории блокируется lock-файлом."""
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            lock_path = _build_lock_file_path(directory)

            first_fd = _acquire_single_instance_lock(lock_path)
            try:
                with self.assertRaises(RuntimeError):
                    _acquire_single_instance_lock(lock_path)
            finally:
                _release_single_instance_lock(lock_path, first_fd)

    def test_single_instance_lock_recovers_from_stale_pid(self):
        """Stale lock-файл очищается и позволяет новый запуск."""
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            lock_path = _build_lock_file_path(directory)
            lock_path.write_text("999999\n", encoding="utf-8")

            fd = _acquire_single_instance_lock(lock_path)
            try:
                self.assertTrue(lock_path.exists())
            finally:
                _release_single_instance_lock(lock_path, fd)


if __name__ == "__main__":
    unittest.main()
