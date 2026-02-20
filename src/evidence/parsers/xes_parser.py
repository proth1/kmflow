"""XES (eXtensible Event Stream) event log parser.

Parses XES format event logs commonly used in process mining.
Extracts traces and events with their attributes.
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
            parser = etree.XMLParser(resolve_entities=False, no_network=True, dtd_validation=False)
            tree = etree.parse(file_path, parser)
            root = tree.getroot()

            # Handle both namespaced and non-namespaced XES files
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"

            traces = root.findall(f"{ns}trace") if ns else root.findall("trace")
            result.metadata = {
                "file_name": file_name,
                "format": "xes",
                "trace_count": len(traces),
            }

            total_events = 0

            for trace_idx, trace in enumerate(traces):
                trace_attrs = self._extract_attributes(trace, ns)
                trace_name = trace_attrs.get("concept:name", f"Trace-{trace_idx + 1}")

                events = trace.findall(f"{ns}event") if ns else trace.findall("event")
                total_events += len(events)

                event_summaries: list[str] = []
                for event in events:
                    event_attrs = self._extract_attributes(event, ns)
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
                    result.fragments.append(
                        ParsedFragment(
                            fragment_type=FragmentType.TABLE,
                            content=content,
                            metadata={
                                "trace_index": trace_idx,
                                "trace_name": trace_name,
                                "event_count": len(events),
                                **{k: v for k, v in trace_attrs.items() if isinstance(v, (str, int, float))},
                            },
                        )
                    )

            result.metadata["total_events"] = total_events

        except etree.XMLSyntaxError as e:
            result.error = f"Invalid XES XML: {e}"
        except Exception as e:
            logger.exception("Failed to parse XES file: %s", file_name)
            result.error = f"XES parse error: {e}"

        return result

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
