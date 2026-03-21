"""Pipeline stage instrumentation decorator."""

from __future__ import annotations

import asyncio
import functools
import inspect
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class PipelineStageEvent:
    """Captured metrics for a single pipeline stage execution."""

    stage: str
    engagement_id: str | None
    evidence_item_id: str | None
    started_at: datetime
    duration_ms: float
    input_count: int
    output_count: int
    error_count: int
    error_type: str | None
    metadata: dict[str, Any] | None = field(default=None)


def _extract_id(
    param_name: str | None,
    default_names: tuple[str, ...],
    bound_args: inspect.BoundArguments,
) -> str | None:
    """Extract a string ID from bound function arguments.

    Checks `param_name` first (if provided), then falls back to each name in
    `default_names`.  Returns None when nothing is found.
    """
    args_dict = bound_args.arguments
    candidates = (param_name,) if param_name is not None else default_names
    for name in candidates:
        if name is None:
            continue
        value = args_dict.get(name)
        if value is not None:
            return str(value)
    return None


def _input_count(bound_args: inspect.BoundArguments) -> int:
    """Return len of the first list argument, or 1 as default."""
    for value in bound_args.arguments.values():
        if isinstance(value, list):
            return len(value)
    return 1


def _output_count(result: Any) -> int:
    """Return len of result if list, 1 if truthy, else 0."""
    if isinstance(result, list):
        return len(result)
    return 1 if result else 0


def pipeline_stage(
    stage_name: str,
    *,
    engagement_id_param: str | None = None,
    evidence_item_id_param: str | None = None,
) -> Any:
    """Decorator that instruments a pipeline stage function.

    Captures timing, input/output counts, and errors, then emits a
    :class:`PipelineStageEvent` to the singleton :class:`MetricsCollector`.

    Works transparently on both synchronous and asynchronous functions.

    Args:
        stage_name: Logical name of the pipeline stage (stored in the DB).
        engagement_id_param: Name of the function parameter that holds the
            engagement ID.  When omitted the decorator searches common names
            (``engagement_id``, ``engagement``).
        evidence_item_id_param: Name of the function parameter that holds the
            evidence item ID.  When omitted the decorator searches common names
            (``evidence_item_id``, ``evidence_id``).
    """

    _engagement_defaults: tuple[str, ...] = ("engagement_id", "engagement")
    _evidence_defaults: tuple[str, ...] = ("evidence_item_id", "evidence_id")

    def decorator(fn: Any) -> Any:
        sig = inspect.signature(fn)

        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                from src.quality.metrics_collector import MetricsCollector

                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()

                engagement_id = _extract_id(engagement_id_param, _engagement_defaults, bound)
                evidence_item_id = _extract_id(evidence_item_id_param, _evidence_defaults, bound)
                in_count = _input_count(bound)

                started_at = datetime.now(tz=UTC)
                t0 = time.perf_counter()
                error_count = 0
                error_type: str | None = None
                result: Any = None

                try:
                    result = await fn(*args, **kwargs)
                    return result
                except Exception as exc:  # Intentionally broad: instrumentation wrapper must capture all exception types for metrics before re-raising
                    error_count = 1
                    error_type = type(exc).__name__
                    raise
                finally:
                    duration_ms = (time.perf_counter() - t0) * 1000.0
                    event = PipelineStageEvent(
                        stage=stage_name,
                        engagement_id=engagement_id,
                        evidence_item_id=evidence_item_id,
                        started_at=started_at,
                        duration_ms=duration_ms,
                        input_count=in_count,
                        output_count=_output_count(result) if error_count == 0 else 0,
                        error_count=error_count,
                        error_type=error_type,
                        metadata=None,
                    )
                    MetricsCollector.instance().record(event)

            return async_wrapper

        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            from src.quality.metrics_collector import MetricsCollector

            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            engagement_id = _extract_id(engagement_id_param, _engagement_defaults, bound)
            evidence_item_id = _extract_id(evidence_item_id_param, _evidence_defaults, bound)
            in_count = _input_count(bound)

            started_at = datetime.now(tz=UTC)
            t0 = time.perf_counter()
            error_count = 0
            error_type: str | None = None
            result: Any = None

            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as exc:  # Intentionally broad: instrumentation wrapper must capture all exception types for metrics before re-raising
                error_count = 1
                error_type = type(exc).__name__
                raise
            finally:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                event = PipelineStageEvent(
                    stage=stage_name,
                    engagement_id=engagement_id,
                    evidence_item_id=evidence_item_id,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    input_count=in_count,
                    output_count=_output_count(result) if error_count == 0 else 0,
                    error_count=error_count,
                    error_type=error_type,
                    metadata=None,
                )
                MetricsCollector.instance().record(event)

        return sync_wrapper

    return decorator
