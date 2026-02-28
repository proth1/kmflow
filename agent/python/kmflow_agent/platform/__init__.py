"""Cross-platform abstraction for OS-specific operations.

Provides a unified interface for:
- Data directory paths
- IPC transport (Unix socket on macOS, named pipe on Windows)
- Credential storage (Keychain on macOS, DPAPI/Credential Manager on Windows)
- File permissions (chmod on macOS, NTFS ACL on Windows)

Usage:
    from kmflow_agent.platform import get_platform
    platform = get_platform()
    data_dir = platform.get_data_dir()
"""

from __future__ import annotations

import sys
from functools import lru_cache

from kmflow_agent.platform._base import PlatformBase

__all__ = ["PlatformBase", "get_platform"]


@lru_cache(maxsize=1)
def get_platform() -> PlatformBase:
    """Return the platform implementation for the current OS.

    Returns MacOSPlatform on darwin, WindowsPlatform on win32.
    Raises RuntimeError on unsupported platforms.
    """
    if sys.platform == "darwin":
        from kmflow_agent.platform._macos import MacOSPlatform

        return MacOSPlatform()
    elif sys.platform == "win32":
        from kmflow_agent.platform._windows import WindowsPlatform

        return WindowsPlatform()
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
