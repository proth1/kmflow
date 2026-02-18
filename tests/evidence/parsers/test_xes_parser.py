"""Tests for the XES event log parser."""

from __future__ import annotations

import os

import pytest

from src.core.models import FragmentType
from src.evidence.parsers.xes_parser import XesParser

SAMPLE_XES = """<?xml version="1.0" encoding="utf-8"?>
<log>
  <trace>
    <string key="concept:name" value="Case-001"/>
    <event>
      <string key="concept:name" value="Submit Application"/>
      <date key="time:timestamp" value="2024-01-15T09:00:00"/>
      <string key="org:resource" value="John"/>
      <string key="lifecycle:transition" value="complete"/>
    </event>
    <event>
      <string key="concept:name" value="Review Application"/>
      <date key="time:timestamp" value="2024-01-15T10:30:00"/>
      <string key="org:resource" value="Jane"/>
    </event>
    <event>
      <string key="concept:name" value="Approve"/>
      <date key="time:timestamp" value="2024-01-15T14:00:00"/>
      <string key="org:resource" value="Manager"/>
    </event>
  </trace>
  <trace>
    <string key="concept:name" value="Case-002"/>
    <event>
      <string key="concept:name" value="Submit Application"/>
      <date key="time:timestamp" value="2024-01-16T08:00:00"/>
    </event>
  </trace>
</log>
"""

SAMPLE_XES_NAMESPACED = """<?xml version="1.0" encoding="utf-8"?>
<log xmlns="http://www.xes-standard.org/">
  <trace>
    <string key="concept:name" value="Case-NS"/>
    <event>
      <string key="concept:name" value="Activity A"/>
      <date key="time:timestamp" value="2024-02-01T12:00:00"/>
    </event>
  </trace>
</log>
"""


class TestXesParser:
    """Tests for XesParser."""

    def test_supported_formats(self) -> None:
        parser = XesParser()
        assert ".xes" in parser.supported_formats
        assert parser.can_parse(".xes")
        assert not parser.can_parse(".xml")

    @pytest.mark.asyncio
    async def test_parse_valid_xes(self, tmp_path: str) -> None:
        """Should extract traces and events from valid XES."""
        parser = XesParser()
        xes_path = os.path.join(str(tmp_path), "test.xes")
        with open(xes_path, "w") as f:
            f.write(SAMPLE_XES)

        result = await parser.parse(xes_path, "test.xes")

        assert result.error is None
        assert result.metadata["format"] == "xes"
        assert result.metadata["trace_count"] == 2
        assert result.metadata["total_events"] == 4
        assert len(result.fragments) == 2  # One per trace

        # Check first trace content
        trace1 = result.fragments[0]
        assert trace1.fragment_type == FragmentType.TABLE
        assert "Case-001" in trace1.content
        assert "Submit Application" in trace1.content
        assert "Review Application" in trace1.content
        assert trace1.metadata["event_count"] == 3

        # Check second trace
        trace2 = result.fragments[1]
        assert "Case-002" in trace2.content
        assert trace2.metadata["event_count"] == 1

    @pytest.mark.asyncio
    async def test_parse_namespaced_xes(self, tmp_path: str) -> None:
        """Should handle XES files with XML namespace."""
        parser = XesParser()
        xes_path = os.path.join(str(tmp_path), "ns.xes")
        with open(xes_path, "w") as f:
            f.write(SAMPLE_XES_NAMESPACED)

        result = await parser.parse(xes_path, "ns.xes")

        assert result.error is None
        assert result.metadata["trace_count"] == 1
        assert "Activity A" in result.fragments[0].content

    @pytest.mark.asyncio
    async def test_parse_file_not_found(self) -> None:
        """Should return error for missing file."""
        parser = XesParser()
        result = await parser.parse("/nonexistent/file.xes", "missing.xes")
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_parse_invalid_xml(self, tmp_path: str) -> None:
        """Should return error for invalid XML."""
        parser = XesParser()
        bad_path = os.path.join(str(tmp_path), "bad.xes")
        with open(bad_path, "w") as f:
            f.write("not valid xml <><>")

        result = await parser.parse(bad_path, "bad.xes")
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_parse_empty_log(self, tmp_path: str) -> None:
        """Should handle XES with no traces."""
        parser = XesParser()
        xes_path = os.path.join(str(tmp_path), "empty.xes")
        with open(xes_path, "w") as f:
            f.write('<?xml version="1.0"?><log></log>')

        result = await parser.parse(xes_path, "empty.xes")
        assert result.error is None
        assert result.metadata["trace_count"] == 0
        assert len(result.fragments) == 0

    @pytest.mark.asyncio
    async def test_event_attributes_extraction(self, tmp_path: str) -> None:
        """Should extract resource and lifecycle attributes."""
        parser = XesParser()
        xes_path = os.path.join(str(tmp_path), "attrs.xes")
        with open(xes_path, "w") as f:
            f.write(SAMPLE_XES)

        result = await parser.parse(xes_path, "attrs.xes")

        # First trace should include resource info
        assert "John" in result.fragments[0].content
        assert "complete" in result.fragments[0].content
