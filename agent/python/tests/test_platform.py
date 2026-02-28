"""Tests for the cross-platform abstraction layer."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


class TestPlatformDetection:
    """Test runtime platform detection."""

    def test_macos_platform_selected_on_darwin(self) -> None:
        with patch.object(sys, "platform", "darwin"):
            # Clear the lru_cache to force re-detection
            from kmflow_agent.platform import get_platform

            get_platform.cache_clear()
            platform = get_platform()
            assert type(platform).__name__ == "MacOSPlatform"
            get_platform.cache_clear()

    def test_unsupported_platform_raises(self) -> None:
        with patch.object(sys, "platform", "linux"):
            from kmflow_agent.platform import get_platform

            get_platform.cache_clear()
            with pytest.raises(RuntimeError, match="Unsupported platform"):
                get_platform()
            get_platform.cache_clear()


class TestMacOSPlatform:
    """Test MacOSPlatform implementation."""

    def test_data_dir_is_application_support(self) -> None:
        from kmflow_agent.platform._macos import MacOSPlatform

        platform = MacOSPlatform()
        data_dir = platform.get_data_dir()
        assert data_dir.name == "KMFlowAgent"
        assert "Application Support" in str(data_dir)

    def test_ipc_address_is_unix_socket(self) -> None:
        from kmflow_agent.platform._macos import MacOSPlatform

        platform = MacOSPlatform()
        addr = platform.get_ipc_address()
        assert addr.endswith("agent.sock")

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions not supported on Windows")
    def test_set_owner_only_permissions(self, tmp_path: Path) -> None:
        from kmflow_agent.platform._macos import MacOSPlatform

        platform = MacOSPlatform()
        test_file = tmp_path / "test.txt"
        test_file.write_text("secret")
        platform.set_owner_only_permissions(test_file)
        # Check permissions are 0o600 (owner read+write only)
        mode = test_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_get_encryption_key_from_env(self, tmp_path: Path) -> None:
        from kmflow_agent.platform._macos import MacOSPlatform

        platform = MacOSPlatform()
        with patch.dict("os.environ", {"KMFLOW_BUFFER_KEY": "test_key_for_encryption"}):
            key = platform.get_encryption_key(tmp_path)
            assert len(key) == 32
            assert key.startswith(b"test_key_for_encryption")


class TestWindowsPlatform:
    """Test WindowsPlatform implementation (runs on any OS, mocks Windows APIs)."""

    def test_data_dir_uses_localappdata(self) -> None:
        from kmflow_agent.platform._windows import WindowsPlatform

        platform = WindowsPlatform()
        with patch.dict("os.environ", {"LOCALAPPDATA": "/tmp/test_appdata"}):
            data_dir = platform.get_data_dir()
            assert data_dir == Path("/tmp/test_appdata/KMFlowAgent")

    def test_data_dir_fallback_without_env(self) -> None:
        from kmflow_agent.platform._windows import WindowsPlatform

        platform = WindowsPlatform()
        # Only clear LOCALAPPDATA; keep HOME/USERPROFILE so Path.home() works
        env_overrides = {"LOCALAPPDATA": ""}
        with patch.dict("os.environ", env_overrides):
            data_dir = platform.get_data_dir()
            assert "KMFlowAgent" in str(data_dir)

    def test_ipc_address_is_pipe_name(self) -> None:
        from kmflow_agent.platform._windows import WindowsPlatform

        platform = WindowsPlatform()
        addr = platform.get_ipc_address()
        assert "pipe" in addr
        assert "KMFlowAgent" in addr

    def test_get_encryption_key_from_env(self, tmp_path: Path) -> None:
        from kmflow_agent.platform._windows import WindowsPlatform

        platform = WindowsPlatform()
        with patch.dict("os.environ", {"KMFLOW_BUFFER_KEY": "windows_test_key_enc"}):
            key = platform.get_encryption_key(tmp_path)
            assert len(key) == 32
