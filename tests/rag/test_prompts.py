"""Tests for RAG prompt templates (src/rag/prompts.py)."""

from __future__ import annotations

from src.rag.prompts import DOMAIN_TEMPLATES, build_context_string, get_prompt_template


class TestPromptTemplates:
    def test_all_templates_have_placeholders(self) -> None:
        for name, template in DOMAIN_TEMPLATES.items():
            assert "{context}" in template, f"Template '{name}' missing {{context}}"
            assert "{query}" in template, f"Template '{name}' missing {{query}}"
            assert "{engagement_id}" in template, f"Template '{name}' missing {{engagement_id}}"

    def test_get_prompt_template_general(self) -> None:
        template = get_prompt_template("general")
        assert "{context}" in template

    def test_get_prompt_template_unknown_falls_back(self) -> None:
        template = get_prompt_template("nonexistent")
        assert template == DOMAIN_TEMPLATES["general"]

    def test_get_prompt_template_process_discovery(self) -> None:
        template = get_prompt_template("process_discovery")
        assert "process" in template.lower()

    def test_build_context_string_empty(self) -> None:
        result = build_context_string([])
        assert result == ""

    def test_build_context_string_formats_sources(self) -> None:
        contexts = [
            {"content": "Fragment A", "source_type": "fragment", "source_id": "abc"},
            {"content": "Fragment B", "source_type": "graph_node", "source_id": "def"},
        ]
        result = build_context_string(contexts)
        assert "Source 1" in result
        assert "Source 2" in result
        assert "Fragment A" in result
        assert "Fragment B" in result
