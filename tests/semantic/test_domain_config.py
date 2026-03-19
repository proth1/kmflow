"""Tests for domain configuration loader."""

from __future__ import annotations

import pytest

from src.evidence.chunking import ChunkingConfig
from src.semantic.domains.loader import (
    get_chunking_config,
    get_embedding_model,
    get_evidence_weights,
    list_domains,
    load_domain_config,
)


class TestDomainConfigLoader:
    """Tests for the domain config loader."""

    def test_list_domains_includes_mortgage_lending(self) -> None:
        domains = list_domains()
        assert "mortgage_lending" in domains

    def test_load_mortgage_lending_config(self) -> None:
        config = load_domain_config("mortgage_lending")
        assert config["domain"] == "mortgage_lending"
        assert "seed_lists" in config
        assert "embedding" in config
        assert "chunking" in config

    def test_load_nonexistent_domain_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="Domain config not found"):
            load_domain_config("nonexistent_domain_xyz")

    def test_get_chunking_config_default(self) -> None:
        config = get_chunking_config()
        assert isinstance(config, ChunkingConfig)
        assert config.target_tokens == 384

    def test_get_chunking_config_mortgage_lending(self) -> None:
        config = get_chunking_config("mortgage_lending")
        assert isinstance(config, ChunkingConfig)
        assert config.target_tokens == 384
        assert config.overlap_tokens == 50

    def test_get_evidence_weights_default(self) -> None:
        weights = get_evidence_weights()
        assert weights == {}

    def test_get_evidence_weights_mortgage_lending(self) -> None:
        weights = get_evidence_weights("mortgage_lending")
        assert "documents" in weights
        assert weights["documents"] == 1.0
        assert weights["bpm_process_models"] == 1.2

    def test_get_embedding_model_default(self) -> None:
        model = get_embedding_model()
        assert "nomic" in model

    def test_get_embedding_model_mortgage_lending(self) -> None:
        model = get_embedding_model("mortgage_lending")
        assert "nomic" in model
