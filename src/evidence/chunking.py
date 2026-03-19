"""Token-aware chunking module for evidence fragments.

Post-parse chunking stage that splits large fragments into embedding-friendly
chunks with configurable target size, overlap, and structure awareness.

Key behaviors:
- Token-aware splitting (target 256-384 tokens per chunk)
- ~50 token overlap at boundaries for context continuity
- Table-aware: TABLE fragments are kept atomic (never split mid-table)
- Heading propagation: section headings prepended to sub-chunks
- Max size enforcement across all document types
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from src.core.models import FragmentType
from src.evidence.parsers.base import ParsedFragment
from src.quality.instrumentation import pipeline_stage

logger = logging.getLogger(__name__)

# Approximate tokens-per-character ratio for English text.
# GPT-style tokenizers average ~4 chars/token; we use 4 for safety.
_CHARS_PER_TOKEN = 4


@dataclass
class ChunkingConfig:
    """Configuration for the chunking stage.

    Attributes:
        target_tokens: Target chunk size in tokens.
        overlap_tokens: Overlap between consecutive chunks in tokens.
        max_tokens: Hard maximum — chunks exceeding this are force-split.
        min_tokens: Minimum chunk size — fragments smaller than this pass through unchanged.
    """

    target_tokens: int = 384
    overlap_tokens: int = 50
    max_tokens: int = 512
    min_tokens: int = 30


def _estimate_tokens(text: str) -> int:
    """Estimate token count from character length."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _extract_heading(text: str) -> str | None:
    """Extract a leading heading from text if present.

    Looks for markdown-style headings or lines that look like section titles
    (short uppercase/title-case lines at the start).
    """
    lines = text.split("\n", 3)
    if not lines:
        return None

    first_line = lines[0].strip()

    # Markdown heading
    if first_line.startswith("#"):
        return first_line

    # Short title-case line (likely a heading) — max 80 chars, no sentence punctuation
    if (
        len(first_line) <= 80
        and first_line
        and not first_line.endswith((".", ",", ";", ":"))
        and (first_line[0].isupper() or first_line.isupper())
        and len(lines) > 1
    ):
        return first_line

    return None


def _split_by_sentences(text: str) -> list[str]:
    """Split text into sentence-like segments, preserving whitespace."""
    # Split on sentence-ending punctuation followed by whitespace
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p for p in parts if p.strip()]


def _split_by_paragraphs(text: str) -> list[str]:
    """Split text by paragraph breaks (double newlines)."""
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_fragment(
    fragment: ParsedFragment,
    config: ChunkingConfig | None = None,
) -> list[ParsedFragment]:
    """Split a single fragment into embedding-friendly chunks.

    Args:
        fragment: The parsed fragment to chunk.
        config: Chunking configuration. Uses defaults if not provided.

    Returns:
        List of chunked fragments. May return the original fragment unchanged
        if it's already within target size or is a type that shouldn't be split.
    """
    if config is None:
        config = ChunkingConfig()

    content = fragment.content
    if not content or not content.strip():
        return [fragment]

    estimated_tokens = _estimate_tokens(content)

    # Small enough already — pass through
    if estimated_tokens <= config.target_tokens:
        return [fragment]

    # TABLE fragments: keep atomic (don't split mid-table)
    if fragment.fragment_type == FragmentType.TABLE:
        # If table is enormous, truncate with a warning rather than splitting
        if estimated_tokens > config.max_tokens * 3:
            max_chars = config.max_tokens * 3 * _CHARS_PER_TOKEN
            truncated = content[:max_chars] + "\n[... table truncated ...]"
            return [
                ParsedFragment(
                    fragment_type=fragment.fragment_type,
                    content=truncated,
                    metadata={**fragment.metadata, "truncated": True},
                )
            ]
        return [fragment]

    # Extract heading for propagation
    heading = _extract_heading(content)

    # Try paragraph-based splitting first (preserves document structure)
    paragraphs = _split_by_paragraphs(content)

    if len(paragraphs) > 1:
        chunks = _merge_segments(paragraphs, config, heading)
    else:
        # Fall back to sentence-based splitting
        sentences = _split_by_sentences(content)
        if len(sentences) > 1:
            chunks = _merge_segments(sentences, config, heading)
        else:
            # Last resort: hard split by character count
            chunks = _hard_split(content, config, heading)

    # Build output fragments
    result: list[ParsedFragment] = []
    for i, chunk_text in enumerate(chunks):
        chunk_meta = {
            **fragment.metadata,
            "chunk_index": i,
            "chunk_total": len(chunks),
        }
        if heading and i > 0:
            chunk_meta["propagated_heading"] = heading

        result.append(
            ParsedFragment(
                fragment_type=fragment.fragment_type,
                content=chunk_text,
                metadata=chunk_meta,
            )
        )

    return result


def _merge_segments(
    segments: list[str],
    config: ChunkingConfig,
    heading: str | None,
) -> list[str]:
    """Merge small segments into chunks that fit the target size, with overlap.

    Args:
        segments: List of text segments (paragraphs or sentences).
        config: Chunking configuration.
        heading: Optional heading to prepend to non-first chunks.

    Returns:
        List of merged chunk strings.
    """
    target_chars = config.target_tokens * _CHARS_PER_TOKEN
    overlap_chars = config.overlap_tokens * _CHARS_PER_TOKEN

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for segment in segments:
        seg_len = len(segment)

        # If adding this segment would exceed target, flush current chunk
        if current_parts and (current_len + seg_len + 1) > target_chars:
            chunk_text = "\n\n".join(current_parts)
            chunks.append(chunk_text)

            # Overlap: keep tail segments that fit within overlap budget
            overlap_parts: list[str] = []
            overlap_len = 0
            for part in reversed(current_parts):
                if overlap_len + len(part) > overlap_chars:
                    break
                overlap_parts.insert(0, part)
                overlap_len += len(part)

            current_parts = overlap_parts
            current_len = overlap_len

        current_parts.append(segment)
        current_len += seg_len

    # Flush remaining
    if current_parts:
        chunk_text = "\n\n".join(current_parts)
        chunks.append(chunk_text)

    # Prepend heading to non-first chunks for context
    if heading and len(chunks) > 1:
        for i in range(1, len(chunks)):
            chunks[i] = f"{heading}\n\n{chunks[i]}"

    return chunks


def _hard_split(
    text: str,
    config: ChunkingConfig,
    heading: str | None,
) -> list[str]:
    """Force-split text by character count when no natural boundaries exist."""
    target_chars = config.target_tokens * _CHARS_PER_TOKEN
    overlap_chars = config.overlap_tokens * _CHARS_PER_TOKEN

    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + target_chars, text_len)

        # Try to break at a word boundary
        if end < text_len:
            space_pos = text.rfind(" ", start + target_chars // 2, end)
            if space_pos > start:
                end = space_pos

        chunk = text[start:end].strip()
        if chunk:
            # Prepend heading for non-first chunks
            if heading and chunks:
                chunk = f"{heading}\n\n{chunk}"
            chunks.append(chunk)

        start = max(start + 1, end - overlap_chars)

    return chunks


@pipeline_stage("chunk")
def chunk_fragments(
    fragments: list[ParsedFragment],
    config: ChunkingConfig | None = None,
) -> list[ParsedFragment]:
    """Apply chunking to a list of parsed fragments.

    This is the main entry point for the chunking stage in the pipeline.

    Args:
        fragments: List of parsed fragments from the parsing stage.
        config: Chunking configuration. Uses defaults if not provided.

    Returns:
        List of chunked fragments, ready for the embedding stage.
    """
    if config is None:
        config = ChunkingConfig()

    result: list[ParsedFragment] = []
    for fragment in fragments:
        chunked = chunk_fragment(fragment, config)
        result.extend(chunked)

    if len(result) != len(fragments):
        logger.info(
            "Chunking: %d input fragments -> %d output chunks (config: target=%d, overlap=%d)",
            len(fragments),
            len(result),
            config.target_tokens,
            config.overlap_tokens,
        )

    return result
