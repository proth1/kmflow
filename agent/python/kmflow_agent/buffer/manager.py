"""SQLite buffer manager for offline event storage.

Events are stored in WAL mode for concurrent read/write.
The buffer enforces a 100MB size limit by pruning oldest events.
Encryption wraps individual event payloads using AES-256-GCM.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kmflow_agent.buffer.encryption import decrypt_payload, encrypt_payload

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.expanduser(
    "~/Library/Application Support/KMFlowAgent/buffer.db"
)
MAX_BUFFER_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    event_json_encrypted BLOB NOT NULL,
    created_at TEXT NOT NULL,
    uploaded INTEGER DEFAULT 0
);
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS ix_events_uploaded ON events(uploaded);
"""


class BufferManager:
    """Manages the local SQLite event buffer."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        encryption_key: bytes | None = None,
    ) -> None:
        self.db_path = db_path
        self._encryption_key = encryption_key or self._default_key()
        self._conn: sqlite3.Connection | None = None
        self._write_count = 0
        self._ensure_db()

    def _default_key(self) -> bytes:
        """Get encryption key from env or generate and persist a random key."""
        env_key = os.environ.get("KMFLOW_BUFFER_KEY")
        if env_key:
            return env_key.encode("utf-8")[:32].ljust(32, b"\0")

        # Generate a random key on first run and persist it
        key_path = Path(self.db_path).parent / ".buffer_key"
        if key_path.exists():
            return key_path.read_bytes()[:32]

        key_path.parent.mkdir(parents=True, exist_ok=True)
        key = os.urandom(32)
        key_path.write_bytes(key)
        os.chmod(key_path, 0o600)
        logger.info("Generated new buffer encryption key at %s", key_path)
        return key

    def _ensure_db(self) -> None:
        """Create the database directory and tables."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(CREATE_TABLE)
        self._conn.execute(CREATE_INDEX)
        self._conn.commit()

    def _db_write_event(self, event: dict[str, Any]) -> str:
        """Synchronous DB write — called via asyncio.to_thread."""
        event_id = str(uuid.uuid4())
        payload = json.dumps(event).encode("utf-8")
        encrypted = encrypt_payload(payload, self._encryption_key)
        now = datetime.now(UTC).isoformat()

        assert self._conn is not None
        self._conn.execute(
            "INSERT INTO events (id, event_json_encrypted, created_at) VALUES (?, ?, ?)",
            (event_id, encrypted, now),
        )
        self._conn.commit()
        self._write_count += 1

        # Check buffer size every 100 writes
        if self._write_count % 100 == 0:
            self._enforce_size_limit_sync()

        return event_id

    async def write_event(self, event: dict[str, Any]) -> str:
        """Write an event to the buffer. Returns the event ID."""
        return await asyncio.to_thread(self._db_write_event, event)

    def _db_read_pending(self, limit: int) -> list[dict[str, Any]]:
        """Synchronous DB read — called via asyncio.to_thread."""
        assert self._conn is not None
        cursor = self._conn.execute(
            "SELECT id, event_json_encrypted FROM events WHERE uploaded = 0 ORDER BY created_at LIMIT ?",
            (limit,),
        )
        results = []
        for row in cursor.fetchall():
            event_id, encrypted = row
            payload = decrypt_payload(encrypted, self._encryption_key)
            event = json.loads(payload.decode("utf-8"))
            event["_buffer_id"] = event_id
            results.append(event)
        return results

    async def read_pending(self, limit: int = 100) -> list[dict[str, Any]]:
        """Read pending (not yet uploaded) events from the buffer."""
        return await asyncio.to_thread(self._db_read_pending, limit)

    def _db_mark_uploaded(self, event_ids: list[str]) -> None:
        """Synchronous DB update — called via asyncio.to_thread."""
        if not event_ids:
            return
        assert self._conn is not None
        placeholders = ",".join("?" for _ in event_ids)
        self._conn.execute(
            f"UPDATE events SET uploaded = 1 WHERE id IN ({placeholders})",
            event_ids,
        )
        self._conn.commit()

    async def mark_uploaded(self, event_ids: list[str]) -> None:
        """Mark events as successfully uploaded."""
        await asyncio.to_thread(self._db_mark_uploaded, event_ids)

    def _db_prune_uploaded(self) -> int:
        """Synchronous DB delete — called via asyncio.to_thread."""
        assert self._conn is not None
        cursor = self._conn.execute("DELETE FROM events WHERE uploaded = 1")
        self._conn.commit()
        return cursor.rowcount

    async def prune_uploaded(self) -> int:
        """Delete uploaded events from the buffer. Returns count deleted."""
        return await asyncio.to_thread(self._db_prune_uploaded)

    def _db_count_pending(self) -> int:
        """Synchronous DB count — called via asyncio.to_thread."""
        assert self._conn is not None
        cursor = self._conn.execute("SELECT COUNT(*) FROM events WHERE uploaded = 0")
        return cursor.fetchone()[0]

    async def count_pending(self) -> int:
        """Count pending events in the buffer."""
        return await asyncio.to_thread(self._db_count_pending)

    def _enforce_size_limit_sync(self) -> None:
        """Prune oldest events if buffer exceeds size limit."""
        assert self._conn is not None
        try:
            size = os.path.getsize(self.db_path)
        except OSError:
            return

        if size > MAX_BUFFER_SIZE_BYTES:
            total = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            to_delete = max(total // 10, 100)
            self._conn.execute(
                "DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY created_at LIMIT ?)",
                (to_delete,),
            )
            self._conn.commit()
            logger.warning(
                "Buffer size limit exceeded (%d bytes), pruned %d events",
                size,
                to_delete,
            )

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
