"""Tests for the SQLite buffer manager."""

from __future__ import annotations

import pytest

from kmflow_agent.buffer.manager import BufferManager


@pytest.mark.asyncio
async def test_write_and_read_event(buffer_manager):
    event = {"event_type": "app_switch", "application_name": "Excel"}
    event_id = await buffer_manager.write_event(event)
    assert event_id

    pending = await buffer_manager.read_pending(limit=10)
    assert len(pending) == 1
    assert pending[0]["event_type"] == "app_switch"
    assert pending[0]["application_name"] == "Excel"
    assert "_buffer_id" in pending[0]


@pytest.mark.asyncio
async def test_mark_uploaded(buffer_manager):
    event_id = await buffer_manager.write_event({"event_type": "mouse_click"})

    pending = await buffer_manager.read_pending()
    assert len(pending) == 1

    await buffer_manager.mark_uploaded([pending[0]["_buffer_id"]])

    pending_after = await buffer_manager.read_pending()
    assert len(pending_after) == 0


@pytest.mark.asyncio
async def test_prune_uploaded(buffer_manager):
    await buffer_manager.write_event({"event_type": "test"})
    pending = await buffer_manager.read_pending()
    await buffer_manager.mark_uploaded([pending[0]["_buffer_id"]])

    deleted = await buffer_manager.prune_uploaded()
    assert deleted == 1


@pytest.mark.asyncio
async def test_count_pending(buffer_manager):
    assert await buffer_manager.count_pending() == 0

    for i in range(5):
        await buffer_manager.write_event({"event_type": f"event_{i}"})

    assert await buffer_manager.count_pending() == 5


@pytest.mark.asyncio
async def test_encryption_roundtrip(buffer_manager):
    event = {"event_type": "keyboard_action", "secret": "sensitive data"}
    await buffer_manager.write_event(event)

    pending = await buffer_manager.read_pending()
    assert pending[0]["secret"] == "sensitive data"


@pytest.mark.asyncio
async def test_close(buffer_manager):
    await buffer_manager.close()
    # Should not raise on double close
    await buffer_manager.close()


@pytest.mark.asyncio
async def test_multiple_events_ordering(buffer_manager):
    for i in range(10):
        await buffer_manager.write_event({"seq": i})

    pending = await buffer_manager.read_pending(limit=10)
    assert len(pending) == 10
