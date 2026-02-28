"""LLM suggestion feedback loop service (Story #390).

Handles rejection feedback recording and retrieval for the LLM prompt
injection loop. When a consultant rejects a suggestion, the pattern
is summarized and stored so future prompts can exclude similar ideas.
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    AlternativeSuggestion,
    LLMAuditLog,
    RejectionFeedback,
    ScenarioModification,
)


async def record_rejection_feedback(
    session: AsyncSession,
    engagement_id: UUID,
    suggestion: AlternativeSuggestion,
) -> RejectionFeedback:
    """Create a RejectionFeedback record from a rejected suggestion.

    Summarizes the suggestion into a pattern string for future prompt exclusion.
    """
    # Summarize the suggestion description into a short pattern
    pattern = _summarize_pattern(suggestion.suggestion_text)

    feedback = RejectionFeedback(
        id=uuid.uuid4(),
        engagement_id=engagement_id,
        suggestion_pattern_summary=pattern,
        rejected_suggestion_ids=[str(suggestion.id)],
    )
    session.add(feedback)
    return feedback


async def get_rejection_patterns(
    session: AsyncSession,
    engagement_id: UUID,
) -> list[str]:
    """Load all rejection patterns for an engagement.

    These patterns are injected into the LLM prompt to avoid repeating
    previously rejected suggestion types.
    """
    result = await session.execute(
        select(RejectionFeedback.suggestion_pattern_summary)
        .where(RejectionFeedback.engagement_id == engagement_id)
        .order_by(RejectionFeedback.created_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


async def build_traceability_chain(
    session: AsyncSession,
    scenario_id: UUID,
    modification_id: UUID,
) -> dict[str, Any] | None:
    """Build full traceability chain: modification → suggestion → audit log.

    Returns the three-tier chain in a single response, or None if the
    modification doesn't have an LLM suggestion source.
    """
    # Load modification
    mod_result = await session.execute(
        select(ScenarioModification)
        .where(ScenarioModification.id == modification_id)
        .where(ScenarioModification.scenario_id == scenario_id)
    )
    modification = mod_result.scalar_one_or_none()
    if modification is None:
        return None

    # Check if this modification has a suggestion source
    suggestion_id = modification.suggestion_id or modification.original_suggestion_id
    if suggestion_id is None:
        return {
            "modification": _modification_to_dict(modification),
            "suggestion": None,
            "audit_log": None,
            "traceability_complete": False,
        }

    # Load linked suggestion
    sugg_result = await session.execute(select(AlternativeSuggestion).where(AlternativeSuggestion.id == suggestion_id))
    suggestion = sugg_result.scalar_one_or_none()

    # Load matching audit log (by scenario_id and matching prompt text)
    audit_log = None
    if suggestion is not None:
        audit_result = await session.execute(
            select(LLMAuditLog)
            .where(LLMAuditLog.scenario_id == scenario_id)
            .where(LLMAuditLog.prompt_text == suggestion.llm_prompt)
            .order_by(LLMAuditLog.created_at.desc())
            .limit(1)
        )
        audit_log = audit_result.scalar_one_or_none()

    return {
        "modification": _modification_to_dict(modification),
        "suggestion": _suggestion_to_dict(suggestion) if suggestion else None,
        "audit_log": _audit_log_to_dict(audit_log) if audit_log else None,
        "traceability_complete": suggestion is not None and audit_log is not None,
    }


def build_exclusion_prompt(rejected_patterns: list[str]) -> str:
    """Format rejected patterns for inclusion in the LLM prompt.

    Returns a string that can be injected into the system prompt to
    guide the LLM away from previously rejected suggestion types.
    """
    if not rejected_patterns:
        return ""

    lines = ["The following suggestion patterns have been previously rejected. Avoid similar suggestions:"]
    for i, pattern in enumerate(rejected_patterns, 1):
        lines.append(f"  {i}. {pattern}")
    return "\n".join(lines)


# -- Serialization helpers ---


def _summarize_pattern(suggestion_text: str) -> str:
    """Create a short pattern summary from full suggestion text.

    Truncates to first 200 chars and adds ellipsis if needed.
    """
    text = suggestion_text.strip()
    if len(text) <= 200:
        return text
    return text[:197] + "..."


def _modification_to_dict(m: ScenarioModification) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "scenario_id": str(m.scenario_id),
        "modification_type": m.modification_type if isinstance(m.modification_type, str) else m.modification_type.value,
        "element_id": m.element_id,
        "element_name": m.element_name,
        "template_source": m.template_source,
        "suggestion_id": str(m.suggestion_id) if m.suggestion_id else None,
        "applied_at": m.applied_at.isoformat() if m.applied_at else None,
    }


def _suggestion_to_dict(s: AlternativeSuggestion) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "scenario_id": str(s.scenario_id),
        "suggestion_text": s.suggestion_text,
        "rationale": s.rationale,
        "disposition": s.disposition if isinstance(s.disposition, str) else s.disposition.value,
        "disposition_notes": s.disposition_notes,
        "disposed_at": s.disposed_at.isoformat() if s.disposed_at else None,
        "llm_prompt": s.llm_prompt,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _audit_log_to_dict(a: LLMAuditLog) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "scenario_id": str(a.scenario_id),
        "prompt_text": a.prompt_text,
        "response_text": a.response_text,
        "model_name": a.model_name,
        "prompt_tokens": a.prompt_tokens,
        "completion_tokens": a.completion_tokens,
        "hallucination_flagged": a.hallucination_flagged,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
