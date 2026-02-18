"""Domain prompt templates for the RAG copilot."""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """You are a Process Intelligence copilot for KMFlow, an evidence-based consulting platform.
You help consultants understand client processes, identify gaps, and make recommendations.

Guidelines:
- Base all answers on the provided evidence context
- Cite specific evidence sources when making claims
- Indicate confidence level when information is incomplete
- Use professional consulting language
- Flag contradictions between evidence sources"""


DOMAIN_TEMPLATES: dict[str, str] = {
    "process_discovery": """Based on the following evidence from engagement {engagement_id}:

{context}

Question: {query}

Analyze the evidence to identify process steps, actors, decisions, and handoffs.
Cite specific evidence fragments that support your findings.""",
    "evidence_traceability": """Evidence context for engagement {engagement_id}:

{context}

Question: {query}

Trace the evidence chain and identify which sources support which findings.
Note any gaps in the evidence trail.""",
    "gap_analysis": """Evidence and process model context for engagement {engagement_id}:

{context}

Question: {query}

Identify gaps between current state (as-is) and the target operating model.
Classify gaps by severity and recommend remediation approaches.""",
    "regulatory": """Regulatory and compliance context for engagement {engagement_id}:

{context}

Question: {query}

Assess compliance posture based on the available evidence.
Identify regulatory requirements that lack supporting evidence.""",
    "general": """Context from engagement {engagement_id}:

{context}

Question: {query}

Provide a thorough answer based on the available evidence.
Cite sources and indicate confidence level.""",
}


def get_prompt_template(query_type: str = "general") -> str:
    """Get the prompt template for a given query type."""
    return DOMAIN_TEMPLATES.get(query_type, DOMAIN_TEMPLATES["general"])


def build_context_string(contexts: list[dict[str, Any]]) -> str:
    """Build a formatted context string from retrieval results."""
    parts = []
    for i, ctx in enumerate(contexts, 1):
        source = ctx.get("source_type", "unknown")
        source_id = ctx.get("source_id", "N/A")
        content = ctx.get("content", "")
        parts.append(f"[Source {i} ({source} {source_id})]\n{content}")
    return "\n\n".join(parts)
