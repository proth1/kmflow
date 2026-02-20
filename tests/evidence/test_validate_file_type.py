"""Tests for validate_file_type in the evidence pipeline.

All tests mock ``python-magic`` via sys.modules so the MIME-type allowlist
logic is tested in isolation, regardless of whether python-magic is installed
(CI has it, local dev may not).
"""

from __future__ import annotations

from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.evidence.pipeline import validate_file_type


def _make_magic_module(return_value: str) -> ModuleType:
    """Create a fake ``magic`` module whose ``from_buffer`` returns *return_value*."""
    mod = ModuleType("magic")
    mod.from_buffer = MagicMock(return_value=return_value)  # type: ignore[attr-defined]
    return mod


class TestValidateFileType:
    """Test suite for validate_file_type()."""

    def test_allowlisted_mime_type_accepted(self) -> None:
        """An allowlisted MIME type should not raise."""
        with patch.dict("sys.modules", {"magic": _make_magic_module("application/pdf")}):
            result = validate_file_type(b"fake pdf content", "report.pdf", mime_type="application/pdf")
        assert result == "application/pdf"

    def test_blocked_mime_type_raises_415(self) -> None:
        """A non-allowlisted MIME type should raise HTTPException 415."""
        with (
            patch.dict("sys.modules", {"magic": _make_magic_module("application/x-executable")}),
            pytest.raises(HTTPException) as exc_info,
        ):
            validate_file_type(b"\x7fELF", "malware.exe", mime_type="application/x-executable")
        assert exc_info.value.status_code == 415
        assert "application/x-executable" in str(exc_info.value.detail)

    def test_octet_stream_accepted(self) -> None:
        """application/octet-stream is allowlisted (used by .bpmn files)."""
        with patch.dict("sys.modules", {"magic": _make_magic_module("application/octet-stream")}):
            result = validate_file_type(b"<bpmn>", "process.bpmn", mime_type="application/octet-stream")
        assert result == "application/octet-stream"

    def test_text_plain_accepted(self) -> None:
        """text/plain should be accepted."""
        with patch.dict("sys.modules", {"magic": _make_magic_module("text/plain")}):
            result = validate_file_type(b"hello world", "notes.txt", mime_type="text/plain")
        assert result == "text/plain"

    def test_csv_accepted(self) -> None:
        """text/csv should be accepted."""
        with patch.dict("sys.modules", {"magic": _make_magic_module("text/csv")}):
            result = validate_file_type(b"a,b,c", "data.csv", mime_type="text/csv")
        assert result == "text/csv"

    def test_image_types_accepted(self) -> None:
        """Common image MIME types should be accepted."""
        for mime in ("image/png", "image/jpeg", "image/gif", "image/svg+xml"):
            with patch.dict("sys.modules", {"magic": _make_magic_module(mime)}):
                result = validate_file_type(b"\x89PNG", "img.png", mime_type=mime)
            assert result == mime

    def test_none_mime_uses_magic_detection(self) -> None:
        """When mime_type is None, magic detection determines the type.
        octet-stream is only accepted for known evidence extensions (.bpmn, .xes, .vsdx).
        """
        with patch.dict("sys.modules", {"magic": _make_magic_module("application/octet-stream")}):
            result = validate_file_type(b"<bpmn>", "process.bpmn", mime_type=None)
        assert result == "application/octet-stream"

    def test_octet_stream_rejected_for_unknown_extension(self) -> None:
        """application/octet-stream with an unknown extension should be rejected."""
        with (
            patch.dict("sys.modules", {"magic": _make_magic_module("application/octet-stream")}),
            pytest.raises(HTTPException) as exc_info,
        ):
            validate_file_type(b"binary data", "file.bin", mime_type=None)
        assert exc_info.value.status_code == 415

    def test_office_document_types_accepted(self) -> None:
        """Microsoft Office MIME types should be accepted."""
        office_types = [
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ]
        for mime in office_types:
            with patch.dict("sys.modules", {"magic": _make_magic_module(mime)}):
                result = validate_file_type(b"PK", "doc.docx", mime_type=mime)
            assert result == mime

    def test_json_accepted(self) -> None:
        """application/json should be accepted."""
        with patch.dict("sys.modules", {"magic": _make_magic_module("application/json")}):
            result = validate_file_type(b'{"key": "value"}', "data.json", mime_type="application/json")
        assert result == "application/json"

    def test_video_mp4_accepted(self) -> None:
        """video/mp4 should be accepted."""
        with patch.dict("sys.modules", {"magic": _make_magic_module("video/mp4")}):
            result = validate_file_type(b"\x00\x00\x00\x1cftyp", "demo.mp4", mime_type="video/mp4")
        assert result == "video/mp4"

    def test_blocked_type_error_message_includes_type(self) -> None:
        """Error detail should name the rejected MIME type."""
        with (
            patch.dict("sys.modules", {"magic": _make_magic_module("application/x-shellscript")}),
            pytest.raises(HTTPException) as exc_info,
        ):
            validate_file_type(b"data", "script.sh", mime_type="application/x-shellscript")
        assert "application/x-shellscript" in exc_info.value.detail

    def test_magic_unavailable_falls_back_to_client_mime(self) -> None:
        """When python-magic is not installed, should fall back to client-provided MIME type."""
        with patch.dict("sys.modules", {"magic": None}):
            result = validate_file_type(b"content", "file.pdf", mime_type="application/pdf")
        assert result == "application/pdf"

    def test_magic_unavailable_none_mime_falls_back_to_octet_stream(self) -> None:
        """When python-magic is unavailable and mime_type is None, falls back to octet-stream.
        Accepted only for known evidence extensions such as .bpmn.
        """
        with patch.dict("sys.modules", {"magic": None}):
            result = validate_file_type(b"<bpmn>", "process.bpmn", mime_type=None)
        assert result == "application/octet-stream"
