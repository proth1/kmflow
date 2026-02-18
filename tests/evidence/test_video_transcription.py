"""Tests for video transcription pipeline (video -> audio -> text).

Tests that the VideoParser._extract_audio method uses AudioParser
for transcription and falls back gracefully.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import FragmentType
from src.evidence.parsers.base import ParsedFragment, ParseResult
from src.evidence.parsers.video_parser import VideoParser


@pytest.fixture
def video_parser() -> VideoParser:
    return VideoParser()


# =============================================================================
# _extract_audio with transcription
# =============================================================================


@pytest.mark.asyncio
async def test_extract_audio_uses_audio_parser_when_transcription_available(
    video_parser: VideoParser, tmp_path: Path
) -> None:
    """When ffmpeg succeeds and WAV has content, AudioParser is invoked for transcription."""
    # Create a fake WAV file with sufficient size
    wav_file = tmp_path / "test.wav"
    wav_file.write_bytes(b"\x00" * 2000)

    # Mock process that succeeds
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    # Mock AudioParser result with transcription fragment
    transcription_fragment = ParsedFragment(
        fragment_type=FragmentType.TEXT,
        content="This is a transcribed meeting about the approval process.",
        metadata={"source": "transcription", "file_name": "test_audio.wav"},
    )
    audio_result = ParseResult()
    audio_result.fragments = [transcription_fragment]

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        patch("tempfile.NamedTemporaryFile") as mock_tmp,
        patch("src.evidence.parsers.audio_parser.AudioParser") as mock_audio_parser_cls,
    ):
        # Make temp file point to our fake WAV
        mock_tmp.return_value.__enter__.return_value.name = str(wav_file)
        mock_audio_parser_cls.return_value.parse = AsyncMock(return_value=audio_result)

        result = await video_parser._extract_audio(str(tmp_path / "meeting.mp4"))

    assert result == "This is a transcribed meeting about the approval process."


@pytest.mark.asyncio
async def test_extract_audio_falls_back_when_no_transcription(video_parser: VideoParser, tmp_path: Path) -> None:
    """When AudioParser returns no transcription fragments, fallback metadata is returned."""
    wav_file = tmp_path / "test.wav"
    wav_file.write_bytes(b"\x00" * 2000)

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    # AudioParser returns only a reference fragment (no transcription)
    ref_fragment = ParsedFragment(
        fragment_type=FragmentType.TEXT,
        content="Audio file: test_audio.wav (wav format)",
        metadata={"source": "audio_reference", "file_name": "test_audio.wav"},
    )
    audio_result = ParseResult()
    audio_result.fragments = [ref_fragment]

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        patch("tempfile.NamedTemporaryFile") as mock_tmp,
        patch("src.evidence.parsers.audio_parser.AudioParser") as mock_audio_parser_cls,
    ):
        mock_tmp.return_value.__enter__.return_value.name = str(wav_file)
        mock_audio_parser_cls.return_value.parse = AsyncMock(return_value=audio_result)

        result = await video_parser._extract_audio(str(tmp_path / "meeting.mp4"))

    # Fallback: returns metadata string about audio
    assert "Audio extracted" in result
    assert "WAV" in result


@pytest.mark.asyncio
async def test_extract_audio_returns_empty_when_ffmpeg_missing(video_parser: VideoParser) -> None:
    """Returns empty string when ffmpeg is not installed."""
    with patch("shutil.which", return_value=None):
        result = await video_parser._extract_audio("/fake/video.mp4")

    assert result == ""


@pytest.mark.asyncio
async def test_extract_audio_returns_empty_when_ffmpeg_fails(video_parser: VideoParser, tmp_path: Path) -> None:
    """Returns empty string when ffmpeg exits with non-zero code."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"error output"))

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        patch("tempfile.NamedTemporaryFile") as mock_tmp,
    ):
        tmp = tmp_path / "test.wav"
        mock_tmp.return_value.__enter__.return_value.name = str(tmp)

        result = await video_parser._extract_audio(str(tmp_path / "video.mp4"))

    assert result == ""


@pytest.mark.asyncio
async def test_extract_audio_returns_empty_when_wav_too_small(video_parser: VideoParser, tmp_path: Path) -> None:
    """Returns empty string when extracted WAV file is too small."""
    wav_file = tmp_path / "test.wav"
    wav_file.write_bytes(b"\x00" * 100)  # Too small (< 1000 bytes)

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    with (
        patch("shutil.which", return_value="/usr/bin/ffmpeg"),
        patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        patch("tempfile.NamedTemporaryFile") as mock_tmp,
    ):
        mock_tmp.return_value.__enter__.return_value.name = str(wav_file)

        result = await video_parser._extract_audio(str(tmp_path / "video.mp4"))

    assert result == ""


# =============================================================================
# Full VideoParser.parse integration
# =============================================================================


@pytest.mark.asyncio
async def test_video_parse_includes_transcription_fragment(tmp_path: Path) -> None:
    """Full parse() returns a transcription fragment when audio is available."""
    video_file = tmp_path / "meeting.mp4"
    video_file.write_bytes(b"\x00" * 100)

    parser = VideoParser()

    with (
        patch.object(parser, "_extract_frames", return_value="640x480, 30 FPS"),
        patch.object(parser, "_extract_audio", return_value="Transcription: quarterly review"),
    ):
        result = await parser.parse(str(video_file), "meeting.mp4")

    # Should have frame info + transcription + reference fragment
    sources = [f.metadata.get("source") for f in result.fragments]
    assert "audio_transcription" in sources
    assert "frame_extraction" in sources


@pytest.mark.asyncio
async def test_video_parse_no_file(tmp_path: Path) -> None:
    """Parse returns error when file does not exist."""
    parser = VideoParser()
    result = await parser.parse(str(tmp_path / "nonexistent.mp4"), "nonexistent.mp4")

    assert result.error is not None
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_video_parse_always_includes_reference_fragment(tmp_path: Path) -> None:
    """Parse always includes a video_reference fragment."""
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"\x00" * 100)

    parser = VideoParser()

    with (
        patch.object(parser, "_extract_frames", return_value=""),
        patch.object(parser, "_extract_audio", return_value=""),
    ):
        result = await parser.parse(str(video_file), "clip.mp4")

    types = [f.metadata.get("type") for f in result.fragments]
    assert "video_reference" in types
