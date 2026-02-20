"""XES (eXtensible Event Stream) event log parser.

Parses XES format event logs commonly used in process mining.
Extracts traces and events with their attributes.

Uses iterparse for streaming to avoid loading large event logs entirely
into memory. XES logs can contain millions of events.
"""

from __future__ import annotations

import logging
from pathlib import Path

from lxml import etree

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)

XES_NS = {"xes": "http://www.xes-standard.org/"}


class XesParser(BaseParser):
    """Parser for XES event log files."""

    supported_formats = [".xes"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse an XES event log and extract traces and events.

        Args:
            file_path: Path to the .xes file.
            file_name: Original filename.

        Returns:
            ParseResult with structured event data fragments.
        """
        result = ParseResult()
        path = Path(file_path)

        if not path.exists():
            result.error = f"File not found: {file_path}"
            return result

        try:
            result.fragments, result.metadata = self._stream_parse(file_path, file_name)
        except etree.XMLSyntaxError as e:
            result.error = f"Invalid XES XML: {e}"
        except Exception as e:
            logger.exception("Failed to parse XES file: %s", file_name)
            result.error = f"XES parse error: {e}"

        return result

    def _stream_parse(
        self, file_path: str, file_name: str
    ) -> tuple[list[ParsedFragment], dict]:
        """Stream-parse the XES file using iterparse.

        Processes one <trace> element at a time so the full document is
        never held in memory simultaneously.
        """
        fragments: list[ParsedFragment] = []
        trace_count = 0
        total_events = 0

        # Detect namespace from first start element without loading the whole tree
        ns_prefix = ""
        parser_ctx = etree.iterparse(
            file_path,
            events=("start",),
            resolve_entities=False,
            no_network=True,
        )
        try:
            _, root_elem = next(iter(parser_ctx))
            if root_elem.tag.startswith("{"):
                ns_prefix = root_elem.tag.split("}")[0] + "}"
        except StopIteration:
            pass
        finally:
            # Close the iterator to release file handle
            del parser_ctx

        trace_tag = f"{ns_prefix}trace"
        event_tag = f"{ns_prefix}event"

        ctx = etree.iterparse(
            file_path,
            events=("end",),
            tag=trace_tag,
            resolve_entities=False,
            no_network=True,
        )

        for _, trace_elem in ctx:
            trace_attrs = self._extract_attributes(trace_elem, ns_prefix)
            trace_name = trace_attrs.get("concept:name", f"Trace-{trace_count + 1}")

            events = trace_elem.findall(event_tag)
            total_events += len(events)

            event_summaries: list[str] = []
            for event in events:
                event_attrs = self._extract_attributes(event, ns_prefix)
                activity = event_attrs.get("concept:name", "unknown")
                timestamp = event_attrs.get("time:timestamp", "")
                resource = event_attrs.get("org:resource", "")
                lifecycle = event_attrs.get("lifecycle:transition", "")

                parts = [activity]
                if lifecycle:
                    parts.append(f"({lifecycle})")
                if resource:
                    parts.append(f"by {resource}")
                if timestamp:
                    parts.append(f"at {timestamp}")
                event_summaries.append(" ".join(parts))

            if event_summaries:
                content = f"Trace: {trace_name}\n" + "\n".join(
                    f"  {i + 1}. {s}" for i, s in enumerate(event_summaries)
                )
                meta: dict = {
                    "trace_index": trace_count,
                    "trace_name": trace_name,
                    "event_count": len(events),
                    **{k: v for k, v in trace_attrs.items() if isinstance(v, (str, int, float))},
                }
                fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.TABLE,
                        content=content,
                        metadata=meta,
                    )
                )

            trace_count += 1
            # Free parsed element from memory to keep RSS low
            trace_elem.clear()

        metadata: dict = {
            "file_name": file_name,
            "format": "xes",
            "trace_count": trace_count,
            "total_events": total_events,
        }
        return fragments, metadata

    @staticmethod
    def _extract_attributes(element: etree._Element, ns: str) -> dict[str, str]:
        """Extract XES attributes from an element.

        XES attributes are child elements like:
        <string key="concept:name" value="Order"/>
        <date key="time:timestamp" value="2024-01-01T10:00:00"/>
        """
        attrs: dict[str, str] = {}
        attr_types = ["string", "date", "int", "float", "boolean", "id"]
        for attr_type in attr_types:
            for attr_elem in element.findall(f"{ns}{attr_type}"):
                key = attr_elem.get("key", "")
                value = attr_elem.get("value", "")
                if key:
                    attrs[key] = value
        return attrs
