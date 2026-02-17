"""Tests for conformance checker (src/conformance/checker.py)."""

from __future__ import annotations

import pytest

from src.conformance.bpmn_parser import parse_bpmn_xml
from src.conformance.checker import ConformanceChecker
from src.conformance.metrics import calculate_metrics

REF_BPMN = '''<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="P1" isExecutable="true">
    <bpmn:startEvent id="S" name="Start"/>
    <bpmn:task id="T1" name="Receive Order"/>
    <bpmn:task id="T2" name="Validate Order"/>
    <bpmn:task id="T3" name="Ship Order"/>
    <bpmn:endEvent id="E" name="End"/>
    <bpmn:sequenceFlow id="F1" sourceRef="S" targetRef="T1"/>
    <bpmn:sequenceFlow id="F2" sourceRef="T1" targetRef="T2"/>
    <bpmn:sequenceFlow id="F3" sourceRef="T2" targetRef="T3"/>
    <bpmn:sequenceFlow id="F4" sourceRef="T3" targetRef="E"/>
  </bpmn:process>
</bpmn:definitions>'''


class TestConformanceChecker:
    def test_perfect_conformance(self) -> None:
        checker = ConformanceChecker()
        result = checker.check_from_xml(REF_BPMN, REF_BPMN)
        assert result.fitness_score == 1.0
        assert result.precision_score == 1.0
        assert result.matching_elements == 3
        assert len(result.deviations) == 0

    def test_missing_activity(self) -> None:
        observed = REF_BPMN.replace(
            '<bpmn:task id="T3" name="Ship Order"/>',
            ''
        )
        checker = ConformanceChecker()
        result = checker.check_from_xml(REF_BPMN, observed)
        assert result.fitness_score < 1.0
        missing = [d for d in result.deviations if d.deviation_type == "missing_activity"]
        assert len(missing) >= 1
        assert missing[0].severity == "high"

    def test_extra_activity(self) -> None:
        observed = REF_BPMN.replace(
            '<bpmn:endEvent id="E" name="End"/>',
            '<bpmn:task id="T4" name="Send Invoice"/>\n    <bpmn:endEvent id="E" name="End"/>'
        )
        checker = ConformanceChecker()
        result = checker.check_from_xml(REF_BPMN, observed)
        extra = [d for d in result.deviations if d.deviation_type == "extra_activity"]
        assert len(extra) >= 1
        assert extra[0].severity == "medium"

    def test_metrics_calculation(self) -> None:
        checker = ConformanceChecker()
        result = checker.check_from_xml(REF_BPMN, REF_BPMN)
        metrics = calculate_metrics(result)
        assert metrics.fitness == 1.0
        assert metrics.precision == 1.0
        assert metrics.f1_score == 1.0
        assert metrics.deviation_count == 0

    def test_partial_conformance_metrics(self) -> None:
        observed = REF_BPMN.replace(
            '<bpmn:task id="T3" name="Ship Order"/>',
            ''
        )
        checker = ConformanceChecker()
        result = checker.check_from_xml(REF_BPMN, observed)
        metrics = calculate_metrics(result)
        assert 0 < metrics.fitness < 1.0
        assert metrics.high_severity_count >= 1
