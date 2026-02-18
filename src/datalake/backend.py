"""Storage backend abstraction for the evidence pipeline.

Defines the ``StorageBackend`` protocol and provides two implementations:

- ``LocalFilesystemBackend``: Current behavior — files on local disk.
- ``DeltaLakeBackend``: Delta Lake via delta-rs for ACID, versioning,
  and time travel. Bronze layer of the medallion architecture.

Configuration selects the backend at startup via ``storage_backend``
setting in ``src.core.config.Settings``.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage metadata
# ---------------------------------------------------------------------------


@dataclass
class StorageMetadata:
    """Metadata returned after a storage write operation.

    Attributes:
        path: The storage path (file path or Delta table URI).
        version: Storage version (always 1 for local, Delta version otherwise).
        content_hash: SHA-256 hash of the stored content.
        size_bytes: Size of the stored content in bytes.
        stored_at: Timestamp of the write.
        extra: Backend-specific metadata.
    """

    path: str
    version: int = 1
    content_hash: str = ""
    size_bytes: int = 0
    stored_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class StorageBackend(Protocol):
    """Abstract storage backend for evidence files.

    Implementations must support write, read, exists, list, and delete.
    The protocol uses ``runtime_checkable`` so code can verify backends
    at runtime with ``isinstance()``.
    """

    async def write(
        self,
        engagement_id: str,
        file_name: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> StorageMetadata:
        """Write evidence content to storage.

        Args:
            engagement_id: Engagement scope for the file.
            file_name: Original filename.
            content: Raw file bytes.
            metadata: Optional metadata to store alongside the file.

        Returns:
            StorageMetadata describing what was written.
        """
        ...

    async def read(self, path: str) -> bytes:
        """Read file content from storage.

        Args:
            path: Storage path returned by a prior ``write()``.

        Returns:
            Raw file bytes.

        Raises:
            FileNotFoundError: If the path does not exist.
        """
        ...

    async def exists(self, path: str) -> bool:
        """Check whether a path exists in storage."""
        ...

    async def list_files(
        self,
        engagement_id: str,
        prefix: str | None = None,
    ) -> list[str]:
        """List stored files for an engagement.

        Args:
            engagement_id: Engagement to list files for.
            prefix: Optional filename prefix filter.

        Returns:
            List of storage paths.
        """
        ...

    async def delete(self, path: str) -> bool:
        """Delete a file from storage.

        Args:
            path: Storage path to delete.

        Returns:
            True if deleted, False if not found.
        """
        ...


# ---------------------------------------------------------------------------
# Local filesystem backend (current behavior)
# ---------------------------------------------------------------------------


class LocalFilesystemBackend:
    """Store evidence files on the local filesystem.

    This is the original KMFlow storage approach: files land in
    ``{base_path}/{engagement_id}/{unique_name}``. No versioning,
    no ACID guarantees, no time travel.
    """

    def __init__(self, base_path: str = "evidence_store") -> None:
        self._base_path = Path(base_path)

    async def write(
        self,
        engagement_id: str,
        file_name: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> StorageMetadata:
        engagement_dir = self._base_path / engagement_id
        engagement_dir.mkdir(parents=True, exist_ok=True)

        unique_name = f"{uuid.uuid4().hex[:8]}_{file_name}"
        file_path = engagement_dir / unique_name

        with open(file_path, "wb") as f:
            f.write(content)

        import hashlib

        content_hash = hashlib.sha256(content).hexdigest()

        return StorageMetadata(
            path=str(file_path),
            version=1,
            content_hash=content_hash,
            size_bytes=len(content),
        )

    async def read(self, path: str) -> bytes:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Evidence file not found: {path}")
        return file_path.read_bytes()

    async def exists(self, path: str) -> bool:
        return Path(path).exists()

    async def list_files(
        self,
        engagement_id: str,
        prefix: str | None = None,
    ) -> list[str]:
        engagement_dir = self._base_path / engagement_id
        if not engagement_dir.exists():
            return []

        files = []
        for entry in engagement_dir.iterdir():
            if entry.is_file():
                if prefix is None or entry.name.startswith(prefix):
                    files.append(str(entry))
        return sorted(files)

    async def delete(self, path: str) -> bool:
        file_path = Path(path)
        if file_path.exists():
            file_path.unlink()
            return True
        return False


# ---------------------------------------------------------------------------
# Delta Lake backend (Bronze layer)
# ---------------------------------------------------------------------------


class DeltaLakeBackend:
    """Store evidence files as a Delta Lake table (Bronze layer).

    Uses ``deltalake`` (delta-rs) for Python-native Delta operations
    without a Spark dependency. Each evidence file becomes a row in a
    Delta table with columns: engagement_id, file_name, content (binary),
    content_hash, size_bytes, stored_at, and user-supplied metadata.

    The Delta table path is ``{base_path}/bronze/evidence_files``.
    """

    def __init__(self, base_path: str = "datalake") -> None:
        self._base_path = Path(base_path)
        self._table_path = str(self._base_path / "bronze" / "evidence_files")
        self._file_store = self._base_path / "bronze" / "files"
        self._file_store.mkdir(parents=True, exist_ok=True)

    def _ensure_table(self) -> None:
        """Create the Delta table if it doesn't exist."""
        try:
            import pyarrow as pa
            from deltalake import DeltaTable

            if not DeltaTable.is_deltatable(self._table_path):
                from deltalake import write_deltalake

                schema = pa.schema([
                    ("id", pa.string()),
                    ("engagement_id", pa.string()),
                    ("file_name", pa.string()),
                    ("file_path", pa.string()),
                    ("content_hash", pa.string()),
                    ("size_bytes", pa.int64()),
                    ("stored_at", pa.string()),
                    ("metadata_json", pa.string()),
                ])
                # Write empty table to initialize
                empty_table = pa.table(
                    {col.name: pa.array([], type=col.type) for col in schema},
                    schema=schema,
                )
                write_deltalake(self._table_path, empty_table, mode="error")
                logger.info("Created Delta table at %s", self._table_path)
        except ImportError:
            raise ImportError(
                "deltalake and pyarrow packages are required for DeltaLakeBackend. "
                "Install with: pip install 'kmflow[datalake]'"
            ) from None

    async def write(
        self,
        engagement_id: str,
        file_name: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> StorageMetadata:
        import hashlib
        import json

        import pyarrow as pa
        from deltalake import write_deltalake

        self._ensure_table()

        content_hash = hashlib.sha256(content).hexdigest()
        record_id = uuid.uuid4().hex[:16]
        now = datetime.now(UTC).isoformat()

        # Store the actual file on disk (Delta metadata table tracks it)
        engagement_dir = self._file_store / engagement_id
        engagement_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{record_id}_{file_name}"
        file_path = engagement_dir / unique_name

        with open(file_path, "wb") as f:
            f.write(content)

        # Append metadata row to Delta table
        row = pa.table({
            "id": [record_id],
            "engagement_id": [engagement_id],
            "file_name": [file_name],
            "file_path": [str(file_path)],
            "content_hash": [content_hash],
            "size_bytes": [len(content)],
            "stored_at": [now],
            "metadata_json": [json.dumps(metadata) if metadata else "{}"],
        })
        write_deltalake(self._table_path, row, mode="append")

        # Get current table version
        from deltalake import DeltaTable

        dt = DeltaTable(self._table_path)
        version = dt.version()

        return StorageMetadata(
            path=str(file_path),
            version=version,
            content_hash=content_hash,
            size_bytes=len(content),
            extra={"delta_table": self._table_path, "record_id": record_id},
        )

    async def read(self, path: str) -> bytes:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Evidence file not found: {path}")
        return file_path.read_bytes()

    async def exists(self, path: str) -> bool:
        return Path(path).exists()

    async def list_files(
        self,
        engagement_id: str,
        prefix: str | None = None,
    ) -> list[str]:
        self._ensure_table()

        from deltalake import DeltaTable

        dt = DeltaTable(self._table_path)
        df = dt.to_pyarrow_table()

        # Filter by engagement_id
        import pyarrow.compute as pc

        mask = pc.equal(df.column("engagement_id"), engagement_id)
        filtered = df.filter(mask)

        paths = filtered.column("file_path").to_pylist()

        if prefix:
            paths = [p for p in paths if Path(p).name.split("_", 1)[-1].startswith(prefix)]

        return sorted(paths)

    async def delete(self, path: str) -> bool:
        file_path = Path(path)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def get_table_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return Delta table version history (time travel metadata)."""
        self._ensure_table()
        from deltalake import DeltaTable

        dt = DeltaTable(self._table_path)
        return dt.history(limit)

    def read_version(self, version: int) -> Any:
        """Read the Delta table at a specific version (time travel)."""
        self._ensure_table()
        from deltalake import DeltaTable

        dt = DeltaTable(self._table_path, version=version)
        return dt.to_pyarrow_table()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_storage_backend(
    backend_type: str = "local",
    base_path: str | None = None,
) -> StorageBackend:
    """Create a storage backend instance based on configuration.

    Args:
        backend_type: One of ``"local"``, ``"delta"``, or ``"databricks"``.
        base_path: Override the default base path.

    Returns:
        A StorageBackend implementation.

    Raises:
        ValueError: If ``backend_type`` is unknown.
    """
    if backend_type == "local":
        return LocalFilesystemBackend(base_path=base_path or "evidence_store")
    elif backend_type == "delta":
        return DeltaLakeBackend(base_path=base_path or "datalake")
    elif backend_type == "databricks":
        raise NotImplementedError(
            "Databricks backend is planned for Phase F. "
            "Use 'delta' for local Delta Lake or 'local' for filesystem."
        )
    else:
        raise ValueError(
            f"Unknown storage backend: {backend_type}. "
            f"Must be one of: local, delta, databricks"
        )
