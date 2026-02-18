"""Tests for the evidence processing pipeline."""

from __future__ import annotations

import os
import tempfile
import uuid

import pytest

from src.evidence.pipeline import compute_content_hash, store_file


class TestContentHash:
    """Test suite for content hashing."""

    def test_compute_hash(self) -> None:
        """Should compute SHA-256 hash of file content."""
        content = b"Hello World"
        hash_value = compute_content_hash(content)
        assert len(hash_value) == 64  # SHA-256 hex is 64 chars
        assert hash_value.isalnum()

    def test_same_content_same_hash(self) -> None:
        """Same content should produce same hash."""
        content = b"identical content"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)
        assert hash1 == hash2

    def test_different_content_different_hash(self) -> None:
        """Different content should produce different hashes."""
        hash1 = compute_content_hash(b"content A")
        hash2 = compute_content_hash(b"content B")
        assert hash1 != hash2

    def test_empty_content_hash(self) -> None:
        """Empty content should produce a valid hash."""
        hash_value = compute_content_hash(b"")
        assert len(hash_value) == 64


class TestStoreFile:
    """Test suite for file storage."""

    @pytest.mark.asyncio
    async def test_store_file_creates_file(self) -> None:
        """Should store file to the filesystem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engagement_id = uuid.uuid4()
            file_content = b"test file content"

            path, _meta = await store_file(
                file_content=file_content,
                file_name="test.pdf",
                engagement_id=engagement_id,
                evidence_store=tmpdir,
            )

            assert os.path.exists(path)
            with open(path, "rb") as f:
                assert f.read() == file_content

    @pytest.mark.asyncio
    async def test_store_file_organizes_by_engagement(self) -> None:
        """Should create engagement-specific directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engagement_id = uuid.uuid4()
            await store_file(
                file_content=b"content",
                file_name="doc.pdf",
                engagement_id=engagement_id,
                evidence_store=tmpdir,
            )

            engagement_dir = os.path.join(tmpdir, str(engagement_id))
            assert os.path.isdir(engagement_dir)

    @pytest.mark.asyncio
    async def test_store_file_unique_names(self) -> None:
        """Should create unique filenames to avoid collisions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engagement_id = uuid.uuid4()

            path1, _ = await store_file(
                file_content=b"content1",
                file_name="same.pdf",
                engagement_id=engagement_id,
                evidence_store=tmpdir,
            )
            path2, _ = await store_file(
                file_content=b"content2",
                file_name="same.pdf",
                engagement_id=engagement_id,
                evidence_store=tmpdir,
            )

            assert path1 != path2
            assert os.path.exists(path1)
            assert os.path.exists(path2)
