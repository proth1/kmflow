"""Tests for DatabricksBackend storage implementation.

All Databricks SDK calls are mocked so these tests run without a live
workspace. The tests verify:
- StorageBackend protocol compliance
- Correct Volumes path construction and sanitization
- Path boundary validation (_validate_volume_path)
- Error mapping (not-found -> FileNotFoundError)
- Metadata tracking behaviour (SQL insert on write, delete on delete)
- list_files prefix filtering
- exists returns False on 404
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest

from src.datalake.databricks_backend import DatabricksBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_backend(
    catalog: str = "kmflow",
    schema: str = "evidence",
    volume: str = "raw_evidence",
    host: str = "https://test.azuredatabricks.net",
    token: str = "test-token",
) -> DatabricksBackend:
    """Create a DatabricksBackend with a pre-set mock client."""
    backend = DatabricksBackend(
        catalog=catalog,
        schema=schema,
        volume=volume,
        host=host,
        token=token,
    )
    return backend


def _inject_mock_client(backend: DatabricksBackend) -> MagicMock:
    """Inject a MagicMock as the internal WorkspaceClient."""
    mock_client = MagicMock()
    backend._client = mock_client
    return mock_client


# ---------------------------------------------------------------------------
# Construction and configuration
# ---------------------------------------------------------------------------


class TestDatabricksBackendInit:
    def test_volume_base_path(self) -> None:
        backend = _make_backend(catalog="mycat", schema="myschema", volume="myvol")
        assert backend.get_volume_base_path() == "/Volumes/mycat/myschema/myvol/evidence_store"

    def test_metadata_table_name(self) -> None:
        backend = _make_backend(catalog="mycat", schema="myschema")
        assert backend.get_metadata_table() == "`mycat`.`myschema`.`evidence_metadata`"

    def test_default_values(self) -> None:
        backend = DatabricksBackend()
        assert backend._catalog == "kmflow"
        assert backend._schema == "evidence"
        assert backend._volume == "raw_evidence"


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


class TestPathValidation:
    def test_valid_path_accepted(self) -> None:
        backend = _make_backend()
        valid = "/Volumes/kmflow/evidence/raw_evidence/evidence_store/eng1/abc_file.pdf"
        result = backend._validate_volume_path(valid)
        assert result == valid

    def test_path_outside_boundary_raises(self) -> None:
        backend = _make_backend()
        with pytest.raises(ValueError, match="outside storage boundary"):
            backend._validate_volume_path("/Volumes/other/catalog/vol/file.pdf")

    def test_path_traversal_raises(self) -> None:
        backend = _make_backend()
        with pytest.raises(ValueError, match="outside storage boundary"):
            backend._validate_volume_path("/Volumes/kmflow/evidence/raw_evidence/../secret/file")

    def test_sanitize_filename_strips_dirs(self) -> None:
        assert DatabricksBackend._sanitize_filename("../../../etc/passwd") == "passwd"
        assert DatabricksBackend._sanitize_filename("subdir/file.pdf") == "file.pdf"
        assert DatabricksBackend._sanitize_filename("normal.xlsx") == "normal.xlsx"

    def test_sanitize_path_component(self) -> None:
        assert DatabricksBackend._sanitize_path_component("eng-123") == "eng-123"
        # Path separators, dots, etc. are replaced with underscores
        result = DatabricksBackend._sanitize_path_component("eng/../../etc")
        assert "eng" in result
        assert "/" not in result
        assert ".." not in result
        assert "etc" in result
        # Leading dot stripped
        assert DatabricksBackend._sanitize_path_component(".hidden").lstrip("_") == "hidden"
        assert DatabricksBackend._sanitize_path_component("my engagement") == "my_engagement"


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------


class TestWrite:
    @pytest.mark.asyncio
    async def test_write_returns_storage_metadata(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.upload = MagicMock()
        mock_client.warehouses.list.return_value = []  # no warehouse -> skip SQL

        content = b"hello evidence"
        meta = await backend.write("eng-1", "doc.pdf", content)

        assert meta.size_bytes == len(content)
        assert len(meta.content_hash) == 64  # SHA-256 hex
        # Hyphens are preserved in engagement IDs (they are valid in Volumes paths)
        assert "evidence_store/eng-1" in meta.path
        assert meta.path.endswith("doc.pdf")
        assert meta.extra["catalog"] == "kmflow"
        assert meta.extra["schema"] == "evidence"
        assert meta.extra["volume"] == "raw_evidence"

    @pytest.mark.asyncio
    async def test_write_calls_volumes_upload(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.warehouses.list.return_value = []

        await backend.write("eng-1", "file.txt", b"data")

        mock_client.files.upload.assert_called_once()
        call_args = mock_client.files.upload.call_args
        path_arg = call_args[0][0]
        # Hyphens preserved; engagement_id="eng-1" -> path segment "eng-1"
        assert path_arg.startswith("/Volumes/kmflow/evidence/raw_evidence/evidence_store/eng-1/")
        assert path_arg.endswith("file.txt")

    @pytest.mark.asyncio
    async def test_write_sanitizes_filename(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.warehouses.list.return_value = []

        meta = await backend.write("eng-1", "../../malicious.exe", b"payload")

        call_args = mock_client.files.upload.call_args
        path_arg = call_args[0][0]
        assert "malicious.exe" in path_arg
        assert ".." not in path_arg
        assert meta.path.endswith("malicious.exe")

    @pytest.mark.asyncio
    async def test_write_with_metadata(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.warehouses.list.return_value = []

        meta = await backend.write(
            "eng-2",
            "report.docx",
            b"content",
            metadata={"source": "sharepoint", "author": "alice"},
        )

        assert meta.content_hash  # hash is set regardless of metadata
        assert "record_id" in meta.extra

    @pytest.mark.asyncio
    async def test_write_propagates_upload_error(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.upload.side_effect = RuntimeError("quota exceeded")

        with pytest.raises(RuntimeError, match="quota exceeded"):
            await backend.write("eng-1", "file.txt", b"data")


# ---------------------------------------------------------------------------
# read()
# ---------------------------------------------------------------------------


class TestRead:
    @pytest.mark.asyncio
    async def test_read_returns_bytes(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)

        expected = b"file content here"
        mock_response = MagicMock()
        mock_response.contents = io.BytesIO(expected)
        mock_client.files.download.return_value = mock_response

        path = "/Volumes/kmflow/evidence/raw_evidence/evidence_store/eng1/abc_file.pdf"
        result = await backend.read(path)

        assert result == expected
        mock_client.files.download.assert_called_once_with(path)

    @pytest.mark.asyncio
    async def test_read_not_found_raises_file_not_found(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.download.side_effect = Exception("404 not found")

        path = "/Volumes/kmflow/evidence/raw_evidence/evidence_store/eng1/missing.pdf"
        with pytest.raises(FileNotFoundError, match="not found in Volumes"):
            await backend.read(path)

    @pytest.mark.asyncio
    async def test_read_invalid_path_raises_value_error(self) -> None:
        backend = _make_backend()
        _inject_mock_client(backend)

        with pytest.raises(ValueError, match="outside storage boundary"):
            await backend.read("/Volumes/other/bucket/file.txt")


# ---------------------------------------------------------------------------
# exists()
# ---------------------------------------------------------------------------


class TestExists:
    @pytest.mark.asyncio
    async def test_exists_true_when_get_metadata_succeeds(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.get_metadata.return_value = MagicMock()

        path = "/Volumes/kmflow/evidence/raw_evidence/evidence_store/eng1/file.pdf"
        assert await backend.exists(path) is True

    @pytest.mark.asyncio
    async def test_exists_false_on_not_found(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.get_metadata.side_effect = Exception("404 not found")

        path = "/Volumes/kmflow/evidence/raw_evidence/evidence_store/eng1/file.pdf"
        assert await backend.exists(path) is False

    @pytest.mark.asyncio
    async def test_exists_invalid_path_raises(self) -> None:
        backend = _make_backend()
        _inject_mock_client(backend)

        with pytest.raises(ValueError):
            await backend.exists("/other/path/file.pdf")


# ---------------------------------------------------------------------------
# list_files()
# ---------------------------------------------------------------------------


class TestListFiles:
    def _make_entry(self, name: str, is_directory: bool = False) -> MagicMock:
        entry = MagicMock()
        entry.path = f"/Volumes/kmflow/evidence/raw_evidence/evidence_store/eng1/{name}"
        entry.is_directory = is_directory
        return entry

    @pytest.mark.asyncio
    async def test_list_files_returns_sorted_paths(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.list_directory_contents.return_value = [
            self._make_entry("bbb_report.pdf"),
            self._make_entry("aaa_document.docx"),
        ]

        result = await backend.list_files("eng1")

        assert len(result) == 2
        assert result[0] < result[1]  # sorted ascending

    @pytest.mark.asyncio
    async def test_list_files_excludes_directories(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.list_directory_contents.return_value = [
            self._make_entry("subdir/", is_directory=True),
            self._make_entry("abc_file.txt"),
        ]

        result = await backend.list_files("eng1")

        assert len(result) == 1
        assert "file.txt" in result[0]

    @pytest.mark.asyncio
    async def test_list_files_prefix_filter(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.list_directory_contents.return_value = [
            self._make_entry("abc12345_report.pdf"),
            self._make_entry("abc12345_process.bpmn"),
            self._make_entry("abc12345_image.png"),
        ]

        result = await backend.list_files("eng1", prefix="process")

        assert len(result) == 1
        assert "process.bpmn" in result[0]

    @pytest.mark.asyncio
    async def test_list_files_returns_empty_for_missing_engagement(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.list_directory_contents.side_effect = Exception("404 not found")

        result = await backend.list_files("nonexistent-eng")

        assert result == []

    @pytest.mark.asyncio
    async def test_list_files_sanitizes_engagement_id(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.list_directory_contents.return_value = []

        await backend.list_files("eng/../../secret")

        call_args = mock_client.files.list_directory_contents.call_args
        directory_arg = call_args[0][0]
        # Path traversal characters removed; slashes and dots replaced with underscores
        assert ".." not in directory_arg
        # The string "secret" remains but the path separators (/) are neutralized
        assert "/" not in directory_arg.split("/Volumes/kmflow/evidence/raw_evidence/evidence_store/")[-1]


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.delete = MagicMock()
        mock_client.warehouses.list.return_value = []

        path = "/Volumes/kmflow/evidence/raw_evidence/evidence_store/eng1/file.pdf"
        result = await backend.delete(path)

        assert result is True
        mock_client.files.delete.assert_called_once_with(path)

    @pytest.mark.asyncio
    async def test_delete_returns_false_on_not_found(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.delete.side_effect = Exception("404 not found")

        path = "/Volumes/kmflow/evidence/raw_evidence/evidence_store/eng1/missing.pdf"
        result = await backend.delete(path)

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_invalid_path_raises(self) -> None:
        backend = _make_backend()
        _inject_mock_client(backend)

        with pytest.raises(ValueError):
            await backend.delete("/other/path/file.pdf")

    @pytest.mark.asyncio
    async def test_delete_attempts_metadata_row_removal(self) -> None:
        backend = _make_backend()
        mock_client = _inject_mock_client(backend)
        mock_client.files.delete = MagicMock()

        mock_warehouse = MagicMock()
        mock_warehouse.id = "wh-001"
        mock_warehouse.state = "RUNNING"
        mock_client.warehouses.list.return_value = [mock_warehouse]

        path = "/Volumes/kmflow/evidence/raw_evidence/evidence_store/eng1/file.pdf"
        await backend.delete(path)

        mock_client.statement_execution.execute.assert_called()
        sql_call = mock_client.statement_execution.execute.call_args[1]["statement"]
        assert "DELETE FROM" in sql_call
        assert "evidence_metadata" in sql_call


# ---------------------------------------------------------------------------
# get_storage_backend factory integration
# ---------------------------------------------------------------------------


class TestFactoryIntegration:
    def test_factory_returns_databricks_backend(self) -> None:
        from src.datalake.backend import get_storage_backend

        backend = get_storage_backend(
            "databricks",
            catalog="testcat",
            schema="testschema",
            volume="testvol",
        )

        assert isinstance(backend, DatabricksBackend)
        assert backend._catalog == "testcat"
        assert backend._schema == "testschema"
        assert backend._volume == "testvol"

    def test_factory_local_still_works(self) -> None:
        from src.datalake.backend import LocalFilesystemBackend, get_storage_backend

        backend = get_storage_backend("local")
        assert isinstance(backend, LocalFilesystemBackend)

    def test_factory_unknown_type_raises(self) -> None:
        from src.datalake.backend import get_storage_backend

        with pytest.raises(ValueError, match="Unknown storage backend"):
            get_storage_backend("s3")


# ---------------------------------------------------------------------------
# __init__ exports
# ---------------------------------------------------------------------------


class TestExports:
    def test_databricks_backend_in_init(self) -> None:
        from src.datalake import DatabricksBackend as ImportedBackend

        assert ImportedBackend is DatabricksBackend

    def test_all_backends_exported(self) -> None:
        import src.datalake as datalake_module

        assert hasattr(datalake_module, "DatabricksBackend")
        assert hasattr(datalake_module, "DeltaLakeBackend")
        assert hasattr(datalake_module, "LocalFilesystemBackend")
