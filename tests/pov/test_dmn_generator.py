"""Tests for the DMN 1.3 generator."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from src.pov.dmn_generator import (
    DMNDecision,
    DMNInput,
    DMNOutput,
    DMNRule,
    generate_dmn_xml,
)

DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"


class TestDmnGenerator:
    """Tests for generate_dmn_xml."""

    def _parse(self, xml_str: str) -> ET.Element:
        return ET.fromstring(xml_str)

    def test_generate_single_decision(self) -> None:
        decision = DMNDecision(
            id="TestDec",
            name="Test Decision",
            hit_policy="FIRST",
            inputs=[
                DMNInput(label="Score", variable="score", type_ref="integer"),
            ],
            outputs=[
                DMNOutput(label="Result", type_ref="string"),
            ],
            rules=[
                DMNRule(id="r1", input_entries=[">= 700"], output_entries=['"Pass"']),
                DMNRule(id="r2", input_entries=["< 500"], output_entries=['"Fail"']),
            ],
        )

        xml_str = generate_dmn_xml([decision], name="Test Model")
        root = self._parse(xml_str)

        assert root.tag == f"{{{DMN_NS}}}definitions"
        assert root.get("name") == "Test Model"

        decisions = root.findall(f".//{{{DMN_NS}}}decision")
        assert len(decisions) == 1
        assert decisions[0].get("name") == "Test Decision"

    def test_decision_table_hit_policy(self) -> None:
        decision = DMNDecision(
            id="Dec1",
            name="Dec 1",
            hit_policy="UNIQUE",
            inputs=[DMNInput(label="X", variable="x")],
            outputs=[DMNOutput(label="Y")],
            rules=[DMNRule(id="r1", input_entries=["1"], output_entries=["a"])],
        )

        xml_str = generate_dmn_xml([decision])
        root = self._parse(xml_str)

        dt = root.find(f".//{{{DMN_NS}}}decisionTable")
        assert dt is not None
        assert dt.get("hitPolicy") == "UNIQUE"

    def test_input_output_columns(self) -> None:
        decision = DMNDecision(
            id="Dec2",
            name="Dec 2",
            inputs=[
                DMNInput(label="Credit Score", variable="creditScore", type_ref="integer"),
                DMNInput(label="LTV", variable="ltv", type_ref="double"),
            ],
            outputs=[
                DMNOutput(label="Eligible", type_ref="boolean"),
                DMNOutput(label="Reason", type_ref="string"),
            ],
            rules=[],
        )

        xml_str = generate_dmn_xml([decision])
        root = self._parse(xml_str)

        inputs = root.findall(f".//{{{DMN_NS}}}input")
        assert len(inputs) == 2
        assert inputs[0].get("label") == "Credit Score"

        outputs = root.findall(f".//{{{DMN_NS}}}output")
        assert len(outputs) == 2
        assert outputs[1].get("label") == "Reason"

    def test_input_expression_variable(self) -> None:
        decision = DMNDecision(
            id="Dec3",
            name="Dec 3",
            inputs=[DMNInput(label="Score", variable="creditScore", type_ref="integer")],
            outputs=[DMNOutput(label="Out")],
            rules=[],
        )

        xml_str = generate_dmn_xml([decision])
        root = self._parse(xml_str)

        expr = root.find(f".//{{{DMN_NS}}}inputExpression")
        assert expr is not None
        assert expr.get("typeRef") == "integer"
        text = expr.find(f"{{{DMN_NS}}}text")
        assert text is not None
        assert text.text == "creditScore"

    def test_allowed_values(self) -> None:
        decision = DMNDecision(
            id="Dec4",
            name="Dec 4",
            inputs=[
                DMNInput(
                    label="Type",
                    variable="type",
                    allowed_values=["small", "medium", "large"],
                ),
            ],
            outputs=[DMNOutput(label="Out")],
            rules=[],
        )

        xml_str = generate_dmn_xml([decision])
        root = self._parse(xml_str)

        iv = root.find(f".//{{{DMN_NS}}}inputValues")
        assert iv is not None
        text = iv.find(f"{{{DMN_NS}}}text")
        assert text is not None
        assert '"small"' in text.text
        assert '"large"' in text.text

    def test_rules_with_entries(self) -> None:
        decision = DMNDecision(
            id="Dec5",
            name="Dec 5",
            inputs=[DMNInput(label="A", variable="a"), DMNInput(label="B", variable="b")],
            outputs=[DMNOutput(label="C")],
            rules=[
                DMNRule(id="r1", input_entries=[">= 10", "-"], output_entries=['"yes"']),
                DMNRule(id="r2", input_entries=["< 5", '"x"'], output_entries=['"no"']),
            ],
        )

        xml_str = generate_dmn_xml([decision])
        root = self._parse(xml_str)

        rules = root.findall(f".//{{{DMN_NS}}}rule")
        assert len(rules) == 2

        # Check first rule entries
        r1_inputs = rules[0].findall(f"{{{DMN_NS}}}inputEntry")
        assert len(r1_inputs) == 2
        assert r1_inputs[0].find(f"{{{DMN_NS}}}text").text == ">= 10"
        assert r1_inputs[1].find(f"{{{DMN_NS}}}text").text == "-"

        r1_outputs = rules[0].findall(f"{{{DMN_NS}}}outputEntry")
        assert len(r1_outputs) == 1
        assert r1_outputs[0].find(f"{{{DMN_NS}}}text").text == '"yes"'

    def test_multiple_decisions(self) -> None:
        decisions = [
            DMNDecision(
                id="D1",
                name="Decision 1",
                inputs=[DMNInput(label="X", variable="x")],
                outputs=[DMNOutput(label="Y")],
                rules=[],
            ),
            DMNDecision(
                id="D2",
                name="Decision 2",
                inputs=[DMNInput(label="A", variable="a")],
                outputs=[DMNOutput(label="B")],
                rules=[DMNRule(id="r1", input_entries=["1"], output_entries=["2"])],
            ),
        ]

        xml_str = generate_dmn_xml(decisions, name="Multi-Decision Model")
        root = self._parse(xml_str)

        decs = root.findall(f".//{{{DMN_NS}}}decision")
        assert len(decs) == 2

    def test_empty_decisions(self) -> None:
        xml_str = generate_dmn_xml([], name="Empty Model")
        root = self._parse(xml_str)

        assert root.get("name") == "Empty Model"
        decs = root.findall(f".//{{{DMN_NS}}}decision")
        assert len(decs) == 0

    def test_xml_declaration(self) -> None:
        xml_str = generate_dmn_xml([])
        assert xml_str.startswith("<?xml version=")

    def test_rule_auto_id(self) -> None:
        rule = DMNRule(input_entries=["1"], output_entries=["2"])
        assert rule.id.startswith("rule_")
        assert len(rule.id) > 5
