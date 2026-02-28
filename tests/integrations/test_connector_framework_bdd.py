"""BDD tests for connector framework (Story #323).

Tests credential provider, retry decorator, transform pipeline,
rate limit parsing, and custom exceptions.
"""

from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import patch

import pytest

from src.integrations.connector_framework import (
    AuthenticationError,
    CanonicalActivityEvent,
    Credential,
    CredentialProvider,
    CredentialSource,
    FieldMappingStep,
    RateLimitError,
    RetryExhaustedError,
    TransformPipeline,
    TransformStep,
    parse_rate_limit_headers,
    with_retry,
)


class TestCredentialProviderEnvVar:
    """Scenario 1 & 4: Credential retrieval from environment variables."""

    def test_retrieves_existing_env_var(self) -> None:
        """Provider returns credential from environment."""
        provider = CredentialProvider()
        with patch.dict(os.environ, {"MY_API_KEY": "secret-123"}):
            cred = provider.get_credential("MY_API_KEY")

        assert cred.key == "MY_API_KEY"
        assert cred.value == "secret-123"
        assert cred.source == CredentialSource.ENV_VAR

    def test_missing_env_var_raises_auth_error(self) -> None:
        """Missing env var raises AuthenticationError with field and hint."""
        provider = CredentialProvider()
        with patch.dict(os.environ, {}, clear=True), pytest.raises(AuthenticationError) as exc_info:
            provider.get_credential("MISSING_KEY")

        err = exc_info.value
        assert err.credential_field == "MISSING_KEY"
        assert "MISSING_KEY" in err.remediation_hint

    def test_has_credential_true_when_exists(self) -> None:
        provider = CredentialProvider()
        with patch.dict(os.environ, {"MY_KEY": "val"}):
            assert provider.has_credential("MY_KEY") is True

    def test_has_credential_false_when_missing(self) -> None:
        provider = CredentialProvider()
        with patch.dict(os.environ, {}, clear=True):
            assert provider.has_credential("NOPE") is False


class TestCredentialProviderSecretsManager:
    """Scenario 1 & 4: Credential retrieval from secrets manager."""

    def test_retrieves_from_secrets_backend(self) -> None:
        secrets = {"db_password": "hunter2"}
        provider = CredentialProvider(secrets_backend=secrets)

        cred = provider.get_credential("db_password", CredentialSource.SECRETS_MANAGER)

        assert cred.value == "hunter2"
        assert cred.source == CredentialSource.SECRETS_MANAGER

    def test_missing_secret_raises_auth_error(self) -> None:
        provider = CredentialProvider(secrets_backend={})

        with pytest.raises(AuthenticationError) as exc_info:
            provider.get_credential("missing", CredentialSource.SECRETS_MANAGER)

        assert exc_info.value.credential_field == "missing"
        assert "secrets manager" in exc_info.value.remediation_hint

    def test_unknown_source_raises_auth_error(self) -> None:
        provider = CredentialProvider()

        with pytest.raises(AuthenticationError) as exc_info:
            provider.get_credential("key", "unknown_backend")

        assert "Unknown credential source" in str(exc_info.value)


class TestRetryDecorator:
    """Scenario 2: Exponential backoff on transient errors."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self) -> None:
        """No retry needed when function succeeds."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        async def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await succeed()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self) -> None:
        """Retries and eventually succeeds."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01, retry_on=(ValueError,))
        async def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("transient")
            return "recovered"

        result = await flaky()
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_retry_exhausted_error(self) -> None:
        """Raises RetryExhaustedError after max retries."""
        call_count = 0

        @with_retry(max_retries=2, base_delay=0.01, retry_on=(RuntimeError,))
        async def always_fail() -> None:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("permanent")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await always_fail()

        assert exc_info.value.attempts == 2
        assert isinstance(exc_info.value.last_error, RuntimeError)
        assert call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_does_not_retry_unexpected_exceptions(self) -> None:
        """Doesn't retry on exception types not in retry_on."""
        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01, retry_on=(ValueError,))
        async def type_error_fn() -> None:
            nonlocal call_count
            call_count += 1
            raise TypeError("unexpected")

        with pytest.raises(TypeError, match="unexpected"):
            await type_error_fn()

        assert call_count == 1  # No retries attempted

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self) -> None:
        """Delays increase exponentially."""
        delays: list[float] = []
        original_sleep = asyncio.sleep

        async def mock_sleep(duration: float) -> None:
            delays.append(duration)
            await original_sleep(0)  # Don't actually sleep

        call_count = 0

        @with_retry(max_retries=3, base_delay=1.0, jitter=False, retry_on=(ValueError,))
        async def always_fail() -> None:
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with (
            patch("src.integrations.connector_framework.asyncio.sleep", side_effect=mock_sleep),
            pytest.raises(RetryExhaustedError),
        ):
            await always_fail()

        assert len(delays) == 3
        assert delays[0] == pytest.approx(1.0)  # 1 * 2^0
        assert delays[1] == pytest.approx(2.0)  # 1 * 2^1
        assert delays[2] == pytest.approx(4.0)  # 1 * 2^2


class TestRateLimitParsing:
    """Scenario 5: Rate limit header parsing."""

    def test_retry_after_seconds(self) -> None:
        """Parses Retry-After as seconds."""
        result = parse_rate_limit_headers({"Retry-After": "30"})
        assert result == 30.0

    def test_retry_after_float(self) -> None:
        """Parses Retry-After as float seconds."""
        result = parse_rate_limit_headers({"Retry-After": "1.5"})
        assert result == 1.5

    def test_retry_after_unparseable(self) -> None:
        """Falls back to 60s for unparseable Retry-After."""
        result = parse_rate_limit_headers({"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
        assert result == 60.0

    def test_x_ratelimit_reset_timestamp(self) -> None:
        """Parses X-RateLimit-Reset as Unix timestamp."""
        future = time.time() + 45
        result = parse_rate_limit_headers({"X-RateLimit-Reset": str(future)})
        assert result is not None
        assert 40 <= result <= 50

    def test_x_ratelimit_reset_past_timestamp(self) -> None:
        """Past timestamp returns 0 (can retry immediately)."""
        past = time.time() - 100
        result = parse_rate_limit_headers({"X-RateLimit-Reset": str(past)})
        assert result == 0.0

    def test_no_rate_limit_headers(self) -> None:
        """Returns None when no rate limit headers present."""
        result = parse_rate_limit_headers({"Content-Type": "application/json"})
        assert result is None

    def test_case_insensitive_headers(self) -> None:
        """Header keys are case-insensitive."""
        result = parse_rate_limit_headers({"retry-after": "10"})
        assert result == 10.0

    def test_retry_after_takes_precedence(self) -> None:
        """Retry-After is checked before X-RateLimit-Reset."""
        result = parse_rate_limit_headers({
            "Retry-After": "5",
            "X-RateLimit-Reset": str(time.time() + 100),
        })
        assert result == 5.0


class TestTransformPipeline:
    """Scenario 3: Raw data normalization to internal evidence format."""

    def test_empty_pipeline_passes_through(self) -> None:
        """Empty pipeline returns records unchanged."""
        pipeline = TransformPipeline()
        record = {"name": "Alice", "age": 30}
        result = pipeline.transform_record(record)
        assert result == record

    def test_field_mapping_step(self) -> None:
        """FieldMappingStep maps source to target fields."""
        step = FieldMappingStep(
            field_map={
                "short_description": "activity_name",
                "sys_created_on": "timestamp",
                "assigned_to": "actor",
            },
            source_system="servicenow",
        )

        record = {
            "short_description": "Close ticket",
            "sys_created_on": "2026-01-15T10:00:00Z",
            "assigned_to": "jsmith",
            "priority": "1",
        }

        result = step.transform(record)
        assert result["activity_name"] == "Close ticket"
        assert result["timestamp"] == "2026-01-15T10:00:00Z"
        assert result["actor"] == "jsmith"
        assert result["source_system"] == "servicenow"
        assert result["extended_attributes"]["priority"] == "1"

    def test_multi_step_pipeline(self) -> None:
        """Pipeline executes steps in order."""

        class UppercaseStep(TransformStep):
            def transform(self, record: dict) -> dict:
                return {k: v.upper() if isinstance(v, str) else v for k, v in record.items()}

        class PrefixStep(TransformStep):
            def transform(self, record: dict) -> dict:
                return {f"out_{k}": v for k, v in record.items()}

        pipeline = TransformPipeline([UppercaseStep(), PrefixStep()])
        result = pipeline.transform_record({"name": "alice"})

        assert result == {"out_name": "ALICE"}

    def test_batch_transform(self) -> None:
        """Batch transform processes all records."""
        step = FieldMappingStep({"x": "y"})
        pipeline = TransformPipeline([step])

        results = pipeline.transform_batch([{"x": 1}, {"x": 2}, {"x": 3}])
        assert len(results) == 3
        assert all("y" in r for r in results)

    def test_to_canonical_events(self) -> None:
        """Pipeline produces valid CanonicalActivityEvent objects."""
        pipeline = TransformPipeline([
            FieldMappingStep(
                field_map={
                    "action": "activity_name",
                    "when": "timestamp",
                    "who": "actor",
                    "ticket": "case_id",
                },
                source_system="jira",
            )
        ])

        records = [
            {
                "action": "Resolve Issue",
                "when": "2026-01-15T14:00:00Z",
                "who": "analyst1",
                "ticket": "PROJ-123",
                "custom_field": "extra",
            }
        ]

        events = pipeline.to_canonical_events(records)
        assert len(events) == 1
        event = events[0]
        assert event.activity_name == "Resolve Issue"
        assert event.timestamp == "2026-01-15T14:00:00Z"
        assert event.actor == "analyst1"
        assert event.source_system == "jira"
        assert event.case_id == "PROJ-123"
        assert event.extended_attributes["custom_field"] == "extra"

    def test_missing_required_fields_raises_error(self) -> None:
        """ValueError raised when required fields are missing."""
        pipeline = TransformPipeline()

        with pytest.raises(ValueError, match="missing required fields"):
            pipeline.to_canonical_events([{"random": "data"}])

    def test_canonical_event_to_dict(self) -> None:
        """CanonicalActivityEvent serializes to dict."""
        event = CanonicalActivityEvent(
            activity_name="Test",
            timestamp="2026-01-01T00:00:00Z",
            actor="user1",
            source_system="test",
        )
        d = event.to_dict()
        assert d["activity_name"] == "Test"
        assert d["source_system"] == "test"
        assert d["extended_attributes"] == {}

    def test_add_step(self) -> None:
        """Steps can be added incrementally."""
        pipeline = TransformPipeline()
        assert len(pipeline.steps) == 0

        pipeline.add_step(TransformStep("step1"))
        assert len(pipeline.steps) == 1
        assert pipeline.steps[0].name == "step1"

    def test_unmapped_fields_in_extended_attributes(self) -> None:
        """Fields without mappings preserved in extended_attributes."""
        step = FieldMappingStep({"name": "activity_name"})
        result = step.transform({"name": "Test", "extra1": "a", "extra2": "b"})

        assert result["activity_name"] == "Test"
        assert result["extended_attributes"]["extra1"] == "a"
        assert result["extended_attributes"]["extra2"] == "b"


class TestCustomExceptions:
    """Exception structure and attributes."""

    def test_authentication_error_attributes(self) -> None:
        err = AuthenticationError(
            "Login failed",
            credential_field="api_key",
            remediation_hint="Refresh your API key",
        )
        assert err.credential_field == "api_key"
        assert err.remediation_hint == "Refresh your API key"
        assert "api_key" in str(err)
        assert "Refresh" in str(err)

    def test_retry_exhausted_error_attributes(self) -> None:
        original = RuntimeError("timeout")
        err = RetryExhaustedError(attempts=5, last_error=original)
        assert err.attempts == 5
        assert err.last_error is original
        assert "5" in str(err)

    def test_credential_dataclass(self) -> None:
        cred = Credential(key="api_key", value="secret", source="env_var")
        assert cred.key == "api_key"
        assert cred.value == "secret"

    def test_credential_repr_masks_value(self) -> None:
        """Credential repr masks value to prevent secret leakage in logs."""
        cred = Credential(key="api_key", value="super-secret-token", source="env_var")
        r = repr(cred)
        assert "super-secret-token" not in r
        assert "***" in r
        assert "api_key" in r
        assert "env_var" in r

    def test_rate_limit_error_attributes(self) -> None:
        """RateLimitError stores retry_after and formats message."""
        err = RateLimitError(retry_after=30.0)
        assert err.retry_after == 30.0
        assert "30.0" in str(err)

        err_custom = RateLimitError(retry_after=5.0, message="Too many requests")
        assert err_custom.retry_after == 5.0
        assert str(err_custom) == "Too many requests"
