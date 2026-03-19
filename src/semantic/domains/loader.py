"""Domain configuration loader.

Loads domain-specific settings from YAML configuration bundles.
Each domain config bundles embedding model, chunking parameters,
entity extraction patterns, evidence weights, and quality thresholds
into a single portable file.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Any

import yaml

from src.evidence.chunking import ChunkingConfig

logger = logging.getLogger(__name__)

_DOMAINS_DIR = Path(__file__).parent


@functools.cache
def list_domains() -> list[str]:
    """List available domain configurations."""
    return [p.stem for p in _DOMAINS_DIR.glob("*.yaml") if p.stem != "__init__"]


@functools.cache
def load_domain_config(domain: str) -> dict[str, Any]:
    """Load a domain configuration by name.

    Args:
        domain: Domain name (e.g., "mortgage_lending").

    Returns:
        Full domain configuration dict.

    Raises:
        FileNotFoundError: If the domain config doesn't exist.
    """
    config_path = _DOMAINS_DIR / f"{domain}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Domain config not found: {domain}. Available: {list_domains()}")

    with open(config_path) as f:
        return yaml.safe_load(f)


def get_chunking_config(domain: str | None = None) -> ChunkingConfig:
    """Get chunking configuration for a domain.

    Args:
        domain: Optional domain name. Uses defaults if not provided.

    Returns:
        ChunkingConfig with domain-specific or default settings.
    """
    if domain is None:
        return ChunkingConfig()

    config = load_domain_config(domain)
    chunking = config.get("chunking", {})
    return ChunkingConfig(
        target_tokens=chunking.get("target_tokens", 384),
        overlap_tokens=chunking.get("overlap_tokens", 50),
        max_tokens=chunking.get("max_tokens", 512),
        min_tokens=chunking.get("min_tokens", 30),
    )


def get_evidence_weights(domain: str | None = None) -> dict[str, float]:
    """Get evidence type weights for consensus scoring.

    Args:
        domain: Optional domain name. Uses equal weights if not provided.

    Returns:
        Dict mapping evidence category to weight.
    """
    if domain is None:
        return {}

    config = load_domain_config(domain)
    return config.get("evidence_weights", {})


def get_embedding_model(domain: str | None = None) -> str:
    """Get the embedding model name for a domain.

    Args:
        domain: Optional domain name. Uses default if not provided.

    Returns:
        Model name string.
    """
    if domain is None:
        return "nomic-ai/nomic-embed-text-v1.5"

    config = load_domain_config(domain)
    embedding = config.get("embedding", {})
    return embedding.get("model", "nomic-ai/nomic-embed-text-v1.5")
