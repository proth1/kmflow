"""Decision intelligence API routes.

Provides endpoints for decision point discovery, business rule retrieval,
DMN export, SME validation, and Form 5 coverage gap analysis.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.models import User
from src.core.permissions import require_engagement_access, require_permission
from src.pov.constants import BRIGHTNESS_BRIGHT_THRESHOLD, BRIGHTNESS_DIM_THRESHOLD

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["decisions"])


# ── Schemas ────────────────────────────────────────────────────────────


class DecisionPointResponse(BaseModel):
    """A decision point discovered in the process."""

    id: str
    name: str
    entity_type: str = "decision"
    confidence: float = 0.0
    rule_count: int = 0
    evidence_sources: int = 0
    brightness: str = "DARK"


class BusinessRuleResponse(BaseModel):
    """A business rule attached to a decision point."""

    id: str
    rule_text: str
    threshold_value: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None
    source_weight: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)


class ValidateRulePayload(BaseModel):
    """Payload for SME validation of a business rule."""

    action: str = Field(..., pattern="^(confirm|correct|reject|defer)$")
    corrected_text: str | None = None
    reasoning: str | None = None
    confidence_override: float | None = Field(None, ge=0.0, le=1.0)


class CoverageGapResponse(BaseModel):
    """Form 5 (Rules) coverage gap for an activity."""

    activity_name: str
    has_rules: bool = False
    rule_count: int = 0
    gap_weight: float = 1.2
    probe_generated: bool = False


class DecisionListResponse(BaseModel):
    """Paginated list of decision points."""

    engagement_id: str
    decisions: list[DecisionPointResponse]
    total: int
    limit: int
    offset: int


class BusinessRuleListResponse(BaseModel):
    """Business rules for a decision point."""

    decision_id: str
    decision_name: str
    rules: list[BusinessRuleResponse]
    total: int


class DmnExportResponse(BaseModel):
    """DMN export for a decision point."""

    decision_id: str
    decision_name: str
    dmn_xml: str
    rule_count: int


class ValidateDecisionResponse(BaseModel):
    """Response from validating a decision rule."""

    decision_id: str
    action: str
    validation_count: int


class CoverageResponse(BaseModel):
    """Decision coverage analysis response."""

    engagement_id: str
    total_activities: int
    covered: int
    gaps: list[CoverageGapResponse]
    coverage_percentage: float


# ── Helpers ────────────────────────────────────────────────────────────


def _elements_for_engagement(
    engagement_id: uuid.UUID,
    element_types: list | None = None,
) -> Any:
    """Build a query for ProcessElements belonging to an engagement via ProcessModel join."""
    from src.core.models.pov import ProcessElement, ProcessModel

    stmt = (
        select(ProcessElement)
        .join(ProcessModel, ProcessElement.model_id == ProcessModel.id)
        .where(ProcessModel.engagement_id == engagement_id)
    )
    if element_types:
        stmt = stmt.where(ProcessElement.element_type.in_(element_types))
    return stmt


def _element_by_id(engagement_id: uuid.UUID, element_id: uuid.UUID) -> Any:
    """Build a query for a single ProcessElement belonging to an engagement."""
    from src.core.models.pov import ProcessElement, ProcessModel

    return (
        select(ProcessElement)
        .join(ProcessModel, ProcessElement.model_id == ProcessModel.id)
        .where(
            ProcessModel.engagement_id == engagement_id,
            ProcessElement.id == element_id,
        )
    )


# ── Decision Discovery ───────────────────────────────────────────────


@router.get("/engagements/{engagement_id}/decisions", response_model=DecisionListResponse)
async def list_decisions(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
) -> dict[str, Any]:
    """List all decision points discovered for an engagement.

    Returns decision points extracted from evidence with confidence scores,
    rule counts, and brightness classification.
    """
    from src.core.models.pov import ProcessElement, ProcessElementType

    stmt = (
        _elements_for_engagement(engagement_id, [ProcessElementType.GATEWAY])
        .where(ProcessElement.confidence_score >= min_confidence)
        .order_by(ProcessElement.confidence_score.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(stmt)
    elements = result.scalars().all()

    decisions = []
    for elem in elements:
        score = elem.confidence_score
        brightness = (
            "BRIGHT"
            if score >= BRIGHTNESS_BRIGHT_THRESHOLD
            else ("DIM" if score >= BRIGHTNESS_DIM_THRESHOLD else "DARK")
        )
        decisions.append(
            {
                "id": str(elem.id),
                "name": elem.name,
                "entity_type": "decision",
                "confidence": round(score, 4),
                "rule_count": elem.metadata_json.get("rule_count", 0) if elem.metadata_json else 0,
                "evidence_sources": elem.evidence_count or 0,
                "brightness": brightness,
            }
        )

    return {
        "engagement_id": str(engagement_id),
        "decisions": decisions,
        "total": len(decisions),
        "limit": limit,
        "offset": offset,
    }


# ── Business Rules for a Decision ───────────────────────────────────


@router.get("/engagements/{engagement_id}/decisions/{decision_id}/rules", response_model=BusinessRuleListResponse)
async def get_decision_rules(
    engagement_id: uuid.UUID,
    decision_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get business rules associated with a decision point.

    Queries the knowledge graph for BusinessRule nodes linked to the
    decision via HAS_RULE relationships.
    """
    stmt = _element_by_id(engagement_id, decision_id)
    result = await session.execute(stmt)
    element = result.scalar_one_or_none()

    if element is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision {decision_id} not found",
        )

    # Rules are stored in metadata_json.rules or as linked graph nodes
    rules_data = []
    if element.metadata_json and "rules" in element.metadata_json:
        for rule in element.metadata_json["rules"]:
            rules_data.append(
                {
                    "id": rule.get("id", str(uuid.uuid4())),
                    "rule_text": rule.get("rule_text", ""),
                    "threshold_value": rule.get("threshold_value"),
                    "effective_from": rule.get("effective_from"),
                    "effective_to": rule.get("effective_to"),
                    "source_weight": rule.get("source_weight", 0.0),
                    "evidence_ids": rule.get("evidence_ids", []),
                }
            )

    return {
        "decision_id": str(decision_id),
        "decision_name": element.name,
        "rules": rules_data,
        "total": len(rules_data),
    }


# ── DMN Export ───────────────────────────────────────────────────────


@router.get("/engagements/{engagement_id}/decisions/{decision_id}/dmn", response_model=DmnExportResponse)
async def export_decision_dmn(
    engagement_id: uuid.UUID,
    decision_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Export a decision as DMN 1.3 XML.

    Generates DMN XML from validated business rules attached to the
    decision point. The DMN can be imported into Camunda or any
    DMN-compliant engine.
    """
    from src.pov.dmn_generator import DMNDecision, DMNInput, DMNOutput, DMNRule, generate_dmn_xml

    stmt = _element_by_id(engagement_id, decision_id)
    result = await session.execute(stmt)
    element = result.scalar_one_or_none()

    if element is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision {decision_id} not found",
        )

    # Build DMN from rules metadata
    rules_data = element.metadata_json.get("rules", []) if element.metadata_json else []
    if not rules_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No business rules attached to this decision — cannot generate DMN",
        )

    # Infer inputs/outputs from the first rule
    sample_rule = rules_data[0]
    input_labels = sample_rule.get("input_labels", ["Input"])
    output_labels = sample_rule.get("output_labels", ["Output"])

    inputs = [DMNInput(label=label, variable=label.lower().replace(" ", "_")) for label in input_labels]
    outputs = [DMNOutput(label=label) for label in output_labels]
    rules = [
        DMNRule(
            id=r.get("id", f"rule_{i}"),
            input_entries=r.get("input_entries", ["-"] * len(inputs)),
            output_entries=r.get("output_entries", [""] * len(outputs)),
        )
        for i, r in enumerate(rules_data)
    ]

    decision = DMNDecision(
        id=str(decision_id).replace("-", "_"),
        name=element.name,
        hit_policy=sample_rule.get("hit_policy", "FIRST"),
        inputs=inputs,
        outputs=outputs,
        rules=rules,
    )

    dmn_xml = generate_dmn_xml([decision], name=f"Decision Model - {element.name}")

    return {
        "decision_id": str(decision_id),
        "decision_name": element.name,
        "dmn_xml": dmn_xml,
        "rule_count": len(rules),
    }


# ── SME Validation ───────────────────────────────────────────────────


@router.post("/engagements/{engagement_id}/decisions/{decision_id}/validate", response_model=ValidateDecisionResponse)
async def validate_decision_rule(
    engagement_id: uuid.UUID,
    decision_id: uuid.UUID,
    payload: ValidateRulePayload,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:update")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Record SME validation of a decision's business rules.

    Captures confirm/correct/reject/defer actions from subject matter
    experts reviewing automatically extracted decision logic.
    """
    stmt = _element_by_id(engagement_id, decision_id)
    result = await session.execute(stmt)
    element = result.scalar_one_or_none()

    if element is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision {decision_id} not found",
        )

    # Update metadata with validation
    meta = element.metadata_json or {}
    validations = meta.get("validations", [])
    validations.append(
        {
            "action": payload.action,
            "corrected_text": payload.corrected_text,
            "reasoning": payload.reasoning,
            "confidence_override": payload.confidence_override,
            "validated_by": str(_user.id),
        }
    )
    meta["validations"] = validations

    if payload.confidence_override is not None:
        element.confidence_score = payload.confidence_override

    element.metadata_json = meta
    await session.flush()

    return {
        "decision_id": str(decision_id),
        "action": payload.action,
        "validation_count": len(validations),
    }


# ── Coverage Gaps ────────────────────────────────────────────────────


@router.get("/engagements/{engagement_id}/decisions/coverage", response_model=CoverageResponse)
async def get_decision_coverage(
    engagement_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permission("engagement:read")),
    _engagement_user: User = Depends(require_engagement_access),
) -> dict[str, Any]:
    """Get Form 5 (Rules) coverage gaps for all activities.

    Identifies activities that lack business rules (GOVERNED_BY edges)
    and returns coverage gap analysis for decision intelligence.
    """
    from src.core.models.pov import ProcessElementType

    stmt = _elements_for_engagement(
        engagement_id,
        [ProcessElementType.ACTIVITY, ProcessElementType.GATEWAY],
    )
    result = await session.execute(stmt)
    elements = result.scalars().all()

    gaps = []
    covered_count = 0
    for elem in elements:
        rule_count = elem.metadata_json.get("rule_count", 0) if elem.metadata_json else 0
        if rule_count > 0:
            covered_count += 1
        else:
            gaps.append(
                {
                    "activity_name": elem.name,
                    "has_rules": False,
                    "rule_count": 0,
                    "gap_weight": 1.2,
                    "probe_generated": True,
                }
            )

    total = len(elements)
    coverage_pct = (covered_count / total * 100) if total > 0 else 0.0

    return {
        "engagement_id": str(engagement_id),
        "total_activities": total,
        "covered": covered_count,
        "gaps": gaps,
        "coverage_percentage": round(coverage_pct, 2),
    }
