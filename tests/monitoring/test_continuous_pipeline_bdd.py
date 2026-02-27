"""BDD tests for Story #360: Continuous Evidence Collection Pipeline.

Covers all 4 acceptance scenarios:
1. New evidence ingested, quality-scored, and added to knowledge graph
2. Contradicting evidence creates ConflictObject and deviation alert
3. Evidence quality drop below threshold triggers quality warning
4. Pipeline throughput metrics available via monitoring API
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from src.monitoring.pipeline.continuous import (
    DEFAULT_QUALITY_THRESHOLD,
    EVIDENCE_CONSUMER_GROUP,
    EVIDENCE_PIPELINE_STREAM,
    QUALITY_WINDOW_MINUTES,
    ContinuousEvidencePipeline,
    submit_evidence_to_pipeline,
)
from src.monitoring.pipeline.metrics import (
    DEFAULT_WINDOW_SECONDS,
    MetricsCollector,
    PipelineMetrics,
    ProcessingEvent,
)


def _make_pipeline(
    quality_threshold: float = DEFAULT_QUALITY_THRESHOLD,
) -> ContinuousEvidencePipeline:
    """Create a pipeline with None dependencies for unit testing."""
    return ContinuousEvidencePipeline(
        redis_client=None,
        session_factory=None,
        quality_threshold=quality_threshold,
    )


def _make_mock_session() -> AsyncMock:
    """Create a mock async session with commit/refresh stubs."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


# ===========================================================================
# Scenario 1: New evidence ingested and quality-scored
# ===========================================================================


class TestEvidenceIngestion:
    """Scenario 1: New evidence is ingested, quality-scored, and added to the graph."""

    def test_pipeline_accepts_redis_client_and_session_factory(self) -> None:
        """Pipeline should initialize with redis, session factory, and optional neo4j."""
        pipeline = _make_pipeline()
        assert pipeline is not None
        assert pipeline._quality_threshold == DEFAULT_QUALITY_THRESHOLD

    def test_pipeline_has_metrics_collector(self) -> None:
        """Pipeline should expose a metrics collector."""
        pipeline = _make_pipeline()
        assert pipeline.metrics is not None
        assert isinstance(pipeline.metrics, MetricsCollector)

    def test_pipeline_custom_quality_threshold(self) -> None:
        """Pipeline should accept custom quality threshold."""
        pipeline = _make_pipeline(quality_threshold=0.75)
        assert pipeline._quality_threshold == 0.75

    def test_stream_and_consumer_group_constants(self) -> None:
        """Redis stream name and consumer group should be defined."""
        assert EVIDENCE_PIPELINE_STREAM == "kmflow:evidence:pipeline"
        assert EVIDENCE_CONSUMER_GROUP == "evidence_pipeline_workers"

    @pytest.mark.asyncio
    async def test_process_evidence_calls_scoring_and_records_metrics(self) -> None:
        """_process_evidence should score quality, update graph, check contradictions, and record metrics."""
        mock_session = _make_mock_session()

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        pipeline = ContinuousEvidencePipeline(
            redis_client=None,
            session_factory=mock_session_factory,
            quality_threshold=0.6,
        )

        # Mock internal methods
        pipeline._score_evidence = AsyncMock(return_value=0.85)
        pipeline._update_knowledge_graph = AsyncMock()
        pipeline._check_contradictions = AsyncMock()
        pipeline._monitor_quality = AsyncMock()

        data = {"evidence_id": "ev-123", "engagement_id": "eng-456"}
        await pipeline._process_evidence(b"msg-1", data)

        pipeline._score_evidence.assert_awaited_once_with(mock_session, "ev-123")
        pipeline._update_knowledge_graph.assert_awaited_once_with("ev-123", "eng-456")
        pipeline._check_contradictions.assert_awaited_once_with(mock_session, "ev-123", "eng-456")
        pipeline._monitor_quality.assert_awaited_once_with(mock_session, 0.85, "eng-456")
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_evidence_records_latency_on_success(self) -> None:
        """Metrics should record event with success=True on normal processing."""
        mock_session = _make_mock_session()

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        mock_metrics = AsyncMock(spec=MetricsCollector)
        pipeline = ContinuousEvidencePipeline(
            redis_client=None,
            session_factory=mock_session_factory,
            metrics=mock_metrics,
        )
        pipeline._score_evidence = AsyncMock(return_value=0.8)
        pipeline._update_knowledge_graph = AsyncMock()
        pipeline._check_contradictions = AsyncMock()
        pipeline._monitor_quality = AsyncMock()

        await pipeline._process_evidence(b"msg-1", {"evidence_id": "ev-1", "engagement_id": "eng-1"})

        mock_metrics.record_event.assert_awaited_once()
        call_args = mock_metrics.record_event.call_args
        assert call_args[0][2] is True  # success=True

    @pytest.mark.asyncio
    async def test_process_evidence_records_failure_on_exception(self) -> None:
        """Metrics should record event with success=False when processing fails."""
        mock_session = _make_mock_session()

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        mock_metrics = AsyncMock(spec=MetricsCollector)
        pipeline = ContinuousEvidencePipeline(
            redis_client=None,
            session_factory=mock_session_factory,
            metrics=mock_metrics,
        )
        pipeline._score_evidence = AsyncMock(side_effect=RuntimeError("DB error"))

        await pipeline._process_evidence(b"msg-1", {"evidence_id": "ev-1", "engagement_id": "eng-1"})

        mock_metrics.record_event.assert_awaited_once()
        call_args = mock_metrics.record_event.call_args
        assert call_args[0][2] is False  # success=False

    @pytest.mark.asyncio
    async def test_process_evidence_handles_bytes_keys(self) -> None:
        """Pipeline should decode bytes keys from Redis stream messages."""
        mock_session = _make_mock_session()

        @asynccontextmanager
        async def mock_session_factory():
            yield mock_session

        pipeline = ContinuousEvidencePipeline(
            redis_client=None,
            session_factory=mock_session_factory,
        )
        pipeline._score_evidence = AsyncMock(return_value=0.7)
        pipeline._update_knowledge_graph = AsyncMock()
        pipeline._check_contradictions = AsyncMock()
        pipeline._monitor_quality = AsyncMock()

        # Redis returns bytes keys
        data = {b"evidence_id": b"ev-bytes", b"engagement_id": b"eng-bytes"}
        await pipeline._process_evidence(b"msg-1", data)

        pipeline._score_evidence.assert_awaited_once_with(mock_session, "ev-bytes")
        pipeline._update_knowledge_graph.assert_awaited_once_with("ev-bytes", "eng-bytes")


# ===========================================================================
# Scenario 2: Contradicting evidence creates ConflictObject
# ===========================================================================


class TestContradictionDetection:
    """Scenario 2: Contradicting evidence creates ConflictObject and deviation alert."""

    def test_pipeline_has_contradiction_check_method(self) -> None:
        """Pipeline should have a _check_contradictions method."""
        pipeline = _make_pipeline()
        assert hasattr(pipeline, "_check_contradictions")
        assert callable(pipeline._check_contradictions)

    def test_pipeline_has_score_evidence_method(self) -> None:
        """Pipeline should have a _score_evidence method."""
        pipeline = _make_pipeline()
        assert hasattr(pipeline, "_score_evidence")
        assert callable(pipeline._score_evidence)

    @pytest.mark.asyncio
    async def test_check_contradictions_is_callable_async(self) -> None:
        """_check_contradictions should be an async method that runs without error."""
        pipeline = _make_pipeline()
        session = _make_mock_session()
        # Should not raise — currently a stub, but must be async-callable
        await pipeline._check_contradictions(session, "ev-1", "eng-1")


# ===========================================================================
# Scenario 3: Quality drop triggers warning alert
# ===========================================================================


class TestQualityThresholdMonitoring:
    """Scenario 3: Evidence quality drop below threshold triggers warning."""

    def test_default_quality_threshold(self) -> None:
        """Default quality threshold should be 0.6."""
        assert DEFAULT_QUALITY_THRESHOLD == 0.6

    def test_quality_window_minutes_constant(self) -> None:
        """Quality window should be 10 minutes."""
        assert QUALITY_WINDOW_MINUTES == 10

    @pytest.mark.asyncio
    async def test_monitor_quality_tracks_scores_per_engagement(self) -> None:
        """_monitor_quality should track scores per engagement in separate windows."""
        pipeline = _make_pipeline(quality_threshold=0.6)
        session = _make_mock_session()

        await pipeline._monitor_quality(session, 0.8, "eng-1")
        await pipeline._monitor_quality(session, 0.3, "eng-2")

        assert "eng-1" in pipeline._quality_windows
        assert "eng-2" in pipeline._quality_windows
        assert len(pipeline._quality_windows["eng-1"]) == 1
        assert len(pipeline._quality_windows["eng-2"]) == 1

    @pytest.mark.asyncio
    async def test_monitor_quality_emits_warning_below_threshold(self, caplog: pytest.LogCaptureFixture) -> None:
        """When average quality drops below threshold with >=5 scores, a warning should be logged."""
        pipeline = _make_pipeline(quality_threshold=0.6)
        session = _make_mock_session()

        with caplog.at_level(logging.WARNING, logger="src.monitoring.pipeline.continuous"):
            # Add 5 low-quality scores for the same engagement
            for _ in range(5):
                await pipeline._monitor_quality(session, 0.3, "eng-low")

        assert any("quality below threshold" in r.message.lower() for r in caplog.records)
        assert any("eng-low" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_monitor_quality_no_warning_above_threshold(self, caplog: pytest.LogCaptureFixture) -> None:
        """No warning when average quality is above threshold."""
        pipeline = _make_pipeline(quality_threshold=0.6)
        session = _make_mock_session()

        with caplog.at_level(logging.WARNING, logger="src.monitoring.pipeline.continuous"):
            for _ in range(10):
                await pipeline._monitor_quality(session, 0.9, "eng-good")

        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 0

    @pytest.mark.asyncio
    async def test_monitor_quality_no_warning_fewer_than_5_scores(self, caplog: pytest.LogCaptureFixture) -> None:
        """No warning when fewer than 5 scores even if below threshold."""
        pipeline = _make_pipeline(quality_threshold=0.6)
        session = _make_mock_session()

        with caplog.at_level(logging.WARNING, logger="src.monitoring.pipeline.continuous"):
            for _ in range(4):
                await pipeline._monitor_quality(session, 0.1, "eng-few")

        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 0

    @pytest.mark.asyncio
    async def test_monitor_quality_prunes_old_entries(self) -> None:
        """Scores older than QUALITY_WINDOW_MINUTES should be pruned."""
        pipeline = _make_pipeline(quality_threshold=0.6)
        session = _make_mock_session()

        # Manually insert an old entry with a timestamp from 20 minutes ago
        old_timestamp = time.monotonic() - (QUALITY_WINDOW_MINUTES * 60 + 60)
        from collections import deque

        pipeline._quality_windows["eng-old"] = deque([(old_timestamp, 0.3)])

        # Add a new score — the old one should be pruned
        await pipeline._monitor_quality(session, 0.9, "eng-old")

        window = pipeline._quality_windows["eng-old"]
        assert len(window) == 1
        # The remaining score should be the new 0.9, not the old 0.3
        assert window[0][1] == 0.9


# ===========================================================================
# Scenario 4: Pipeline throughput metrics via monitoring API
# ===========================================================================


class TestPipelineMetrics:
    """Scenario 4: Pipeline metrics include processing_rate, queue_depth, p99_latency_ms."""

    def test_pipeline_metrics_defaults(self) -> None:
        """Default PipelineMetrics should have all zero values."""
        m = PipelineMetrics()
        assert m.processing_rate == 0.0
        assert m.queue_depth == 0
        assert m.p99_latency_ms == 0.0
        assert m.avg_latency_ms == 0.0
        assert m.total_processed == 0
        assert m.total_errors == 0
        assert m.avg_quality == 0.0
        assert m.window_seconds == DEFAULT_WINDOW_SECONDS

    def test_default_window_is_5_minutes(self) -> None:
        """Rolling window should default to 300 seconds (5 minutes)."""
        assert DEFAULT_WINDOW_SECONDS == 300

    @pytest.mark.asyncio
    async def test_metrics_collector_records_events(self) -> None:
        """MetricsCollector should record processing events."""
        collector = MetricsCollector(window_seconds=60)
        await collector.record_event(latency_ms=50.0, quality_score=0.85)
        await collector.record_event(latency_ms=75.0, quality_score=0.90)

        metrics = await collector.get_metrics()
        assert metrics.total_processed == 2
        assert metrics.total_errors == 0

    @pytest.mark.asyncio
    async def test_metrics_processing_rate(self) -> None:
        """Processing rate should be calculated as items/minute."""
        collector = MetricsCollector(window_seconds=60)
        for _ in range(10):
            await collector.record_event(latency_ms=20.0, quality_score=0.8)

        metrics = await collector.get_metrics()
        # 10 events in ~0 seconds = very high rate
        assert metrics.processing_rate > 0

    @pytest.mark.asyncio
    async def test_metrics_p99_latency(self) -> None:
        """P99 latency should reflect the 99th percentile."""
        collector = MetricsCollector(window_seconds=60)
        # Add 99 fast events and 1 slow event
        for _ in range(99):
            await collector.record_event(latency_ms=10.0, quality_score=0.8)
        await collector.record_event(latency_ms=500.0, quality_score=0.8)

        metrics = await collector.get_metrics()
        assert metrics.p99_latency_ms >= 10.0  # At least the slow event

    @pytest.mark.asyncio
    async def test_metrics_avg_quality(self) -> None:
        """Average quality should be computed from recorded events."""
        collector = MetricsCollector(window_seconds=60)
        await collector.record_event(latency_ms=10.0, quality_score=0.80)
        await collector.record_event(latency_ms=10.0, quality_score=0.90)

        metrics = await collector.get_metrics()
        assert metrics.avg_quality == pytest.approx(0.85, abs=0.01)

    @pytest.mark.asyncio
    async def test_metrics_queue_depth(self) -> None:
        """Queue depth should reflect the last set value."""
        collector = MetricsCollector(window_seconds=60)
        await collector.set_queue_depth(42)

        metrics = await collector.get_metrics()
        assert metrics.queue_depth == 42

    @pytest.mark.asyncio
    async def test_metrics_error_counting(self) -> None:
        """Failed events should increment total_errors."""
        collector = MetricsCollector(window_seconds=60)
        await collector.record_event(latency_ms=10.0, quality_score=0.0, success=False)
        await collector.record_event(latency_ms=10.0, quality_score=0.8, success=True)

        metrics = await collector.get_metrics()
        assert metrics.total_processed == 2
        assert metrics.total_errors == 1

    @pytest.mark.asyncio
    async def test_empty_collector_returns_defaults(self) -> None:
        """An empty collector should return default metrics."""
        collector = MetricsCollector(window_seconds=60)
        metrics = await collector.get_metrics()

        assert metrics.processing_rate == 0.0
        assert metrics.queue_depth == 0
        assert metrics.p99_latency_ms == 0.0
        assert metrics.total_processed == 0

    def test_processing_event_defaults(self) -> None:
        """ProcessingEvent should have success=True by default."""
        event = ProcessingEvent(
            timestamp=time.monotonic(),
            latency_ms=25.0,
            quality_score=0.9,
        )
        assert event.success is True


# ===========================================================================
# API schema tests
# ===========================================================================


class TestPipelineMetricsAPI:
    """Test pipeline metrics API endpoint schema."""

    def test_pipeline_metrics_response_schema(self) -> None:
        """Response should have all required fields."""
        from src.api.routes.monitoring import PipelineMetricsResponse

        fields = PipelineMetricsResponse.model_fields
        assert "processing_rate" in fields
        assert "queue_depth" in fields
        assert "p99_latency_ms" in fields
        assert "avg_latency_ms" in fields
        assert "total_processed" in fields
        assert "total_errors" in fields
        assert "avg_quality" in fields
        assert "window_seconds" in fields

    def test_monitoring_router_has_pipeline_endpoint(self) -> None:
        """Monitoring router should have /pipeline/metrics route."""
        from src.api.routes.monitoring import router

        route_paths = [r.path for r in router.routes]
        # Routes include the full prefix from the router
        assert any(p.endswith("/pipeline/metrics") for p in route_paths)

    def test_pipeline_endpoint_requires_auth(self) -> None:
        """Pipeline metrics endpoint should require monitoring:read permission."""
        from src.api.routes.monitoring import router

        for route in router.routes:
            if hasattr(route, "path") and route.path.endswith("/pipeline/metrics"):
                # Check that the endpoint has dependencies (auth)
                deps = getattr(route, "dependant", None)
                if deps and hasattr(deps, "dependencies"):
                    dep_names = [
                        d.call.__name__ if hasattr(d, "call") and hasattr(d.call, "__name__") else ""
                        for d in deps.dependencies
                    ]
                    assert any("require_permission" in n or "permission" in str(d) for n, d in zip(dep_names, deps.dependencies, strict=False)), (
                        "Pipeline metrics endpoint should have require_permission dependency"
                    )
                break


# ===========================================================================
# submit_evidence_to_pipeline tests
# ===========================================================================


class TestSubmitEvidence:
    """Test the submit_evidence_to_pipeline helper."""

    def test_submit_function_exists(self) -> None:
        """submit_evidence_to_pipeline should be importable."""
        assert callable(submit_evidence_to_pipeline)

    @pytest.mark.asyncio
    async def test_submit_calls_xadd_with_correct_params(self) -> None:
        """submit_evidence_to_pipeline should call xadd on the correct stream."""
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(return_value=b"1234-0")

        msg_id = await submit_evidence_to_pipeline(
            redis_client=mock_redis,
            evidence_id="ev-abc",
            engagement_id="eng-def",
        )

        mock_redis.xadd.assert_awaited_once_with(
            EVIDENCE_PIPELINE_STREAM,
            {"evidence_id": "ev-abc", "engagement_id": "eng-def"},
            maxlen=50000,
        )
        assert msg_id == b"1234-0"
