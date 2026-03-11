"""Tests for the DMN 1.3 parser."""

from __future__ import annotations

import os
import tempfile

import pytest

from src.evidence.parsers.dmn_parser import DmnParser


@pytest.fixture
def dmn_parser() -> DmnParser:
    return DmnParser()


@pytest.fixture
def sample_dmn_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"
             id="test_decisions"
             name="Test Decision Model"
             namespace="http://test.example.com/dmn">

  <decision id="Eligibility" name="Eligibility Check">
    <decisionTable id="dt_eligibility" hitPolicy="FIRST">
      <input id="input_score" label="Credit Score">
        <inputExpression id="ie_score" typeRef="integer">
          <text>creditScore</text>
        </inputExpression>
      </input>
      <input id="input_amount" label="Loan Amount">
        <inputExpression id="ie_amount" typeRef="double">
          <text>loanAmount</text>
        </inputExpression>
        <inputValues id="iv_amount">
          <text>"small","medium","large"</text>
        </inputValues>
      </input>
      <output id="output_eligible" label="Eligible" typeRef="boolean" />
      <output id="output_reason" label="Reason" typeRef="string" />

      <rule id="rule_good">
        <inputEntry id="ie1_r1"><text>&gt;= 700</text></inputEntry>
        <inputEntry id="ie2_r1"><text>-</text></inputEntry>
        <outputEntry id="oe1_r1"><text>true</text></outputEntry>
        <outputEntry id="oe2_r1"><text>"Good credit"</text></outputEntry>
      </rule>

      <rule id="rule_bad">
        <inputEntry id="ie1_r2"><text>&lt; 580</text></inputEntry>
        <inputEntry id="ie2_r2"><text>-</text></inputEntry>
        <outputEntry id="oe1_r2"><text>false</text></outputEntry>
        <outputEntry id="oe2_r2"><text>"Below minimum"</text></outputEntry>
      </rule>
    </decisionTable>
  </decision>

  <decision id="Authority" name="Approval Authority">
    <decisionTable id="dt_authority" hitPolicy="UNIQUE">
      <input id="input_type" label="Type">
        <inputExpression id="ie_type" typeRef="string">
          <text>exceptionType</text>
        </inputExpression>
      </input>
      <output id="output_auth" label="Authority" typeRef="string" />

      <rule id="rule_auth1">
        <inputEntry id="ie1_a1"><text>"MINOR"</text></inputEntry>
        <outputEntry id="oe1_a1"><text>"Manager"</text></outputEntry>
      </rule>
    </decisionTable>
  </decision>
</definitions>"""


@pytest.fixture
def dmn_file(sample_dmn_xml: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".dmn")
    with os.fdopen(fd, "w") as f:
        f.write(sample_dmn_xml)
    yield path
    os.unlink(path)


class TestDmnParser:
    """Tests for DmnParser."""

    def test_supported_formats(self, dmn_parser: DmnParser) -> None:
        assert dmn_parser.can_parse(".dmn")
        assert not dmn_parser.can_parse(".bpmn")
        assert not dmn_parser.can_parse(".xml")

    @pytest.mark.asyncio
    async def test_parse_decisions(self, dmn_parser: DmnParser, dmn_file: str) -> None:
        result = await dmn_parser.parse(dmn_file, "test.dmn")

        assert result.error is None
        assert result.metadata["decision_count"] == 2
        assert result.metadata["total_rules"] == 3
        assert result.metadata["parser"] == "dmn"
        assert result.metadata["evidence_category"] == "decision_models"

    @pytest.mark.asyncio
    async def test_parse_decision_fragments(self, dmn_parser: DmnParser, dmn_file: str) -> None:
        result = await dmn_parser.parse(dmn_file, "test.dmn")

        # Should have: 2 decisions + 2 decision tables + 3 rules = 7 fragments
        assert len(result.fragments) == 7

        # Check decision fragments
        decision_frags = [f for f in result.fragments if f.metadata.get("element_type") == "decision"]
        assert len(decision_frags) == 2
        names = {f.metadata["decision_name"] for f in decision_frags}
        assert names == {"Eligibility Check", "Approval Authority"}

    @pytest.mark.asyncio
    async def test_parse_decision_tables(self, dmn_parser: DmnParser, dmn_file: str) -> None:
        result = await dmn_parser.parse(dmn_file, "test.dmn")

        dt_frags = [f for f in result.fragments if f.metadata.get("element_type") == "decisionTable"]
        assert len(dt_frags) == 2

        # Check first decision table
        eligibility_dt = next(f for f in dt_frags if f.metadata["decision_name"] == "Eligibility Check")
        assert eligibility_dt.metadata["hit_policy"] == "FIRST"
        assert eligibility_dt.metadata["input_count"] == 2
        assert eligibility_dt.metadata["output_count"] == 2
        assert eligibility_dt.metadata["input_labels"] == ["Credit Score", "Loan Amount"]

    @pytest.mark.asyncio
    async def test_parse_rules(self, dmn_parser: DmnParser, dmn_file: str) -> None:
        result = await dmn_parser.parse(dmn_file, "test.dmn")

        rule_frags = [f for f in result.fragments if f.metadata.get("element_type") == "businessRule"]
        assert len(rule_frags) == 3

        # Check first rule
        rule_good = next(f for f in rule_frags if f.metadata["element_id"] == "rule_good")
        assert rule_good.metadata["hit_policy"] == "FIRST"
        assert rule_good.metadata["input_entries"] == [">= 700", "-"]
        assert rule_good.metadata["output_entries"] == ["true", '"Good credit"']
        assert "Credit Score" in rule_good.metadata["rule_text"]

    @pytest.mark.asyncio
    async def test_parse_unsupported_format(self, dmn_parser: DmnParser) -> None:
        result = await dmn_parser.parse("/tmp/test.xml", "test.xml")
        assert result.error is not None
        assert "Unsupported" in result.error

    @pytest.mark.asyncio
    async def test_parse_invalid_xml(self, dmn_parser: DmnParser) -> None:
        fd, path = tempfile.mkstemp(suffix=".dmn")
        with os.fdopen(fd, "w") as f:
            f.write("this is not xml")
        try:
            result = await dmn_parser.parse(path, "bad.dmn")
            assert result.error is not None
            assert "Parse error" in result.error
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_parse_real_dmn_file(self, dmn_parser: DmnParser) -> None:
        """Parse the actual underwriting DMN evidence file."""
        dmn_path = os.path.join(
            os.path.dirname(__file__),
            "../../../evidence/loan-origination/km4work/underwriting-decision-rules.dmn",
        )
        if not os.path.exists(dmn_path):
            pytest.skip("Real DMN file not available")

        result = await dmn_parser.parse(dmn_path, "underwriting-decision-rules.dmn")

        assert result.error is None
        assert result.metadata["decision_count"] == 2
        assert result.metadata["total_rules"] == 14  # 9 + 5 rules

        # Verify decisions extracted
        decision_frags = [f for f in result.fragments if f.metadata.get("element_type") == "decision"]
        names = {f.metadata["decision_name"] for f in decision_frags}
        assert "Product Eligibility Determination" in names
        assert "Exception Approval Authority Level" in names

    @pytest.mark.asyncio
    async def test_parse_empty_decision(self, dmn_parser: DmnParser) -> None:
        """Decision with no decision table."""
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"
             id="empty" name="Empty" namespace="http://test.example.com/dmn">
  <decision id="EmptyDec" name="Empty Decision" />
</definitions>"""
        fd, path = tempfile.mkstemp(suffix=".dmn")
        with os.fdopen(fd, "w") as f:
            f.write(xml)
        try:
            result = await dmn_parser.parse(path, "empty.dmn")
            assert result.error is None
            assert result.metadata["decision_count"] == 1
            assert result.metadata["total_rules"] == 0
        finally:
            os.unlink(path)
