"""DMN 1.3 XML parser for decision model evidence.

Extracts decisions, decision tables, input/output columns, rules,
and hit policies from DMN 1.3 XML files. Produces structured
ParsedFragments with BusinessRule metadata for graph ingestion.
"""

from __future__ import annotations

import logging
from pathlib import Path

from lxml import etree

from src.core.models import FragmentType
from src.evidence.parsers.base import BaseParser, ParsedFragment, ParseResult, detect_xml_namespace

logger = logging.getLogger(__name__)

# DMN 1.3 namespace
DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"
DMN_NSMAP = {"dmn": DMN_NS}


class DmnParser(BaseParser):
    """Parser for DMN 1.3 XML decision model files."""

    supported_formats = [".dmn"]

    async def parse(self, file_path: str, file_name: str) -> ParseResult:
        """Parse a DMN file and extract decision elements.

        Extracts:
        - Decisions (name, id)
        - Decision tables (hit policy, input/output columns)
        - Rules (input entries, output entries)
        - Input/output variable definitions
        """
        ext = Path(file_name).suffix.lower()
        if ext not in self.supported_formats:
            return ParseResult(error=f"Unsupported DMN format: {ext}")

        try:
            return await self._parse_dmn(file_path)
        except Exception as e:
            logger.exception("Failed to parse DMN: %s", file_name)
            return ParseResult(error=f"Parse error: {e}")

    async def _parse_dmn(self, file_path: str) -> ParseResult:
        """Parse a DMN XML file and extract decision model elements."""
        fragments: list[ParsedFragment] = []
        metadata: dict[str, str | int | float | bool | list[str] | None] = {}

        parser = etree.XMLParser(resolve_entities=False, no_network=True, dtd_validation=False)
        tree = etree.parse(file_path, parser)
        root = tree.getroot()

        nsmap = self._detect_namespace(root)
        ns = nsmap.get("dmn", DMN_NS)

        # Extract top-level definitions metadata
        defn_name = root.get("name", "")
        defn_id = root.get("id", "")
        metadata["dmn_name"] = defn_name
        metadata["dmn_id"] = defn_id
        metadata["evidence_category"] = "decision_models"
        metadata["parser"] = "dmn"

        # Extract decisions
        decisions = root.findall(f".//{{{ns}}}decision")
        metadata["decision_count"] = len(decisions)

        total_rules = 0

        for decision in decisions:
            decision_id = decision.get("id", "")
            decision_name = decision.get("name", decision_id)

            # Decision fragment
            fragments.append(
                ParsedFragment(
                    fragment_type=FragmentType.PROCESS_ELEMENT,
                    content=f"decision: {decision_name}",
                    metadata={
                        "element_type": "decision",
                        "element_id": decision_id,
                        "decision_name": decision_name,
                        "dmn_id": defn_id,
                    },
                )
            )

            # Extract decision tables within this decision
            for dt in decision.findall(f".//{{{ns}}}decisionTable"):
                dt_id = dt.get("id", "")
                hit_policy = dt.get("hitPolicy", "UNIQUE")

                # Extract inputs
                inputs = []
                for inp in dt.findall(f"{{{ns}}}input"):
                    inp_label = inp.get("label", inp.get("id", ""))
                    inp_id = inp.get("id", "")
                    expr_elem = inp.find(f"{{{ns}}}inputExpression")
                    type_ref = expr_elem.get("typeRef", "string") if expr_elem is not None else "string"
                    variable = ""
                    text_elem = expr_elem.find(f"{{{ns}}}text") if expr_elem is not None else None
                    if text_elem is not None and text_elem.text:
                        variable = text_elem.text.strip()

                    # Extract allowed values
                    allowed_values: list[str] = []
                    values_elem = inp.find(f"{{{ns}}}inputValues")
                    if values_elem is not None:
                        values_text = values_elem.find(f"{{{ns}}}text")
                        if values_text is not None and values_text.text:
                            allowed_values = [v.strip().strip('"') for v in values_text.text.split(",")]

                    inputs.append(
                        {
                            "id": inp_id,
                            "label": inp_label,
                            "variable": variable,
                            "type_ref": type_ref,
                            "allowed_values": allowed_values,
                        }
                    )

                # Extract outputs
                outputs = []
                for out in dt.findall(f"{{{ns}}}output"):
                    out_label = out.get("label", out.get("id", ""))
                    out_id = out.get("id", "")
                    out_type = out.get("typeRef", "string")
                    outputs.append(
                        {
                            "id": out_id,
                            "label": out_label,
                            "type_ref": out_type,
                        }
                    )

                # Decision table fragment
                fragments.append(
                    ParsedFragment(
                        fragment_type=FragmentType.PROCESS_ELEMENT,
                        content=f"decisionTable: {decision_name} (hitPolicy={hit_policy})",
                        metadata={
                            "element_type": "decisionTable",
                            "element_id": dt_id,
                            "decision_id": decision_id,
                            "decision_name": decision_name,
                            "hit_policy": hit_policy,
                            "input_count": len(inputs),
                            "output_count": len(outputs),
                            "input_labels": [str(i["label"]) for i in inputs],
                            "output_labels": [str(o["label"]) for o in outputs],
                        },
                    )
                )

                # Extract rules
                rules = dt.findall(f"{{{ns}}}rule")
                for rule in rules:
                    rule_id = rule.get("id", "")

                    input_entries = []
                    for ie in rule.findall(f"{{{ns}}}inputEntry"):
                        text_el = ie.find(f"{{{ns}}}text")
                        input_entries.append(text_el.text.strip() if text_el is not None and text_el.text else "-")

                    output_entries = []
                    for oe in rule.findall(f"{{{ns}}}outputEntry"):
                        text_el = oe.find(f"{{{ns}}}text")
                        output_entries.append(text_el.text.strip() if text_el is not None and text_el.text else "")

                    # Build human-readable rule text
                    conditions = []
                    for i, entry in enumerate(input_entries):
                        if entry != "-" and i < len(inputs):
                            conditions.append(f"{inputs[i]['label']} {entry}")

                    results = []
                    for i, entry in enumerate(output_entries):
                        if entry and i < len(outputs):
                            results.append(f"{outputs[i]['label']}={entry}")

                    rule_text = " AND ".join(conditions) if conditions else "default"
                    rule_text += f" → {', '.join(results)}" if results else ""

                    fragments.append(
                        ParsedFragment(
                            fragment_type=FragmentType.PROCESS_ELEMENT,
                            content=f"businessRule: {rule_text}",
                            metadata={
                                "element_type": "businessRule",
                                "element_id": rule_id,
                                "decision_id": decision_id,
                                "decision_name": decision_name,
                                "hit_policy": hit_policy,
                                "input_entries": input_entries,
                                "output_entries": output_entries,
                                "rule_text": rule_text,
                            },
                        )
                    )
                    total_rules += 1

        metadata["total_rules"] = total_rules
        return ParseResult(fragments=fragments, metadata=metadata)

    def _detect_namespace(self, root: etree._Element) -> dict[str, str]:
        """Detect the DMN namespace from the root element."""
        return detect_xml_namespace(root, "dmn", DMN_NS, spec_path="omg.org/spec/DMN")
