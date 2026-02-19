"""Tests for validate_file_type in the evidence pipeline."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.evidence.pipeline import validate_file_type


class TestValidateFileType:
    """Test suite for validate_file_type()."""

    def test_allowlisted_mime_type_accepted(self) -> None:
        """An allowlisted MIME type should not raise."""
        result = validate_file_type(b"fake pdf content", "report.pdf", mime_type="application/pdf")
        assert result == "application/pdf"

    def test_blocked_mime_type_raises_415(self) -> None:
        """A non-allowlisted MIME type should raise HTTPException 415."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_type(b"\x7fELF", "malware.exe", mime_type="application/x-executable")
        assert exc_info.value.status_code == 415
        assert "application/x-executable" in str(exc_info.value.detail)

    def test_octet_stream_accepted(self) -> None:
        """application/octet-stream is allowlisted (used by .bpmn files)."""
        result = validate_file_type(b"<bpmn>", "process.bpmn", mime_type="application/octet-stream")
        assert result == "application/octet-stream"

    def test_text_plain_accepted(self) -> None:
        """text/plain should be accepted."""
        result = validate_file_type(b"hello world", "notes.txt", mime_type="text/plain")
        assert result == "text/plain"

    def test_csv_accepted(self) -> None:
        """text/csv should be accepted."""
        result = validate_file_type(b"a,b,c", "data.csv", mime_type="text/csv")
        assert result == "text/csv"

    def test_image_types_accepted(self) -> None:
        """Common image MIME types should be accepted."""
        for mime in ("image/png", "image/jpeg", "image/gif", "image/svg+xml"):
            result = validate_file_type(b"\x89PNG", "img.png", mime_type=mime)
            assert result == mime

    def test_none_mime_uses_fallback(self) -> None:
        """When mime_type is None, should fall back to octet-stream (which is allowlisted)."""
        # Without python-magic, falls back to "application/octet-stream"
        result = validate_file_type(b"some content", "file.bin", mime_type=None)
        # Should not raise - octet-stream is in the allowlist
        assert isinstance(result, str)

    def test_office_document_types_accepted(self) -> None:
        """Microsoft Office MIME types should be accepted."""
        office_types = [
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ]
        for mime in office_types:
            result = validate_file_type(b"PK", "doc.docx", mime_type=mime)
            assert result == mime

    def test_json_accepted(self) -> None:
        """application/json should be accepted."""
        result = validate_file_type(b'{"key": "value"}', "data.json", mime_type="application/json")
        assert result == "application/json"

    def test_video_mp4_accepted(self) -> None:
        """video/mp4 should be accepted."""
        result = validate_file_type(b"\x00\x00\x00\x1cftyp", "demo.mp4", mime_type="video/mp4")
        assert result == "video/mp4"

    def test_blocked_type_error_message_includes_type(self) -> None:
        """Error detail should name the rejected MIME type."""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_type(b"data", "script.sh", mime_type="application/x-shellscript")
        assert "application/x-shellscript" in exc_info.value.detail
