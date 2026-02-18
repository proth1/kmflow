"""Tests for the SaaS Exports parser."""

from __future__ import annotations

import json
import os

import pytest

from src.core.models import FragmentType
from src.evidence.parsers.saas_parser import SaaSExportsParser

SAMPLE_SALESFORCE_JSON = json.dumps([
    {"Id": "001A000001", "Name": "Acme Corp", "Type": "Account", "Industry": "Technology"},
    {"Id": "001A000002", "Name": "Globex Inc", "Type": "Account", "Industry": "Finance"},
])

SAMPLE_SAP_CSV = """material_id,description,plant,MARA_type
MAT001,Widget A,1000,FERT
MAT002,Widget B,2000,ROH
"""

SAMPLE_SERVICENOW_JSON = json.dumps({
    "export_date": "2024-06-15T10:00:00Z",
    "table": "incident",
    "records": [
        {"number": "INC001", "short_description": "Login issue", "priority": "2"},
        {"number": "INC002", "short_description": "Email down", "priority": "1"},
    ],
})


class TestSaaSExportsParser:
    """Tests for SaaSExportsParser."""

    def test_supported_formats(self) -> None:
        parser = SaaSExportsParser()
        assert ".salesforce" in parser.supported_formats
        assert ".sap_export" in parser.supported_formats
        assert ".servicenow_export" in parser.supported_formats
        assert parser.can_parse(".salesforce")
        assert not parser.can_parse(".csv")

    @pytest.mark.asyncio
    async def test_parse_salesforce_json(self, tmp_path: str) -> None:
        """Should parse Salesforce JSON export and detect Account objects."""
        parser = SaaSExportsParser()
        fp = os.path.join(str(tmp_path), "export.salesforce")
        with open(fp, "w") as f:
            f.write(SAMPLE_SALESFORCE_JSON)

        result = await parser.parse(fp, "export.salesforce")

        assert result.error is None
        assert result.metadata["source_system"] == "salesforce"
        assert result.metadata["evidence_category"] == "saas_exports"
        assert len(result.fragments) > 0

        # Should detect Account object type
        entity_frags = [f for f in result.fragments if f.fragment_type == FragmentType.ENTITY]
        assert any("Account" in f.content for f in entity_frags)

    @pytest.mark.asyncio
    async def test_parse_sap_csv(self, tmp_path: str) -> None:
        """Should parse SAP CSV export with metadata enrichment."""
        parser = SaaSExportsParser()
        fp = os.path.join(str(tmp_path), "materials.sap_export")
        with open(fp, "w") as f:
            f.write(SAMPLE_SAP_CSV)

        result = await parser.parse(fp, "materials.sap_export")

        assert result.error is None
        assert result.metadata["source_system"] == "sap"
        assert result.metadata["evidence_category"] == "saas_exports"

        # Should have TABLE fragment from CSV parsing
        table_frags = [f for f in result.fragments if f.fragment_type == FragmentType.TABLE]
        assert len(table_frags) >= 1
        assert "Widget A" in table_frags[0].content

    @pytest.mark.asyncio
    async def test_parse_servicenow_json(self, tmp_path: str) -> None:
        """Should parse ServiceNow JSON export and extract export date."""
        parser = SaaSExportsParser()
        fp = os.path.join(str(tmp_path), "incidents.servicenow_export")
        with open(fp, "w") as f:
            f.write(SAMPLE_SERVICENOW_JSON)

        result = await parser.parse(fp, "incidents.servicenow_export")

        assert result.error is None
        assert result.metadata["source_system"] == "servicenow"
        assert result.metadata["export_date"] == "2024-06-15T10:00:00Z"
        # incident object should be detected
        detected = result.metadata.get("detected_objects", [])
        assert "incident" in detected

    @pytest.mark.asyncio
    async def test_parse_file_not_found(self) -> None:
        """Should return error for missing file."""
        parser = SaaSExportsParser()
        result = await parser.parse("/nonexistent/export.salesforce", "export.salesforce")
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fragments_tagged_with_saas_metadata(self, tmp_path: str) -> None:
        """All fragments should have saas_exports category and source_system."""
        parser = SaaSExportsParser()
        fp = os.path.join(str(tmp_path), "data.salesforce")
        with open(fp, "w") as f:
            f.write(SAMPLE_SALESFORCE_JSON)

        result = await parser.parse(fp, "data.salesforce")

        for frag in result.fragments:
            assert frag.metadata.get("evidence_category") == "saas_exports"
            assert frag.metadata.get("source_system") == "salesforce"
