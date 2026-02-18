"""Tests for the Visio .vsdx parser."""

from __future__ import annotations

import os
import zipfile

import pytest

from src.core.models import FragmentType
from src.evidence.parsers.visio_parser import VisioParser

SAMPLE_PAGE_XML = """<?xml version="1.0" encoding="utf-8"?>
<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main">
  <Shapes>
    <Shape ID="1" Name="Process.101" Master="1">
      <Text>Review Application</Text>
    </Shape>
    <Shape ID="2" Name="Decision.201" Master="2">
      <Text>Approved?</Text>
    </Shape>
    <Shape ID="3" Name="Dynamic connector" Type="Foreign">
      <Text>Yes</Text>
    </Shape>
    <Shape ID="4" Name="Start/End.301">
      <Text>Start</Text>
    </Shape>
    <Shape ID="5" Name="Rectangle.401">
      <Text>Process Step</Text>
    </Shape>
  </Shapes>
</PageContents>
"""


def _create_vsdx(tmp_path: str, page_xml: str = SAMPLE_PAGE_XML) -> str:
    """Create a minimal .vsdx file with the given page XML."""
    vsdx_path = os.path.join(tmp_path, "test.vsdx")
    with zipfile.ZipFile(vsdx_path, "w") as zf:
        zf.writestr("visio/pages/page1.xml", page_xml)
    return vsdx_path


class TestVisioParser:
    """Tests for VisioParser."""

    def test_supported_formats(self) -> None:
        parser = VisioParser()
        assert ".vsdx" in parser.supported_formats
        assert parser.can_parse(".vsdx")
        assert not parser.can_parse(".pdf")

    @pytest.mark.asyncio
    async def test_parse_valid_vsdx(self, tmp_path: str) -> None:
        """Should extract shapes and connectors from valid .vsdx."""
        parser = VisioParser()
        vsdx_path = _create_vsdx(str(tmp_path))

        result = await parser.parse(vsdx_path, "test.vsdx")

        assert result.error is None
        assert result.metadata["format"] == "vsdx"
        assert result.metadata["page_count"] == 1
        assert len(result.fragments) > 0

        # Check that process elements were extracted
        process_frags = [f for f in result.fragments if f.fragment_type == FragmentType.PROCESS_ELEMENT]
        assert len(process_frags) >= 1

        # Check connector was found
        rel_frags = [f for f in result.fragments if f.fragment_type == FragmentType.RELATIONSHIP]
        assert len(rel_frags) >= 1

    @pytest.mark.asyncio
    async def test_parse_file_not_found(self) -> None:
        """Should return error for missing file."""
        parser = VisioParser()
        result = await parser.parse("/nonexistent/file.vsdx", "missing.vsdx")
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_parse_not_zip(self, tmp_path: str) -> None:
        """Should return error for non-ZIP file."""
        parser = VisioParser()
        bad_path = os.path.join(str(tmp_path), "bad.vsdx")
        with open(bad_path, "w") as f:
            f.write("not a zip file")

        result = await parser.parse(bad_path, "bad.vsdx")
        assert result.error is not None
        assert "not a valid" in result.error.lower() or "corrupt" in result.error.lower()

    @pytest.mark.asyncio
    async def test_parse_empty_vsdx(self, tmp_path: str) -> None:
        """Should handle .vsdx with no shapes."""
        parser = VisioParser()
        empty_xml = """<?xml version="1.0" encoding="utf-8"?>
<PageContents xmlns="http://schemas.microsoft.com/office/visio/2012/main">
  <Shapes/>
</PageContents>
"""
        vsdx_path = _create_vsdx(str(tmp_path), empty_xml)
        result = await parser.parse(vsdx_path, "empty.vsdx")

        assert result.error is None
        assert result.metadata["shape_count"] == 0

    @pytest.mark.asyncio
    async def test_shape_classification(self) -> None:
        """Test shape type classification logic."""
        parser = VisioParser()
        from lxml import etree

        ns = "http://schemas.microsoft.com/office/visio/2012/main"
        shape = etree.Element(f"{{{ns}}}Shape", Name="Process.101")
        assert parser._classify_shape(shape) == "activity"

        shape = etree.Element(f"{{{ns}}}Shape", Name="Decision.201")
        assert parser._classify_shape(shape) == "gateway"

        shape = etree.Element(f"{{{ns}}}Shape", Name="Start.301")
        assert parser._classify_shape(shape) == "event"

        shape = etree.Element(f"{{{ns}}}Shape", Name="Dynamic connector", Type="Foreign")
        assert parser._classify_shape(shape) == "connector"

    @pytest.mark.asyncio
    async def test_page_number_extraction(self) -> None:
        """Test page number parsing from filenames."""
        assert VisioParser._extract_page_number("visio/pages/page1.xml") == 1
        assert VisioParser._extract_page_number("visio/pages/page12.xml") == 12

    @pytest.mark.asyncio
    async def test_multi_page_vsdx(self, tmp_path: str) -> None:
        """Should handle multi-page .vsdx files."""
        parser = VisioParser()
        vsdx_path = os.path.join(str(tmp_path), "multi.vsdx")
        with zipfile.ZipFile(vsdx_path, "w") as zf:
            zf.writestr("visio/pages/page1.xml", SAMPLE_PAGE_XML)
            zf.writestr("visio/pages/page2.xml", SAMPLE_PAGE_XML)

        result = await parser.parse(vsdx_path, "multi.vsdx")
        assert result.error is None
        assert result.metadata["page_count"] == 2
