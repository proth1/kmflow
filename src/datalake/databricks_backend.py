"""Databricks storage backend for the evidence pipeline.

Implements the ``StorageBackend`` protocol using Databricks Volumes API
(Unity Catalog Volumes) for file storage and a Delta table for metadata
tracking. This backend is selected when ``storage_backend = "databricks"``
in the application configuration.

Optional dependency: ``databricks-sdk``. The backend degrades gracefully
if the SDK is not installed (raises ``ImportError`` at method call time,
not at import time).
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.datalake.backend import StorageMetadata

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional SDK import guard
# ---------------------------------------------------------------------------

try:
    from databricks.sdk import WorkspaceClient  # type: ignore[import-untyped]
    from databricks.sdk.service.files import UploadRequest  # type: ignore[import-untyped]

    _HAS_DATABRICKS = True
except ImportError:
    _HAS_DATABRICKS = False


# ---------------------------------------------------------------------------
# DatabricksBackend
# ---------------------------------------------------------------------------


class DatabricksBackend:
    """Store evidence files in Databricks Volumes (Unity Catalog).

    Files are written to::

        /Volumes/{catalog}/{schema}/{volume}/evidence_store/{engagement_id}/{unique_name}

    A Delta table at ``{catalog}.{schema}.evidence_metadata`` tracks every
    file write with full provenance metadata (engagement ID, content hash,
    timestamps, user-supplied metadata). This mirrors the pattern used by
    ``DeltaLakeBackend`` so callers see consistent behavior across backends.

    Authentication uses the Databricks SDK's standard credential chain:
    environment variables ``DATABRICKS_HOST`` + ``DATABRICKS_TOKEN``, or
    a ``.databrickscfg`` profile, or Azure/GCP managed identity, in that
    order of precedence. Pass explicit ``host`` and ``token`` parameters
    to override.

    Args:
        catalog: Unity Catalog catalog name (default: ``"kmflow"``).
        schema: Unity Catalog schema name (default: ``"evidence"``).
        volume: Unity Catalog volume name (default: ``"raw_evidence"``).
        host: Databricks workspace URL. Falls back to ``DATABRICKS_HOST``
            env var if omitted.
        token: Databricks personal access token or service-principal
            OAuth token. Falls back to ``DATABRICKS_TOKEN`` env var.
    """

    def __init__(
        self,
        catalog: str = "kmflow",
        schema: str = "evidence",
        volume: str = "raw_evidence",
        host: str = "",
        token: str = "",
    ) -> None:
        self._catalog = catalog
        self._schema = schema
        self._volume = volume
        self._host = host
        self._token = token

        # Base Volumes path for file storage
        self._volume_base = f"/Volumes/{catalog}/{schema}/{volume}/evidence_store"

        # Full-qualified Delta table for metadata tracking
        self._metadata_table = f"`{catalog}`.`{schema}`.`evidence_metadata`"

        self._client: Any = None  # Initialized lazily on first use

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        """Return (and lazily initialise) the Databricks WorkspaceClient.

        If ``self._client`` has already been set (e.g. injected in tests),
        it is returned immediately without checking for the SDK package.

        Raises:
            ImportError: If ``databricks-sdk`` is not installed and no
                client has been pre-injected.
            RuntimeError: If host/token are missing and not in env.
        """
        if self._client is not None:
            return self._client

        if not _HAS_DATABRICKS:
            raise ImportError(
                "databricks-sdk is required for DatabricksBackend. "
                "Install with: pip install 'kmflow[databricks]'"
            ) from None

        if self._client is None:
            kwargs: dict[str, Any] = {}
            if self._host:
                kwargs["host"] = self._host
            if self._token:
                kwargs["token"] = self._token
            self._client = WorkspaceClient(**kwargs)
            logger.info(
                "DatabricksBackend connected to workspace; catalog=%s schema=%s volume=%s",
                self._catalog,
                self._schema,
                self._volume,
            )
        return self._client

    def _volume_path(self, engagement_id: str, unique_name: str) -> str:
        """Build the full Volumes path for a given file."""
        safe_engagement = self._sanitize_path_component(engagement_id)
        return f"{self._volume_base}/{safe_engagement}/{unique_name}"

    @staticmethod
    def _sanitize_filename(file_name: str) -> str:
        """Strip directory components from filename to prevent path injection."""
        return Path(file_name).name

    @staticmethod
    def _sanitize_path_component(component: str) -> str:
        """Remove characters that could escape the Volumes path hierarchy.

        Allows alphanumerics, hyphens, and underscores only. Replaces
        other characters with underscores and strips leading dots.
        """
        sanitized = "".join(
            c if c.isalnum() or c in ("-", "_") else "_"
            for c in component
        )
        return sanitized.lstrip(".")

    def _validate_volume_path(self, path: str) -> str:
        """Ensure a stored path is within the configured Volumes hierarchy.

        Args:
            path: Storage path returned by a prior ``write()`` call.

        Returns:
            The validated path (unchanged).

        Raises:
            ValueError: If the path escapes the configured volume base.
        """
        if not path.startswith(self._volume_base):
            raise ValueError(
                f"Path is outside storage boundary: {path!r} "
                f"(expected prefix: {self._volume_base!r})"
            )
        return path

    def _ensure_metadata_table(self, w: Any) -> None:
        """Create the evidence metadata Delta table if it does not exist.

        The table lives in Unity Catalog and is created once per workspace
        on first write. Subsequent calls are no-ops after the first check.
        """
        ddl = f"""
        CREATE TABLE IF NOT EXISTS {self._metadata_table} (
            id             STRING        NOT NULL,
            engagement_id  STRING        NOT NULL,
            file_name      STRING        NOT NULL,
            volume_path    STRING        NOT NULL,
            content_hash   STRING        NOT NULL,
            size_bytes     BIGINT        NOT NULL,
            stored_at      STRING        NOT NULL,
            metadata_json  STRING,
            CONSTRAINT pk_evidence_metadata PRIMARY KEY (id)
        )
        USING DELTA
        COMMENT 'KMFlow evidence file metadata — managed by DatabricksBackend'
        """
        try:
            w.statement_execution.execute(
                warehouse_id=self._get_warehouse_id(w),
                statement=ddl.strip(),
            )
            logger.debug("Ensured metadata table: %s", self._metadata_table)
        except Exception as exc:
            logger.warning(
                "Could not ensure metadata table %s: %s",
                self._metadata_table,
                exc,
            )

    def _get_warehouse_id(self, w: Any) -> str:
        """Return the first running SQL warehouse ID.

        In practice callers should pass a warehouse ID explicitly; this
        helper provides a best-effort default for simple deployments.
        """
        try:
            warehouses = list(w.warehouses.list())
            for wh in warehouses:
                if getattr(wh, "state", None) in ("RUNNING", "STOPPED"):
                    return str(wh.id)
        except Exception:
            pass
        return ""

    # ------------------------------------------------------------------
    # StorageBackend protocol methods
    # ------------------------------------------------------------------

    async def write(
        self,
        engagement_id: str,
        file_name: str,
        content: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> StorageMetadata:
        """Write evidence content to Databricks Volumes.

        The file is uploaded using the Databricks Files API
        (``workspace_client.files.upload``), which maps to Unity Catalog
        Volumes. A metadata row is appended to the Delta tracking table.

        Args:
            engagement_id: Engagement scope for the file.
            file_name: Original filename (directory components are stripped).
            content: Raw file bytes.
            metadata: Optional metadata to store alongside the file.

        Returns:
            ``StorageMetadata`` with ``path`` set to the Volumes URI and
            ``extra`` containing ``catalog``, ``schema``, ``volume``,
            and the auto-generated ``record_id``.
        """
        import io

        w = self._get_client()

        safe_name = self._sanitize_filename(file_name)
        content_hash = hashlib.sha256(content).hexdigest()
        record_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()

        unique_name = f"{record_id[:16]}_{safe_name}"
        volume_path = self._volume_path(engagement_id, unique_name)

        logger.debug(
            "DatabricksBackend.write: engagement=%s path=%s bytes=%d",
            engagement_id,
            volume_path,
            len(content),
        )

        # Upload to Databricks Volumes via Files API
        try:
            w.files.upload(volume_path, io.BytesIO(content), overwrite=True)
        except Exception as exc:
            logger.error("Failed to upload file to Volumes: %s", exc)
            raise

        # Append metadata row to the tracking Delta table
        metadata_json = json.dumps(metadata) if metadata else "{}"
        insert_sql = f"""
        INSERT INTO {self._metadata_table}
        (id, engagement_id, file_name, volume_path, content_hash,
         size_bytes, stored_at, metadata_json)
        VALUES
        ('{record_id}', '{engagement_id}', '{safe_name}', '{volume_path}',
         '{content_hash}', {len(content)}, '{now}', '{metadata_json}')
        """
        try:
            wh_id = self._get_warehouse_id(w)
            if wh_id:
                w.statement_execution.execute(
                    warehouse_id=wh_id,
                    statement=insert_sql.strip(),
                )
        except Exception as exc:
            logger.warning("Failed to write metadata row: %s", exc)

        return StorageMetadata(
            path=volume_path,
            version=1,
            content_hash=content_hash,
            size_bytes=len(content),
            extra={
                "catalog": self._catalog,
                "schema": self._schema,
                "volume": self._volume,
                "record_id": record_id,
                "metadata_table": self._metadata_table,
            },
        )

    async def read(self, path: str) -> bytes:
        """Read file content from Databricks Volumes.

        Args:
            path: Volumes path returned by a prior ``write()`` call.

        Returns:
            Raw file bytes.

        Raises:
            ValueError: If ``path`` is outside the configured volume.
            FileNotFoundError: If the file does not exist in Volumes.
            ImportError: If ``databricks-sdk`` is not installed.
        """
        self._validate_volume_path(path)
        w = self._get_client()

        logger.debug("DatabricksBackend.read: path=%s", path)

        try:
            response = w.files.download(path)
            # The Files API returns a response object with a `contents` stream
            content: bytes = response.contents.read()
            return content
        except Exception as exc:
            error_str = str(exc).lower()
            if "not found" in error_str or "does not exist" in error_str or "404" in error_str:
                raise FileNotFoundError(f"Evidence file not found in Volumes: {path}") from exc
            raise

    async def exists(self, path: str) -> bool:
        """Check whether a path exists in Databricks Volumes.

        Args:
            path: Volumes path to check.

        Returns:
            ``True`` if the file exists, ``False`` otherwise.
        """
        self._validate_volume_path(path)
        w = self._get_client()

        try:
            w.files.get_metadata(path)
            return True
        except Exception as exc:
            error_str = str(exc).lower()
            if "not found" in error_str or "does not exist" in error_str or "404" in error_str:
                return False
            logger.warning("Unexpected error checking existence of %s: %s", path, exc)
            return False

    async def list_files(
        self,
        engagement_id: str,
        prefix: str | None = None,
    ) -> list[str]:
        """List stored files for an engagement.

        Queries the Databricks Volumes directory for the engagement rather
        than the metadata Delta table so the listing reflects actual storage
        state (resilient to metadata table lag).

        Args:
            engagement_id: Engagement to list files for.
            prefix: Optional filename prefix filter (applied to original
                file name, i.e., the portion after the ``{record_id[:16]}_``
                prefix).

        Returns:
            Sorted list of Volumes paths.
        """
        w = self._get_client()
        safe_engagement = self._sanitize_path_component(engagement_id)
        directory = f"{self._volume_base}/{safe_engagement}"

        paths: list[str] = []
        try:
            entries = w.files.list_directory_contents(directory)
            for entry in entries:
                entry_path = getattr(entry, "path", None)
                if not entry_path:
                    continue
                if not getattr(entry, "is_directory", False):
                    if prefix is None:
                        paths.append(entry_path)
                    else:
                        # Strip the record_id prefix to check against user's prefix
                        base_name = Path(entry_path).name
                        original_name = base_name.split("_", 1)[-1] if "_" in base_name else base_name
                        if original_name.startswith(prefix):
                            paths.append(entry_path)
        except Exception as exc:
            error_str = str(exc).lower()
            if "not found" in error_str or "does not exist" in error_str or "404" in error_str:
                return []
            logger.warning(
                "Error listing Volumes directory %s: %s", directory, exc
            )
            return []

        return sorted(paths)

    async def delete(self, path: str) -> bool:
        """Delete a file from Databricks Volumes.

        Also removes the corresponding row from the metadata Delta table
        (best-effort; failure to remove the metadata row is logged but
        does not cause ``delete`` to return ``False``).

        Args:
            path: Volumes path to delete.

        Returns:
            ``True`` if the file was deleted, ``False`` if it was not found.
        """
        self._validate_volume_path(path)
        w = self._get_client()

        logger.debug("DatabricksBackend.delete: path=%s", path)

        try:
            w.files.delete(path)
            deleted = True
        except Exception as exc:
            error_str = str(exc).lower()
            if "not found" in error_str or "does not exist" in error_str or "404" in error_str:
                return False
            raise

        # Remove metadata row (best-effort)
        escaped_path = path.replace("'", "''")
        delete_sql = f"""
        DELETE FROM {self._metadata_table}
        WHERE volume_path = '{escaped_path}'
        """
        try:
            wh_id = self._get_warehouse_id(w)
            if wh_id:
                w.statement_execution.execute(
                    warehouse_id=wh_id,
                    statement=delete_sql.strip(),
                )
        except Exception as exc:
            logger.warning(
                "Failed to remove metadata row for %s: %s", path, exc
            )

        return deleted

    # ------------------------------------------------------------------
    # Databricks-specific extras
    # ------------------------------------------------------------------

    def get_volume_base_path(self) -> str:
        """Return the Volumes base path for this backend instance."""
        return self._volume_base

    def get_metadata_table(self) -> str:
        """Return the fully-qualified Unity Catalog metadata table name."""
        return self._metadata_table
