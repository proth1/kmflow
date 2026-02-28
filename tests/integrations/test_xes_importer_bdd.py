"""BDD tests for XES event log importer (Story #332).

Tests XES parsing, standard extension mapping, batch processing,
compressed format support, and streaming behavior.
"""

from __future__ import annotations

import gzip
import io
from pathlib import Path

from src.integrations.importers.xes_importer import (
    ImportResult,
    ParsedEvent,
    flatten_batches,
    parse_xes_file,
    parse_xes_stream,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_XES = FIXTURES_DIR / "sample.xes"


class TestValidXESParsing:
    """Scenario 1: Valid XES file parsing to CanonicalActivityEvent."""

    def test_parses_sample_file(self) -> None:
        """Sample XES file is parsed correctly."""
        batches, result = parse_xes_file(SAMPLE_XES)

        assert result.success
        assert result.total_events == 5
        assert result.total_traces == 2

    def test_case_id_preserved(self) -> None:
        """Trace concept:name becomes case_id on events."""
        batches, result = parse_xes_file(SAMPLE_XES)
        events = flatten_batches(batches)

        case1_events = [e for e in events if e.case_id == "Case-001"]
        case2_events = [e for e in events if e.case_id == "Case-002"]

        assert len(case1_events) == 3
        assert len(case2_events) == 2

    def test_event_count_matches(self) -> None:
        """Total imported event count matches XES file."""
        batches, result = parse_xes_file(SAMPLE_XES)
        events = flatten_batches(batches)

        assert len(events) == result.total_events == 5

    def test_file_not_found(self) -> None:
        """Missing file returns error result."""
        batches, result = parse_xes_file("/nonexistent/file.xes")

        assert not result.success
        assert len(result.errors) == 1
        assert "not found" in result.errors[0]


class TestStandardExtensionMapping:
    """Scenario 2: Standard XES extension attribute extraction."""

    def test_concept_name_maps_to_activity_name(self) -> None:
        """concept:name maps to activity_name."""
        batches, _ = parse_xes_file(SAMPLE_XES)
        events = flatten_batches(batches)

        assert events[0].activity_name == "Submit Application"
        assert events[1].activity_name == "Review Application"

    def test_lifecycle_transition_maps_to_lifecycle_phase(self) -> None:
        """lifecycle:transition maps to lifecycle_phase."""
        batches, _ = parse_xes_file(SAMPLE_XES)
        events = flatten_batches(batches)

        assert events[0].lifecycle_phase == "complete"
        assert events[1].lifecycle_phase == "start"
        assert events[2].lifecycle_phase == "complete"

    def test_time_timestamp_maps_to_timestamp(self) -> None:
        """time:timestamp maps to event timestamp in ISO 8601."""
        batches, _ = parse_xes_file(SAMPLE_XES)
        events = flatten_batches(batches)

        assert events[0].timestamp == "2026-01-15T09:00:00Z"
        assert events[3].timestamp == "2026-01-16T08:00:00Z"

    def test_org_resource_maps_to_actor(self) -> None:
        """org:resource maps to actor."""
        batches, _ = parse_xes_file(SAMPLE_XES)
        events = flatten_batches(batches)

        assert events[0].actor == "Alice"
        assert events[1].actor == "Bob"
        assert events[3].actor == "Charlie"
        assert events[4].actor == "Diana"

    def test_org_group_maps_to_resource(self) -> None:
        """org:group maps to resource."""
        xml = b"""<?xml version="1.0"?>
        <log xmlns="http://www.xes-standard.org/">
          <trace>
            <string key="concept:name" value="C1"/>
            <event>
              <string key="concept:name" value="Task A"/>
              <string key="org:resource" value="Alice"/>
              <string key="org:group" value="Engineering"/>
            </event>
          </trace>
        </log>"""
        source = io.BytesIO(xml)
        batches, _ = parse_xes_stream(source)
        events = flatten_batches(batches)

        assert events[0].actor == "Alice"
        assert events[0].resource == "Engineering"

    def test_non_standard_attributes_in_extended(self) -> None:
        """Non-standard attributes stored in extended_attributes."""
        batches, _ = parse_xes_file(SAMPLE_XES)
        events = flatten_batches(batches)

        # First event has department="Sales"
        assert events[0].extended_attributes["department"] == "Sales"

        # Second event has priority=3 (int)
        assert events[1].extended_attributes["priority"] == 3

    def test_typed_attribute_values(self) -> None:
        """XES typed attributes (int, float, boolean) are parsed correctly."""
        batches, _ = parse_xes_file(SAMPLE_XES)
        events = flatten_batches(batches)

        # Last event in Case-002 has cost=150.50 and automated=false
        approve_event = events[4]
        assert approve_event.extended_attributes["cost"] == 150.50
        assert approve_event.extended_attributes["automated"] is False


class TestBatchProcessing:
    """Scenario 3: Batch processing for large files."""

    def test_events_batched_correctly(self) -> None:
        """Events are split into batches of specified size."""
        batches, result = parse_xes_file(SAMPLE_XES, batch_size=2)

        # 5 events / batch_size 2 = 3 batches (2, 2, 1)
        assert len(batches) == 3
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2
        assert len(batches[2]) == 1
        assert result.batches_committed == 3

    def test_single_batch_for_small_file(self) -> None:
        """Small file fits in one batch."""
        batches, result = parse_xes_file(SAMPLE_XES, batch_size=1000)

        assert len(batches) == 1
        assert len(batches[0]) == 5
        assert result.batches_committed == 1

    def test_batch_size_one(self) -> None:
        """Each event in its own batch."""
        batches, result = parse_xes_file(SAMPLE_XES, batch_size=1)

        assert len(batches) == 5
        assert all(len(b) == 1 for b in batches)

    def test_streaming_large_generated_xes(self) -> None:
        """Streaming parser handles many events without DOM loading."""
        # Generate a XES file with 100 events programmatically
        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_parts.append('<log xmlns="http://www.xes-standard.org/">')
        xml_parts.append("<trace>")
        xml_parts.append('<string key="concept:name" value="BigCase"/>')

        for i in range(100):
            xml_parts.append("<event>")
            xml_parts.append(f'<string key="concept:name" value="Activity_{i}"/>')
            xml_parts.append(f'<date key="time:timestamp" value="2026-01-01T{i % 24:02d}:00:00Z"/>')
            xml_parts.append(f'<string key="org:resource" value="Worker_{i % 10}"/>')
            xml_parts.append("</event>")

        xml_parts.append("</trace>")
        xml_parts.append("</log>")

        xes_bytes = "\n".join(xml_parts).encode("utf-8")
        source = io.BytesIO(xes_bytes)

        batches, result = parse_xes_stream(source, batch_size=25)

        assert result.total_events == 100
        assert result.total_traces == 1
        assert len(batches) == 4  # 100 / 25
        assert all(len(b) == 25 for b in batches)


class TestCompressedFormat:
    """Support for .xes.gz compressed files."""

    def test_parse_gzip_xes(self, tmp_path: Path) -> None:
        """Parses .xes.gz compressed files."""
        # Read original, compress, and parse
        xes_content = SAMPLE_XES.read_bytes()
        gz_path = tmp_path / "sample.xes.gz"

        with gzip.open(gz_path, "wb") as f:
            f.write(xes_content)

        batches, result = parse_xes_file(gz_path)

        assert result.success
        assert result.total_events == 5
        assert result.total_traces == 2

    def test_compressed_events_match_uncompressed(self, tmp_path: Path) -> None:
        """Compressed and uncompressed produce identical results."""
        plain_batches, plain_result = parse_xes_file(SAMPLE_XES)
        plain_events = flatten_batches(plain_batches)

        xes_content = SAMPLE_XES.read_bytes()
        gz_path = tmp_path / "sample.xes.gz"
        with gzip.open(gz_path, "wb") as f:
            f.write(xes_content)

        gz_batches, gz_result = parse_xes_file(gz_path)
        gz_events = flatten_batches(gz_batches)

        assert plain_result.total_events == gz_result.total_events
        assert len(plain_events) == len(gz_events)

        for p, g in zip(plain_events, gz_events, strict=True):
            assert p.activity_name == g.activity_name
            assert p.timestamp == g.timestamp
            assert p.actor == g.actor
            assert p.case_id == g.case_id


class TestParsedEventSerialization:
    """ParsedEvent data structure."""

    def test_to_dict(self) -> None:
        event = ParsedEvent(
            activity_name="Test",
            timestamp="2026-01-01T00:00:00Z",
            actor="user1",
            case_id="C1",
        )
        d = event.to_dict()
        assert d["activity_name"] == "Test"
        assert d["source_system"] == "xes_import"
        assert d["case_id"] == "C1"

    def test_import_result_success_flag(self) -> None:
        result = ImportResult(total_events=10, total_traces=2)
        assert result.success

        result_with_errors = ImportResult(total_events=10, errors=["bad"])
        assert not result_with_errors.success

        empty_result = ImportResult()
        assert not empty_result.success

    def test_flatten_batches(self) -> None:
        e1 = ParsedEvent(activity_name="A")
        e2 = ParsedEvent(activity_name="B")
        e3 = ParsedEvent(activity_name="C")

        flat = flatten_batches([[e1, e2], [e3]])
        assert len(flat) == 3
        assert flat[0].activity_name == "A"
        assert flat[2].activity_name == "C"


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_empty_xes(self) -> None:
        """Empty XES log with no traces."""
        xml = b'<?xml version="1.0"?><log xmlns="http://www.xes-standard.org/"></log>'
        source = io.BytesIO(xml)

        batches, result = parse_xes_stream(source)

        assert result.total_events == 0
        assert result.total_traces == 0
        assert len(batches) == 0

    def test_trace_without_events(self) -> None:
        """Trace with no events."""
        xml = b"""<?xml version="1.0"?>
        <log xmlns="http://www.xes-standard.org/">
          <trace>
            <string key="concept:name" value="Empty-Case"/>
          </trace>
        </log>"""
        source = io.BytesIO(xml)

        batches, result = parse_xes_stream(source)

        assert result.total_traces == 1
        assert result.total_events == 0

    def test_event_without_standard_attributes(self) -> None:
        """Event with only non-standard attributes."""
        xml = b"""<?xml version="1.0"?>
        <log xmlns="http://www.xes-standard.org/">
          <trace>
            <string key="concept:name" value="Case-X"/>
            <event>
              <string key="custom_field" value="custom_value"/>
            </event>
          </trace>
        </log>"""
        source = io.BytesIO(xml)

        batches, result = parse_xes_stream(source)

        assert result.total_events == 1
        events = flatten_batches(batches)
        assert events[0].activity_name == ""
        assert events[0].case_id == "Case-X"
        assert events[0].extended_attributes["custom_field"] == "custom_value"

    def test_multiple_traces_streaming(self) -> None:
        """Multiple traces parsed sequentially with correct case IDs."""
        xml = b"""<?xml version="1.0"?>
        <log xmlns="http://www.xes-standard.org/">
          <trace>
            <string key="concept:name" value="T1"/>
            <event><string key="concept:name" value="A"/></event>
          </trace>
          <trace>
            <string key="concept:name" value="T2"/>
            <event><string key="concept:name" value="B"/></event>
          </trace>
          <trace>
            <string key="concept:name" value="T3"/>
            <event><string key="concept:name" value="C"/></event>
          </trace>
        </log>"""
        source = io.BytesIO(xml)

        batches, result = parse_xes_stream(source)
        events = flatten_batches(batches)

        assert result.total_traces == 3
        assert events[0].case_id == "T1"
        assert events[1].case_id == "T2"
        assert events[2].case_id == "T3"

    def test_malformed_xml_returns_error(self) -> None:
        """Malformed XML returns error in ImportResult, not an exception."""
        source = io.BytesIO(b"<not valid xml!!!!!")
        batches, result = parse_xes_stream(source)

        assert not result.success
        assert len(result.errors) == 1
        assert "XML parse error" in result.errors[0]
