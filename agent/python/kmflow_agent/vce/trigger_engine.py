"""VCE trigger engine for server-side trigger evaluation (Triggers 3-5).

Triggers 1-2 (HIGH_DWELL, LOW_CONFIDENCE) are evaluated in the native layer
and passed via IPC. This engine handles:
  - RECURRING_EXCEPTION: >= 3 error screens for the same app in a time window
  - NOVEL_CLUSTER: screen feature vector distance > threshold from known clusters
  - TAXONOMY_BOUNDARY: app transition crosses engagement-defined system boundaries
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Error screen tracking window (minutes)
_EXCEPTION_WINDOW_MINUTES = 30
# Number of error occurrences to fire RECURRING_EXCEPTION
_EXCEPTION_THRESHOLD = 3

# Novel cluster distance threshold (cosine-distance-like, 0-1 range)
_NOVEL_CLUSTER_THRESHOLD = 0.40


class TriggerEngine:
    """Evaluates server-side VCE trigger conditions.

    Maintains per-app error occurrence history and a simple cluster prototype
    store for novelty detection.
    """

    def __init__(self) -> None:
        # Maps app_name → deque of (timestamp, screen_class) tuples
        self._error_history: dict[str, deque[datetime]] = defaultdict(
            lambda: deque(maxlen=100)
        )
        # Known screen feature cluster prototypes — list of feature dicts
        self._cluster_prototypes: list[dict[str, float]] = []

    def check_recurring_exception(
        self, app_name: str, screen_class: str
    ) -> bool:
        """Check if error screens for app_name exceed the recurrence threshold.

        Fires when >= EXCEPTION_THRESHOLD error screens are observed for the
        same app within EXCEPTION_WINDOW_MINUTES.

        Args:
            app_name: Application name.
            screen_class: Classified screen state.

        Returns:
            True if RECURRING_EXCEPTION trigger should fire.
        """
        if screen_class != "error":
            return False

        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=_EXCEPTION_WINDOW_MINUTES)

        history = self._error_history[app_name]
        history.append(now)

        # Count occurrences within window
        count = sum(1 for ts in history if ts >= cutoff)
        if count >= _EXCEPTION_THRESHOLD:
            logger.debug(
                "RECURRING_EXCEPTION trigger: app=%s count=%d", app_name, count
            )
            return True
        return False

    def check_novel_cluster(self, features: dict[str, float]) -> bool:
        """Check if the screen feature vector is distant from known clusters.

        Uses a simple cosine-distance approximation against stored prototypes.
        If no prototypes exist yet, registers this as the first cluster and
        does not fire.

        Args:
            features: Dict of feature_name → float value (e.g., {"word_count": 12.0}).

        Returns:
            True if NOVEL_CLUSTER trigger should fire.
        """
        if not self._cluster_prototypes:
            # Bootstrap: register this as the first known cluster
            self._cluster_prototypes.append(dict(features))
            return False

        min_distance = min(
            self._cosine_distance(features, proto)
            for proto in self._cluster_prototypes
        )

        if min_distance > _NOVEL_CLUSTER_THRESHOLD:
            logger.debug(
                "NOVEL_CLUSTER trigger: min_distance=%.3f threshold=%.3f",
                min_distance,
                _NOVEL_CLUSTER_THRESHOLD,
            )
            # Add to prototypes to avoid repeated triggering on the same cluster
            self._cluster_prototypes.append(dict(features))
            return True
        return False

    def check_taxonomy_boundary(
        self,
        from_app: str,
        to_app: str,
        config: dict,
    ) -> bool:
        """Check if an app transition crosses engagement-defined system boundaries.

        Boundaries are defined in agent config as a list of pairs or sets.
        Example config format:
          {"taxonomy_boundaries": [["SAP", "Excel"], ["Salesforce", "Word"]]}

        Args:
            from_app: Application name before the switch.
            to_app: Application name after the switch.
            config: Agent configuration dict.

        Returns:
            True if TAXONOMY_BOUNDARY trigger should fire.
        """
        boundaries: list[list[str]] = config.get("taxonomy_boundaries", [])
        from_lower = from_app.lower()
        to_lower = to_app.lower()

        for boundary in boundaries:
            lower_boundary = [b.lower() for b in boundary]
            # Check if the transition crosses this boundary (one app on each side)
            if from_lower in lower_boundary and to_lower in lower_boundary:
                logger.debug(
                    "TAXONOMY_BOUNDARY trigger: %s → %s crosses %s",
                    from_app,
                    to_app,
                    boundary,
                )
                return True
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_distance(a: dict[str, float], b: dict[str, float]) -> float:
        """Compute cosine distance (1 - cosine_similarity) between two feature dicts.

        Keys present in one but not the other are treated as 0.
        Returns 1.0 if either vector is zero-magnitude.
        """
        keys = set(a) | set(b)
        dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
        mag_a = math.sqrt(sum(v ** 2 for v in a.values()))
        mag_b = math.sqrt(sum(v ** 2 for v in b.values()))
        if mag_a == 0 or mag_b == 0:
            return 1.0
        similarity = dot / (mag_a * mag_b)
        return 1.0 - max(-1.0, min(1.0, similarity))
