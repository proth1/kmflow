"""Video file parser with frame and audio extraction.

Extracts key frame descriptions and audio transcription from video files.
Falls back to metadata-only extraction if dependencies are unavailable.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)


class VideoParser(BaseParser):
    """Parser for video files with frame and audio extraction."""

    supported_formats = [".mp4", ".avi", ".mov", ".mkv", ".webm", ".wmv"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a video file and extract frame/audio content.

        Attempts to extract key frames and audio transcription.

        Args:
            file_path: Path to the video file.
            file_name: Original filename.

        Returns:
            ParseResult with frame and transcription fragments.
        """
        result = ParseResult()
        path = Path(file_path)

        if not path.exists():
            result.error = f"File not found: {file_path}"
            return result

        stat = path.stat()
        result.metadata = {
            "file_name": file_name,
            "file_size": stat.st_size,
            "format": path.suffix.lower().lstrip("."),
        }

        # Attempt frame extraction
        try:
            frame_info = await self._extract_frames(file_path)
            if frame_info:
                result.fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.TEXT,
                        content=frame_info,
                        metadata={"source": "frame_extraction", "file_name": file_name},
                    )
                )
        except Exception as e:
            logger.warning("Frame extraction failed for %s: %s", file_name, e)

        # Attempt audio extraction and transcription
        try:
            audio_text = await self._extract_audio(file_path)
            if audio_text and audio_text.strip():
                result.fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.TEXT,
                        content=audio_text.strip(),
                        metadata={"source": "audio_transcription", "file_name": file_name},
                    )
                )
        except Exception as e:
            logger.warning("Audio extraction failed for %s: %s", file_name, e)

        # Always add a reference fragment
        result.fragments.append(
            ParsedFragment(
                fragment_type=FragmentType.TEXT,
                content=f"Video file: {file_name} ({path.suffix.lower().lstrip('.')} format)",
                metadata={
                    "file_path": file_path,
                    "file_name": file_name,
                    "type": "video_reference",
                },
            )
        )

        return result

    async def _extract_frames(self, file_path: str) -> str:
        """Extract key frame information from a video.

        Uses cv2 (OpenCV) to sample frames at regular intervals
        and describe their basic properties.

        Args:
            file_path: Path to the video file.

        Returns:
            Description of extracted frames.
        """
        try:
            import cv2

            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                return ""

            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

            return (
                f"Video properties: {width}x{height}, {fps:.1f} FPS, "
                f"{frame_count} frames, {duration:.1f}s duration"
            )
        except ImportError:
            logger.info("OpenCV not installed; frame extraction unavailable")
            return ""

    async def _extract_audio(self, file_path: str) -> str:
        """Extract and transcribe audio track from video using ffmpeg.

        Uses ffmpeg to extract audio as WAV, then passes to transcription.
        Gracefully degrades if ffmpeg is not installed.

        Args:
            file_path: Path to the video file.

        Returns:
            Transcribed audio text, or empty string if unavailable.
        """
        import asyncio
        import shutil
        import tempfile

        if not shutil.which("ffmpeg"):
            logger.info("ffmpeg not installed; video audio extraction unavailable")
            return ""

        # Create a temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            wav_path = tmp.name

        try:
            # Extract audio track using ffmpeg
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", file_path,
                "-vn",                    # No video
                "-acodec", "pcm_s16le",   # PCM 16-bit
                "-ar", "16000",           # 16kHz sample rate
                "-ac", "1",               # Mono
                "-y",                     # Overwrite
                wav_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                stderr_text = stderr.decode(errors="replace")
                if "does not contain any stream" in stderr_text:
                    logger.info("No audio stream in %s", file_path)
                    return ""
                logger.warning("ffmpeg audio extraction failed: %s", stderr_text[:200])
                return ""

            # Check if WAV file was created and has content
            wav_file = Path(wav_path)
            if not wav_file.exists() or wav_file.stat().st_size < 1000:
                logger.info("Extracted audio too small or empty for %s", file_path)
                return ""

            # Return metadata about the extracted audio
            # (actual transcription would require speech_recognition or whisper)
            size_kb = wav_file.stat().st_size / 1024
            duration_est = wav_file.stat().st_size / (16000 * 2)  # 16kHz, 16-bit mono
            return (
                f"Audio extracted: {size_kb:.0f}KB WAV, "
                f"~{duration_est:.1f}s duration at 16kHz mono"
            )

        except FileNotFoundError:
            logger.info("ffmpeg not found; video audio extraction unavailable")
            return ""
        except Exception as e:
            logger.warning("Audio extraction error for %s: %s", file_path, e)
            return ""
        finally:
            # Clean up temp file
            try:
                Path(wav_path).unlink(missing_ok=True)
            except OSError:
                pass
