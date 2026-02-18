"""Silver layer writers for the medallion architecture.

Writes parsed fragments, extracted entities, and quality events to
Silver Delta tables. These are derived, cleaned datasets produced by
the intelligence pipeline from Bronze (raw) evidence.

Tables:
- ``silver_evidence_fragments``: Parsed text fragments with metadata.
- ``silver_extracted_entities``: Named entities extracted from fragments.
- ``silver_quality_events``: Quality score snapshots per evidence item.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SilverLayerWriter:
    """Writes intelligence pipeline outputs to Silver Delta tables.

    Each write appends rows to the appropriate Silver table. If Delta Lake
    is not installed, writes fall back to JSON files on disk.

    Args:
        base_path: Root path for the datalake directory.
    """

    def __init__(self, base_path: str = "datalake") -> None:
        self._base_path = Path(base_path).resolve()
        self._silver_path = self._base_path / "silver"
        self._silver_path.mkdir(parents=True, exist_ok=True)
        self._has_delta = self._check_delta()

    @staticmethod
    def _check_delta() -> bool:
        """Check if deltalake is available."""
        try:
            import deltalake  # noqa: F401

            return True
        except ImportError:
            return False

    async def write_fragments(
        self,
        engagement_id: str,
        evidence_item_id: str,
        fragments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Write parsed evidence fragments to the Silver fragments table.

        Args:
            engagement_id: Engagement scope.
            evidence_item_id: The source evidence item ID.
            fragments: List of fragment dicts with keys:
                id, fragment_type, content, metadata_json.

        Returns:
            Dict with rows_written and table_path.
        """
        if not fragments:
            return {"rows_written": 0, "table_path": ""}

        table_path = str(self._silver_path / "evidence_fragments")
        now = datetime.now(UTC).isoformat()

        rows = []
        for frag in fragments:
            rows.append(
                {
                    "id": str(frag.get("id", uuid.uuid4())),
                    "engagement_id": engagement_id,
                    "evidence_item_id": evidence_item_id,
                    "fragment_type": str(frag.get("fragment_type", "text")),
                    "content": frag.get("content", ""),
                    "content_hash": hashlib.sha256(frag.get("content", "").encode()).hexdigest(),
                    "metadata_json": json.dumps(frag.get("metadata_json")) if frag.get("metadata_json") else "{}",
                    "written_at": now,
                }
            )

        if self._has_delta:
            return self._write_delta_fragments(table_path, rows)
        return self._write_json_fallback(table_path, rows, "fragments")

    async def write_entities(
        self,
        engagement_id: str,
        evidence_item_id: str,
        entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Write extracted entities to the Silver entities table.

        Args:
            engagement_id: Engagement scope.
            evidence_item_id: The source evidence item ID.
            entities: List of entity dicts with keys:
                entity_type, value, confidence, fragment_id.

        Returns:
            Dict with rows_written and table_path.
        """
        if not entities:
            return {"rows_written": 0, "table_path": ""}

        table_path = str(self._silver_path / "extracted_entities")
        now = datetime.now(UTC).isoformat()

        rows = []
        for entity in entities:
            rows.append(
                {
                    "id": uuid.uuid4().hex,
                    "engagement_id": engagement_id,
                    "evidence_item_id": evidence_item_id,
                    "fragment_id": str(entity.get("fragment_id", "")),
                    "entity_type": str(entity.get("entity_type", "")),
                    "value": str(entity.get("value", "")),
                    "confidence": float(entity.get("confidence", 0.0)),
                    "written_at": now,
                }
            )

        if self._has_delta:
            return self._write_delta_entities(table_path, rows)
        return self._write_json_fallback(table_path, rows, "entities")

    async def write_quality_event(
        self,
        engagement_id: str,
        evidence_item_id: str,
        scores: dict[str, float],
    ) -> dict[str, Any]:
        """Write a quality score snapshot to the Silver quality events table.

        Args:
            engagement_id: Engagement scope.
            evidence_item_id: The evidence item scored.
            scores: Dict with completeness, reliability, freshness, consistency.

        Returns:
            Dict with rows_written and table_path.
        """
        table_path = str(self._silver_path / "quality_events")
        now = datetime.now(UTC).isoformat()

        row = {
            "id": uuid.uuid4().hex,
            "engagement_id": engagement_id,
            "evidence_item_id": evidence_item_id,
            "completeness_score": scores.get("completeness", 0.0),
            "reliability_score": scores.get("reliability", 0.0),
            "freshness_score": scores.get("freshness", 0.0),
            "consistency_score": scores.get("consistency", 0.0),
            "overall_score": sum(scores.values()) / max(len(scores), 1),
            "recorded_at": now,
        }

        if self._has_delta:
            return self._write_delta_quality(table_path, [row])
        return self._write_json_fallback(table_path, [row], "quality")

    def _write_delta_fragments(self, table_path: str, rows: list[dict]) -> dict[str, Any]:
        """Write fragment rows to a Delta table."""
        import pyarrow as pa
        from deltalake import DeltaTable, write_deltalake

        schema = pa.schema(
            [
                ("id", pa.string()),
                ("engagement_id", pa.string()),
                ("evidence_item_id", pa.string()),
                ("fragment_type", pa.string()),
                ("content", pa.string()),
                ("content_hash", pa.string()),
                ("metadata_json", pa.string()),
                ("written_at", pa.string()),
            ]
        )

        table = pa.table(
            {col.name: [r[col.name] for r in rows] for col in schema},
            schema=schema,
        )

        if DeltaTable.is_deltatable(table_path):
            write_deltalake(table_path, table, mode="append")
        else:
            write_deltalake(table_path, table, mode="error")

        logger.info(
            "Wrote %d fragment rows to Silver Delta table %s",
            len(rows),
            table_path,
        )
        return {"rows_written": len(rows), "table_path": table_path}

    def _write_delta_entities(self, table_path: str, rows: list[dict]) -> dict[str, Any]:
        """Write entity rows to a Delta table."""
        import pyarrow as pa
        from deltalake import DeltaTable, write_deltalake

        schema = pa.schema(
            [
                ("id", pa.string()),
                ("engagement_id", pa.string()),
                ("evidence_item_id", pa.string()),
                ("fragment_id", pa.string()),
                ("entity_type", pa.string()),
                ("value", pa.string()),
                ("confidence", pa.float64()),
                ("written_at", pa.string()),
            ]
        )

        table = pa.table(
            {col.name: [r[col.name] for r in rows] for col in schema},
            schema=schema,
        )

        if DeltaTable.is_deltatable(table_path):
            write_deltalake(table_path, table, mode="append")
        else:
            write_deltalake(table_path, table, mode="error")

        logger.info(
            "Wrote %d entity rows to Silver Delta table %s",
            len(rows),
            table_path,
        )
        return {"rows_written": len(rows), "table_path": table_path}

    def _write_delta_quality(self, table_path: str, rows: list[dict]) -> dict[str, Any]:
        """Write quality event rows to a Delta table."""
        import pyarrow as pa
        from deltalake import DeltaTable, write_deltalake

        schema = pa.schema(
            [
                ("id", pa.string()),
                ("engagement_id", pa.string()),
                ("evidence_item_id", pa.string()),
                ("completeness_score", pa.float64()),
                ("reliability_score", pa.float64()),
                ("freshness_score", pa.float64()),
                ("consistency_score", pa.float64()),
                ("overall_score", pa.float64()),
                ("recorded_at", pa.string()),
            ]
        )

        table = pa.table(
            {col.name: [r[col.name] for r in rows] for col in schema},
            schema=schema,
        )

        if DeltaTable.is_deltatable(table_path):
            write_deltalake(table_path, table, mode="append")
        else:
            write_deltalake(table_path, table, mode="error")

        logger.info(
            "Wrote %d quality event rows to Silver Delta table %s",
            len(rows),
            table_path,
        )
        return {"rows_written": len(rows), "table_path": table_path}

    def _write_json_fallback(self, table_path: str, rows: list[dict], category: str) -> dict[str, Any]:
        """Fallback: write rows as JSON files when Delta Lake is not installed."""
        fallback_dir = Path(table_path)
        fallback_dir.mkdir(parents=True, exist_ok=True)

        file_name = f"{category}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.json"
        file_path = fallback_dir / file_name

        with open(file_path, "w") as f:
            json.dump(rows, f, indent=2)

        logger.info(
            "Wrote %d %s rows to JSON fallback %s",
            len(rows),
            category,
            file_path,
        )
        return {"rows_written": len(rows), "table_path": str(file_path)}
