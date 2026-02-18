"""Tests for SME annotation model and route schemas."""

from __future__ import annotations

from src.core.models import Annotation, MetricCategory, MetricReading, SuccessMetric


class TestAnnotationModel:
    """Tests for Annotation model structure."""

    def test_annotation_tablename(self) -> None:
        """Should use 'annotations' table."""
        assert Annotation.__tablename__ == "annotations"

    def test_annotation_has_required_columns(self) -> None:
        """Should have all required columns."""
        column_names = {c.key for c in Annotation.__table__.columns}
        required = {"id", "engagement_id", "target_type", "target_id", "author_id", "content", "created_at", "updated_at"}
        assert required.issubset(column_names)


class TestSuccessMetricModel:
    """Tests for SuccessMetric model structure."""

    def test_success_metric_tablename(self) -> None:
        """Should use 'success_metrics' table."""
        assert SuccessMetric.__tablename__ == "success_metrics"

    def test_success_metric_has_required_columns(self) -> None:
        """Should have all required columns."""
        column_names = {c.key for c in SuccessMetric.__table__.columns}
        required = {"id", "name", "unit", "target_value", "category", "created_at"}
        assert required.issubset(column_names)


class TestMetricReadingModel:
    """Tests for MetricReading model structure."""

    def test_metric_reading_tablename(self) -> None:
        """Should use 'metric_readings' table."""
        assert MetricReading.__tablename__ == "metric_readings"

    def test_metric_reading_has_required_columns(self) -> None:
        """Should have all required columns."""
        column_names = {c.key for c in MetricReading.__table__.columns}
        required = {"id", "metric_id", "engagement_id", "value", "recorded_at"}
        assert required.issubset(column_names)


class TestMetricCategory:
    """Tests for MetricCategory enum."""

    def test_all_categories_defined(self) -> None:
        """Should have 6 categories."""
        assert len(MetricCategory) == 6

    def test_category_values(self) -> None:
        """Should have expected category values."""
        values = {c.value for c in MetricCategory}
        assert values == {
            "process_efficiency",
            "quality",
            "compliance",
            "customer_satisfaction",
            "cost",
            "timeliness",
        }
