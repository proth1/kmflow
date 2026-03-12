"""Financial regulatory document parser for SEC/FINRA/FCA/MAS/HKMA/ESMA documents.

Extends the base regulatory parsing capabilities with financial-domain specifics:
section-level extraction with rule numbering (e.g., 15c3-3(a)(1)), cross-reference
detection, obligation classification, and jurisdiction auto-detection.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Jurisdiction detection: ordered by specificity (longer patterns first)
# ---------------------------------------------------------------------------

_JURISDICTION_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # Pattern, jurisdiction, regulatory_body
    (re.compile(r"\bFINRA\b", re.IGNORECASE), "US", "FINRA"),
    (re.compile(r"\bSEC\b|\bSecurities and Exchange Commission\b", re.IGNORECASE), "US", "SEC"),
    (re.compile(r"\bFCA\b|\bFinancial Conduct Authority\b", re.IGNORECASE), "UK", "FCA"),
    (re.compile(r"\bMAS\b|\bMonetary Authority of Singapore\b", re.IGNORECASE), "Singapore", "MAS"),
    (re.compile(r"\bHKMA\b|\bHong Kong Monetary Authority\b", re.IGNORECASE), "HK", "HKMA"),
    (re.compile(r"\bESMA\b|\bEuropean Securities and Markets Authority\b", re.IGNORECASE), "EU", "ESMA"),
]

# ---------------------------------------------------------------------------
# Section boundary patterns for financial regulations
# ---------------------------------------------------------------------------

# Matches numbered rules like: 15c3-3, Rule 17a-5, § 240.15c3-3, Section 4(a)(1)
_SECTION_BOUNDARY_PATTERNS: list[re.Pattern[str]] = [
    # § 240.15c3-3 or § 15c3-3
    re.compile(r"^§+\s*\d+[\w.\-]*", re.IGNORECASE),
    # Rule 15c3-3 or Rule 17a-5(a)
    re.compile(r"^Rule\s+\d+[\w.\-]+", re.IGNORECASE),
    # Section 4(a)(1) or Section 15(b)
    re.compile(r"^Section\s+\d+[\w()\-]*", re.IGNORECASE),
    # Article 5 or Article 25(1)
    re.compile(r"^Article\s+\d+[\w()\-]*", re.IGNORECASE),
    # Part II or Part 4
    re.compile(r"^Part\s+(?:[IVX]+|\d+)\b", re.IGNORECASE),
    # "1.2.3 Title" or "15c3-3 Title"
    re.compile(r"^\d+[\w.\-]+\s+[A-Z]"),
    # "(a) Text" or "(a)(1) Text"
    re.compile(r"^\([a-z]\)(?:\(\d+\))?\s+\S"),
    # "i. Text" or "ii. Text"
    re.compile(r"^(?:i{1,3}|iv|v|vi{0,3}|ix|x)\.\s+\S", re.IGNORECASE),
]

# Matches inline rule citations within text (for cross-reference detection)
_RULE_CITATION_PATTERN = re.compile(
    r"""
    (?:
        (?:Rule|Section|§)\s+\d+[\w.\-]+   # Rule 15c3-3, Section 240.15c3-3, § 240.15
        | \d+[\w]+-\d+(?:\([a-z]\)(?:\(\d+\))*)?  # 15c3-3(a)(1), 17a-5
        | CFR\s+\d+\.\d+                    # CFR 240.15c3-3
        | USC\s+\d+[a-z]*                   # USC 78o
        | (?:FINRA|FCA|MAS|HKMA|ESMA)\s+Rule\s+\d+[\w.\-]+  # FINRA Rule 4370
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Section ID extraction from the first line of a section
# ---------------------------------------------------------------------------

_SECTION_ID_PATTERN = re.compile(
    r"""
    (?:
        §+\s*(?P<sec_sym>[\d\w.\-]+)           # § 240.15c3-3
        | (?:Rule|Section|Article|Part)\s+       # Rule / Section / Article / Part
          (?P<named>[\d\w.\-()+]+)              # 15c3-3(a)(1)
        | (?P<bare>\d+[\w.\-]+)                 # bare 15c3-3 or 1.2.3
        | \((?P<paren>[a-z])\)                  # (a) / (b)
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Obligation classification
# ---------------------------------------------------------------------------

# Prohibitive must be checked before mandatory (longer negation phrases)
_PROHIBITIVE_PATTERNS = re.compile(
    r"\b(?:shall\s+not|must\s+not|may\s+not|prohibited\s+from|is\s+prohibited|are\s+prohibited|"
    r"no\s+(?:broker[\-\s]?dealer|broker|dealer|person|member|firm|registrant|entity)\s+shall)\b",
    re.IGNORECASE,
)

_MANDATORY_PATTERNS = re.compile(
    r"\b(?:shall|must|is\s+required\s+to|are\s+required\s+to|required\s+to|"
    r"obligated\s+to|mandatory|will\s+be\s+required)\b",
    re.IGNORECASE,
)

_PERMISSIVE_PATTERNS = re.compile(
    r"\b(?:may|can|is\s+permitted\s+to|are\s+permitted\s+to|is\s+allowed\s+to|"
    r"at\s+the\s+discretion\s+of|optionally)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Effective date extraction
# ---------------------------------------------------------------------------

_EFFECTIVE_DATE_PATTERN = re.compile(
    r"""
    (?:effective|effective\s+date|in\s+effect|as\s+of|adopted|amended)\s+
    (?:on\s+)?
    (?:
        (?:January|February|March|April|May|June|July|August|September|October|November|December)
        \s+\d{1,2},?\s+\d{4}
        | \d{1,2}/\d{1,2}/\d{4}
        | \d{4}-\d{2}-\d{2}
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)


class FinancialRegulatoryParser(BaseParser):
    """Parser for SEC/FINRA/FCA/MAS/HKMA/ESMA regulatory documents.

    Performs section-level extraction with structured metadata:
    - section_id: numeric/alphanumeric section identifier (e.g., "15c3-3(a)(1)")
    - section_title: descriptive title from the section header line
    - obligation_type: MANDATORY | PERMISSIVE | PROHIBITIVE
    - jurisdiction: US | UK | Singapore | HK | EU (document-level, auto-detected)
    - regulatory_body: SEC | FINRA | FCA | MAS | HKMA | ESMA
    - cross_references: list of cited rules/sections within the fragment
    - effective_date: first effective date found in the document (document-level)
    """

    supported_formats = [".pdf", ".html", ".xml", ".txt"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a financial regulatory document and extract structured sections.

        Args:
            file_path: Path to the document file.
            file_name: Original filename used for format routing.

        Returns:
            ParseResult with section-level fragments and document-level metadata.
        """
        ext = Path(file_name).suffix.lower()
        try:
            if ext == ".pdf":
                return await self._parse_pdf(file_path, file_name)
            elif ext in (".html", ".htm"):
                return await self._parse_html(file_path, file_name)
            elif ext == ".xml":
                return await self._parse_xml(file_path, file_name)
            else:
                return await self._parse_text(file_path, file_name)
        except Exception as e:  # Intentionally broad: parser library exceptions vary by format
            logger.exception("Failed to parse financial regulatory document: %s", file_name)
            return ParseResult(error=f"Parse error: {e}")

    # ------------------------------------------------------------------
    # Format-specific text extraction
    # ------------------------------------------------------------------

    async def _parse_pdf(self, file_path: str, file_name: str) -> ParseResult:
        """Extract text from PDF via pdfplumber, then run regulatory analysis."""
        import pdfplumber

        pages_text: list[str] = []
        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)

        full_text = "\n".join(pages_text)
        result = self._analyse_text(full_text, file_name)
        result.metadata["page_count"] = page_count
        return result

    async def _parse_html(self, file_path: str, file_name: str) -> ParseResult:
        """Strip HTML markup and run regulatory analysis on body text."""
        from lxml import html as lxml_html

        with open(file_path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()

        tree = lxml_html.fromstring(content)
        for element in tree.iter("script", "style"):
            element.drop_tree()  # type: ignore[attr-defined]  # lxml HtmlElement method

        body = tree.find(".//body")
        text = body.text_content() if body is not None else tree.text_content()  # type: ignore[attr-defined]  # lxml HtmlElement method
        return self._analyse_text(text, file_name)

    async def _parse_xml(self, file_path: str, file_name: str) -> ParseResult:
        """Extract text content from XML (e.g., EDGAR XBRL filings)."""
        from lxml import etree

        with open(file_path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()

        try:
            root = etree.fromstring(content.encode())
            text = " ".join(str(t) for t in root.itertext())
        except etree.XMLSyntaxError:
            # Fall back to regex-based tag stripping
            text = re.sub(r"<[^>]+>", " ", content)

        return self._analyse_text(text, file_name)

    async def _parse_text(self, file_path: str, file_name: str) -> ParseResult:
        """Read plain text and run regulatory analysis."""
        path = Path(file_path)
        if not path.exists():
            return ParseResult(error=f"File not found: {file_path}")

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="latin-1")

        return self._analyse_text(text, file_name)

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def _analyse_text(self, text: str, file_name: str) -> ParseResult:
        """Detect jurisdiction, split into sections, classify obligations.

        Args:
            text: Full document text (already stripped of markup).
            file_name: Original filename for metadata.

        Returns:
            ParseResult with one ParsedFragment per extracted section.
        """
        result = ParseResult()

        jurisdiction, regulatory_body = self._detect_jurisdiction(text)
        effective_date = self._extract_effective_date(text)

        result.metadata = {
            "file_name": file_name,
            "total_chars": len(text),
            "jurisdiction": jurisdiction,
            "regulatory_body": regulatory_body,
        }
        if effective_date:
            result.metadata["effective_date"] = effective_date

        sections = self._split_into_sections(text)
        result.metadata["section_count"] = len(sections)

        for section_text in sections:
            if not section_text.strip():
                continue
            fragment = self._build_fragment(
                section_text,
                file_name=file_name,
                jurisdiction=jurisdiction,
                regulatory_body=regulatory_body,
                effective_date=effective_date,
            )
            result.fragments.append(fragment)

        return result

    def _build_fragment(
        self,
        section_text: str,
        *,
        file_name: str,
        jurisdiction: str,
        regulatory_body: str,
        effective_date: str | None,
    ) -> ParsedFragment:
        """Build a ParsedFragment with full financial regulatory metadata."""
        first_line = section_text.splitlines()[0].strip() if section_text.strip() else ""

        section_id = self._extract_section_id(first_line)
        section_title = self._extract_section_title(first_line, section_id)
        obligation_type = self._classify_obligation(section_text)
        cross_refs = self._extract_cross_references(section_text)

        metadata: dict[str, str | int | float | bool | list[str] | None] = {
            "source": "financial_regulatory_section",
            "file_name": file_name,
            "section_id": section_id,
            "section_title": section_title,
            "obligation_type": obligation_type,
            "jurisdiction": jurisdiction,
            "regulatory_body": regulatory_body,
            "cross_references": cross_refs,
        }
        if effective_date:
            metadata["effective_date"] = effective_date

        return ParsedFragment(
            fragment_type=FragmentType.TEXT,
            content=section_text.strip(),
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Section splitting
    # ------------------------------------------------------------------

    def _split_into_sections(self, text: str) -> list[str]:
        """Split document text into sections based on regulatory numbering patterns.

        Falls back to double-newline paragraph splitting when no section boundaries
        are detected.

        Args:
            text: Full document text.

        Returns:
            List of section strings.
        """
        lines = text.split("\n")
        sections: list[str] = []
        current: list[str] = []

        for line in lines:
            stripped = line.strip()
            is_boundary = any(p.match(stripped) for p in _SECTION_BOUNDARY_PATTERNS)
            if is_boundary and current:
                sections.append("\n".join(current))
                current = []
            current.append(line)

        if current:
            sections.append("\n".join(current))

        # If no boundaries matched, fall back to paragraph splitting
        if len(sections) <= 1:
            paragraphs = re.split(r"\n\s*\n", text)
            return [p for p in paragraphs if p.strip()]

        return sections

    # ------------------------------------------------------------------
    # Field extractors
    # ------------------------------------------------------------------

    def _detect_jurisdiction(self, text: str) -> tuple[str, str]:
        """Auto-detect the issuing jurisdiction and regulatory body.

        Scans the first 2,000 characters (where header info typically appears)
        for known regulator acronyms and full names.

        Args:
            text: Document text.

        Returns:
            (jurisdiction, regulatory_body) tuple; defaults to ("UNKNOWN", "UNKNOWN").
        """
        header = text[:2000]
        for pattern, jurisdiction, body in _JURISDICTION_PATTERNS:
            if pattern.search(header):
                return jurisdiction, body
        return "UNKNOWN", "UNKNOWN"

    def _extract_effective_date(self, text: str) -> str | None:
        """Find the first effective date mention in the document.

        Args:
            text: Document text.

        Returns:
            Matched date string, or None if not found.
        """
        match = _EFFECTIVE_DATE_PATTERN.search(text)
        return match.group(0).strip() if match else None

    def _extract_section_id(self, first_line: str) -> str:
        """Extract the alphanumeric section identifier from a section's first line.

        Args:
            first_line: The leading line of the section (e.g., "§ 240.15c3-3 Customer Protection").

        Returns:
            Section ID string (e.g., "240.15c3-3"), or empty string if not parseable.
        """
        match = _SECTION_ID_PATTERN.search(first_line)
        if not match:
            return ""
        # Return whichever capture group matched
        for group_name in ("sec_sym", "named", "bare", "paren"):
            value = match.group(group_name)
            if value:
                return value.strip("().,")
        return ""

    def _extract_section_title(self, first_line: str, section_id: str) -> str:
        """Extract a human-readable title from the section's first line.

        Strips the leading section identifier to yield just the descriptive title.

        Args:
            first_line: The leading line of the section.
            section_id: Already-extracted section ID to strip from the line.

        Returns:
            Title string, or the first_line stripped if no title portion found.
        """
        if not first_line:
            return ""
        # Remove leading keyword + section_id
        title = re.sub(
            r"^(?:§+\s*|Rule\s+|Section\s+|Article\s+|Part\s+)[\d\w.\-()+]*\s*",
            "",
            first_line,
            flags=re.IGNORECASE,
        ).strip()
        return title if title else first_line.strip()

    def _classify_obligation(self, text: str) -> str:
        """Classify the predominant obligation type in a section's text.

        Precedence: PROHIBITIVE > MANDATORY > PERMISSIVE > INFORMATIONAL

        Args:
            text: Section text.

        Returns:
            One of: "PROHIBITIVE", "MANDATORY", "PERMISSIVE", "INFORMATIONAL".
        """
        if _PROHIBITIVE_PATTERNS.search(text):
            return "PROHIBITIVE"
        if _MANDATORY_PATTERNS.search(text):
            return "MANDATORY"
        if _PERMISSIVE_PATTERNS.search(text):
            return "PERMISSIVE"
        return "INFORMATIONAL"

    def _extract_cross_references(self, text: str) -> list[str]:
        """Find all rule/section citations within a section's text.

        Args:
            text: Section text.

        Returns:
            Deduplicated list of cited rule strings in order of appearance.
        """
        matches = _RULE_CITATION_PATTERN.findall(text)
        seen: set[str] = set()
        result: list[str] = []
        for m in matches:
            normalised = m.strip()
            if normalised not in seen:
                seen.add(normalised)
                result.append(normalised)
        return result
