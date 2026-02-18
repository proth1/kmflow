"""Tests for the Controls/Evidence parser."""

from __future__ import annotations

import json
import os

import pytest

from src.core.models import FragmentType
from src.evidence.parsers.controls_parser import ControlsParser

SAMPLE_CTRL_CSV = """control_id,control_type,description,effectiveness
CTRL-001,preventive,Access control for admin panel,effective
CTRL-002,detective,Log monitoring for anomalies,partially_effective
CTRL-003,corrective,Incident response procedure,ineffective
"""

SAMPLE_AUDIT_CSV = """timestamp,actor,action,resource,details
2024-01-15T09:00:00Z,admin,login,system,Successful login
2024-01-15T09:15:00Z,admin,modify,user_roles,Changed role for user123
2024-01-15T10:00:00Z,auditor,review,audit_log,Quarterly review
"""

SAMPLE_MONITOR_JSON = json.dumps(
    {
        "monitor_id": "MON-001",
        "check_time": "2024-01-15T12:00:00Z",
        "summary": {
            "total_checks": 50,
            "passed": 47,
            "failed": 3,
        },
        "results": [
            {"check": "disk_space", "status": "pass"},
            {"check": "memory_usage", "status": "fail", "value": "95%"},
        ],
    }
)


class TestControlsParser:
    """Tests for ControlsParser."""

    def test_supported_formats(self) -> None:
        parser = ControlsParser()
        assert ".ctrl" in parser.supported_formats
        assert ".audit" in parser.supported_formats
        assert ".monitor" in parser.supported_formats
        assert parser.can_parse(".ctrl")
        assert not parser.can_parse(".csv")

    @pytest.mark.asyncio
    async def test_parse_control_matrix(self, tmp_path: str) -> None:
        """Should extract controls from CSV matrix."""
        parser = ControlsParser()
        fp = os.path.join(str(tmp_path), "controls.ctrl")
        with open(fp, "w") as f:
            f.write(SAMPLE_CTRL_CSV)

        result = await parser.parse(fp, "controls.ctrl")

        assert result.error is None
        assert result.metadata["evidence_category"] == "controls_evidence"
        assert result.metadata["control_count"] == 3

        # Should have TABLE fragment
        table_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TABLE]
        assert len(table_frags) == 1
        assert "CTRL-001" in table_frags[0].content

        # Should have TEXT fragments for each control description
        text_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TEXT]
        assert len(text_frags) == 3
        assert text_frags[0].metadata.get("control_id") == "CTRL-001"
        assert text_frags[0].metadata.get("effectiveness_rating") == "effective"

    @pytest.mark.asyncio
    async def test_parse_audit_trail(self, tmp_path: str) -> None:
        """Should extract audit trail entries."""
        parser = ControlsParser()
        fp = os.path.join(str(tmp_path), "trail.audit")
        with open(fp, "w") as f:
            f.write(SAMPLE_AUDIT_CSV)

        result = await parser.parse(fp, "trail.audit")

        assert result.error is None
        assert result.metadata["entry_count"] == 3
        assert "admin" in result.metadata["unique_actors"]
        assert "auditor" in result.metadata["unique_actors"]

        table_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TABLE]
        assert len(table_frags) == 1
        assert "login" in table_frags[0].content

    @pytest.mark.asyncio
    async def test_parse_monitoring_output(self, tmp_path: str) -> None:
        """Should parse JSON monitoring output."""
        parser = ControlsParser()
        fp = os.path.join(str(tmp_path), "check.monitor")
        with open(fp, "w") as f:
            f.write(SAMPLE_MONITOR_JSON)

        result = await parser.parse(fp, "check.monitor")

        assert result.error is None
        assert result.metadata["evidence_category"] == "controls_evidence"
        assert result.metadata["record_count"] == 1

        # Should have TEXT fragment for the full output
        text_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TEXT]
        assert len(text_frags) >= 1

    @pytest.mark.asyncio
    async def test_parse_monitoring_array(self, tmp_path: str) -> None:
        """Should handle array-format monitoring output."""
        parser = ControlsParser()
        data = [{"check": "cpu", "status": "pass"}, {"check": "disk", "status": "fail"}]
        fp = os.path.join(str(tmp_path), "checks.monitor")
        with open(fp, "w") as f:
            json.dump(data, f)

        result = await parser.parse(fp, "checks.monitor")

        assert result.error is None
        table_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TABLE]
        assert len(table_frags) == 1

    @pytest.mark.asyncio
    async def test_parse_file_not_found(self) -> None:
        """Should return error for missing file."""
        parser = ControlsParser()
        result = await parser.parse("/nonexistent/file.ctrl", "missing.ctrl")
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_parse_empty_control_matrix(self, tmp_path: str) -> None:
        """Should handle empty CSV gracefully."""
        parser = ControlsParser()
        fp = os.path.join(str(tmp_path), "empty.ctrl")
        with open(fp, "w") as f:
            f.write("control_id,description\n")

        result = await parser.parse(fp, "empty.ctrl")
        assert result.error is None
        assert result.metadata["control_count"] == 0

    @pytest.mark.asyncio
    async def test_parse_invalid_monitor_json(self, tmp_path: str) -> None:
        """Should return error for invalid JSON."""
        parser = ControlsParser()
        fp = os.path.join(str(tmp_path), "bad.monitor")
        with open(fp, "w") as f:
            f.write("not valid json {{{")

        result = await parser.parse(fp, "bad.monitor")
        assert result.error is not None
