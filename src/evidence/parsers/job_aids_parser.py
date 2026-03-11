"""Job Aids and Edge Cases evidence parser.

Handles job aids, quick reference guides, edge case documentation,
and exception handling procedures. Implements rule extraction for
decision trees, threshold tables, and if/then logic.
"""

from __future__ import annotations

import logging
import re

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult
from src.evidence.parsers.document_parser import DocumentParser

logger = logging.getLogger(__name__)

# Rule extraction patterns for job aids
_THRESHOLD_PATTERN = re.compile(
    r"(?:threshold|limit|cutoff|minimum|maximum|at\s+least|no\s+more\s+than|"
    r"must\s+be|must\s+exceed|cannot\s+exceed|"
    r"greater\s+than|less\s+than|equal\s+to|between)\s+"
    r"(\$?[\d,]+\.?\d*%?)\s*"
    r"(?:and\s+(\$?[\d,]+\.?\d*%?))?",
    re.IGNORECASE,
)

_IF_THEN_PATTERN = re.compile(
    r"(?:^|\.\s+|\n)\s*(?:if|when|where|unless)\s+"
    r"(.{10,120}?)\s*(?:,\s*then|→|=>|:)\s*"
    r"(.{5,120}?)(?:\.|$|\n)",
    re.IGNORECASE | re.MULTILINE,
)

_EXCEPTION_PATTERN = re.compile(
    r"(?:exception|override|waiver|deviation|escalat)\w*\s*"
    r"(?::|—|–|-)\s*(.{10,200}?)(?:\.|$|\n)",
    re.IGNORECASE | re.MULTILINE,
)

_DECISION_TREE_PATTERN = re.compile(
    r"(?:yes|no|true|false|approve|reject|pass|fail)\s*"
    r"(?:→|=>|->|:)\s*(.{5,100}?)(?:\.|$|\n)",
    re.IGNORECASE | re.MULTILINE,
)


class JobAidsParser(BaseParser):
    """Parser for Job Aids and Edge Cases evidence.

    Extends DocumentParser with rule extraction capabilities:
    - Threshold/limit detection
    - If/then condition-action pairs
    - Exception/override handling rules
    - Decision tree branch extraction
    """

    supported_formats = [".jobaid", ".edgecase"]

    def __init__(self) -> None:
        self._doc_parser = DocumentParser()

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a Job Aids file.

        Args:
            file_path: Path to the file.
            file_name: Original filename.

        Returns:
            ParseResult with job_aids_edge_cases category metadata
            and extracted business rule fragments.
        """
        result = await self._doc_parser.parse(file_path, file_name)

        result.metadata["evidence_category"] = "job_aids_edge_cases"
        result.metadata["parser"] = "job_aids"

        for fragment in result.fragments:
            fragment.metadata["evidence_category"] = "job_aids_edge_cases"

        # Extract rules from text fragments
        rule_fragments = self._extract_rules(result.fragments)
        result.fragments.extend(rule_fragments)
        result.metadata["extracted_rule_count"] = len(rule_fragments)

        return result

    def _extract_rules(self, fragments: list[ParsedFragment]) -> list[ParsedFragment]:
        """Extract business rules from parsed text fragments.

        Scans all text fragments for threshold values, if/then conditions,
        exception handling procedures, and decision tree branches.

        Returns:
            List of new ParsedFragment objects with fragment_type=PROCESS_ELEMENT
            and element_type=businessRule metadata.
        """
        rules: list[ParsedFragment] = []
        seen_rules: set[str] = set()

        for fragment in fragments:
            if fragment.fragment_type != FragmentType.TEXT:
                continue

            text = fragment.content

            # Extract threshold rules
            for match in _THRESHOLD_PATTERN.finditer(text):
                value = match.group(1)
                upper = match.group(2)
                context_start = max(0, match.start() - 50)
                context_end = min(len(text), match.end() + 50)
                context = text[context_start:context_end].strip()

                rule_text = f"Threshold: {value}"
                if upper:
                    rule_text = f"Range: {value} to {upper}"

                rule_key = rule_text.lower()
                if rule_key not in seen_rules:
                    seen_rules.add(rule_key)
                    rules.append(
                        ParsedFragment(
                            fragment_type=FragmentType.PROCESS_ELEMENT,
                            content=f"businessRule: {rule_text}",
                            metadata={
                                "element_type": "businessRule",
                                "rule_type": "threshold",
                                "threshold_value": value,
                                "upper_bound": upper,
                                "context": context,
                                "evidence_category": "job_aids_edge_cases",
                            },
                        )
                    )

            # Extract if/then condition-action pairs
            for match in _IF_THEN_PATTERN.finditer(text):
                condition = match.group(1).strip()
                action = match.group(2).strip()
                rule_text = f"IF {condition} THEN {action}"

                rule_key = rule_text.lower()
                if rule_key not in seen_rules:
                    seen_rules.add(rule_key)
                    rules.append(
                        ParsedFragment(
                            fragment_type=FragmentType.PROCESS_ELEMENT,
                            content=f"businessRule: {rule_text}",
                            metadata={
                                "element_type": "businessRule",
                                "rule_type": "condition_action",
                                "condition": condition,
                                "action": action,
                                "evidence_category": "job_aids_edge_cases",
                            },
                        )
                    )

            # Extract exception handling rules
            for match in _EXCEPTION_PATTERN.finditer(text):
                exception_text = match.group(1).strip()
                if len(exception_text) < 15:
                    continue

                rule_text = f"Exception: {exception_text}"
                rule_key = rule_text.lower()
                if rule_key not in seen_rules:
                    seen_rules.add(rule_key)
                    rules.append(
                        ParsedFragment(
                            fragment_type=FragmentType.PROCESS_ELEMENT,
                            content=f"businessRule: {rule_text}",
                            metadata={
                                "element_type": "businessRule",
                                "rule_type": "exception",
                                "exception_text": exception_text,
                                "evidence_category": "job_aids_edge_cases",
                            },
                        )
                    )

            # Extract decision tree branches
            for match in _DECISION_TREE_PATTERN.finditer(text):
                branch_text = match.group(1).strip()
                if len(branch_text) < 10:
                    continue

                full_match = match.group(0).strip()
                rule_key = full_match.lower()
                if rule_key not in seen_rules:
                    seen_rules.add(rule_key)
                    rules.append(
                        ParsedFragment(
                            fragment_type=FragmentType.PROCESS_ELEMENT,
                            content=f"businessRule: {full_match}",
                            metadata={
                                "element_type": "businessRule",
                                "rule_type": "decision_branch",
                                "branch_outcome": branch_text,
                                "evidence_category": "job_aids_edge_cases",
                            },
                        )
                    )

        return rules
