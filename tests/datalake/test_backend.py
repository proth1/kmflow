"""Tests for storage backend abstraction.

Tests cover: LocalFilesystemBackend CRUD, StorageBackend protocol
conformance, factory function, and pipeline integration.
"""

from __future__ import annotations

import pytest

from src.datalake.backend import (
    LocalFilesystemBackend,
    StorageBackend,
    StorageMetadata,
    get_storage_backend,
)


# ---------------------------------------------------------------------------
# LocalFilesystemBackend
# ---------------------------------------------------------------------------


class TestLocalFilesystemBackend:
    """Test local filesystem storage backend."""

    @pytest.fixture
    def backend(self, tmp_path) -> LocalFilesystemBackend:
        return LocalFilesystemBackend(base_path=str(tmp_path / "evidence"))

    @pytest.mark.asyncio
    async def test_write_creates_file(self, backend: LocalFilesystemBackend) -> None:
        result = await backend.write(
            engagement_id="eng-1",
            file_name="test.pdf",
            content=b"hello world",
        )
        assert isinstance(result, StorageMetadata)
        assert result.size_bytes == 11
        assert result.version == 1
        assert result.content_hash != ""
        assert "test.pdf" in result.path

    @pytest.mark.asyncio
    async def test_read_returns_content(self, backend: LocalFilesystemBackend) -> None:
        result = await backend.write("eng-1", "doc.txt", b"test content")
        data = await backend.read(result.path)
        assert data == b"test content"

    @pytest.mark.asyncio
    async def test_read_nonexistent_raises(self, backend: LocalFilesystemBackend) -> None:
        with pytest.raises(FileNotFoundError):
            await backend.read("/nonexistent/path.txt")

    @pytest.mark.asyncio
    async def test_exists(self, backend: LocalFilesystemBackend) -> None:
        result = await backend.write("eng-1", "check.txt", b"data")
        assert await backend.exists(result.path) is True
        assert await backend.exists("/nope") is False

    @pytest.mark.asyncio
    async def test_list_files(self, backend: LocalFilesystemBackend) -> None:
        await backend.write("eng-1", "a.txt", b"a")
        await backend.write("eng-1", "b.txt", b"b")
        await backend.write("eng-2", "c.txt", b"c")

        files = await backend.list_files("eng-1")
        assert len(files) == 2

        files_eng2 = await backend.list_files("eng-2")
        assert len(files_eng2) == 1

    @pytest.mark.asyncio
    async def test_list_files_empty_engagement(self, backend: LocalFilesystemBackend) -> None:
        files = await backend.list_files("nonexistent")
        assert files == []

    @pytest.mark.asyncio
    async def test_delete(self, backend: LocalFilesystemBackend) -> None:
        result = await backend.write("eng-1", "del.txt", b"data")
        assert await backend.delete(result.path) is True
        assert await backend.exists(result.path) is False
        assert await backend.delete(result.path) is False

    @pytest.mark.asyncio
    async def test_write_with_metadata(self, backend: LocalFilesystemBackend) -> None:
        result = await backend.write(
            "eng-1", "meta.txt", b"data", metadata={"source": "test"}
        )
        assert result.path != ""

    @pytest.mark.asyncio
    async def test_content_hash_is_sha256(self, backend: LocalFilesystemBackend) -> None:
        result = await backend.write("eng-1", "hash.txt", b"test")
        assert len(result.content_hash) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Verify backends implement the StorageBackend protocol."""

    def test_local_backend_is_storage_backend(self) -> None:
        backend = LocalFilesystemBackend()
        assert isinstance(backend, StorageBackend)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestGetStorageBackend:
    """Test the backend factory function."""

    def test_local_backend(self) -> None:
        backend = get_storage_backend("local")
        assert isinstance(backend, LocalFilesystemBackend)

    def test_local_backend_custom_path(self) -> None:
        backend = get_storage_backend("local", base_path="/tmp/test")
        assert isinstance(backend, LocalFilesystemBackend)

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown storage backend"):
            get_storage_backend("s3")

    def test_databricks_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError, match="Phase F"):
            get_storage_backend("databricks")
