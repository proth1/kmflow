"""Controls and evidence parser for audit/compliance artifacts.

Handles control matrices (.ctrl), audit trails (.audit), and
monitoring outputs (.monitor). Extracts structured control data,
audit entries, and monitoring results.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)

# Control effectiveness keywords
_EFFECTIVENESS_KEYWORDS = frozenset(
    {
        "effective",
        "ineffective",
        "partially_effective",
        "not_tested",
        "not_applicable",
    }
)


class ControlsParser(BaseParser):
    """Parser for controls, audit trails, and monitoring evidence.

    Routes by extension:
    - .ctrl → control matrices (CSV/XLSX format)
    - .audit → audit trail logs (CSV format)
    - .monitor → monitoring outputs (JSON format)
    """

    supported_formats = [".ctrl", ".audit", ".monitor"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a controls/evidence file.

        Routes to the appropriate sub-parser based on file extension.

        Args:
            file_path: Path to the file.
            file_name: Original filename.

        Returns:
            ParseResult with control/audit fragments and metadata.
        """
        path = Path(file_path)
        if not path.exists():
            return ParseResult(error=f"File not found: {file_path}")

        ext = Path(file_name).suffix.lower()
        try:
            if ext == ".ctrl":
                return await self._parse_control_matrix(path, file_name)
            elif ext == ".audit":
                return await self._parse_audit_trail(path, file_name)
            elif ext == ".monitor":
                return await self._parse_monitoring_output(path, file_name)
            else:
                return ParseResult(error=f"Unsupported controls format: {ext}")
        except Exception as e:
            logger.exception("Failed to parse controls file: %s", file_name)
            return ParseResult(error=f"Controls parse error: {e}")

    async def _parse_control_matrix(self, path: Path, file_name: str) -> ParseResult:
        """Parse a control matrix file (CSV or XLSX format).

        Extracts individual controls with their IDs, types, descriptions,
        and effectiveness ratings.

        Args:
            path: File path.
            file_name: Original filename.

        Returns:
            ParseResult with TABLE and TEXT fragments.
        """
        fragments: list[ParsedFragment] = []

        # Try reading as CSV first
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = path.read_text(encoding="latin-1")

        reader = csv.DictReader(io.StringIO(raw))
        rows = list(reader)

        if not rows:
            return ParseResult(
                fragments=[],
                metadata={"file_name": file_name, "evidence_category": "controls_evidence", "control_count": 0},
            )

        # Full table fragment
        table_lines = []
        headers = list(rows[0].keys()) if rows else []
        table_lines.append(" | ".join(headers))
        for row in rows:
            table_lines.append(" | ".join(str(row.get(h, "")) for h in headers))

        fragments.append(
            ParsedFragment(
                fragment_type=FragmentType.TABLE,
                content="\n".join(table_lines),
                metadata={
                    "row_count": len(rows),
                    "column_count": len(headers),
                    "source": "control_matrix",
                },
            )
        )

        # Extract individual control descriptions
        control_count = 0
        for row in rows:
            control_id = row.get("control_id") or row.get("Control ID") or row.get("id", "")
            control_type = row.get("control_type") or row.get("Control Type") or row.get("type", "")
            description = row.get("description") or row.get("Description") or ""
            effectiveness = row.get("effectiveness") or row.get("Effectiveness") or row.get("rating", "")

            if description:
                fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.TEXT,
                        content=description,
                        metadata={
                            "control_id": control_id,
                            "control_type": control_type,
                            "effectiveness_rating": effectiveness,
                            "source": "control_description",
                        },
                    )
                )
                control_count += 1

        return ParseResult(
            fragments=fragments,
            metadata={
                "file_name": file_name,
                "evidence_category": "controls_evidence",
                "parser": "controls",
                "control_count": control_count,
                "total_rows": len(rows),
            },
        )

    async def _parse_audit_trail(self, path: Path, file_name: str) -> ParseResult:
        """Parse an audit trail log file (CSV format).

        Extracts audit entries with timestamps, actors, and actions.

        Args:
            path: File path.
            file_name: Original filename.

        Returns:
            ParseResult with TABLE fragment and audit metadata.
        """
        fragments: list[ParsedFragment] = []

        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = path.read_text(encoding="latin-1")

        reader = csv.DictReader(io.StringIO(raw))
        rows = list(reader)

        if not rows:
            return ParseResult(
                fragments=[],
                metadata={"file_name": file_name, "evidence_category": "controls_evidence", "entry_count": 0},
            )

        # Full table
        headers = list(rows[0].keys())
        table_lines = [" | ".join(headers)]
        for row in rows:
            table_lines.append(" | ".join(str(row.get(h, "")) for h in headers))

        fragments.append(
            ParsedFragment(
                fragment_type=FragmentType.TABLE,
                content="\n".join(table_lines),
                metadata={
                    "row_count": len(rows),
                    "column_count": len(headers),
                    "source": "audit_trail",
                },
            )
        )

        # Extract unique actors and actions for metadata
        actors = {row.get("actor") or row.get("Actor") or row.get("user", "") for row in rows}
        actions = {row.get("action") or row.get("Action") or row.get("event", "") for row in rows}

        return ParseResult(
            fragments=fragments,
            metadata={
                "file_name": file_name,
                "evidence_category": "controls_evidence",
                "parser": "controls",
                "entry_count": len(rows),
                "unique_actors": sorted(a for a in actors if a),
                "unique_actions": sorted(a for a in actions if a),
            },
        )

    async def _parse_monitoring_output(self, path: Path, file_name: str) -> ParseResult:
        """Parse a monitoring output file (JSON format).

        Extracts monitoring results, alerts, and metrics.

        Args:
            path: File path.
            file_name: Original filename.

        Returns:
            ParseResult with TEXT/TABLE fragments and monitoring metadata.
        """
        fragments: list[ParsedFragment] = []

        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return ParseResult(error=f"Invalid JSON in monitoring file: {e}")
        except Exception as e:
            return ParseResult(error=f"Failed to read monitoring file: {e}")

        if isinstance(data, list):
            # Array of monitoring records
            content = json.dumps(data, indent=2, default=str)
            fragments.append(
                ParsedFragment(
                    fragment_type=FragmentType.TABLE,
                    content=content,
                    metadata={"record_count": len(data), "source": "monitoring_output"},
                )
            )
            record_count = len(data)
        elif isinstance(data, dict):
            # Single monitoring report
            content = json.dumps(data, indent=2, default=str)
            fragments.append(
                ParsedFragment(
                    fragment_type=FragmentType.TEXT,
                    content=content,
                    metadata={"key_count": len(data), "source": "monitoring_output"},
                )
            )
            record_count = 1

            # Extract summary if present
            if "summary" in data or "results" in data:
                summary = data.get("summary") or data.get("results")
                if isinstance(summary, (dict, list)):
                    fragments.append(
                        ParsedFragment(
                            fragment_type=FragmentType.TEXT,
                            content=json.dumps(summary, indent=2, default=str),
                            metadata={"source": "monitoring_summary"},
                        )
                    )
        else:
            fragments.append(
                ParsedFragment(
                    fragment_type=FragmentType.TEXT,
                    content=str(data),
                    metadata={"source": "monitoring_output"},
                )
            )
            record_count = 1

        return ParseResult(
            fragments=fragments,
            metadata={
                "file_name": file_name,
                "evidence_category": "controls_evidence",
                "parser": "controls",
                "record_count": record_count,
            },
        )
