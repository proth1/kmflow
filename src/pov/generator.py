"""POV Generator - Main pipeline for the LCD algorithm.

Orchestrates all steps of the LCD algorithm:
1. Evidence Aggregation
2. Entity Extraction
3. Cross-Source Triangulation
4. Consensus Building
5. Contradiction Resolution
6. Confidence Scoring
7. BPMN Assembly
8. Gap Detection

Returns a ProcessModel with all elements, contradictions, and gaps.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    Contradiction,
    EvidenceGap,
    ProcessElement,
    ProcessElementType,
    ProcessModel,
    ProcessModelStatus,
)
from src.pov.aggregation import aggregate_evidence
from src.pov.assembly import assemble_bpmn
from src.pov.consensus import build_consensus
from src.pov.contradiction import detect_contradictions
from src.pov.extraction import extract_from_evidence
from src.pov.gaps import detect_gaps
from src.pov.scoring import classify_confidence, score_all_elements
from src.pov.triangulation import triangulate_elements
from src.semantic.entity_extraction import EntityType

logger = logging.getLogger(__name__)

# Map entity types to ProcessElementType
_ENTITY_TYPE_MAP: dict[str, ProcessElementType] = {
    EntityType.ACTIVITY: ProcessElementType.ACTIVITY,
    EntityType.DECISION: ProcessElementType.GATEWAY,
    EntityType.ROLE: ProcessElementType.ROLE,
    EntityType.SYSTEM: ProcessElementType.SYSTEM,
    EntityType.DOCUMENT: ProcessElementType.DOCUMENT,
}


@dataclass
class GenerationResult:
    """Result from POV generation.

    Attributes:
        process_model: The generated ProcessModel ORM object.
        success: Whether generation completed successfully.
        error: Error message if generation failed.
        stats: Generation statistics.
    """

    process_model: ProcessModel | None = None
    success: bool = False
    error: str = ""
    stats: dict[str, int] = field(default_factory=dict)


async def generate_pov(
    session: AsyncSession,
    engagement_id: str,
    scope: str = "all",
    generated_by: str = "lcd_algorithm",
) -> GenerationResult:
    """Generate a Process Point of View for an engagement.

    Orchestrates the full LCD algorithm pipeline:
    1. Aggregate validated evidence
    2. Extract entities from fragments
    3. Triangulate across sources
    4. Build consensus model
    5. Detect and resolve contradictions
    6. Score confidence
    7. Assemble BPMN XML
    8. Detect evidence gaps
    9. Persist to database

    Args:
        session: Async database session.
        engagement_id: The engagement to generate a POV for.
        scope: Scope filter for evidence (default: "all").
        generated_by: Identifier for who/what triggered generation.

    Returns:
        GenerationResult with the ProcessModel or error details.
    """
    # Create the process model record in GENERATING status
    model = ProcessModel(
        id=uuid.uuid4(),
        engagement_id=uuid.UUID(engagement_id),
        version=1,
        scope=scope,
        status=ProcessModelStatus.GENERATING,
        generated_by=generated_by,
    )
    session.add(model)
    await session.flush()

    try:
        # Step 1: Aggregate evidence
        aggregated = await aggregate_evidence(session, engagement_id, scope if scope != "all" else None)

        if aggregated.evidence_count == 0:
            model.status = ProcessModelStatus.FAILED
            model.metadata_json = {"error": "No validated evidence found"}
            await session.flush()
            return GenerationResult(
                process_model=model,
                success=False,
                error="No validated evidence found for this engagement and scope",
            )

        # Step 2: Extract entities
        extraction = await extract_from_evidence(aggregated.evidence_items, aggregated.fragments)

        if not extraction.entities:
            model.status = ProcessModelStatus.FAILED
            model.metadata_json = {"error": "No entities extracted from evidence"}
            await session.flush()
            return GenerationResult(
                process_model=model,
                success=False,
                error="No entities could be extracted from the evidence",
            )

        # Step 3: Triangulate across sources
        triangulated = triangulate_elements(
            extraction.entities,
            extraction.entity_to_evidence,
            aggregated.evidence_items,
        )

        # Step 4: Build consensus
        consensus_result = build_consensus(triangulated, aggregated.evidence_items)
        consensus = consensus_result.elements

        # Step 5: Detect and resolve contradictions
        contradictions = detect_contradictions(consensus, aggregated.evidence_items)

        # Step 6: Score confidence
        scored = score_all_elements(consensus, aggregated.evidence_items)

        # Step 7: Assemble BPMN
        bpmn_xml = assemble_bpmn(scored, process_name=f"POV: {scope}")

        # Step 8: Detect gaps
        gaps = detect_gaps(consensus, scored, aggregated.evidence_items)

        # Calculate overall model confidence
        overall_confidence = sum(s[1] for s in scored) / len(scored) if scored else 0.0

        # Persist elements
        element_records: list[ProcessElement] = []
        for elem, score, level in scored:
            entity = elem.triangulated.entity
            element_type = _ENTITY_TYPE_MAP.get(entity.entity_type, ProcessElementType.ACTIVITY)

            pe = ProcessElement(
                id=uuid.uuid4(),
                model_id=model.id,
                element_type=element_type,
                name=entity.name,
                confidence_score=round(score, 4),
                triangulation_score=round(elem.triangulated.triangulation_score, 4),
                corroboration_level=elem.triangulated.corroboration_level,
                evidence_count=elem.triangulated.source_count,
                evidence_ids=elem.triangulated.evidence_ids,
                metadata_json={
                    "confidence_level": level,
                    "entity_type": str(entity.entity_type),
                    "weighted_vote_score": round(elem.weighted_vote_score, 4),
                },
            )
            session.add(pe)
            element_records.append(pe)

        # Persist contradictions
        contradiction_records: list[Contradiction] = []
        for c in contradictions:
            cr = Contradiction(
                id=uuid.uuid4(),
                model_id=model.id,
                element_name=c.element_name,
                field_name=c.field_name,
                values=c.values,
                resolution_value=c.resolution_value,
                resolution_reason=c.resolution_reason,
                evidence_ids=c.evidence_ids,
            )
            session.add(cr)
            contradiction_records.append(cr)

        # Persist gaps
        gap_records: list[EvidenceGap] = []
        for g in gaps:
            gr = EvidenceGap(
                id=uuid.uuid4(),
                model_id=model.id,
                gap_type=g.gap_type,
                description=g.description,
                severity=g.severity,
                recommendation=g.recommendation,
            )
            session.add(gr)
            gap_records.append(gr)

        # Update the process model
        model.status = ProcessModelStatus.COMPLETED
        model.confidence_score = round(overall_confidence, 4)
        model.bpmn_xml = bpmn_xml
        model.element_count = len(element_records)
        model.evidence_count = aggregated.evidence_count
        model.contradiction_count = len(contradiction_records)
        model.generated_at = datetime.now(UTC)
        model.metadata_json = {
            "overall_confidence_level": classify_confidence(overall_confidence),
            "element_count": len(element_records),
            "contradiction_count": len(contradiction_records),
            "gap_count": len(gap_records),
            "evidence_count": aggregated.evidence_count,
            "fragment_count": aggregated.fragment_count,
            "raw_entity_count": extraction.raw_entity_count,
            "resolved_entity_count": len(extraction.entities),
        }

        await session.flush()

        logger.info(
            "POV generation complete for engagement %s: %d elements, %d contradictions, %d gaps, confidence=%.3f",
            engagement_id,
            len(element_records),
            len(contradiction_records),
            len(gap_records),
            overall_confidence,
        )

        return GenerationResult(
            process_model=model,
            success=True,
            stats={
                "elements": len(element_records),
                "contradictions": len(contradiction_records),
                "gaps": len(gap_records),
                "evidence_items": aggregated.evidence_count,
                "fragments": aggregated.fragment_count,
            },
        )

    except (ValueError, RuntimeError) as e:
        logger.exception("POV generation failed for engagement %s", engagement_id)
        model.status = ProcessModelStatus.FAILED
        model.metadata_json = {"error": str(e)}
        await session.flush()

        return GenerationResult(
            process_model=model,
            success=False,
            error=str(e),
        )
