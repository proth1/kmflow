"""XES (eXtensible Event Stream) importer (Story #332).

Parses IEEE XES (1849-2016) event log files into ``ParsedEvent``
objects using streaming XML parsing. ``ParsedEvent`` is a
pre-canonicalization intermediate that preserves XES-specific
fields (e.g. ``lifecycle_phase``) before conversion to
``CanonicalActivityEvent`` in the integration pipeline.

Uses ``defusedxml`` for XXE and entity-expansion protection since
XES files are untrusted external artifacts.

Supports plain .xes and .xes.gz compressed formats.

Standard XES extensions mapped:
- concept:name → activity_name
- lifecycle:transition → lifecycle_phase
- time:timestamp → timestamp
- org:resource → actor
- org:group → resource
"""

from __future__ import annotations

import contextlib
import gzip
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any
from xml.etree.ElementTree import ParseError

from defusedxml.ElementTree import iterparse

logger = logging.getLogger(__name__)

# Standard attribute key mappings (XES key → ParsedEvent field)
_STANDARD_MAPPINGS: dict[str, str] = {
    "concept:name": "activity_name",
    "lifecycle:transition": "lifecycle_phase",
    "time:timestamp": "timestamp",
    "org:resource": "actor",
    "org:group": "resource",
}

DEFAULT_BATCH_SIZE = 1000


@dataclass
class ImportResult:
    """Result of an XES import operation."""

    total_events: int = 0
    total_traces: int = 0
    batches_committed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.total_events > 0 and len(self.errors) == 0


@dataclass
class ParsedEvent:
    """A single parsed XES event before canonicalization."""

    activity_name: str = ""
    timestamp: str = ""
    actor: str = ""
    lifecycle_phase: str = ""
    resource: str = ""
    case_id: str = ""
    extended_attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_name": self.activity_name,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "lifecycle_phase": self.lifecycle_phase,
            "resource": self.resource,
            "case_id": self.case_id,
            "source_system": "xes_import",
            "extended_attributes": self.extended_attributes,
        }


def _extract_attribute_value(elem: Any) -> tuple[str, Any]:
    """Extract key and value from a XES attribute element.

    XES attributes are typed: <string key="..." value="..."/>,
    <date key="..." value="..."/>, <int key="..." value="..."/>, etc.
    """
    key = elem.get("key", "")
    value = elem.get("value", "")

    tag = elem.tag
    # Strip namespace if present
    if "}" in tag:
        tag = tag.split("}")[1]

    if tag == "int":
        with contextlib.suppress(ValueError, TypeError):
            value = int(value)
    elif tag == "float":
        with contextlib.suppress(ValueError, TypeError):
            value = float(value)
    elif tag == "boolean":
        value = value.lower() in ("true", "1")

    return key, value


def _open_xes_file(path: Path) -> IO[bytes]:
    """Open a .xes or .xes.gz file for reading."""
    if path.name.endswith(".gz"):
        return gzip.open(path, "rb")
    return open(path, "rb")  # noqa: SIM115


def parse_xes_stream(
    source: IO[bytes],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> tuple[list[list[ParsedEvent]], ImportResult]:
    """Parse XES event log from a byte stream using streaming XML.

    Uses iterparse for memory-efficient parsing of large files.
    Events are yielded in batches.

    Args:
        source: Binary file-like object containing XES XML.
        batch_size: Number of events per batch.

    Returns:
        Tuple of (batches of parsed events, import result).
    """
    result = ImportResult()
    all_batches: list[list[ParsedEvent]] = []
    current_batch: list[ParsedEvent] = []

    current_trace_case_id = ""
    current_event: ParsedEvent | None = None
    in_event = False

    try:
        context = iterparse(source, events=("start", "end"))

        for xml_event, elem in context:
            tag = elem.tag
            # Strip namespace
            if "}" in tag:
                tag = tag.split("}")[1]

            if xml_event == "start":
                if tag == "trace":
                    current_trace_case_id = ""
                    result.total_traces += 1
                elif tag == "event":
                    in_event = True
                    current_event = ParsedEvent(case_id=current_trace_case_id)

            elif xml_event == "end":
                if tag == "trace":
                    current_trace_case_id = ""

                elif tag == "event" and current_event is not None:
                    in_event = False
                    result.total_events += 1
                    current_batch.append(current_event)

                    if len(current_batch) >= batch_size:
                        all_batches.append(current_batch)
                        result.batches_committed += 1
                        current_batch = []

                    current_event = None
                    # Free memory for processed elements
                    elem.clear()

                elif tag in ("string", "date", "int", "float", "boolean"):
                    key, value = _extract_attribute_value(elem)

                    if in_event and current_event is not None:
                        # Map standard XES attributes
                        mapped = _STANDARD_MAPPINGS.get(key)
                        if mapped:
                            setattr(current_event, mapped, str(value))
                        else:
                            current_event.extended_attributes[key] = value
                    elif not in_event and key == "concept:name":
                        # Trace-level concept:name = case ID
                        current_trace_case_id = str(value)

                    elem.clear()

    except ParseError as exc:
        result.errors.append(f"XML parse error: {exc}")
        logger.error("XES parse failed: %s", exc)
        return all_batches, result

    # Flush remaining events
    if current_batch:
        all_batches.append(current_batch)
        result.batches_committed += 1

    logger.info(
        "XES import complete: %d events in %d traces (%d batches)",
        result.total_events,
        result.total_traces,
        result.batches_committed,
    )

    return all_batches, result


def parse_xes_file(
    path: str | Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> tuple[list[list[ParsedEvent]], ImportResult]:
    """Parse a XES file from disk.

    Supports both .xes (plain XML) and .xes.gz (gzip compressed) formats.

    Args:
        path: Path to the XES file.
        batch_size: Number of events per batch.

    Returns:
        Tuple of (batches of parsed events, import result).
    """
    file_path = Path(path)
    if not file_path.exists():
        result = ImportResult()
        result.errors.append(f"File not found: {file_path}")
        return [], result

    with _open_xes_file(file_path) as f:
        return parse_xes_stream(f, batch_size=batch_size)


def flatten_batches(batches: list[list[ParsedEvent]]) -> list[ParsedEvent]:
    """Flatten batches into a single list of events."""
    return [event for batch in batches for event in batch]
