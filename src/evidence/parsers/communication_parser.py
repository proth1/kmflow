"""Communication parser for email and chat export analysis.

Parses email exports (EML, MBOX) and chat exports to extract
communication patterns, key discussions, and stakeholder interactions.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)

# Patterns for email header detection
_EMAIL_HEADERS = re.compile(
    r"^(?:From|To|Subject|Date|Cc|Bcc):\s+.+",
    re.IGNORECASE | re.MULTILINE,
)

# Pattern for chat message format "Name (timestamp): message"
_CHAT_PATTERN = re.compile(
    r"^(.+?)\s*[\[(](\d{1,2}[:/]\d{2}(?:[:/]\d{2})?(?:\s*[AP]M)?)\s*[\])]\s*:?\s*(.+)",
    re.IGNORECASE,
)

# Process-related keywords for filtering relevant discussions
_PROCESS_KEYWORDS = frozenset({
    "process", "workflow", "approval", "review", "sign-off",
    "handoff", "escalation", "exception", "workaround",
    "bottleneck", "delay", "sla", "compliance", "audit",
    "policy", "procedure", "control", "risk",
})


class CommunicationParser(BaseParser):
    """Parser for email and chat communication exports.

    Extracts individual messages, identifies process-relevant discussions,
    and maps communication patterns (who communicates about what).
    """

    supported_formats = [".eml", ".mbox", ".chat", ".msg"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a communication export and extract patterns.

        Args:
            file_path: Path to the communication file.
            file_name: Original filename.

        Returns:
            ParseResult with message fragments and communication metadata.
        """
        result = ParseResult()
        path = Path(file_path)

        if not path.exists():
            result.error = f"File not found: {file_path}"
            return result

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="latin-1")
            except Exception as e:
                result.error = f"Failed to read file: {e}"
                return result

        result.metadata = {
            "file_name": file_name,
            "format": path.suffix.lower().lstrip("."),
        }

        ext = path.suffix.lower()
        if ext in (".eml", ".mbox", ".msg"):
            fragments = self._parse_email(text, file_name)
        else:
            fragments = self._parse_chat(text, file_name)

        result.fragments = fragments
        result.metadata["message_count"] = len(fragments)

        # Count process-relevant messages
        relevant = sum(
            1 for f in fragments if f.metadata.get("process_relevant")
        )
        result.metadata["process_relevant_count"] = relevant

        return result

    def _parse_email(self, text: str, file_name: str) -> list[ParsedFragment]:
        """Parse email content into fragments.

        Splits by email boundaries and extracts headers + body.

        Args:
            text: Raw email text.
            file_name: Source filename.

        Returns:
            List of parsed email fragments.
        """
        fragments: list[ParsedFragment] = []

        # Split multi-message files (mbox format)
        messages = re.split(r"^From\s+\S+@\S+", text, flags=re.MULTILINE)
        if len(messages) <= 1:
            messages = [text]

        for msg in messages:
            msg = msg.strip()
            if not msg:
                continue

            # Extract subject line
            subject_match = re.search(r"^Subject:\s*(.+)", msg, re.IGNORECASE | re.MULTILINE)
            subject = subject_match.group(1).strip() if subject_match else "No subject"

            # Extract body (after blank line)
            parts = msg.split("\n\n", 1)
            body = parts[1].strip() if len(parts) > 1 else msg

            is_relevant = self._is_process_relevant(subject + " " + body)

            fragments.append(
                ParsedFragment(
                    fragment_type=FragmentType.TEXT,
                    content=body[:2000] if len(body) > 2000 else body,
                    metadata={
                        "source": "email",
                        "subject": subject,
                        "file_name": file_name,
                        "process_relevant": is_relevant,
                    },
                )
            )

        return fragments

    def _parse_chat(self, text: str, file_name: str) -> list[ParsedFragment]:
        """Parse chat export into fragments.

        Groups consecutive messages into conversation segments.

        Args:
            text: Raw chat text.
            file_name: Source filename.

        Returns:
            List of parsed chat fragments.
        """
        fragments: list[ParsedFragment] = []
        lines = text.split("\n")
        current_segment: list[str] = []
        segment_participants: set[str] = set()

        for line in lines:
            match = _CHAT_PATTERN.match(line.strip())
            if match:
                sender = match.group(1).strip()
                message = match.group(3).strip()
                segment_participants.add(sender)
                current_segment.append(f"{sender}: {message}")
            elif line.strip():
                current_segment.append(line.strip())

            # Flush segment every 20 messages for manageable fragments
            if len(current_segment) >= 20:
                content = "\n".join(current_segment)
                is_relevant = self._is_process_relevant(content)
                fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.TEXT,
                        content=content,
                        metadata={
                            "source": "chat",
                            "participants": list(segment_participants),
                            "file_name": file_name,
                            "process_relevant": is_relevant,
                        },
                    )
                )
                current_segment = []
                segment_participants = set()

        # Flush remaining
        if current_segment:
            content = "\n".join(current_segment)
            is_relevant = self._is_process_relevant(content)
            fragments.append(
                ParsedFragment(
                    fragment_type=FragmentType.TEXT,
                    content=content,
                    metadata={
                        "source": "chat",
                        "participants": list(segment_participants),
                        "file_name": file_name,
                        "process_relevant": is_relevant,
                    },
                )
            )

        return fragments

    def _is_process_relevant(self, text: str) -> bool:
        """Check if text contains process-related keywords.

        Args:
            text: Text to check.

        Returns:
            True if process keywords found.
        """
        text_lower = text.lower()
        return any(kw in text_lower for kw in _PROCESS_KEYWORDS)
