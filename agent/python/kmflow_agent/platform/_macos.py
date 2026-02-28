"""macOS platform implementation.

Extracts existing macOS-specific code from buffer/manager.py and auth.py
into the platform abstraction interface.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

from kmflow_agent.platform._base import PlatformBase

logger = logging.getLogger(__name__)

_KEYCHAIN_SERVICE = "com.kmflow.agent"


class MacOSPlatform(PlatformBase):
    """macOS implementation using Keychain, Unix sockets, and chmod."""

    def get_data_dir(self) -> Path:
        return Path.home() / "Library" / "Application Support" / "KMFlowAgent"

    def get_ipc_address(self) -> str:
        return str(self.get_data_dir() / "agent.sock")

    async def create_ipc_server(
        self,
        client_handler: Any,
        shutdown_event: asyncio.Event,
    ) -> None:
        """Start a Unix domain socket server."""
        socket_path = self.get_ipc_address()
        socket_dir = os.path.dirname(socket_path)
        os.makedirs(socket_dir, mode=0o700, exist_ok=True)

        # Remove stale socket file
        if os.path.exists(socket_path):
            os.unlink(socket_path)

        server = await asyncio.start_unix_server(client_handler, path=socket_path)

        # Restrict socket file to owner-only
        os.chmod(socket_path, stat.S_IRUSR | stat.S_IWUSR)

        logger.info("IPC server listening on %s", socket_path)

        try:
            while not shutdown_event.is_set():
                await asyncio.sleep(0.5)
        finally:
            server.close()
            await server.wait_closed()
            if os.path.exists(socket_path):
                os.unlink(socket_path)
            logger.info("IPC server stopped")

    def store_credential(self, key: str, value: str) -> bool:
        # Delete existing entry first
        subprocess.run(
            ["security", "delete-generic-password", "-s", _KEYCHAIN_SERVICE, "-a", key],
            capture_output=True,
            timeout=5,
        )
        try:
            result = subprocess.run(
                [
                    "security",
                    "add-generic-password",
                    "-s", _KEYCHAIN_SERVICE,
                    "-a", key,
                    "-w", value,
                    "-U",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_credential(self, key: str) -> str | None:
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s", _KEYCHAIN_SERVICE,
                    "-a", key,
                    "-w",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.debug("Keychain read failed for key=%s", key)
        return None

    def delete_credential(self, key: str) -> None:
        try:
            subprocess.run(
                [
                    "security",
                    "delete-generic-password",
                    "-s", _KEYCHAIN_SERVICE,
                    "-a", key,
                ],
                capture_output=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    def set_owner_only_permissions(self, path: Path) -> None:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)

    def get_encryption_key(self, data_dir: Path) -> bytes:
        # Try environment variable first (CI/testing)
        env_key = os.environ.get("KMFLOW_BUFFER_KEY")
        if env_key:
            return env_key.encode("utf-8")[:32].ljust(32, b"\0")

        # Try Keychain
        stored = self.get_credential("buffer_encryption_key")
        if stored:
            return base64.b64decode(stored)[:32]

        # Migrate legacy file
        key_path = data_dir / ".buffer_key"
        if key_path.exists():
            key = key_path.read_bytes()[:32]
            encoded = base64.b64encode(key).decode("ascii")
            if self.store_credential("buffer_encryption_key", encoded):
                key_path.unlink(missing_ok=True)
                logger.info("Migrated buffer encryption key from file to Keychain")
            return key

        # Generate new key
        key = os.urandom(32)
        encoded = base64.b64encode(key).decode("ascii")
        data_dir.mkdir(parents=True, exist_ok=True)
        if self.store_credential("buffer_encryption_key", encoded):
            logger.info("Generated new buffer encryption key in Keychain")
        else:
            # Fallback to file if Keychain unavailable (CI)
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key_path.write_bytes(key)
            os.chmod(key_path, 0o600)
            logger.warning("Keychain unavailable, stored buffer key in file")
        return key
