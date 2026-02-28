"""Obligation enforcement for PDP PERMIT decisions.

Applies data-handling obligations returned by the PDP to response payloads.
Each method is a pure function operating on dicts so they can be composed
and tested independently of the database.

Supported obligations (matching ObligationType enum):
  - MASK_FIELDS: Replace specified field values with "***"
  - SUPPRESS_COHORT: Return None if cohort_size < threshold (caller suppresses)
  - APPLY_WATERMARK: Inject _watermark metadata into response
  - ENFORCE_FIELD_ALLOWLIST: Strip fields not in the allowed set
  - APPLY_RETENTION_LIMIT: Truncate list results to retention_limit entries
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.models.pdp import ObligationType

logger = logging.getLogger(__name__)

# Sentinel returned by apply_cohort_suppression when suppression fires.
# Callers should check for None and respond with 204 / empty body.
_SUPPRESSED = None


class ObligationEnforcer:
    """Apply PDP obligations to response data.

    All methods are class methods (stateless) — no instance state needed.
    enforce_all() is the primary entry point for the PEP middleware.
    """

    @classmethod
    def apply_masking(cls, data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        """Replace specified field values with '***' (recursive).

        Masks fields at the top level and one level deep inside nested dicts.
        List items that are dicts are also masked recursively.

        Args:
            data: The response payload dict.
            fields: Field names to mask.

        Returns:
            New dict with masked values (original is not mutated).
        """
        if not fields:
            return data

        field_set = set(fields)
        return cls._mask_recursive(data, field_set)

    @classmethod
    def _mask_recursive(cls, obj: Any, fields: set[str]) -> Any:
        """Recursively mask fields inside dicts and lists."""
        if isinstance(obj, dict):
            return {
                k: "***" if k in fields else cls._mask_recursive(v, fields)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [cls._mask_recursive(item, fields) for item in obj]
        return obj

    @classmethod
    def apply_cohort_suppression(
        cls,
        data: dict[str, Any],
        min_cohort: int,
    ) -> dict[str, Any] | None:
        """Suppress response entirely when cohort is too small.

        Checks 'cohort_size' key in the top-level response dict. If the
        value is below min_cohort, returns None to signal suppression.
        If no cohort_size key is present, suppression does NOT fire so that
        endpoints without cohort metadata are not accidentally blocked.

        Args:
            data: The response payload dict.
            min_cohort: Minimum cohort size required for disclosure.

        Returns:
            The original data dict if cohort is sufficient, None if suppressed.
        """
        cohort = data.get("cohort_size")
        if cohort is not None and cohort < min_cohort:
            logger.info("ObligationEnforcer: cohort_size=%d < min=%d, suppressing response", cohort, min_cohort)
            return _SUPPRESSED
        return data

    @classmethod
    def apply_watermark(cls, data: dict[str, Any], actor: str) -> dict[str, Any]:
        """Inject a _watermark block into the response metadata.

        The watermark records who received the data and under what policy.
        Downstream export handlers should embed this in generated documents.

        Args:
            data: The response payload dict.
            actor: Identity of the requester (email or user ID).

        Returns:
            New dict with _watermark key added (original is not mutated).
        """
        from datetime import UTC, datetime

        return {
            **data,
            "_watermark": {
                "recipient": actor,
                "issued_at": datetime.now(UTC).isoformat(),
            },
        }

    @classmethod
    def apply_field_allowlist(cls, data: dict[str, Any], allowed: list[str]) -> dict[str, Any]:
        """Strip any fields not present in the allowed list (top-level only).

        This enforces field-level access control for roles that should only
        see a subset of a resource's attributes. Nested objects are kept
        intact — only top-level keys are filtered.

        Args:
            data: The response payload dict.
            allowed: List of field names that the caller is permitted to see.

        Returns:
            New dict containing only allowed fields.
        """
        if not allowed:
            return {}
        allowed_set = set(allowed)
        return {k: v for k, v in data.items() if k in allowed_set}

    @classmethod
    def apply_retention_limit(cls, data: dict[str, Any], limit: int) -> dict[str, Any]:
        """Truncate list values in the response to the retention limit.

        Iterates over top-level values that are lists and slices them to
        at most `limit` entries. Useful for enforcing data minimization
        on bulk-export or list endpoints.

        Args:
            data: The response payload dict.
            limit: Maximum number of items allowed per list field.

        Returns:
            New dict with list values truncated (original is not mutated).
        """
        result = {}
        for k, v in data.items():
            if isinstance(v, list) and len(v) > limit:
                result[k] = v[:limit]
            else:
                result[k] = v
        return result

    @classmethod
    def enforce_all(
        cls,
        data: dict[str, Any],
        obligations: list[Any],
        *,
        actor: str = "unknown",
    ) -> dict[str, Any] | None:
        """Apply all obligations in sequence.

        Obligations are applied in the order they appear in the list.
        If SUPPRESS_COHORT fires, None is returned immediately without
        applying further obligations (there is nothing to enforce on).

        Args:
            data: The response payload dict.
            obligations: List of obligation objects with .obligation_type
                and .parameters attributes (e.g. PolicyObligation instances
                or SimpleNamespace objects from the PEP middleware).
            actor: Identity string injected into watermarks.

        Returns:
            Transformed data dict, or None if suppression fired.
        """
        result: dict[str, Any] | None = data

        for ob in obligations:
            if result is None:
                break

            ob_type = ob.obligation_type
            params: dict[str, Any] = ob.parameters or {}

            if ob_type == ObligationType.MASK_FIELDS:
                fields = params.get("fields", [])
                result = cls.apply_masking(result, fields)

            elif ob_type == ObligationType.SUPPRESS_COHORT:
                min_cohort = int(params.get("min_cohort", params.get("threshold", 5)))
                result = cls.apply_cohort_suppression(result, min_cohort)

            elif ob_type == ObligationType.APPLY_WATERMARK:
                result = cls.apply_watermark(result, actor)

            elif ob_type == ObligationType.ENFORCE_FIELD_ALLOWLIST:
                allowed = params.get("allowed_fields", params.get("fields", []))
                result = cls.apply_field_allowlist(result, allowed)

            elif ob_type == ObligationType.APPLY_RETENTION_LIMIT:
                limit = int(params.get("limit", params.get("retention_limit", 1000)))
                result = cls.apply_retention_limit(result, limit)

            elif ob_type == ObligationType.LOG_ENHANCED_AUDIT:
                # Handled by the audit middleware — no data transformation needed
                pass

            else:
                logger.debug("ObligationEnforcer: no handler for obligation type %s", ob_type)

        return result
