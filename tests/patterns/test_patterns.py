"""Tests for pattern anonymization and matching modules."""

from __future__ import annotations

import pytest

from src.patterns.anonymizer import (
    anonymize_pattern_data,
    anonymize_text,
    compute_anonymization_hash,
)
from src.patterns.matcher import (
    compute_similarity,
    find_applicable_patterns,
    rank_patterns,
)


class TestAnonymizeText:
    """Tests for anonymize_text function."""

    def test_replaces_email_addresses(self):
        text = "Contact john.doe@example.com for details"
        result = anonymize_text(text)
        assert "[REDACTED_0]" in result
        assert "john.doe@example.com" not in result

    def test_replaces_phone_numbers(self):
        text = "Call 555-123-4567 or 555.987.6543"
        result = anonymize_text(text)
        assert "[REDACTED_1]" in result
        assert "555-123-4567" not in result
        assert "555.987.6543" not in result

    def test_replaces_ssn(self):
        text = "SSN: 123-45-6789"
        result = anonymize_text(text)
        assert "[REDACTED_2]" in result
        assert "123-45-6789" not in result

    def test_leaves_normal_text_unchanged(self):
        text = "This is normal text without PII"
        result = anonymize_text(text)
        assert result == text

    def test_replaces_multiple_patterns(self):
        text = "Email alice@test.com, phone 555-123-4567 and SSN 111-22-3333"
        result = anonymize_text(text)
        assert "[REDACTED_0]" in result  # email
        assert "[REDACTED_1]" in result  # phone
        assert "[REDACTED_2]" in result  # SSN
        assert "alice@test.com" not in result
        assert "555-123-4567" not in result
        assert "111-22-3333" not in result


class TestAnonymizePatternData:
    """Tests for anonymize_pattern_data function."""

    def test_deep_copy_and_anonymize_dict(self):
        data = {
            "contact": "alice@example.com",
            "phone": "555-111-2222",
        }
        result = anonymize_pattern_data(data)
        assert result["contact"] == "[REDACTED_0]"
        assert result["phone"] == "[REDACTED_1]"
        assert data["contact"] == "alice@example.com"  # original unchanged

    def test_deep_copy_and_anonymize_nested_dict(self):
        data = {
            "level1": {
                "level2": {
                    "email": "test@example.com",
                }
            }
        }
        result = anonymize_pattern_data(data)
        assert result["level1"]["level2"]["email"] == "[REDACTED_0]"

    def test_deep_copy_and_anonymize_list(self):
        data = {
            "emails": ["alice@test.com", "bob@test.com"],
        }
        result = anonymize_pattern_data(data)
        assert result["emails"][0] == "[REDACTED_0]"
        assert result["emails"][1] == "[REDACTED_0]"

    def test_replaces_client_name_throughout_structure(self):
        data = {
            "name": "Acme Corp",
            "description": "Process for Acme Corp operations",
            "nested": {
                "client": "Acme Corp",
            }
        }
        result = anonymize_pattern_data(data, client_name="Acme Corp")
        assert result["name"] == "[CLIENT]"
        assert "[CLIENT]" in result["description"]
        assert result["nested"]["client"] == "[CLIENT]"

    def test_replaces_engagement_name_throughout_structure(self):
        data = {
            "engagement": "Project Alpha",
            "summary": "Project Alpha summary",
        }
        result = anonymize_pattern_data(data, engagement_name="Project Alpha")
        assert result["engagement"] == "[ENGAGEMENT]"
        assert "[ENGAGEMENT]" in result["summary"]

    def test_handles_none_client_name(self):
        data = {"test": "value"}
        result = anonymize_pattern_data(data, client_name=None)
        assert result == {"test": "value"}

    def test_handles_none_engagement_name(self):
        data = {"test": "value"}
        result = anonymize_pattern_data(data, engagement_name=None)
        assert result == {"test": "value"}


class TestComputeAnonymizationHash:
    """Tests for compute_anonymization_hash function."""

    def test_deterministic_for_same_input(self):
        data = {"key": "value", "num": 123}
        hash1 = compute_anonymization_hash(data)
        hash2 = compute_anonymization_hash(data)
        assert hash1 == hash2

    def test_different_for_different_input(self):
        data1 = {"key": "value1"}
        data2 = {"key": "value2"}
        hash1 = compute_anonymization_hash(data1)
        hash2 = compute_anonymization_hash(data2)
        assert hash1 != hash2

    def test_returns_16_character_string(self):
        data = {"test": "data"}
        result = compute_anonymization_hash(data)
        assert len(result) == 16
        assert isinstance(result, str)


class TestComputeSimilarity:
    """Tests for compute_similarity function."""

    def test_identical_vectors_return_one(self):
        vec = [1.0, 0.5, 0.3]
        similarity = compute_similarity(vec, vec)
        assert similarity == pytest.approx(1.0)

    def test_orthogonal_vectors_return_zero(self):
        vec_a = [1.0, 0.0]
        vec_b = [0.0, 1.0]
        similarity = compute_similarity(vec_a, vec_b)
        assert similarity == pytest.approx(0.0)

    def test_mismatched_lengths_return_zero(self):
        vec_a = [1.0, 2.0]
        vec_b = [1.0, 2.0, 3.0]
        similarity = compute_similarity(vec_a, vec_b)
        assert similarity == 0.0

    def test_empty_vectors_return_zero(self):
        similarity = compute_similarity([], [])
        assert similarity == 0.0

    def test_zero_vectors_return_zero(self):
        vec_a = [0.0, 0.0, 0.0]
        vec_b = [1.0, 2.0, 3.0]
        similarity = compute_similarity(vec_a, vec_b)
        assert similarity == 0.0

    def test_similar_vectors_return_high_score(self):
        vec_a = [1.0, 2.0, 3.0]
        vec_b = [1.0, 2.0, 3.0]
        similarity = compute_similarity(vec_a, vec_b)
        assert similarity == pytest.approx(1.0)


class TestRankPatterns:
    """Tests for rank_patterns function."""

    def test_returns_top_k_results_sorted_by_score(self):
        query = [1.0, 0.0, 0.0]
        patterns = [
            {"id": "p1", "embedding": [1.0, 0.0, 0.0]},  # similarity 1.0
            {"id": "p2", "embedding": [0.5, 0.5, 0.0]},  # similarity ~0.7
            {"id": "p3", "embedding": [0.0, 1.0, 0.0]},  # similarity 0.0
        ]
        results = rank_patterns(query, patterns, top_k=2, min_score=0.0)
        assert len(results) == 2
        assert results[0]["id"] == "p1"
        assert results[1]["id"] == "p2"
        assert results[0]["similarity_score"] > results[1]["similarity_score"]

    def test_filters_by_min_score(self):
        query = [1.0, 0.0]
        patterns = [
            {"id": "p1", "embedding": [1.0, 0.0]},  # similarity 1.0
            {"id": "p2", "embedding": [0.0, 1.0]},  # similarity 0.0
        ]
        results = rank_patterns(query, patterns, min_score=0.5)
        assert len(results) == 1
        assert results[0]["id"] == "p1"

    def test_skips_patterns_without_embeddings(self):
        query = [1.0, 0.0]
        patterns = [
            {"id": "p1", "embedding": [1.0, 0.0]},
            {"id": "p2"},  # no embedding
        ]
        results = rank_patterns(query, patterns)
        assert len(results) == 1
        assert results[0]["id"] == "p1"

    def test_adds_similarity_score_to_results(self):
        query = [1.0, 0.0]
        patterns = [{"id": "p1", "embedding": [1.0, 0.0]}]
        results = rank_patterns(query, patterns)
        assert "similarity_score" in results[0]
        assert results[0]["similarity_score"] == pytest.approx(1.0)

    def test_returns_empty_when_no_matches(self):
        query = [1.0, 0.0]
        patterns = [{"id": "p1", "embedding": [0.0, 1.0]}]
        results = rank_patterns(query, patterns, min_score=0.5)
        assert len(results) == 0


class TestFindApplicablePatterns:
    """Tests for find_applicable_patterns function."""

    def test_filters_by_industry_case_insensitive(self):
        patterns = [
            {"id": "p1", "industry": "Banking"},
            {"id": "p2", "industry": "Healthcare"},
            {"id": "p3", "industry": "banking"},
        ]
        results = find_applicable_patterns("banking", [], patterns)
        assert len(results) == 2
        assert {r["id"] for r in results} == {"p1", "p3"}

    def test_filters_by_categories(self):
        patterns = [
            {"id": "p1", "category": "approval"},
            {"id": "p2", "category": "review"},
            {"id": "p3", "category": "approval"},
        ]
        results = find_applicable_patterns("", ["approval"], patterns)
        assert len(results) == 2
        assert {r["id"] for r in results} == {"p1", "p3"}

    def test_patterns_with_no_industry_match_everything(self):
        patterns = [
            {"id": "p1"},  # no industry
            {"id": "p2", "industry": "Banking"},
        ]
        results = find_applicable_patterns("Healthcare", [], patterns)
        assert len(results) == 1
        assert results[0]["id"] == "p1"

    def test_empty_categories_list_matches_all(self):
        patterns = [
            {"id": "p1", "category": "approval"},
            {"id": "p2", "category": "review"},
        ]
        results = find_applicable_patterns("", [], patterns)
        assert len(results) == 2

    def test_industry_and_category_filters_combined(self):
        patterns = [
            {"id": "p1", "industry": "Banking", "category": "approval"},
            {"id": "p2", "industry": "Banking", "category": "review"},
            {"id": "p3", "industry": "Healthcare", "category": "approval"},
        ]
        results = find_applicable_patterns("Banking", ["approval"], patterns)
        assert len(results) == 1
        assert results[0]["id"] == "p1"
