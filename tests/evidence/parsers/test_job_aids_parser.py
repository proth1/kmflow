"""Tests for job aids parser rule extraction."""

from __future__ import annotations

from src.core.models import FragmentType
from src.evidence.parsers.base import ParsedFragment
from src.evidence.parsers.job_aids_parser import JobAidsParser


class TestExtractRules:
    """Tests for JobAidsParser._extract_rules()."""

    def _make_text_fragment(self, text: str) -> ParsedFragment:
        return ParsedFragment(
            fragment_type=FragmentType.TEXT,
            content=text,
            metadata={},
        )

    def _extract(self, text: str) -> list[ParsedFragment]:
        parser = JobAidsParser()
        fragments = [self._make_text_fragment(text)]
        return parser._extract_rules(fragments)

    def test_threshold_extraction(self) -> None:
        rules = self._extract("The minimum $500,000 is required for loan approval.")
        assert len(rules) >= 1
        threshold_rules = [r for r in rules if r.metadata.get("rule_type") == "threshold"]
        assert len(threshold_rules) >= 1
        assert "$500,000" in threshold_rules[0].metadata.get("threshold_value", "")

    def test_threshold_range(self) -> None:
        rules = self._extract("Income must be between $50,000 and $200,000 annually.")
        threshold_rules = [r for r in rules if r.metadata.get("rule_type") == "threshold"]
        assert len(threshold_rules) >= 1
        assert threshold_rules[0].metadata.get("upper_bound") is not None

    def test_if_then_extraction(self) -> None:
        rules = self._extract("If the applicant's credit score exceeds 750, then approve automatically.")
        condition_rules = [r for r in rules if r.metadata.get("rule_type") == "condition_action"]
        assert len(condition_rules) >= 1
        assert "credit score" in condition_rules[0].metadata.get("condition", "").lower()
        assert "approve" in condition_rules[0].metadata.get("action", "").lower()

    def test_exception_extraction(self) -> None:
        rules = self._extract(
            "Exception: Manual review is required for applicants with prior bankruptcy filings within 7 years."
        )
        exception_rules = [r for r in rules if r.metadata.get("rule_type") == "exception"]
        assert len(exception_rules) >= 1
        assert "bankruptcy" in exception_rules[0].metadata.get("exception_text", "").lower()

    def test_decision_tree_extraction(self) -> None:
        rules = self._extract("Yes → proceed to underwriting review for final determination.")
        decision_rules = [r for r in rules if r.metadata.get("rule_type") == "decision_branch"]
        assert len(decision_rules) >= 1

    def test_deduplication(self) -> None:
        text = "The threshold must exceed $100. The threshold must exceed $100."
        rules = self._extract(text)
        threshold_rules = [r for r in rules if r.metadata.get("rule_type") == "threshold"]
        assert len(threshold_rules) == 1

    def test_no_rules_in_plain_text(self) -> None:
        rules = self._extract("The quick brown fox jumps over the lazy dog.")
        assert len(rules) == 0

    def test_skips_non_text_fragments(self) -> None:
        parser = JobAidsParser()
        fragments = [
            ParsedFragment(
                fragment_type=FragmentType.PROCESS_ELEMENT,
                content="Not a text fragment",
                metadata={},
            )
        ]
        rules = parser._extract_rules(fragments)
        assert len(rules) == 0

    def test_all_rules_have_business_rule_element_type(self) -> None:
        rules = self._extract(
            "The minimum 650 credit score required. If the DTI exceeds 43%, then deny the application."
        )
        for rule in rules:
            assert rule.metadata.get("element_type") == "businessRule"
            assert rule.content.startswith("businessRule:")

    def test_short_exceptions_filtered(self) -> None:
        """Exception text under 15 chars should be filtered out."""
        rules = self._extract("Exception: too short.")
        exception_rules = [r for r in rules if r.metadata.get("rule_type") == "exception"]
        assert len(exception_rules) == 0
