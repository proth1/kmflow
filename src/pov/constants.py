"""Constants for the POV generator and LCD algorithm.

Evidence type weights, confidence levels, and scoring parameters
used across the POV generation pipeline.
"""

from __future__ import annotations

# Evidence type weights for consensus building.
# Higher weight = more authoritative evidence type.
EVIDENCE_TYPE_WEIGHTS: dict[str, float] = {
    "structured_data": 1.0,
    "task_mining": 0.90,
    "bpm_process_models": 0.85,
    "documents": 0.75,
    "controls_evidence": 0.70,
    "regulatory_policy": 0.70,
    "saas_exports": 0.65,
    "domain_communications": 0.50,
    "images": 0.45,
    "audio": 0.40,
    "video": 0.40,
    "km4work": 0.35,
    "job_aids_edge_cases": 0.30,
}

# Default weight for unknown evidence categories
DEFAULT_EVIDENCE_WEIGHT: float = 0.30

# Legacy flat-weight formula (kept for backwards compatibility)
CONFIDENCE_FACTOR_WEIGHTS: dict[str, float] = {
    "coverage": 0.30,
    "agreement": 0.25,
    "quality": 0.20,
    "reliability": 0.15,
    "recency": 0.10,
}

# Two-stage confidence formula weights (PRD v2.1 Section 6.3)
# Stage 1a: strength = coverage * 0.55 + agreement * 0.45
STRENGTH_WEIGHTS: dict[str, float] = {
    "coverage": 0.55,
    "agreement": 0.45,
}

# Stage 1b: quality = quality * 0.40 + reliability * 0.35 + recency * 0.25
QUALITY_WEIGHTS: dict[str, float] = {
    "quality": 0.40,
    "reliability": 0.35,
    "recency": 0.25,
}

# Stage 2: final_score = min(strength, quality)

# Minimum Viable Confidence threshold
MVC_THRESHOLD: float = 0.40

# Brightness thresholds
BRIGHTNESS_BRIGHT_THRESHOLD: float = 0.75
BRIGHTNESS_DIM_THRESHOLD: float = 0.40
# Below DIM_THRESHOLD = DARK

# Grades that cap brightness at DIM
GRADES_CAPPED_AT_DIM: frozenset[str] = frozenset({"D", "U"})

# Confidence level thresholds
CONFIDENCE_LEVELS: list[tuple[str, float]] = [
    ("VERY_HIGH", 0.90),
    ("HIGH", 0.75),
    ("MEDIUM", 0.50),
    ("LOW", 0.25),
    ("VERY_LOW", 0.0),
]

# Triangulation thresholds for corroboration levels
TRIANGULATION_THRESHOLDS: dict[str, float] = {
    "strongly": 0.70,
    "moderately": 0.40,
    # Below 0.40 = weakly
}

# Four evidence planes from PRD Section 6.2
EVIDENCE_PLANES: dict[str, str] = {
    "structured_data": "system_behavioral",
    "task_mining": "system_behavioral",  # Forward-looking: not yet in EvidenceCategory enum
    "saas_exports": "system_behavioral",
    "bpm_process_models": "documented_formal",
    "documents": "documented_formal",
    "regulatory_policy": "documented_formal",
    "controls_evidence": "documented_formal",
    "images": "observed_field",
    "video": "observed_field",
    "job_aids_edge_cases": "observed_field",
    "km4work": "human_interpretation",
    "audio": "human_interpretation",
    "domain_communications": "human_interpretation",
}

# Cross-plane corroboration bonus for evidence_agreement
CROSS_PLANE_BONUS: float = 0.15
