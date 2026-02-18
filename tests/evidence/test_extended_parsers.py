"""Tests for extended evidence parsers (image, audio, video, regulatory, communication)."""

from __future__ import annotations

import tempfile

import pytest

from src.core.models import FragmentType
from src.evidence.parsers.audio_parser import AudioParser
from src.evidence.parsers.communication_parser import CommunicationParser
from src.evidence.parsers.factory import classify_by_extension, get_parser
from src.evidence.parsers.image_parser import ImageParser
from src.evidence.parsers.regulatory_parser import RegulatoryParser
from src.evidence.parsers.video_parser import VideoParser

# -- ImageParser Tests -------------------------------------------------------


class TestImageParser:
    """Tests for image parser with OCR."""

    def test_supported_formats(self) -> None:
        parser = ImageParser()
        assert parser.can_parse(".png")
        assert parser.can_parse(".jpg")
        assert parser.can_parse(".jpeg")
        assert parser.can_parse(".tiff")
        assert parser.can_parse(".bmp")
        assert not parser.can_parse(".pdf")

    @pytest.mark.asyncio
    async def test_parse_nonexistent_file(self) -> None:
        parser = ImageParser()
        result = await parser.parse("/nonexistent/image.png", "image.png")
        assert result.error is not None
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_parse_image_file(self) -> None:
        """Parse a minimal image file (OCR may not extract text)."""
        parser = ImageParser()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            # Write a minimal PNG header
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            f.flush()

            result = await parser.parse(f.name, "test.png")

        # Should have at least the reference fragment
        assert len(result.fragments) >= 1
        image_frags = [f for f in result.fragments if f.fragment_type == FragmentType.IMAGE]
        assert len(image_frags) == 1
        assert result.metadata["format"] == "png"


# -- AudioParser Tests -------------------------------------------------------


class TestAudioParser:
    """Tests for audio parser with transcription."""

    def test_supported_formats(self) -> None:
        parser = AudioParser()
        assert parser.can_parse(".mp3")
        assert parser.can_parse(".wav")
        assert parser.can_parse(".m4a")
        assert parser.can_parse(".ogg")
        assert not parser.can_parse(".pdf")

    @pytest.mark.asyncio
    async def test_parse_nonexistent_file(self) -> None:
        parser = AudioParser()
        result = await parser.parse("/nonexistent/audio.mp3", "audio.mp3")
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_parse_audio_file(self) -> None:
        """Parse a minimal audio file (transcription may not be available)."""
        parser = AudioParser()
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"\x00" * 100)
            f.flush()

            result = await parser.parse(f.name, "meeting.mp3")

        assert len(result.fragments) >= 1
        assert result.metadata["format"] == "mp3"


# -- VideoParser Tests -------------------------------------------------------


class TestVideoParser:
    """Tests for video parser."""

    def test_supported_formats(self) -> None:
        parser = VideoParser()
        assert parser.can_parse(".mp4")
        assert parser.can_parse(".avi")
        assert parser.can_parse(".mov")
        assert not parser.can_parse(".mp3")

    @pytest.mark.asyncio
    async def test_parse_nonexistent_file(self) -> None:
        parser = VideoParser()
        result = await parser.parse("/nonexistent/video.mp4", "video.mp4")
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_parse_video_file(self) -> None:
        parser = VideoParser()
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00" * 100)
            f.flush()

            result = await parser.parse(f.name, "demo.mp4")

        assert len(result.fragments) >= 1
        assert result.metadata["format"] == "mp4"


# -- RegulatoryParser Tests --------------------------------------------------


class TestRegulatoryParser:
    """Tests for regulatory clause parser."""

    def test_supported_formats(self) -> None:
        parser = RegulatoryParser()
        assert parser.can_parse(".reg")
        assert parser.can_parse(".policy")
        assert not parser.can_parse(".pdf")

    @pytest.mark.asyncio
    async def test_parse_nonexistent_file(self) -> None:
        parser = RegulatoryParser()
        result = await parser.parse("/nonexistent/policy.reg", "policy.reg")
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_parse_regulatory_document(self) -> None:
        """Parse a regulatory document with clauses."""
        parser = RegulatoryParser()
        content = """Section 1.1 Data Retention
Organizations shall retain financial records for a minimum of seven (7) years.

Section 1.2 Access Control
Access to sensitive data must be restricted to authorized personnel only.

Section 1.3 Audit Requirements
Organizations are required to maintain comprehensive audit trails.
"""
        with tempfile.NamedTemporaryFile(suffix=".reg", delete=False, mode="w") as f:
            f.write(content)
            f.flush()

            result = await parser.parse(f.name, "data_policy.reg")

        assert len(result.fragments) >= 3
        assert result.metadata["clause_count"] >= 3

        # Check obligation detection
        obligation_frags = [
            f for f in result.fragments if f.metadata.get("has_obligation")
        ]
        assert len(obligation_frags) >= 2  # "shall" and "must" and "required"

    @pytest.mark.asyncio
    async def test_parse_document_paragraph_fallback(self) -> None:
        """Parse document without clause numbering (paragraph fallback)."""
        parser = RegulatoryParser()
        content = """This policy defines data handling procedures.

All employees must follow these guidelines when processing data.

Violations will result in disciplinary action."""

        with tempfile.NamedTemporaryFile(suffix=".policy", delete=False, mode="w") as f:
            f.write(content)
            f.flush()

            result = await parser.parse(f.name, "general.policy")

        assert len(result.fragments) >= 2


# -- CommunicationParser Tests -----------------------------------------------


class TestCommunicationParser:
    """Tests for communication parser."""

    def test_supported_formats(self) -> None:
        parser = CommunicationParser()
        assert parser.can_parse(".eml")
        assert parser.can_parse(".mbox")
        assert parser.can_parse(".chat")
        assert not parser.can_parse(".pdf")

    @pytest.mark.asyncio
    async def test_parse_nonexistent_file(self) -> None:
        parser = CommunicationParser()
        result = await parser.parse("/nonexistent/mail.eml", "mail.eml")
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_parse_email(self) -> None:
        """Parse an email file with headers and body."""
        parser = CommunicationParser()
        content = """From: alice@example.com
To: bob@example.com
Subject: Process Review Meeting Notes

Hi Bob,

We discussed the approval workflow bottleneck during today's meeting.
The current process requires three sign-offs which creates delays.

Best,
Alice
"""
        with tempfile.NamedTemporaryFile(suffix=".eml", delete=False, mode="w") as f:
            f.write(content)
            f.flush()

            result = await parser.parse(f.name, "meeting_notes.eml")

        assert len(result.fragments) >= 1
        assert result.metadata["message_count"] >= 1
        # Should detect process-relevant keywords
        assert result.metadata["process_relevant_count"] >= 1

    @pytest.mark.asyncio
    async def test_parse_chat(self) -> None:
        """Parse a chat export file."""
        parser = CommunicationParser()
        content = """Alice [10:00]: Has everyone reviewed the new compliance process?
Bob [10:02]: Yes, the approval workflow needs a review step
Carol [10:05]: I noticed a bottleneck in the escalation path
Alice [10:07]: Let's discuss the workaround in the next meeting
"""
        with tempfile.NamedTemporaryFile(suffix=".chat", delete=False, mode="w") as f:
            f.write(content)
            f.flush()

            result = await parser.parse(f.name, "team_chat.chat")

        assert len(result.fragments) >= 1
        assert result.metadata["process_relevant_count"] >= 1


# -- Factory Integration Tests -----------------------------------------------


class TestFactoryIntegration:
    """Tests for parser factory with new parsers."""

    def test_image_parser_registered(self) -> None:
        parser = get_parser("screenshot.png")
        assert parser is not None
        assert isinstance(parser, ImageParser)

    def test_audio_parser_registered(self) -> None:
        parser = get_parser("meeting.mp3")
        assert parser is not None
        assert isinstance(parser, AudioParser)

    def test_video_parser_registered(self) -> None:
        parser = get_parser("demo.mp4")
        assert parser is not None
        assert isinstance(parser, VideoParser)

    def test_regulatory_parser_registered(self) -> None:
        parser = get_parser("policy.reg")
        assert parser is not None
        assert isinstance(parser, RegulatoryParser)

    def test_communication_parser_registered(self) -> None:
        parser = get_parser("email.eml")
        assert parser is not None
        assert isinstance(parser, CommunicationParser)

    def test_classify_new_extensions(self) -> None:
        assert classify_by_extension("test.mp3") == "audio"
        assert classify_by_extension("test.mp4") == "video"
        assert classify_by_extension("test.reg") == "regulatory_policy"
        assert classify_by_extension("test.eml") == "domain_communications"
        assert classify_by_extension("test.tiff") == "images"
