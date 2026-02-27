"""LLM Modification Suggestion Engine with audit logging (Story #374).

Wraps the existing AlternativeSuggesterService with:
- LLMAuditLog persistence in a finally block
- Governance flag detection via knowledge graph control tags
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.models import LLMAuditLog, SimulationScenario
from src.simulation.suggester import AlternativeSuggesterService

logger = logging.getLogger(__name__)

# Framing language required in all suggestions
CONSIDERATION_FRAMING = "consideration for review"


async def generate_audited_suggestions(
    scenario: SimulationScenario,
    user_id: UUID,
    session: AsyncSession,
    graph_service: Any = None,
    context_notes: str | None = None,
) -> list[dict[str, Any]]:
    """Generate LLM suggestions with full audit logging.

    The audit log is written in a finally block to ensure persistence
    even on LLM failure.

    Args:
        scenario: The scenario with modifications loaded.
        user_id: Requesting user's ID.
        session: Database session for persistence.
        graph_service: Optional knowledge graph service for governance lookup.
        context_notes: Optional user-provided context.

    Returns:
        List of suggestion dicts with governance flags.
    """
    settings = get_settings()
    suggester = AlternativeSuggesterService(settings)

    prompt_text = suggester._build_prompt(scenario, context_notes)
    response_text: str | None = None
    error_message: str | None = None
    prompt_tokens = 0
    completion_tokens = 0
    suggestions: list[dict[str, Any]] = []

    try:
        llm_response = await suggester._call_llm(prompt_text)
        response_text = llm_response
        suggestions = suggester._parse_response(llm_response, prompt_text)

        # Estimate tokens from text length (approximation when SDK doesn't return usage)
        prompt_tokens = len(prompt_text) // 4
        completion_tokens = len(llm_response) // 4

    except Exception as exc:
        error_message = str(exc)
        logger.exception("LLM suggestion failed for scenario %s", scenario.id)
        suggestions = suggester._fallback_suggestions(scenario, prompt_text)
        response_text = suggestions[0].get("llm_response") if suggestions else None

    finally:
        # Always persist audit log
        audit_entry = LLMAuditLog(
            scenario_id=scenario.id,
            user_id=user_id,
            prompt_text=prompt_text,
            response_text=response_text,
            evidence_ids=None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_name=settings.suggester_model,
            error_message=error_message,
        )
        session.add(audit_entry)
        await session.flush()

    # Post-process: add governance flags
    if graph_service:
        suggestions = await _enrich_with_governance(suggestions, scenario, graph_service)

    # Ensure framing language in all suggestions
    for s in suggestions:
        text = s.get("suggestion_text", "")
        if CONSIDERATION_FRAMING not in text.lower():
            s["suggestion_text"] = f"[Consideration for review] {text}"

    return suggestions


async def _enrich_with_governance(
    suggestions: list[dict[str, Any]],
    scenario: SimulationScenario,
    graph_service: Any,
) -> list[dict[str, Any]]:
    """Enrich suggestions with governance flags from knowledge graph.

    Queries the knowledge graph for process elements tagged with
    regulatory controls and adds governance flags to any suggestion
    that affects those elements.
    """
    try:
        records = await graph_service.run_query(
            """
            MATCH (act:Activity)-[:GOVERNED_BY]->(ctrl:Control)
            WHERE act.engagement_id = $engagement_id
            RETURN act.element_id AS element_id, act.name AS activity_name,
                   ctrl.name AS control_name, ctrl.regulation AS regulation
            LIMIT 500
            """,
            {"engagement_id": str(scenario.engagement_id)},
        )
    except Exception:
        logger.exception("Failed to query governance tags for %s", scenario.engagement_id)
        return suggestions

    # Build a map of governed elements
    governed: dict[str, list[dict[str, str]]] = {}
    for rec in records:
        eid = rec.get("element_id", "")
        governed.setdefault(eid, []).append(
            {
                "activity": rec.get("activity_name", ""),
                "control": rec.get("control_name", ""),
                "regulation": rec.get("regulation", ""),
            }
        )

    for suggestion in suggestions:
        flags = suggestion.get("governance_flags") or []
        if isinstance(flags, dict):
            flags = [flags] if flags else []

        # Check if any affected elements are governed
        affected = suggestion.get("affected_element_ids") or []
        for eid in affected:
            if eid in governed:
                for gov in governed[eid]:
                    flags.append(
                        {
                            "type": "known_constraint",
                            "regulation": gov["regulation"],
                            "control": gov["control"],
                            "activity": gov["activity"],
                            "message": (
                                f"Known constraint: {gov['activity']} is governed by "
                                f"{gov['control']} ({gov['regulation']})"
                            ),
                        }
                    )
        suggestion["governance_flags"] = flags if flags else None

    return suggestions
