"""Windows platform implementation.

Uses DPAPI for credential storage, named pipes for IPC, and NTFS ACLs
for file permissions. Falls back to TCP loopback if named pipe creation fails.
"""

from __future__ import annotations

import asyncio
import base64
import ctypes
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from kmflow_agent.platform._base import PlatformBase

logger = logging.getLogger(__name__)

_CREDENTIAL_TARGET_PREFIX = "KMFlowAgent:"
_PIPE_NAME = r"\\.\pipe\KMFlowAgent"
_TCP_FALLBACK_HOST = "127.0.0.1"
_TCP_FALLBACK_PORT = 19847


class WindowsPlatform(PlatformBase):
    """Windows implementation using DPAPI, named pipes, and NTFS ACLs."""

    def get_data_dir(self) -> Path:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if not local_app_data:
            local_app_data = str(Path.home() / "AppData" / "Local")
        return Path(local_app_data) / "KMFlowAgent"

    def get_ipc_address(self) -> str:
        return _PIPE_NAME

    async def create_ipc_server(
        self,
        client_handler: Any,
        shutdown_event: asyncio.Event,
    ) -> None:
        """Start a TCP loopback server as the IPC transport.

        Python's asyncio does not natively support named pipe servers on Windows.
        We use TCP loopback (127.0.0.1) restricted to localhost as a reliable
        fallback. The C# client connects to this address.

        A future enhancement can use ProactorEventLoop with win32pipe for true
        named pipe support.
        """
        data_dir = self.get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)

        server = await asyncio.start_server(
            client_handler,
            host=_TCP_FALLBACK_HOST,
            port=_TCP_FALLBACK_PORT,
        )

        # Write the port to a file so the C# client can discover it
        port_file = data_dir / "ipc_port"
        port_file.write_text(str(_TCP_FALLBACK_PORT))
        self.set_owner_only_permissions(port_file)

        logger.info(
            "IPC server listening on %s:%d (TCP loopback)",
            _TCP_FALLBACK_HOST,
            _TCP_FALLBACK_PORT,
        )

        try:
            while not shutdown_event.is_set():
                await asyncio.sleep(0.5)
        finally:
            server.close()
            await server.wait_closed()
            port_file.unlink(missing_ok=True)
            logger.info("IPC server stopped")

    def store_credential(self, key: str, value: str) -> bool:
        target = f"{_CREDENTIAL_TARGET_PREFIX}{key}"
        try:
            # Use cmdkey to store in Windows Credential Manager
            result = subprocess.run(
                ["cmdkey", f"/generic:{target}", f"/user:KMFlowAgent", f"/pass:{value}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Failed to store credential via cmdkey for key=%s", key)
            return False

    def get_credential(self, key: str) -> str | None:
        target = f"{_CREDENTIAL_TARGET_PREFIX}{key}"
        try:
            # cmdkey /list doesn't expose passwords, so we use DPAPI file fallback
            # For a real implementation, use ctypes to call CredRead from advapi32.dll
            cred_file = self.get_data_dir() / "credentials" / f"{key}.dpapi"
            if cred_file.exists():
                encrypted = cred_file.read_bytes()
                return self._dpapi_unprotect(encrypted)
        except Exception:
            logger.debug("Credential read failed for key=%s", key)
        return None

    def delete_credential(self, key: str) -> None:
        target = f"{_CREDENTIAL_TARGET_PREFIX}{key}"
        try:
            subprocess.run(
                ["cmdkey", f"/delete:{target}"],
                capture_output=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Also remove DPAPI file if present
        cred_file = self.get_data_dir() / "credentials" / f"{key}.dpapi"
        cred_file.unlink(missing_ok=True)

    def set_owner_only_permissions(self, path: Path) -> None:
        """Set NTFS ACL to owner-only using icacls."""
        try:
            # Remove inherited permissions and grant only the current user
            username = os.environ.get("USERNAME", "")
            if username:
                subprocess.run(
                    ["icacls", str(path), "/inheritance:r",
                     "/grant:r", f"{username}:(F)"],
                    capture_output=True,
                    timeout=10,
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Failed to set owner-only permissions on %s", path)

    def get_encryption_key(self, data_dir: Path) -> bytes:
        # Try environment variable first (CI/testing)
        env_key = os.environ.get("KMFLOW_BUFFER_KEY")
        if env_key:
            return env_key.encode("utf-8")[:32].ljust(32, b"\0")

        # Try DPAPI-encrypted key file
        key_file = data_dir / ".buffer_key.dpapi"
        if key_file.exists():
            try:
                encrypted = key_file.read_bytes()
                decrypted = self._dpapi_unprotect(encrypted)
                if decrypted:
                    return base64.b64decode(decrypted)[:32]
            except Exception:
                logger.warning("Failed to decrypt buffer key, generating new one")

        # Generate new key and store with DPAPI
        key = os.urandom(32)
        encoded = base64.b64encode(key).decode("ascii")
        data_dir.mkdir(parents=True, exist_ok=True)

        encrypted = self._dpapi_protect(encoded)
        if encrypted:
            key_file.write_bytes(encrypted)
            self.set_owner_only_permissions(key_file)
            logger.info("Generated new buffer encryption key (DPAPI-protected)")
        else:
            # Fallback: plain file (CI environments without DPAPI)
            plain_file = data_dir / ".buffer_key"
            plain_file.write_bytes(key)
            self.set_owner_only_permissions(plain_file)
            logger.warning("DPAPI unavailable, stored buffer key in plain file")

        return key

    # -- DPAPI helpers via ctypes --

    @staticmethod
    def _dpapi_protect(plaintext: str) -> bytes | None:
        """Encrypt a string using Windows DPAPI (current user scope)."""
        try:
            from ctypes import wintypes

            crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

            data = plaintext.encode("utf-8")
            input_blob = DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
            output_blob = DATA_BLOB()

            if crypt32.CryptProtectData(
                ctypes.byref(input_blob), None, None, None, None, 0,
                ctypes.byref(output_blob),
            ):
                result = ctypes.string_at(output_blob.pbData, output_blob.cbData)
                ctypes.windll.kernel32.LocalFree(output_blob.pbData)  # type: ignore[attr-defined]
                return result
        except Exception:
            pass
        return None

    @staticmethod
    def _dpapi_unprotect(encrypted: bytes) -> str | None:
        """Decrypt DPAPI-protected data (current user scope)."""
        try:
            from ctypes import wintypes

            crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]

            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

            input_blob = DATA_BLOB(len(encrypted), ctypes.create_string_buffer(encrypted, len(encrypted)))
            output_blob = DATA_BLOB()

            if crypt32.CryptUnprotectData(
                ctypes.byref(input_blob), None, None, None, None, 0,
                ctypes.byref(output_blob),
            ):
                result = ctypes.string_at(output_blob.pbData, output_blob.cbData).decode("utf-8")
                ctypes.windll.kernel32.LocalFree(output_blob.pbData)  # type: ignore[attr-defined]
                return result
        except Exception:
            pass
        return None
