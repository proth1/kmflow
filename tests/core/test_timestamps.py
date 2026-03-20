"""Tests for the shared timestamp parsing utility (src/core/timestamps.py)."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

from src.core.timestamps import parse_timestamp


class TestParseTimestamp:
    """Tests for parse_timestamp()."""

    def test_parse_iso_format(self) -> None:
        result = parse_timestamp("2026-01-15T10:30:00Z")
        assert result is not None
        assert result.tzinfo is not None

    def test_parse_iso_with_offset(self) -> None:
        result = parse_timestamp("2026-01-15T10:30:00+05:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_parse_none_returns_none(self) -> None:
        assert parse_timestamp(None) is None

    def test_parse_empty_string_returns_none(self) -> None:
        assert parse_timestamp("") is None

    def test_parse_datetime_passthrough(self) -> None:
        dt = datetime(2026, 1, 15, tzinfo=UTC)
        assert parse_timestamp(dt) is dt

    def test_parse_naive_datetime_adds_utc(self) -> None:
        dt = datetime(2026, 1, 15)
        result = parse_timestamp(dt)
        assert result is not None
        assert result.tzinfo is not None
        assert result.tzinfo == UTC

    def test_parse_date_only_string(self) -> None:
        result = parse_timestamp("2026-01-15")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15
        assert result.tzinfo is not None

    def test_parse_datetime_no_timezone_adds_utc(self) -> None:
        result = parse_timestamp("2026-01-15T10:30:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_parse_iso_returns_correct_year(self) -> None:
        result = parse_timestamp("2026-03-20T12:00:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 3
        assert result.day == 20

    def test_parse_unparseable_returns_none(self) -> None:
        result = parse_timestamp("not-a-date")
        assert result is None

    def test_parse_space_separated_format(self) -> None:
        result = parse_timestamp("2026-01-15 10:30:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_parse_dmy_slash_format(self) -> None:
        result = parse_timestamp("15/01/2026")
        assert result is not None
        assert result.tzinfo is not None

    def test_aware_datetime_passthrough_preserves_timezone(self) -> None:
        """Aware datetime with non-UTC timezone is returned as-is."""
        from datetime import timedelta

        tz_plus5 = timezone(timedelta(hours=5))
        dt = datetime(2026, 1, 15, 10, 30, tzinfo=tz_plus5)
        result = parse_timestamp(dt)
        assert result is dt
        assert result.tzinfo == tz_plus5
