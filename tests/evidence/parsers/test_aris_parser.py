"""Tests for the ARIS (.aml) parser."""

from __future__ import annotations

import os

import pytest

from src.core.models import FragmentType
from src.evidence.parsers.aris_parser import ArisParser

SAMPLE_AML = """<?xml version="1.0" encoding="utf-8"?>
<AML>
  <Group>
    <ObjDef ObjDef.ID="obj-1" TypeNum="OT_FUNC" SymbolNum="ST_FUNC">
      <AttrDef AttrDef.Type="AT_NAME">
        <AttrValue>Submit Application</AttrValue>
      </AttrDef>
    </ObjDef>
    <ObjDef ObjDef.ID="obj-2" TypeNum="OT_EVT" SymbolNum="ST_EVT">
      <AttrDef AttrDef.Type="AT_NAME">
        <AttrValue>Application Received</AttrValue>
      </AttrDef>
    </ObjDef>
    <ObjDef ObjDef.ID="obj-3" TypeNum="OT_FUNC" SymbolNum="ST_FUNC">
      <AttrDef AttrDef.Type="AT_NAME">
        <AttrValue>Review Application</AttrValue>
      </AttrDef>
    </ObjDef>
    <ObjDef ObjDef.ID="obj-4" TypeNum="OT_ORG_UNIT" SymbolNum="ST_ORG_UNIT">
      <AttrDef AttrDef.Type="AT_NAME">
        <AttrValue>HR Department</AttrValue>
      </AttrDef>
    </ObjDef>
    <CxnDef CxnDef.Type="CT_IS_PREDEC_OF" ToObjDef.IdRef="obj-1" FromObjDef.IdRef="obj-2"/>
    <CxnDef CxnDef.Type="CT_IS_PREDEC_OF" ToObjDef.IdRef="obj-2" FromObjDef.IdRef="obj-3"/>
    <CxnDef CxnDef.Type="CT_EXEC" ToObjDef.IdRef="obj-4" FromObjDef.IdRef="obj-1"/>
  </Group>
</AML>
"""

SAMPLE_AML_PLAINTEXT = """<?xml version="1.0" encoding="utf-8"?>
<AML>
  <Group>
    <ObjDef ObjDef.ID="pt-1" TypeNum="OT_FUNC">
      <PlainText TextValue="Process Order"/>
    </ObjDef>
  </Group>
</AML>
"""


class TestArisParser:
    """Tests for ArisParser."""

    def test_supported_formats(self) -> None:
        parser = ArisParser()
        assert ".aml" in parser.supported_formats
        assert parser.can_parse(".aml")
        assert not parser.can_parse(".bpmn")

    @pytest.mark.asyncio
    async def test_parse_valid_aml(self, tmp_path: str) -> None:
        """Should extract objects and connections from valid AML."""
        parser = ArisParser()
        fp = os.path.join(str(tmp_path), "process.aml")
        with open(fp, "w") as f:
            f.write(SAMPLE_AML)

        result = await parser.parse(fp, "process.aml")

        assert result.error is None
        assert result.metadata["format"] == "aml"
        assert result.metadata["object_count"] == 4
        assert result.metadata["connection_count"] == 3

        # Should have PROCESS_ELEMENT fragments for each object
        proc_frags = [f for f in result.fragments if f.fragment_type == FragmentType.PROCESS_ELEMENT]
        assert len(proc_frags) == 4

        names = {f.content for f in proc_frags}
        assert "Submit Application" in names
        assert "Application Received" in names
        assert "Review Application" in names
        assert "HR Department" in names

        # Check element types
        submit = next(f for f in proc_frags if f.content == "Submit Application")
        assert submit.metadata["element_type"] == "activity"

        event = next(f for f in proc_frags if f.content == "Application Received")
        assert event.metadata["element_type"] == "event"

        org = next(f for f in proc_frags if f.content == "HR Department")
        assert org.metadata["element_type"] == "org_unit"

        # Should have RELATIONSHIP fragment for connections
        rel_frags = [f for f in result.fragments if f.fragment_type == FragmentType.RELATIONSHIP]
        assert len(rel_frags) == 1
        assert "sequence_flow" in rel_frags[0].content

    @pytest.mark.asyncio
    async def test_parse_plaintext_fallback(self, tmp_path: str) -> None:
        """Should extract name from PlainText when AttrDef is missing."""
        parser = ArisParser()
        fp = os.path.join(str(tmp_path), "plain.aml")
        with open(fp, "w") as f:
            f.write(SAMPLE_AML_PLAINTEXT)

        result = await parser.parse(fp, "plain.aml")

        assert result.error is None
        assert result.metadata["object_count"] == 1
        proc_frags = [f for f in result.fragments if f.fragment_type == FragmentType.PROCESS_ELEMENT]
        assert len(proc_frags) == 1
        assert proc_frags[0].content == "Process Order"

    @pytest.mark.asyncio
    async def test_parse_file_not_found(self) -> None:
        """Should return error for missing file."""
        parser = ArisParser()
        result = await parser.parse("/nonexistent/file.aml", "missing.aml")
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_parse_invalid_xml(self, tmp_path: str) -> None:
        """Should return error for invalid XML."""
        parser = ArisParser()
        fp = os.path.join(str(tmp_path), "bad.aml")
        with open(fp, "w") as f:
            f.write("not valid xml <><>")

        result = await parser.parse(fp, "bad.aml")
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_parse_empty_aml(self, tmp_path: str) -> None:
        """Should handle AML with no objects."""
        parser = ArisParser()
        fp = os.path.join(str(tmp_path), "empty.aml")
        with open(fp, "w") as f:
            f.write('<?xml version="1.0"?><AML></AML>')

        result = await parser.parse(fp, "empty.aml")
        assert result.error is None
        assert result.metadata["object_count"] == 0
        assert len(result.fragments) == 0

    @pytest.mark.asyncio
    async def test_object_types_in_metadata(self, tmp_path: str) -> None:
        """Should report discovered object types in metadata."""
        parser = ArisParser()
        fp = os.path.join(str(tmp_path), "types.aml")
        with open(fp, "w") as f:
            f.write(SAMPLE_AML)

        result = await parser.parse(fp, "types.aml")
        types = result.metadata.get("object_types", [])
        assert "activity" in types
        assert "event" in types
        assert "org_unit" in types
