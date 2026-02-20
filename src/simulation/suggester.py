"""LLM-assisted alternative scenario suggestion service.

Builds prompts from scenario context, calls Claude API,
and returns structured suggestions with governance flags.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


class AlternativeSuggesterService:
    """Generates alternative scenario suggestions using Claude."""

    async def generate_suggestions(
        self,
        scenario: Any,
        user_id: UUID,
        context_notes: str | None = None,
    ) -> list[dict[str, Any]]:
        """Generate alternative suggestions for a scenario.

        Args:
            scenario: The SimulationScenario ORM object (with modifications loaded).
            user_id: The requesting user's ID.
            context_notes: Optional user-provided context.

        Returns:
            List of suggestion dicts ready for persistence.
        """
        prompt = self._build_prompt(scenario, context_notes)

        try:
            llm_response = await self._call_llm(prompt)
            suggestions = self._parse_response(llm_response, prompt)
        except Exception:
            logger.exception("LLM suggestion generation failed, returning fallback")
            suggestions = self._fallback_suggestions(scenario, prompt)

        return suggestions

    def _build_prompt(self, scenario: Any, context_notes: str | None) -> str:
        """Build the LLM prompt from scenario context."""
        modifications_desc = ""
        if hasattr(scenario, "modifications") and scenario.modifications:
            mod_lines = []
            for m in scenario.modifications:
                mod_type = m.modification_type.value if hasattr(m.modification_type, "value") else m.modification_type
                mod_lines.append(f"- {mod_type}: {m.element_name}")
            modifications_desc = "\n".join(mod_lines)

        prompt = f"""You are a process intelligence advisor. Analyze this scenario and suggest 2-3 alternative approaches.

Scenario: {scenario.name}
Type: {scenario.simulation_type.value if hasattr(scenario.simulation_type, 'value') else scenario.simulation_type}
Description: {scenario.description or 'No description provided'}

Current modifications:
{modifications_desc or 'None'}

{f'Additional context: {context_notes}' if context_notes else ''}

For each suggestion, provide:
1. A clear suggestion text (what to do differently)
2. A rationale (why this approach could be better)
3. Governance flags (any compliance or risk considerations)
4. Evidence gaps (what additional data would be needed)

Format as JSON array with keys: suggestion_text, rationale, governance_flags, evidence_gaps

IMPORTANT: Frame all suggestions as "considerations for review" - not prescriptive recommendations.
Surface unknowns and areas where evidence is insufficient for confident recommendations."""

        return prompt

    async def _call_llm(self, prompt: str) -> str:
        """Call Claude API for suggestions."""
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]

    def _parse_response(
        self, llm_response: str, prompt: str
    ) -> list[dict[str, Any]]:
        """Parse LLM response into structured suggestions."""
        # Try to extract JSON from response
        try:
            # Find JSON array in response
            start = llm_response.find("[")
            end = llm_response.rfind("]") + 1
            if start >= 0 and end > start:
                parsed = json.loads(llm_response[start:end])
                results = []
                for item in parsed:
                    results.append({
                        "suggestion_text": item.get("suggestion_text", ""),
                        "rationale": item.get("rationale", ""),
                        "governance_flags": item.get("governance_flags"),
                        "evidence_gaps": item.get("evidence_gaps"),
                        "llm_prompt": prompt,
                        "llm_response": llm_response,
                    })
                return results
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        # Fallback: treat entire response as single suggestion
        return [{
            "suggestion_text": llm_response[:500],
            "rationale": "Auto-parsed from unstructured LLM response",
            "governance_flags": {"parse_warning": "Response was not structured JSON"},
            "evidence_gaps": None,
            "llm_prompt": prompt,
            "llm_response": llm_response,
        }]

    def _fallback_suggestions(
        self, scenario: Any, prompt: str
    ) -> list[dict[str, Any]]:
        """Generate fallback suggestions when LLM is unavailable."""
        return [
            {
                "suggestion_text": (
                    f"Consider reviewing the governance implications of "
                    f"modifications in scenario '{scenario.name}'"
                ),
                "rationale": (
                    "When LLM analysis is unavailable, manual governance review "
                    "ensures compliance considerations are not overlooked."
                ),
                "governance_flags": {
                    "warning": "Generated without LLM analysis - manual review recommended"
                },
                "evidence_gaps": {
                    "note": "LLM unavailable - evidence gap analysis could not be performed"
                },
                "llm_prompt": prompt,
                "llm_response": "LLM_UNAVAILABLE: Fallback suggestion generated",
            }
        ]
