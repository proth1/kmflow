"""Shared test fixtures for the Python agent tests."""

from __future__ import annotations

import os
import tempfile

import pytest

from kmflow_agent.buffer.manager import BufferManager


@pytest.fixture
def temp_db_path(tmp_path):
    """Provide a temporary database path."""
    return str(tmp_path / "test_buffer.db")


@pytest.fixture
def encryption_key():
    """Fixed encryption key for testing."""
    return b"test-key-32-bytes-long-for-aes!!"


@pytest.fixture
def buffer_manager(temp_db_path, encryption_key):
    """Create a BufferManager with a temp database."""
    return BufferManager(db_path=temp_db_path, encryption_key=encryption_key)
