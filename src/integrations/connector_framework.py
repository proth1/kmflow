"""Connector framework: auth, retry, and data normalization pipeline (Story #323).

Provides reusable infrastructure for all integration connectors:
- CredentialProvider: abstraction for credential sources (env vars, secrets manager)
- @with_retry: decorator with exponential backoff and jitter
- TransformPipeline: ordered transform steps for data normalization
- Rate limit header parsing for Retry-After and X-RateLimit-Reset
- Custom exceptions (AuthenticationError, RetryExhaustedError, RateLimitError)

Relationship to existing modules:
- ``base.py``: Defines the abstract ``BaseConnector`` interface and connection
  lifecycle (connect/disconnect/health_check). Connectors subclass it.
- ``utils.py``: Provides ``retry_request`` (httpx-specific) and ``paginate_api``
  helpers tied to httpx.AsyncClient.
- This module adds *transport-agnostic* building blocks (credentials, generic
  retry decorator, transform pipeline) that ``BaseConnector`` implementations
  can compose without depending on httpx directly.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)


# -- Exceptions ---


class ConnectorError(Exception):
    """Base exception for connector errors."""


class AuthenticationError(ConnectorError):
    """Raised when authentication fails.

    Attributes:
        credential_field: The credential field that caused the failure.
        remediation_hint: Suggestion for fixing the issue.
    """

    def __init__(
        self,
        message: str,
        credential_field: str = "",
        remediation_hint: str = "",
    ) -> None:
        self.credential_field = credential_field
        self.remediation_hint = remediation_hint
        full_msg = message
        if credential_field:
            full_msg += f" (field: {credential_field})"
        if remediation_hint:
            full_msg += f". Hint: {remediation_hint}"
        super().__init__(full_msg)


class RetryExhaustedError(ConnectorError):
    """Raised when all retry attempts are exhausted.

    Attributes:
        attempts: Number of attempts made.
        last_error: The last error encountered.
    """

    def __init__(self, attempts: int, last_error: Exception | None = None) -> None:
        self.attempts = attempts
        self.last_error = last_error
        msg = f"All {attempts} retry attempts exhausted"
        if last_error:
            msg += f": {last_error}"
        super().__init__(msg)


class RateLimitError(ConnectorError):
    """Raised when a rate limit is hit."""

    def __init__(self, retry_after: float, message: str = "") -> None:
        self.retry_after = retry_after
        super().__init__(message or f"Rate limited, retry after {retry_after:.1f}s")


# -- Credential Provider ---


class CredentialSource(enum.StrEnum):
    """Supported credential sources."""

    ENV_VAR = "env_var"
    SECRETS_MANAGER = "secrets_manager"


@dataclass(frozen=True)
class Credential:
    """A resolved credential value."""

    key: str
    value: str
    source: str

    def __repr__(self) -> str:
        return f"Credential(key={self.key!r}, value='***', source={self.source!r})"


class CredentialProvider:
    """Abstraction for credential retrieval from multiple backends.

    Supports environment variables and a pluggable secrets manager.
    """

    def __init__(self, secrets_backend: dict[str, str] | None = None) -> None:
        """Initialize with optional secrets manager backend.

        Args:
            secrets_backend: Dict simulating a secrets manager (key -> value).
                In production, this would be an AWS Secrets Manager or Vault client.
        """
        self._secrets_backend = secrets_backend or {}

    def get_credential(
        self,
        key: str,
        source: str = CredentialSource.ENV_VAR,
    ) -> Credential:
        """Retrieve a credential by key from the specified source.

        Args:
            key: The credential key or environment variable name.
            source: Where to look for the credential.

        Returns:
            Resolved Credential.

        Raises:
            AuthenticationError: If credential is not found.
        """
        if source == CredentialSource.ENV_VAR:
            value = os.environ.get(key)
            if value is None:
                raise AuthenticationError(
                    "Credential not found in environment",
                    credential_field=key,
                    remediation_hint=f"Set the {key} environment variable",
                )
            return Credential(key=key, value=value, source=source)

        if source == CredentialSource.SECRETS_MANAGER:
            value = self._secrets_backend.get(key)
            if value is None:
                raise AuthenticationError(
                    "Credential not found in secrets manager",
                    credential_field=key,
                    remediation_hint=f"Add '{key}' to your secrets manager",
                )
            return Credential(key=key, value=value, source=source)

        raise AuthenticationError(
            f"Unknown credential source: {source}",
            credential_field=key,
            remediation_hint="Use 'env_var' or 'secrets_manager'",
        )

    def has_credential(self, key: str, source: str = CredentialSource.ENV_VAR) -> bool:
        """Check if a credential exists without raising."""
        try:
            self.get_credential(key, source)
            return True
        except AuthenticationError:
            return False


# -- Retry Decorator ---


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    jitter: bool = True,
    retry_on: tuple[type[Exception], ...] = (Exception,),
) -> Callable[..., Any]:
    """Decorator for exponential backoff retry with jitter.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds (doubles each retry).
        jitter: Whether to add random jitter to delays.
        retry_on: Exception types to retry on.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_error: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_on as exc:
                    last_error = exc
                    if attempt >= max_retries:
                        break

                    delay = base_delay * (2**attempt)
                    if jitter:
                        delay *= 0.5 + random.random()  # noqa: S311

                    logger.warning(
                        "Retry %d/%d for %s after %.2fs: %s",
                        attempt + 1,
                        max_retries,
                        func.__name__,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

            raise RetryExhaustedError(max_retries, last_error)

        return wrapper

    return decorator


# -- Rate Limit Parsing ---


def parse_rate_limit_headers(headers: dict[str, str]) -> float | None:
    """Parse rate limit reset time from HTTP response headers.

    Supports:
    - Retry-After: seconds (integer) or HTTP-date
    - X-RateLimit-Reset: Unix timestamp

    Args:
        headers: HTTP response headers (case-insensitive lookup).

    Returns:
        Seconds to wait before retrying, or None if no rate limit headers found.
    """
    # Normalize header keys to lowercase
    normalized = {k.lower(): v for k, v in headers.items()}

    # Retry-After: seconds (most common)
    retry_after = normalized.get("retry-after")
    if retry_after is not None:
        try:
            return float(retry_after)
        except ValueError:
            # Could be an HTTP-date, treat as 60s default
            logger.warning("Unparseable Retry-After header: %s", retry_after)
            return 60.0

    # X-RateLimit-Reset: Unix timestamp
    reset_ts = normalized.get("x-ratelimit-reset")
    if reset_ts is not None:
        try:
            reset_time = float(reset_ts)
            wait_seconds = max(0.0, reset_time - time.time())
            return wait_seconds
        except ValueError:
            logger.warning("Unparseable X-RateLimit-Reset header: %s", reset_ts)
            return 60.0

    return None


# -- Transform Pipeline ---


@dataclass(frozen=True)
class CanonicalActivityEvent:
    """KMFlow's internal canonical activity event format.

    This is the target format that all connector data is normalized to.
    """

    activity_name: str
    timestamp: str
    actor: str
    source_system: str
    case_id: str = ""
    resource: str = ""
    extended_attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity_name": self.activity_name,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "source_system": self.source_system,
            "case_id": self.case_id,
            "resource": self.resource,
            "extended_attributes": self.extended_attributes,
        }


class TransformStep:
    """A single step in a transform pipeline.

    Subclass and override transform() for custom logic.
    """

    def __init__(self, name: str = "") -> None:
        self.name = name or self.__class__.__name__

    def transform(self, record: dict[str, Any]) -> dict[str, Any]:
        """Transform a single record. Override in subclasses."""
        return record


class FieldMappingStep(TransformStep):
    """Maps source fields to target fields using a mapping dict."""

    def __init__(self, field_map: dict[str, str], source_system: str = "") -> None:
        """Initialize with field mapping.

        Args:
            field_map: Dict of {source_field: target_field}.
            source_system: Name of the source system for tracking.
        """
        super().__init__(name="field_mapping")
        self._field_map = field_map
        self._source_system = source_system

    def transform(self, record: dict[str, Any]) -> dict[str, Any]:
        """Map fields, preserving unmapped fields in extended_attributes."""
        result: dict[str, Any] = {}
        extended: dict[str, Any] = {}

        for key, value in record.items():
            target = self._field_map.get(key)
            if target:
                result[target] = value
            else:
                extended[key] = value

        if extended:
            result["extended_attributes"] = extended

        if self._source_system and "source_system" not in result:
            result["source_system"] = self._source_system

        return result


class TransformPipeline:
    """Ordered pipeline of transform steps for data normalization.

    Steps execute in order, each receiving the output of the previous step.
    """

    def __init__(self, steps: list[TransformStep] | None = None) -> None:
        self._steps: list[TransformStep] = steps or []

    def add_step(self, step: TransformStep) -> None:
        """Add a transform step to the pipeline."""
        self._steps.append(step)

    @property
    def steps(self) -> list[TransformStep]:
        """List of pipeline steps."""
        return list(self._steps)

    def transform_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Run a single record through all transform steps."""
        result = dict(record)
        for step in self._steps:
            result = step.transform(result)
        return result

    def transform_batch(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Run a batch of records through all transform steps."""
        return [self.transform_record(r) for r in records]

    def to_canonical_events(
        self,
        records: list[dict[str, Any]],
    ) -> list[CanonicalActivityEvent]:
        """Transform records and convert to CanonicalActivityEvent objects.

        Records must have required fields after transformation:
        activity_name, timestamp, actor, source_system.
        Missing required fields raise ValueError.
        """
        transformed = self.transform_batch(records)
        events = []

        for i, record in enumerate(transformed):
            missing = [f for f in ("activity_name", "timestamp", "actor", "source_system") if not record.get(f)]
            if missing:
                msg = f"Record {i}: missing required fields: {', '.join(missing)}"
                raise ValueError(msg)

            events.append(
                CanonicalActivityEvent(
                    activity_name=record["activity_name"],
                    timestamp=record["timestamp"],
                    actor=record["actor"],
                    source_system=record["source_system"],
                    case_id=record.get("case_id", ""),
                    resource=record.get("resource", ""),
                    extended_attributes=record.get("extended_attributes", {}),
                )
            )

        return events
