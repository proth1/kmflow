"""Suggestion review service (Story #379).

Handles ACCEPT/MODIFY/REJECT workflow for LLM-generated alternative suggestions.
Each disposition creates the appropriate ScenarioModification and updates
the suggestion status atomically within a single transaction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models import (
    AlternativeSuggestion,
    ModificationType,
    ScenarioModification,
    SuggestionDisposition,
)


async def review_suggestion(
    session: AsyncSession,
    scenario_id: UUID,
    suggestion_id: UUID,
    disposition: SuggestionDisposition,
    user_id: UUID,
    modified_content: dict[str, Any] | None = None,
    rejection_reason: str | None = None,
    disposition_notes: str | None = None,
) -> dict[str, Any]:
    """Process a suggestion review decision.

    Args:
        session: Database session (caller manages commit).
        scenario_id: The scenario owning the suggestion.
        suggestion_id: The suggestion to review.
        disposition: ACCEPTED, MODIFIED, or REJECTED.
        user_id: The reviewing user's ID.
        modified_content: Required when disposition is MODIFIED.
        rejection_reason: Required when disposition is REJECTED.
        disposition_notes: Optional notes for any disposition.

    Returns:
        Dict with suggestion and optional modification details.

    Raises:
        ValueError: If validation fails (suggestion not found, not PENDING,
            missing required fields).
    """
    # Load suggestion scoped to scenario with row-level lock to prevent
    # concurrent disposition race conditions
    result = await session.execute(
        select(AlternativeSuggestion)
        .where(
            AlternativeSuggestion.id == suggestion_id,
            AlternativeSuggestion.scenario_id == scenario_id,
        )
        .with_for_update()
    )
    suggestion = result.scalar_one_or_none()
    if not suggestion:
        raise ValueError(f"Suggestion {suggestion_id} not found for scenario {scenario_id}")

    if suggestion.disposition != SuggestionDisposition.PENDING:
        raise ValueError(f"Suggestion {suggestion_id} is already {suggestion.disposition.value}")

    # Validate required fields per disposition
    if disposition == SuggestionDisposition.MODIFIED and not modified_content:
        raise ValueError("modified_content is required when disposition is MODIFIED")
    if disposition == SuggestionDisposition.REJECTED and not rejection_reason:
        raise ValueError("rejection_reason is required when disposition is REJECTED")

    now = datetime.now(UTC)

    # Update suggestion
    suggestion.disposition = disposition
    suggestion.disposition_notes = disposition_notes or rejection_reason
    suggestion.disposed_at = now
    suggestion.disposed_by_user_id = user_id

    modification = None

    if disposition == SuggestionDisposition.ACCEPTED:
        # Create modification from original suggestion content
        modification = ScenarioModification(
            scenario_id=scenario_id,
            modification_type=ModificationType.TASK_MODIFY,
            element_id=str(suggestion_id),
            element_name=suggestion.suggestion_text[:512],
            change_data={"description": suggestion.suggestion_text, "rationale": suggestion.rationale},
            template_source="llm_suggestion",
            suggestion_id=suggestion_id,
        )
        session.add(modification)

    elif disposition == SuggestionDisposition.MODIFIED:
        # Store modified content on the suggestion
        suggestion.modified_content = modified_content

        # Create modification from modified content
        modification = ScenarioModification(
            scenario_id=scenario_id,
            modification_type=ModificationType.TASK_MODIFY,
            element_id=str(suggestion_id),
            element_name=modified_content.get("name", suggestion.suggestion_text[:512]),
            change_data=modified_content,
            template_source="llm_suggestion",
            original_suggestion_id=suggestion_id,
        )
        session.add(modification)

    # REJECTED: no modification created

    return {
        "suggestion_id": str(suggestion_id),
        "disposition": disposition.value,
        "disposed_at": now.isoformat(),
        "modification_id": str(modification.id) if modification else None,
    }
