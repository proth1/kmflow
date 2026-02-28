"""Unix domain socket server for receiving events from the Swift capture layer.

Listens on a user-private Unix domain socket and reads newline-delimited JSON events.
Each event is L2-filtered and written to the local SQLite buffer.

SCREEN_CAPTURE events (VCE pipeline):
  1. Extract base64-encoded image bytes from payload
  2. Run OCR → redact PII
  3. Run HybridClassifier (rule-based + VLM stub)
  4. Build VCERecord with classification results
  5. Discard image bytes from memory (explicit del + gc hint)
  6. Buffer VCERecord metadata for upload via VCEUploader

Privacy: image bytes are NEVER written to SQLite buffer, disk, or logs.
Only VCERecord metadata (no pixel data) is persisted.
"""

from __future__ import annotations

import asyncio
import base64
import gc
import json
import logging
import os
import stat
from datetime import datetime, timezone
from typing import Any

from kmflow_agent.buffer.manager import BufferManager
from kmflow_agent.pii.l2_filter import L2Filter
from kmflow_agent.vce.classifier import HybridClassifier
from kmflow_agent.vce.ocr import OCREngine
from kmflow_agent.vce.record import VCERecord
from kmflow_agent.vce.redactor import redact_pii

logger = logging.getLogger(__name__)

# User-private directory — not world-readable /tmp
_SOCKET_DIR = os.path.expanduser("~/Library/Application Support/KMFlowAgent")
SOCKET_PATH = os.path.join(_SOCKET_DIR, "agent.sock")

# IPC event type for screen captures (from native VCECaptureManager)
_SCREEN_CAPTURE_EVENT = "SCREEN_CAPTURE"


class SocketServer:
    """Async Unix domain socket server for Swift → Python IPC."""

    def __init__(
        self,
        buffer: BufferManager,
        socket_path: str = SOCKET_PATH,
        vce_queue: asyncio.Queue[VCERecord] | None = None,
    ) -> None:
        self.buffer = buffer
        self.socket_path = socket_path
        self.l2_filter = L2Filter()
        self._ocr = OCREngine()
        self._classifier = HybridClassifier()
        # VCE records are enqueued here for the VCEUploader to drain
        self._vce_queue: asyncio.Queue[VCERecord] = vce_queue or asyncio.Queue(maxsize=500)
        self._event_count = 0
        self._vce_count = 0

    @property
    def vce_queue(self) -> asyncio.Queue[VCERecord]:
        """Queue of VCERecord objects ready for upload."""
        return self._vce_queue

    async def serve(self, shutdown_event: asyncio.Event) -> None:
        """Start the socket server and accept connections until shutdown."""
        # Ensure socket directory exists with restricted permissions
        socket_dir = os.path.dirname(self.socket_path)
        os.makedirs(socket_dir, mode=0o700, exist_ok=True)

        # Remove stale socket file
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        server = await asyncio.start_unix_server(
            self._handle_client, path=self.socket_path
        )

        # Restrict socket file permissions to owner-only
        os.chmod(self.socket_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

        logger.info("Socket server listening on %s", self.socket_path)

        try:
            while not shutdown_event.is_set():
                await asyncio.sleep(0.5)
        finally:
            server.close()
            await server.wait_closed()
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
            logger.info(
                "Socket server stopped (events=%d vce=%d)",
                self._event_count,
                self._vce_count,
            )

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single Swift client connection."""
        logger.info("Swift client connected")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    event_data = json.loads(line.decode("utf-8").strip())
                    await self._process_event(event_data)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON received: %s", line[:100])
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Client handler error")
        finally:
            writer.close()
            logger.info("Swift client disconnected")

    async def _process_event(self, event_data: dict[str, Any]) -> None:
        """Route event to the appropriate handler based on event_type."""
        event_type = event_data.get("event_type")

        if event_type == _SCREEN_CAPTURE_EVENT:
            await self._process_screen_capture(event_data)
        else:
            await self._process_standard_event(event_data)

    async def _process_standard_event(self, event_data: dict[str, Any]) -> None:
        """Apply L2 PII filter and buffer the event."""
        filtered = self.l2_filter.filter_event(event_data)
        await self.buffer.write_event(filtered)
        self._event_count += 1

    async def _process_screen_capture(self, event_data: dict[str, Any]) -> None:
        """Process a SCREEN_CAPTURE event through the VCE pipeline.

        Privacy guarantees:
        - Image bytes are extracted, decoded, used for OCR + classification,
          and then explicitly deleted and garbage-collected.
        - Image bytes are NEVER written to the SQLite buffer, disk, or logs.
        - Only the VCERecord metadata is enqueued for upload.
        """
        image_bytes: bytes | None = None
        try:
            # Decode image bytes — held in memory only for OCR
            raw_b64 = event_data.get("image_bytes", "")
            image_bytes = base64.b64decode(raw_b64) if raw_b64 else b""

            # Extract context metadata from the payload
            app_name: str = event_data.get("application_name", "")
            window_title: str = event_data.get("window_title", "")
            dwell_ms: int = int(event_data.get("dwell_ms", 0))
            interaction_intensity: float = float(event_data.get("interaction_intensity", 0.0))
            trigger_reason: str = event_data.get("trigger_reason", "high_dwell")

            # OCR — extract text from pixel data
            raw_ocr_text = await self._ocr.extract_text(image_bytes)

            # PII redaction of OCR output
            redacted_text, sensitivity_flags = redact_pii(raw_ocr_text)

            # Redact window title as well
            redacted_title, title_flags = redact_pii(window_title)
            all_flags = list(dict.fromkeys(sensitivity_flags + title_flags))

            # Classification — rule-based (Phase 1), VLM optional
            screen_class, confidence, method = self._classifier.classify(
                ocr_text=redacted_text,
                window_title=redacted_title,
                app_name=app_name,
                interaction_intensity=interaction_intensity,
                dwell_ms=dwell_ms,
                image_bytes=image_bytes if image_bytes else None,
            )

        except Exception as exc:
            logger.warning("VCE pipeline error: %s", exc)
            screen_class = "other"
            confidence = 0.0
            method = "rule_based"
            redacted_text = ""
            redacted_title = ""
            all_flags = []
            app_name = event_data.get("application_name", "")
            dwell_ms = int(event_data.get("dwell_ms", 0))
            interaction_intensity = float(event_data.get("interaction_intensity", 0.0))
            trigger_reason = event_data.get("trigger_reason", "high_dwell")
        finally:
            # Explicitly discard image bytes — NEVER persisted to disk
            if image_bytes is not None:
                del image_bytes
                gc.collect()

        # Build VCERecord — contains only metadata, no pixel data
        ts_str = event_data.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now(timezone.utc)
        except ValueError:
            ts = datetime.now(timezone.utc)

        record = VCERecord(
            timestamp=ts,
            screen_state_class=screen_class,
            confidence=confidence,
            trigger_reason=trigger_reason,
            application_name=app_name,
            dwell_ms=dwell_ms,
            sensitivity_flags=all_flags,
            window_title_redacted=redacted_title or None,
            interaction_intensity=interaction_intensity or None,
            ocr_text_redacted=redacted_text or None,
            classification_method=method,
        )

        # Enqueue for upload — never touches disk storage
        try:
            self._vce_queue.put_nowait(record)
            self._vce_count += 1
            logger.debug(
                "VCE record enqueued: screen_class=%s confidence=%.2f method=%s",
                screen_class,
                confidence,
                method,
            )
        except asyncio.QueueFull:
            logger.warning("VCE upload queue full — record dropped (screen_class=%s)", screen_class)

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def vce_count(self) -> int:
        return self._vce_count
