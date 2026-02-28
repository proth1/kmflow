"""Abstract base class defining the cross-platform interface.

Each platform (macOS, Windows) implements this interface with OS-specific
behavior for data storage, IPC, credentials, and file permissions.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class PlatformBase(ABC):
    """Abstract interface for platform-specific operations."""

    @abstractmethod
    def get_data_dir(self) -> Path:
        """Return the platform-appropriate data directory.

        macOS: ~/Library/Application Support/KMFlowAgent/
        Windows: %LOCALAPPDATA%\\KMFlowAgent\\
        """

    @abstractmethod
    def get_ipc_address(self) -> str:
        """Return the IPC address for the capture-to-Python transport.

        macOS: Unix socket path (~/Library/Application Support/KMFlowAgent/agent.sock)
        Windows: Named pipe name (\\\\.\\ pipe\\KMFlowAgent) or TCP loopback address
        """

    @abstractmethod
    async def create_ipc_server(
        self,
        client_handler: Any,
        shutdown_event: asyncio.Event,
    ) -> None:
        """Start the IPC server and accept connections until shutdown.

        Args:
            client_handler: Async callback(reader, writer) for each client.
            shutdown_event: Set this event to stop the server.
        """

    @abstractmethod
    def store_credential(self, key: str, value: str) -> bool:
        """Store a secret credential in the OS credential store.

        macOS: macOS Keychain via 'security' CLI
        Windows: Windows Credential Manager via 'cmdkey' or DPAPI

        Returns True on success.
        """

    @abstractmethod
    def get_credential(self, key: str) -> str | None:
        """Retrieve a credential from the OS credential store.

        Returns the secret string, or None if not found.
        """

    @abstractmethod
    def delete_credential(self, key: str) -> None:
        """Delete a credential from the OS credential store."""

    @abstractmethod
    def set_owner_only_permissions(self, path: Path) -> None:
        """Set file permissions so only the current user can access the file.

        macOS: chmod 0600
        Windows: NTFS ACL with owner SID only
        """

    @abstractmethod
    def get_encryption_key(self, data_dir: Path) -> bytes:
        """Get or generate the buffer encryption key using OS credential store.

        The key is stored in the OS credential store (Keychain/DPAPI) and
        generated on first access. Legacy file-based keys are migrated.

        Returns a 32-byte encryption key.
        """
