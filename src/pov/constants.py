"""Constants for the POV generator and LCD algorithm.

Evidence type weights, confidence levels, and scoring parameters
used across the POV generation pipeline.
"""

from __future__ import annotations

# Evidence type weights for consensus building.
# Higher weight = more authoritative evidence type.
EVIDENCE_TYPE_WEIGHTS: dict[str, float] = {
    "structured_data": 1.0,
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

# Confidence scoring factor weights (must sum to 1.0)
CONFIDENCE_FACTOR_WEIGHTS: dict[str, float] = {
    "coverage": 0.30,
    "agreement": 0.25,
    "quality": 0.20,
    "reliability": 0.15,
    "recency": 0.10,
}

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
