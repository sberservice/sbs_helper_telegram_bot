"""test_qdrant_sync.py — тесты синхронизации remote→local Qdrant."""

import types
import unittest
from unittest import mock

from src.core.ai.qdrant_sync import QdrantRemoteToLocalSync


class _Point:
    """Простой тестовый объект точки Qdrant."""

    def __init__(self, point_id):
        self.id = point_id


class TestQdrantRemoteToLocalSync(unittest.TestCase):
    """Проверки best-effort синхронизации remote→local."""

    @mock.patch(
        "src.core.ai.qdrant_sync.ai_settings.AI_RAG_VECTOR_SYNC_COLLECTION",
        "env_collection",
    )
    def test_collection_name_defaults_from_sync_env(self):
        """Имя коллекции по умолчанию берётся из AI_RAG_VECTOR_SYNC_COLLECTION."""
        syncer = QdrantRemoteToLocalSync()
        self.assertEqual(syncer.collection_name, "env_collection")

    @mock.patch("src.core.ai.qdrant_sync.ai_settings.AI_RAG_VECTOR_REMOTE_URL", "")
    def test_validate_arguments_requires_remote_url(self):
        """Синхронизация не запускается без URL удалённого Qdrant."""
        syncer = QdrantRemoteToLocalSync(collection_name="rag_chunks_v1")
        with self.assertRaises(ValueError):
            syncer.sync()

    @mock.patch("src.core.ai.qdrant_sync.ai_settings.AI_RAG_VECTOR_REMOTE_URL", "http://remote")
    def test_validate_arguments_blocks_delete_missing_with_max_points(self):
        """Комбинация delete-missing и max-points запрещена для безопасности."""
        syncer = QdrantRemoteToLocalSync(
            collection_name="rag_chunks_v1",
            delete_missing=True,
            max_points=10,
        )
        with self.assertRaises(ValueError):
            syncer.sync()

    @mock.patch("src.core.ai.qdrant_sync.ai_settings.AI_RAG_VECTOR_REMOTE_URL", "http://remote")
    def test_sync_dry_run_counts_without_upsert(self):
        """В dry-run режимe считаются точки без записи в local индекс."""

        class _RemoteClient:
            def __init__(self):
                self.calls = 0

            def scroll(self, **_kwargs):
                if self.calls == 0:
                    self.calls += 1
                    return ([_Point(1), _Point(2)], None)
                return ([], None)

        local_client = mock.Mock()
        syncer = QdrantRemoteToLocalSync(collection_name="rag_chunks_v1", dry_run=True, batch_size=50)

        with mock.patch.object(syncer, "_ensure_local_collection"), mock.patch.object(
            syncer, "_build_remote_client", return_value=_RemoteClient()
        ), mock.patch.object(syncer, "_build_local_client", return_value=local_client):
            stats = syncer.sync()

        self.assertEqual(stats.scanned, 2)
        self.assertEqual(stats.skipped, 2)
        self.assertEqual(stats.synced, 0)
        self.assertEqual(stats.batches, 1)
        local_client.upsert.assert_not_called()

    @mock.patch("src.core.ai.qdrant_sync.ai_settings.AI_RAG_VECTOR_REMOTE_URL", "http://remote")
    def test_sync_upserts_points_to_local(self):
        """При обычном запуске точки из remote записываются в local."""

        class _RemoteClient:
            def __init__(self):
                self.calls = 0

            def scroll(self, **_kwargs):
                if self.calls == 0:
                    self.calls += 1
                    return ([_Point(10), _Point(11)], None)
                return ([], None)

        local_client = mock.Mock()
        syncer = QdrantRemoteToLocalSync(collection_name="rag_chunks_v1", dry_run=False, batch_size=2)

        with mock.patch.object(syncer, "_ensure_local_collection"), mock.patch.object(
            syncer, "_build_remote_client", return_value=_RemoteClient()
        ), mock.patch.object(syncer, "_build_local_client", return_value=local_client):
            stats = syncer.sync()

        self.assertEqual(stats.scanned, 2)
        self.assertEqual(stats.synced, 2)
        self.assertEqual(stats.failed, 0)
        local_client.upsert.assert_called_once()

    def test_delete_missing_local_points(self):
        """Лишние local точки удаляются при включённом reconcile удалений."""

        class _VectorParams:
            def __init__(self, size, distance):
                self.size = size
                self.distance = distance

        class _PointIdsList:
            def __init__(self, points):
                self.points = points

        class _CollectionInfo:
            def __init__(self):
                self.config = types.SimpleNamespace(
                    params=types.SimpleNamespace(
                        vectors=_VectorParams(size=3, distance="cosine")
                    )
                )

        fake_qdrant_module = types.SimpleNamespace(
            models=types.SimpleNamespace(PointIdsList=_PointIdsList, VectorParams=_VectorParams)
        )

        class _RemoteClient:
            def __init__(self):
                self.calls = 0

            def get_collection(self, _collection_name):
                return _CollectionInfo()

            def scroll(self, **_kwargs):
                if self.calls == 0:
                    self.calls += 1
                    return ([_Point(1), _Point(3)], None)
                return ([], None)

        class _LocalClient:
            def __init__(self):
                self.deleted = []
                self.calls = 0

            def collection_exists(self, _collection_name):
                return True

            def get_collection(self, _collection_name):
                return _CollectionInfo()

            def upsert(self, **_kwargs):
                return None

            def scroll(self, **_kwargs):
                if self.calls == 0:
                    self.calls += 1
                    return ([_Point(1), _Point(3)], "after_remote")
                if self.calls == 1:
                    self.calls += 1
                    return ([_Point(1), _Point(2), _Point(3)], None)
                return ([], None)

            def delete(self, **kwargs):
                points_selector = kwargs["points_selector"]
                self.deleted.extend(points_selector.points)

        local_client = _LocalClient()
        syncer = QdrantRemoteToLocalSync(
            collection_name="rag_chunks_v1",
            dry_run=False,
            batch_size=10,
            delete_missing=True,
        )

        with mock.patch.dict("sys.modules", {"qdrant_client": fake_qdrant_module}), mock.patch(
            "src.core.ai.qdrant_sync.ai_settings.AI_RAG_VECTOR_REMOTE_URL",
            "http://remote",
        ), mock.patch.object(syncer, "_build_remote_client", return_value=_RemoteClient()), mock.patch.object(
            syncer,
            "_build_local_client",
            return_value=local_client,
        ):
            stats = syncer.sync()

        self.assertEqual(stats.deleted, 1)
        self.assertEqual(local_client.deleted, [2])


if __name__ == "__main__":
    unittest.main()
