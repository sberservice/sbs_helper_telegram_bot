"""qdrant_sync.py — best-effort синхронизация remote→local Qdrant."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
from typing import Any

from config import ai_settings

logger = logging.getLogger(__name__)

QDRANT_SYNC_CATCH_EXCEPTIONS: tuple[type[BaseException], ...] = (
    RuntimeError,
    ValueError,
    TypeError,
    OSError,
)


@dataclass
class QdrantSyncStats:
    """Сводная статистика выполнения синхронизации."""

    scanned: int = 0
    synced: int = 0
    skipped: int = 0
    failed: int = 0
    deleted: int = 0
    batches: int = 0


class QdrantRemoteToLocalSync:
    """Сервис синхронизации одной коллекции remote Qdrant в local Qdrant."""

    def __init__(
        self,
        collection_name: str | None = None,
        batch_size: int = 200,
        dry_run: bool = False,
        delete_missing: bool = False,
        max_points: int | None = None,
    ) -> None:
        self.collection_name = (collection_name or ai_settings.AI_RAG_VECTOR_SYNC_COLLECTION).strip()
        self.batch_size = max(1, int(batch_size))
        self.dry_run = bool(dry_run)
        self.delete_missing = bool(delete_missing)
        self.max_points = max_points if (max_points or 0) > 0 else None

    def sync(self) -> QdrantSyncStats:
        """Выполнить one-way синхронизацию remote коллекции в local коллекцию."""
        self._validate_arguments()

        remote_client = self._build_remote_client()
        local_client = self._build_local_client()

        self._ensure_local_collection(remote_client=remote_client, local_client=local_client)

        stats = QdrantSyncStats()
        remote_ids = self._sync_points(remote_client=remote_client, local_client=local_client, stats=stats)

        if self.delete_missing:
            self._delete_missing_local_points(
                local_client=local_client,
                remote_ids=remote_ids,
                stats=stats,
            )

        return stats

    def _validate_arguments(self) -> None:
        """Проверить валидность параметров запуска синхронизации."""
        if not self.collection_name:
            raise ValueError("Имя коллекции не задано")

        if not str(ai_settings.AI_RAG_VECTOR_REMOTE_URL or "").strip():
            raise ValueError("Для синхронизации требуется AI_RAG_VECTOR_REMOTE_URL")

        if self.delete_missing and self.max_points is not None:
            raise ValueError("--delete-missing нельзя использовать вместе с --max-points")

    def _build_remote_client(self):
        """Создать клиент удалённого Qdrant по текущим env-настройкам."""
        from qdrant_client import QdrantClient

        return QdrantClient(
            url=str(ai_settings.AI_RAG_VECTOR_REMOTE_URL or "").strip(),
            api_key=str(ai_settings.AI_RAG_VECTOR_REMOTE_API_KEY or "").strip() or None,
            timeout=max(1.0, float(ai_settings.AI_RAG_VECTOR_REMOTE_TIMEOUT_SECONDS)),
        )

    def _build_local_client(self):
        """Создать клиент локального Qdrant по пути из env-настроек."""
        from qdrant_client import QdrantClient

        db_path = Path(ai_settings.AI_RAG_VECTOR_DB_PATH).expanduser().resolve()
        db_path.mkdir(parents=True, exist_ok=True)
        return QdrantClient(path=str(db_path))

    def _ensure_local_collection(self, remote_client: Any, local_client: Any) -> None:
        """Проверить совместимость и наличие целевой локальной коллекции."""
        from qdrant_client import models

        remote_info = remote_client.get_collection(self.collection_name)
        remote_vectors = remote_info.config.params.vectors
        remote_params = self._extract_single_vector_params(remote_vectors)

        if local_client.collection_exists(self.collection_name):
            local_info = local_client.get_collection(self.collection_name)
            local_vectors = local_info.config.params.vectors
            local_params = self._extract_single_vector_params(local_vectors)

            if int(local_params.size) != int(remote_params.size):
                raise RuntimeError(
                    "Несовместимая размерность коллекции: "
                    f"remote={remote_params.size} local={local_params.size}"
                )

            if str(local_params.distance) != str(remote_params.distance):
                raise RuntimeError(
                    "Несовместимая метрика коллекции: "
                    f"remote={remote_params.distance} local={local_params.distance}"
                )
            return

        local_client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=int(remote_params.size),
                distance=remote_params.distance,
            ),
        )

    @staticmethod
    def _extract_single_vector_params(vectors_config: Any):
        """Извлечь VectorParams для коллекций с одним dense-вектором."""
        from qdrant_client import models

        if isinstance(vectors_config, models.VectorParams):
            return vectors_config

        if isinstance(vectors_config, dict) and len(vectors_config) == 1:
            return next(iter(vectors_config.values()))

        raise RuntimeError("Поддерживаются только коллекции с одним dense-вектором")

    def _sync_points(self, remote_client: Any, local_client: Any, stats: QdrantSyncStats) -> set[str]:
        """Считать точки из remote и синхронизировать их в local батчами."""
        offset = None
        remote_ids: set[str] = set()

        while True:
            points, next_offset = remote_client.scroll(
                collection_name=self.collection_name,
                limit=self.batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )

            if not points:
                break

            batch_points = []
            for point in points:
                if self.max_points is not None and stats.scanned >= self.max_points:
                    break

                stats.scanned += 1
                point_id = self._normalize_point_id(getattr(point, "id", None))
                if point_id is not None:
                    remote_ids.add(point_id)
                batch_points.append(point)

            if batch_points:
                stats.batches += 1
                if self.dry_run:
                    stats.skipped += len(batch_points)
                else:
                    try:
                        local_client.upsert(
                            collection_name=self.collection_name,
                            points=batch_points,
                            wait=True,
                        )
                        stats.synced += len(batch_points)
                    except QDRANT_SYNC_CATCH_EXCEPTIONS:
                        stats.failed += len(batch_points)
                        logger.exception(
                            "Не удалось синхронизировать batch в local Qdrant: collection=%s size=%s",
                            self.collection_name,
                            len(batch_points),
                        )

            if self.max_points is not None and stats.scanned >= self.max_points:
                break

            if next_offset is None:
                break
            offset = next_offset

        return remote_ids

    def _delete_missing_local_points(self, local_client: Any, remote_ids: set[str], stats: QdrantSyncStats) -> None:
        """Удалить локальные точки, которых нет в remote коллекции."""
        from qdrant_client import models

        offset = None
        while True:
            points, next_offset = local_client.scroll(
                collection_name=self.collection_name,
                limit=self.batch_size,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )

            if not points:
                break

            missing_ids = []
            for point in points:
                point_id = self._normalize_point_id(getattr(point, "id", None))
                if point_id is None:
                    continue
                if point_id not in remote_ids:
                    missing_ids.append(getattr(point, "id", None))

            if missing_ids:
                if self.dry_run:
                    stats.deleted += len(missing_ids)
                else:
                    try:
                        local_client.delete(
                            collection_name=self.collection_name,
                            points_selector=models.PointIdsList(points=missing_ids),
                            wait=True,
                        )
                        stats.deleted += len(missing_ids)
                    except QDRANT_SYNC_CATCH_EXCEPTIONS:
                        logger.exception(
                            "Не удалось удалить лишние точки из local Qdrant: collection=%s size=%s",
                            self.collection_name,
                            len(missing_ids),
                        )

            if next_offset is None:
                break
            offset = next_offset

    @staticmethod
    def _normalize_point_id(point_id: Any) -> str | None:
        """Нормализовать ID точки в строку для сравнения множеств идентификаторов."""
        if point_id is None:
            return None
        return str(point_id)
