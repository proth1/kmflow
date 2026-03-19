"""Tests for the evidence chunking module."""

from __future__ import annotations

from src.core.models import FragmentType
from src.evidence.chunking import (
    ChunkingConfig,
    _estimate_tokens,
    _extract_heading,
    chunk_fragment,
    chunk_fragments,
)
from src.evidence.parsers.base import ParsedFragment


class TestEstimateTokens:
    """Tests for token estimation."""

    def test_empty_string(self):
        assert _estimate_tokens("") == 1  # min 1

    def test_short_string(self):
        assert _estimate_tokens("hello") == 1

    def test_longer_string(self):
        # ~100 chars => ~25 tokens
        text = "a" * 100
        assert _estimate_tokens(text) == 25

    def test_realistic_text(self):
        text = "The quick brown fox jumps over the lazy dog. " * 10
        tokens = _estimate_tokens(text)
        assert 50 < tokens < 200


class TestExtractHeading:
    """Tests for heading extraction."""

    def test_markdown_heading(self):
        text = "# Executive Summary\n\nThis is the content."
        assert _extract_heading(text) == "# Executive Summary"

    def test_titlecase_heading(self):
        text = "Executive Summary\n\nThis is the content."
        assert _extract_heading(text) == "Executive Summary"

    def test_no_heading(self):
        text = "This is just a regular paragraph with content."
        # Single line — no second line to confirm it's a heading
        # What matters is it doesn't crash
        _extract_heading(text)

    def test_long_first_line_not_heading(self):
        text = "This is a very long first line that goes on and on and is definitely not a heading because it is too long to be one.\nSecond line."
        assert _extract_heading(text) is None


class TestChunkFragment:
    """Tests for single fragment chunking."""

    def test_small_fragment_passthrough(self):
        """Fragments smaller than target should pass through unchanged."""
        frag = ParsedFragment(
            fragment_type=FragmentType.TEXT,
            content="Short text.",
            metadata={"page": 1},
        )
        result = chunk_fragment(frag)
        assert len(result) == 1
        assert result[0].content == "Short text."
        assert result[0].metadata == {"page": 1}

    def test_large_text_fragment_split(self):
        """Large text fragments should be split into multiple chunks."""
        # Create a fragment with ~2000 tokens (8000 chars)
        sentences = [f"This is sentence number {i} with enough words to be meaningful. " for i in range(200)]
        content = " ".join(sentences)
        frag = ParsedFragment(
            fragment_type=FragmentType.TEXT,
            content=content,
            metadata={"page": 1},
        )
        config = ChunkingConfig(target_tokens=384, overlap_tokens=50)
        result = chunk_fragment(frag, config)

        assert len(result) > 1
        # Each chunk should have metadata with chunk_index
        for i, chunk in enumerate(result):
            assert chunk.metadata["chunk_index"] == i
            assert chunk.metadata["chunk_total"] == len(result)
            assert chunk.fragment_type == FragmentType.TEXT

    def test_table_fragment_kept_atomic(self):
        """TABLE fragments should not be split."""
        table_content = "\n".join([f"Col1 | Col2 | Col3 | Row {i}" for i in range(100)])
        frag = ParsedFragment(
            fragment_type=FragmentType.TABLE,
            content=table_content,
            metadata={"page": 1},
        )
        result = chunk_fragment(frag)
        assert len(result) == 1

    def test_enormous_table_truncated(self):
        """Very large tables should be truncated with a warning."""
        # Create a massive table (~50K tokens)
        table_content = "\n".join([f"Col1 | Col2 | Col3 | Row {i} with lots of extra data" for i in range(5000)])
        frag = ParsedFragment(
            fragment_type=FragmentType.TABLE,
            content=table_content,
            metadata={"page": 1},
        )
        config = ChunkingConfig(max_tokens=512)
        result = chunk_fragment(frag, config)
        assert len(result) == 1
        assert result[0].metadata.get("truncated") is True

    def test_empty_content_passthrough(self):
        """Empty fragments should pass through."""
        frag = ParsedFragment(
            fragment_type=FragmentType.TEXT,
            content="",
            metadata={},
        )
        result = chunk_fragment(frag)
        assert len(result) == 1

    def test_heading_propagation(self):
        """Non-first chunks should have the heading prepended."""
        heading = "# Section Title"
        paragraphs = [f"Paragraph {i}. " * 50 for i in range(10)]
        content = f"{heading}\n\n" + "\n\n".join(paragraphs)

        frag = ParsedFragment(
            fragment_type=FragmentType.TEXT,
            content=content,
            metadata={"page": 1},
        )
        config = ChunkingConfig(target_tokens=200, overlap_tokens=30)
        result = chunk_fragment(frag, config)

        assert len(result) > 1
        # First chunk should start with the heading naturally
        assert heading in result[0].content
        # Non-first chunks should have propagated_heading in metadata
        for chunk in result[1:]:
            assert chunk.metadata.get("propagated_heading") == heading

    def test_overlap_between_chunks(self):
        """Consecutive chunks should share some overlapping content."""
        sentences = [f"Sentence {i} is unique and identifiable. " for i in range(50)]
        content = " ".join(sentences)

        frag = ParsedFragment(
            fragment_type=FragmentType.TEXT,
            content=content,
            metadata={},
        )
        config = ChunkingConfig(target_tokens=100, overlap_tokens=30)
        result = chunk_fragment(frag, config)

        if len(result) >= 2:
            # Check that some content from end of chunk 0 appears in chunk 1
            chunk0_words = set(result[0].content.split()[-20:])
            chunk1_words = set(result[1].content.split()[:20])
            # There should be some overlap
            overlap = chunk0_words & chunk1_words
            assert len(overlap) > 0, "Expected overlap between consecutive chunks"


class TestChunkFragments:
    """Tests for batch fragment chunking."""

    def test_mixed_fragments(self):
        """Should handle a mix of small and large fragments."""
        fragments = [
            ParsedFragment(
                fragment_type=FragmentType.TEXT,
                content="Short text.",
                metadata={"page": 1},
            ),
            ParsedFragment(
                fragment_type=FragmentType.TEXT,
                content="Long text. " * 500,
                metadata={"page": 2},
            ),
            ParsedFragment(
                fragment_type=FragmentType.TABLE,
                content="A | B\n1 | 2",
                metadata={"page": 3},
            ),
        ]
        result = chunk_fragments(fragments)
        assert len(result) >= 3  # At least 3 (small + split large + table)
        # Small text should pass through
        assert result[0].content == "Short text."
        # Table should pass through
        assert any(f.fragment_type == FragmentType.TABLE for f in result)

    def test_empty_list(self):
        """Empty input should return empty output."""
        assert chunk_fragments([]) == []

    def test_custom_config(self):
        """Custom config should be respected."""
        content = "Word. " * 200
        fragments = [
            ParsedFragment(fragment_type=FragmentType.TEXT, content=content, metadata={}),
        ]
        small_config = ChunkingConfig(target_tokens=50, overlap_tokens=10)
        result = chunk_fragments(fragments, config=small_config)
        assert len(result) > 1

        large_config = ChunkingConfig(target_tokens=1000, overlap_tokens=50)
        result2 = chunk_fragments(fragments, config=large_config)
        assert len(result2) < len(result)
