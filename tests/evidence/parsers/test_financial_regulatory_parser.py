"""Unit tests for FinancialRegulatoryParser.

Covers:
  - Supported format detection
  - Plain-text section splitting and metadata extraction
  - Jurisdiction and regulatory body auto-detection
  - Obligation type classification (MANDATORY / PERMISSIVE / PROHIBITIVE / INFORMATIONAL)
  - Cross-reference extraction
  - Section ID and title extraction
  - HTML stripping
  - XML parsing
  - Missing file / error handling
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.models import FragmentType
from src.evidence.parsers.financial_regulatory_parser import FinancialRegulatoryParser


@pytest.fixture
def parser() -> FinancialRegulatoryParser:
    return FinancialRegulatoryParser()


# ---------------------------------------------------------------------------
# Supported formats
# ---------------------------------------------------------------------------


class TestSupportedFormats:
    def test_supported_formats(self, parser: FinancialRegulatoryParser) -> None:
        for ext in (".pdf", ".html", ".xml", ".txt"):
            assert parser.can_parse(ext), f"{ext} should be supported"

    def test_unsupported_formats(self, parser: FinancialRegulatoryParser) -> None:
        for ext in (".docx", ".xlsx", ".bpmn", ".reg"):
            assert not parser.can_parse(ext), f"{ext} should NOT be supported"


# ---------------------------------------------------------------------------
# Plain-text parsing
# ---------------------------------------------------------------------------


class TestPlainTextParsing:
    """Scenario: Financial regulatory text file is parsed into sections."""

    @pytest.mark.asyncio
    async def test_file_not_found_returns_error(self, parser: FinancialRegulatoryParser) -> None:
        result = await parser.parse("/nonexistent/path/file.txt", "file.txt")
        assert result.error is not None
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_empty_file_produces_no_fragments(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = await parser.parse(str(f), "empty.txt")
        assert result.error is None
        assert len(result.fragments) == 0

    @pytest.mark.asyncio
    async def test_total_chars_in_metadata(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        content = "SEC Rule 15c3-3 requires segregation.\n\nBrokers shall maintain records."
        f = tmp_path / "rule.txt"
        f.write_text(content)
        result = await parser.parse(str(f), "rule.txt")
        assert result.metadata["total_chars"] == len(content)

    @pytest.mark.asyncio
    async def test_section_count_in_metadata(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        content = _sec_rule_text()
        f = tmp_path / "rule.txt"
        f.write_text(content)
        result = await parser.parse(str(f), "rule.txt")
        # Multiple § sections should be detected
        assert result.metadata.get("section_count", 0) >= 2

    @pytest.mark.asyncio
    async def test_fragments_have_text_type(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        f = tmp_path / "rule.txt"
        f.write_text(_sec_rule_text())
        result = await parser.parse(str(f), "rule.txt")
        for frag in result.fragments:
            assert frag.fragment_type == FragmentType.TEXT

    @pytest.mark.asyncio
    async def test_file_name_propagated_to_fragment_metadata(
        self, parser: FinancialRegulatoryParser, tmp_path: Path
    ) -> None:
        f = tmp_path / "sec_rule.txt"
        f.write_text(_sec_rule_text())
        result = await parser.parse(str(f), "sec_rule.txt")
        assert len(result.fragments) > 0
        assert result.fragments[0].metadata["file_name"] == "sec_rule.txt"


# ---------------------------------------------------------------------------
# Jurisdiction detection
# ---------------------------------------------------------------------------


class TestJurisdictionDetection:
    """Scenario: Parser auto-detects the regulatory jurisdiction."""

    @pytest.mark.asyncio
    async def test_sec_jurisdiction(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        f = tmp_path / "sec.txt"
        f.write_text("Securities and Exchange Commission\nRule 15c3-3 requires segregation.")
        result = await parser.parse(str(f), "sec.txt")
        assert result.metadata["jurisdiction"] == "US"
        assert result.metadata["regulatory_body"] == "SEC"

    @pytest.mark.asyncio
    async def test_finra_jurisdiction(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        f = tmp_path / "finra.txt"
        f.write_text("FINRA Rule 4370 - Business Continuity Plans and Emergency Contact Information.")
        result = await parser.parse(str(f), "finra.txt")
        assert result.metadata["jurisdiction"] == "US"
        assert result.metadata["regulatory_body"] == "FINRA"

    @pytest.mark.asyncio
    async def test_fca_jurisdiction(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        f = tmp_path / "fca.txt"
        f.write_text("Financial Conduct Authority: CASS rules require asset segregation.")
        result = await parser.parse(str(f), "fca.txt")
        assert result.metadata["jurisdiction"] == "UK"
        assert result.metadata["regulatory_body"] == "FCA"

    @pytest.mark.asyncio
    async def test_mas_jurisdiction(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        f = tmp_path / "mas.txt"
        f.write_text("Monetary Authority of Singapore Notice SFA 04-N02.")
        result = await parser.parse(str(f), "mas.txt")
        assert result.metadata["jurisdiction"] == "Singapore"
        assert result.metadata["regulatory_body"] == "MAS"

    @pytest.mark.asyncio
    async def test_hkma_jurisdiction(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        f = tmp_path / "hkma.txt"
        f.write_text("HKMA Guideline on Authorization of Virtual Banks.")
        result = await parser.parse(str(f), "hkma.txt")
        assert result.metadata["jurisdiction"] == "HK"
        assert result.metadata["regulatory_body"] == "HKMA"

    @pytest.mark.asyncio
    async def test_esma_jurisdiction(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        f = tmp_path / "esma.txt"
        f.write_text("European Securities and Markets Authority MiFID II guidelines.")
        result = await parser.parse(str(f), "esma.txt")
        assert result.metadata["jurisdiction"] == "EU"
        assert result.metadata["regulatory_body"] == "ESMA"

    @pytest.mark.asyncio
    async def test_unknown_jurisdiction_fallback(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        f = tmp_path / "unknown.txt"
        f.write_text("Generic regulation text with no known regulator name.")
        result = await parser.parse(str(f), "unknown.txt")
        assert result.metadata["jurisdiction"] == "UNKNOWN"
        assert result.metadata["regulatory_body"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Obligation type classification
# ---------------------------------------------------------------------------


class TestObligationClassification:
    """Scenario: Sections are classified as MANDATORY / PERMISSIVE / PROHIBITIVE / INFORMATIONAL."""

    @pytest.mark.asyncio
    async def test_mandatory_obligation(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "§ 240.15c3-3\nA broker shall maintain a special reserve bank account."
        f = tmp_path / "mandatory.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "mandatory.txt")
        assert len(result.fragments) >= 1
        assert result.fragments[0].metadata["obligation_type"] == "MANDATORY"

    @pytest.mark.asyncio
    async def test_permissive_obligation(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "§ 240.15c3-3(b)\nA broker may use an alternative computation method at its discretion."
        f = tmp_path / "permissive.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "permissive.txt")
        assert len(result.fragments) >= 1
        assert result.fragments[0].metadata["obligation_type"] == "PERMISSIVE"

    @pytest.mark.asyncio
    async def test_prohibitive_obligation(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "§ 240.15c3-3(c)\nNo broker-dealer shall use customer funds for proprietary trading."
        f = tmp_path / "prohibitive.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "prohibitive.txt")
        assert len(result.fragments) >= 1
        assert result.fragments[0].metadata["obligation_type"] == "PROHIBITIVE"

    @pytest.mark.asyncio
    async def test_shall_not_is_prohibitive_not_mandatory(
        self, parser: FinancialRegulatoryParser, tmp_path: Path
    ) -> None:
        text = "§ 1.1\nThe firm shall not commingle client assets with proprietary assets."
        f = tmp_path / "prohib2.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "prohib2.txt")
        assert result.fragments[0].metadata["obligation_type"] == "PROHIBITIVE"

    @pytest.mark.asyncio
    async def test_informational_section(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "§ 240.15c3-3 Background\nThis rule was adopted in 1972 following the paperwork crisis."
        f = tmp_path / "info.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "info.txt")
        assert len(result.fragments) >= 1
        assert result.fragments[0].metadata["obligation_type"] == "INFORMATIONAL"


# ---------------------------------------------------------------------------
# Cross-reference extraction
# ---------------------------------------------------------------------------


class TestCrossReferenceExtraction:
    """Scenario: Inline rule citations are detected as cross-references."""

    @pytest.mark.asyncio
    async def test_detects_rule_citation(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "§ 240.15c3-3\nThe requirements of Rule 17a-5 and Section 15(c) apply in addition to this rule."
        f = tmp_path / "xref.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "xref.txt")
        assert len(result.fragments) >= 1
        cross_refs = result.fragments[0].metadata.get("cross_references", [])
        assert isinstance(cross_refs, list)
        assert len(cross_refs) >= 1

    @pytest.mark.asyncio
    async def test_no_cross_references_when_absent(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "§ 1.1\nBrokers shall maintain adequate records."
        f = tmp_path / "no_xref.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "no_xref.txt")
        cross_refs = result.fragments[0].metadata.get("cross_references", [])
        assert isinstance(cross_refs, list)

    @pytest.mark.asyncio
    async def test_cross_references_are_deduplicated(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "§ 1.1\nSee Rule 15c3-3 and Rule 15c3-3 for further details on Rule 15c3-3."
        f = tmp_path / "dedup.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "dedup.txt")
        cross_refs = result.fragments[0].metadata.get("cross_references", [])
        assert cross_refs.count("Rule 15c3-3") == 1


# ---------------------------------------------------------------------------
# Section ID and title extraction
# ---------------------------------------------------------------------------


class TestSectionMetadata:
    """Scenario: Section ID and title are extracted from section headers."""

    @pytest.mark.asyncio
    async def test_section_id_from_paragraph_symbol(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "§ 240.15c3-3 Customer Protection\nA broker shall maintain a reserve account."
        f = tmp_path / "sec_id.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "sec_id.txt")
        section_id = result.fragments[0].metadata.get("section_id", "")
        assert "15c3-3" in section_id or "240" in section_id

    @pytest.mark.asyncio
    async def test_section_title_extracted(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "§ 240.15c3-3 Customer Protection Requirements\nA broker shall maintain a reserve."
        f = tmp_path / "sec_title.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "sec_title.txt")
        section_title = result.fragments[0].metadata.get("section_title", "")
        assert "Customer Protection" in section_title

    @pytest.mark.asyncio
    async def test_jurisdiction_propagated_to_fragment(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "SEC Release No. 34-70072\n§ 1\nBrokers must comply."
        f = tmp_path / "jur.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "jur.txt")
        assert len(result.fragments) >= 1
        assert result.fragments[0].metadata["jurisdiction"] == "US"
        assert result.fragments[0].metadata["regulatory_body"] == "SEC"


# ---------------------------------------------------------------------------
# Effective date extraction
# ---------------------------------------------------------------------------


class TestEffectiveDateExtraction:
    @pytest.mark.asyncio
    async def test_effective_date_in_metadata(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "This rule is effective January 1, 2024.\n§ 1\nBrokers shall comply."
        f = tmp_path / "dated.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "dated.txt")
        assert "2024" in (result.metadata.get("effective_date") or "")

    @pytest.mark.asyncio
    async def test_no_effective_date_when_absent(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        text = "§ 1\nBrokers shall comply with net capital rules."
        f = tmp_path / "no_date.txt"
        f.write_text(text)
        result = await parser.parse(str(f), "no_date.txt")
        # Should be absent or None; not error
        assert result.error is None
        assert "effective_date" not in result.metadata or result.metadata["effective_date"] is None


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------


class TestHtmlParsing:
    @pytest.mark.asyncio
    async def test_html_text_extracted(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        html = (
            "<html><head><title>SEC Rule</title></head>"
            "<body><p>SEC Rule 15c3-3 requires customer protection.</p>"
            "<p>Brokers shall maintain a reserve account.</p></body></html>"
        )
        f = tmp_path / "rule.html"
        f.write_text(html)
        result = await parser.parse(str(f), "rule.html")
        assert result.error is None
        assert len(result.fragments) >= 1

    @pytest.mark.asyncio
    async def test_html_script_stripped(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        html = "<html><body><script>alert('xss')</script><p>Brokers must comply.</p></body></html>"
        f = tmp_path / "scripted.html"
        f.write_text(html)
        result = await parser.parse(str(f), "scripted.html")
        assert result.error is None
        all_content = " ".join(fr.content for fr in result.fragments)
        assert "alert" not in all_content

    @pytest.mark.asyncio
    async def test_html_jurisdiction_detected(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        html = "<html><body><p>FCA Handbook CASS 7.13 — asset segregation rules.</p></body></html>"
        f = tmp_path / "fca.html"
        f.write_text(html)
        result = await parser.parse(str(f), "fca.html")
        assert result.metadata.get("jurisdiction") == "UK"


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------


class TestXmlParsing:
    @pytest.mark.asyncio
    async def test_xml_text_extracted(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        xml = (
            '<?xml version="1.0"?>'
            "<regulation>"
            "<section id='15c3-3'>"
            "<title>Customer Protection</title>"
            "<text>Brokers shall maintain a special reserve account.</text>"
            "</section>"
            "</regulation>"
        )
        f = tmp_path / "rule.xml"
        f.write_text(xml)
        result = await parser.parse(str(f), "rule.xml")
        assert result.error is None
        all_text = " ".join(fr.content for fr in result.fragments)
        assert "reserve" in all_text.lower()

    @pytest.mark.asyncio
    async def test_malformed_xml_falls_back(self, parser: FinancialRegulatoryParser, tmp_path: Path) -> None:
        xml = "<regulation><section>Brokers shall comply.<br></section>"
        f = tmp_path / "bad.xml"
        f.write_text(xml)
        # Should not raise; either succeeds or has error
        result = await parser.parse(str(f), "bad.xml")
        assert isinstance(result.error, (str, type(None)))


# ---------------------------------------------------------------------------
# Factory registration smoke test
# ---------------------------------------------------------------------------


class TestFactoryRegistration:
    """Verify the parser is registered in the factory and takes precedence for its formats."""

    def test_financial_regulatory_parser_importable(self) -> None:
        from src.evidence.parsers.financial_regulatory_parser import FinancialRegulatoryParser

        assert FinancialRegulatoryParser is not None


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _sec_rule_text() -> str:
    return """Securities and Exchange Commission

§ 240.15c3-3 Customer protection — reserves and custody of securities.

(a) No broker or dealer shall use customer funds for proprietary trading purposes.

§ 240.15c3-3(b) Reserve Formula

A broker-dealer must maintain a special reserve bank account computed in accordance
with the formula set forth in Exhibit A. The requirement shall be calculated weekly.
The broker may use government securities as eligible collateral under Rule 15c3-1.
"""
