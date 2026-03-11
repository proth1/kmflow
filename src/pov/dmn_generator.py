"""Generate DMN 1.3 XML from validated BusinessRule graph nodes.

Produces DMN 1.3 decision tables that can be imported into Camunda,
Drools, or any DMN-compliant engine. Each decision maps to one or more
rules extracted from the knowledge graph via the consensus algorithm.
"""

from __future__ import annotations

import logging
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"
DMNDI_NS = "https://www.omg.org/spec/DMN/20191111/DMNDI/"
DC_NS = "http://www.omg.org/spec/DMN/20180521/DC/"


@dataclass
class DMNInput:
    """An input column for a DMN decision table."""

    label: str
    variable: str
    type_ref: str = "string"
    allowed_values: list[str] = field(default_factory=list)


@dataclass
class DMNOutput:
    """An output column for a DMN decision table."""

    label: str
    type_ref: str = "string"


@dataclass
class DMNRule:
    """A single rule (row) in a DMN decision table."""

    id: str = ""
    input_entries: list[str] = field(default_factory=list)
    output_entries: list[str] = field(default_factory=list)
    annotation: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"rule_{uuid.uuid4().hex[:8]}"


@dataclass
class DMNDecision:
    """A decision containing a decision table with inputs, outputs, and rules."""

    id: str
    name: str
    hit_policy: str = "UNIQUE"
    inputs: list[DMNInput] = field(default_factory=list)
    outputs: list[DMNOutput] = field(default_factory=list)
    rules: list[DMNRule] = field(default_factory=list)


def generate_dmn_xml(
    decisions: list[DMNDecision],
    *,
    name: str = "Generated Decision Model",
    namespace: str = "http://kmflow.ai/dmn",
) -> str:
    """Generate DMN 1.3 XML from a list of decisions.

    Args:
        decisions: List of DMNDecision objects with tables and rules.
        name: Name for the DMN definitions element.
        namespace: Target namespace for the DMN model.

    Returns:
        DMN 1.3 XML string.
    """
    ET.register_namespace("", DMN_NS)
    ET.register_namespace("dmndi", DMNDI_NS)
    ET.register_namespace("dc", DC_NS)

    defn_id = f"Definitions_{uuid.uuid4().hex[:8]}"
    definitions = ET.Element(
        f"{{{DMN_NS}}}definitions",
        {
            "id": defn_id,
            "name": name,
            "namespace": namespace,
        },
    )

    for decision in decisions:
        _add_decision(definitions, decision)

    ET.indent(definitions, space="  ")
    xml_str = ET.tostring(definitions, encoding="unicode", xml_declaration=True)

    logger.info(
        "Generated DMN with %d decisions, %d total rules",
        len(decisions),
        sum(len(d.rules) for d in decisions),
    )

    return xml_str


def _add_decision(parent: ET.Element, decision: DMNDecision) -> None:
    """Add a decision element with its decision table to the definitions."""
    dec_elem = ET.SubElement(
        parent,
        f"{{{DMN_NS}}}decision",
        {"id": decision.id, "name": decision.name},
    )

    dt_id = f"dt_{decision.id}"
    dt_elem = ET.SubElement(
        dec_elem,
        f"{{{DMN_NS}}}decisionTable",
        {"id": dt_id, "hitPolicy": decision.hit_policy},
    )

    # Add inputs
    for i, inp in enumerate(decision.inputs):
        inp_id = f"input_{decision.id}_{i}"
        inp_elem = ET.SubElement(
            dt_elem,
            f"{{{DMN_NS}}}input",
            {"id": inp_id, "label": inp.label},
        )
        expr_id = f"ie_{decision.id}_{i}"
        expr_elem = ET.SubElement(
            inp_elem,
            f"{{{DMN_NS}}}inputExpression",
            {"id": expr_id, "typeRef": inp.type_ref},
        )
        text_elem = ET.SubElement(expr_elem, f"{{{DMN_NS}}}text")
        text_elem.text = inp.variable

        if inp.allowed_values:
            iv_elem = ET.SubElement(
                inp_elem,
                f"{{{DMN_NS}}}inputValues",
                {"id": f"iv_{decision.id}_{i}"},
            )
            iv_text = ET.SubElement(iv_elem, f"{{{DMN_NS}}}text")
            iv_text.text = ",".join(f'"{v}"' for v in inp.allowed_values)

    # Add outputs
    for i, out in enumerate(decision.outputs):
        out_id = f"output_{decision.id}_{i}"
        ET.SubElement(
            dt_elem,
            f"{{{DMN_NS}}}output",
            {"id": out_id, "label": out.label, "typeRef": out.type_ref},
        )

    # Add rules
    for rule in decision.rules:
        rule_elem = ET.SubElement(
            dt_elem,
            f"{{{DMN_NS}}}rule",
            {"id": rule.id},
        )

        for j, entry in enumerate(rule.input_entries):
            ie_elem = ET.SubElement(
                rule_elem,
                f"{{{DMN_NS}}}inputEntry",
                {"id": f"ie_{rule.id}_{j}"},
            )
            ie_text = ET.SubElement(ie_elem, f"{{{DMN_NS}}}text")
            ie_text.text = entry

        for j, entry in enumerate(rule.output_entries):
            oe_elem = ET.SubElement(
                rule_elem,
                f"{{{DMN_NS}}}outputEntry",
                {"id": f"oe_{rule.id}_{j}"},
            )
            oe_text = ET.SubElement(oe_elem, f"{{{DMN_NS}}}text")
            oe_text.text = entry
