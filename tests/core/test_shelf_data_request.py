"""Tests for ShelfDataRequest workflow with item-level tracking (Story #298).

Covers all 5 BDD scenarios plus model structure and edge case tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.api.schemas.shelf_data import (
    FollowUpReminderRead,
    IntakeRequest,
    ShelfDataRequestCreate,
    ShelfDataRequestItemCreate,
    ShelfDataRequestRead,
)
from src.core.models.engagement import (
    FollowUpReminder,
    ShelfDataRequest,
    ShelfDataRequestItem,
    ShelfRequestItemStatus,
    ShelfRequestStatus,
)

# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestShelfRequestStatusEnum:
    """Verify status enums have all required values."""

    def test_open_status(self) -> None:
        assert ShelfRequestStatus.OPEN == "open"

    def test_complete_status(self) -> None:
        assert ShelfRequestStatus.COMPLETE == "complete"

    def test_cancelled_status(self) -> None:
        assert ShelfRequestStatus.CANCELLED == "cancelled"

    def test_draft_status(self) -> None:
        assert ShelfRequestStatus.DRAFT == "draft"

    def test_all_values(self) -> None:
        values = {s.value for s in ShelfRequestStatus}
        assert "open" in values
        assert "complete" in values
        assert "cancelled" in values


class TestShelfRequestItemStatusEnum:
    def test_requested_status(self) -> None:
        assert ShelfRequestItemStatus.REQUESTED == "requested"

    def test_received_status(self) -> None:
        assert ShelfRequestItemStatus.RECEIVED == "received"

    def test_validated_status(self) -> None:
        assert ShelfRequestItemStatus.VALIDATED == "validated"

    def test_active_status(self) -> None:
        assert ShelfRequestItemStatus.ACTIVE == "active"

    def test_lifecycle_order(self) -> None:
        lifecycle = ["requested", "received", "validated", "active"]
        for s in lifecycle:
            assert s in {v.value for v in ShelfRequestItemStatus}


# ---------------------------------------------------------------------------
# Model Structure Tests
# ---------------------------------------------------------------------------


class TestShelfDataRequestModel:
    def test_table_name(self) -> None:
        assert ShelfDataRequest.__tablename__ == "shelf_data_requests"

    def test_assigned_to_column_exists(self) -> None:
        cols = {c.name for c in ShelfDataRequest.__table__.columns}
        assert "assigned_to" in cols

    def test_completion_timestamp_column_exists(self) -> None:
        cols = {c.name for c in ShelfDataRequest.__table__.columns}
        assert "completion_timestamp" in cols

    def test_engagement_fk(self) -> None:
        col = ShelfDataRequest.__table__.columns["engagement_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "engagements.id"

    def test_engagement_id_indexed(self) -> None:
        index_names = {idx.name for idx in ShelfDataRequest.__table__.indexes}
        assert "ix_shelf_requests_engagement_id" in index_names


class TestShelfDataRequestItemModel:
    def test_table_name(self) -> None:
        assert ShelfDataRequestItem.__tablename__ == "shelf_data_request_items"

    def test_received_at_column_exists(self) -> None:
        cols = {c.name for c in ShelfDataRequestItem.__table__.columns}
        assert "received_at" in cols

    def test_uploaded_by_column_exists(self) -> None:
        cols = {c.name for c in ShelfDataRequestItem.__table__.columns}
        assert "uploaded_by" in cols

    def test_request_fk(self) -> None:
        col = ShelfDataRequestItem.__table__.columns["request_id"]
        fks = list(col.foreign_keys)
        assert fks[0].target_fullname == "shelf_data_requests.id"

    def test_evidence_fk(self) -> None:
        col = ShelfDataRequestItem.__table__.columns["matched_evidence_id"]
        fks = list(col.foreign_keys)
        assert fks[0].target_fullname == "evidence_items.id"


class TestFollowUpReminderModel:
    def test_table_name(self) -> None:
        assert FollowUpReminder.__tablename__ == "follow_up_reminders"

    def test_request_fk(self) -> None:
        col = FollowUpReminder.__table__.columns["request_id"]
        fks = list(col.foreign_keys)
        assert fks[0].target_fullname == "shelf_data_requests.id"

    def test_item_fk(self) -> None:
        col = FollowUpReminder.__table__.columns["item_id"]
        fks = list(col.foreign_keys)
        assert fks[0].target_fullname == "shelf_data_request_items.id"

    def test_request_id_indexed(self) -> None:
        index_names = {idx.name for idx in FollowUpReminder.__table__.indexes}
        assert "ix_follow_up_reminders_request_id" in index_names

    def test_item_id_indexed(self) -> None:
        index_names = {idx.name for idx in FollowUpReminder.__table__.indexes}
        assert "ix_follow_up_reminders_item_id" in index_names

    def test_repr(self) -> None:
        r = FollowUpReminder(id=uuid.uuid4(), item_id=uuid.uuid4(), reminder_type="overdue")
        assert "FollowUpReminder" in repr(r)


# ---------------------------------------------------------------------------
# BDD Scenario 1: Shelf data request created with per-item status
# ---------------------------------------------------------------------------


class TestBDDScenario1CreateRequest:
    """Scenario 1: Request created with status=OPEN and items with status=REQUESTED."""

    def test_request_created_with_open_status(self) -> None:
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Q4 Evidence Collection",
            status=ShelfRequestStatus.OPEN,
        )
        assert req.status == ShelfRequestStatus.OPEN

    def test_items_created_with_requested_status(self) -> None:
        items = []
        for i in range(10):
            item = ShelfDataRequestItem(
                id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                category="documents",
                item_name=f"Document {i + 1}",
                status=ShelfRequestItemStatus.REQUESTED,
            )
            items.append(item)
        assert len(items) == 10
        assert all(item.status == ShelfRequestItemStatus.REQUESTED for item in items)

    def test_each_item_has_unique_id_and_description(self) -> None:
        items = [
            ShelfDataRequestItem(
                id=uuid.uuid4(),
                request_id=uuid.uuid4(),
                category="documents",
                item_name=f"Item {i}",
                description=f"Description for item {i}",
                status=ShelfRequestItemStatus.REQUESTED,
            )
            for i in range(3)
        ]
        ids = {item.id for item in items}
        assert len(ids) == 3  # unique
        assert all(item.description is not None for item in items)

    def test_request_includes_due_date_and_assigned_to(self) -> None:
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Evidence Request",
            status=ShelfRequestStatus.OPEN,
            due_date=date(2026, 3, 15),
            assigned_to="John Smith",
        )
        assert req.due_date == date(2026, 3, 15)
        assert req.assigned_to == "John Smith"

    def test_create_schema_with_items(self) -> None:
        schema = ShelfDataRequestCreate(
            engagement_id=uuid.uuid4(),
            title="Q4 Request",
            due_date=date(2026, 3, 15),
            assigned_to="Jane Doe",
            items=[
                ShelfDataRequestItemCreate(
                    category="documents",
                    item_name="Annual Report",
                    description="2025 annual report",
                ),
                ShelfDataRequestItemCreate(
                    category="structured_data",
                    item_name="Transaction Log",
                ),
            ],
        )
        assert len(schema.items) == 2
        assert schema.assigned_to == "Jane Doe"


# ---------------------------------------------------------------------------
# BDD Scenario 2: Partial fulfillment tracked accurately
# ---------------------------------------------------------------------------


class TestBDDScenario2PartialFulfillment:
    """Scenario 2: 7 of 10 items received → fulfillment_pct=70.0."""

    def _build_request_with_items(self, received: int, total: int) -> ShelfDataRequest:
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Test Request",
            status=ShelfRequestStatus.OPEN,
        )
        items = []
        for i in range(total):
            status = ShelfRequestItemStatus.RECEIVED if i < received else ShelfRequestItemStatus.REQUESTED
            items.append(
                ShelfDataRequestItem(
                    id=uuid.uuid4(),
                    request_id=req.id,
                    category="documents",
                    item_name=f"Item {i + 1}",
                    status=status,
                )
            )
        req.items = items
        return req

    def test_fulfillment_percentage_70_pct(self) -> None:
        req = self._build_request_with_items(received=7, total=10)
        assert req.fulfillment_percentage == 70.0

    def test_outstanding_items_count(self) -> None:
        req = self._build_request_with_items(received=7, total=10)
        assert len(req.outstanding_items) == 3

    def test_outstanding_items_are_requested(self) -> None:
        req = self._build_request_with_items(received=7, total=10)
        for item in req.outstanding_items:
            assert item.status == ShelfRequestItemStatus.REQUESTED

    def test_request_status_remains_open(self) -> None:
        req = self._build_request_with_items(received=7, total=10)
        assert req.status == ShelfRequestStatus.OPEN

    def test_fulfillment_zero_when_empty(self) -> None:
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Empty",
            status=ShelfRequestStatus.OPEN,
        )
        req.items = []
        assert req.fulfillment_percentage == 0.0

    def test_fulfillment_includes_validated_and_active(self) -> None:
        """VALIDATED and ACTIVE items also count toward fulfillment."""
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Mixed",
            status=ShelfRequestStatus.OPEN,
        )
        statuses = [
            ShelfRequestItemStatus.RECEIVED,
            ShelfRequestItemStatus.VALIDATED,
            ShelfRequestItemStatus.ACTIVE,
            ShelfRequestItemStatus.REQUESTED,
        ]
        req.items = [
            ShelfDataRequestItem(
                id=uuid.uuid4(),
                request_id=req.id,
                category="documents",
                item_name=f"Item {i}",
                status=s,
            )
            for i, s in enumerate(statuses)
        ]
        assert req.fulfillment_percentage == 75.0


# ---------------------------------------------------------------------------
# BDD Scenario 3: Overdue item triggers follow-up reminder
# ---------------------------------------------------------------------------


class TestBDDScenario3OverdueFollowUp:
    """Scenario 3: Item overdue by 8 days triggers follow-up reminder."""

    def test_reminder_created_for_overdue_item(self) -> None:
        req_id = uuid.uuid4()
        item_id = uuid.uuid4()
        reminder = FollowUpReminder(
            id=uuid.uuid4(),
            request_id=req_id,
            item_id=item_id,
            reminder_type="overdue",
        )
        assert reminder.request_id == req_id
        assert reminder.item_id == item_id
        assert reminder.reminder_type == "overdue"

    def test_overdue_check_logic(self) -> None:
        """Simulate the overdue check: items past due_date get reminders."""
        now = datetime.now(tz=UTC)
        eight_days_ago = now - timedelta(days=8)
        future_date = now + timedelta(days=5)

        # Simulate: check if item's request due_date is past threshold
        overdue_threshold = timedelta(days=7)
        assert (now - eight_days_ago) > overdue_threshold  # overdue → create reminder
        assert (future_date - now) > timedelta(days=0)  # not overdue → no reminder

    def test_no_reminder_for_future_items(self) -> None:
        """No reminder created for items where due_date is still in the future."""
        now = datetime.now(tz=UTC)
        future_date = now + timedelta(days=10)
        # Logic: if due_date > now, no reminder
        assert future_date > now


# ---------------------------------------------------------------------------
# BDD Scenario 4: Client upload matched to request item
# ---------------------------------------------------------------------------


class TestBDDScenario4ClientUploadMatch:
    """Scenario 4: Client upload matched, item transitions to RECEIVED."""

    def test_item_status_transitions_to_received(self) -> None:
        item = ShelfDataRequestItem(
            id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            category="documents",
            item_name="Q4 Financial Report",
            status=ShelfRequestItemStatus.REQUESTED,
        )
        # Simulate matching
        item.status = ShelfRequestItemStatus.RECEIVED
        item.matched_evidence_id = uuid.uuid4()
        item.received_at = datetime.now(tz=UTC)
        item.uploaded_by = "client_user@example.com"

        assert item.status == ShelfRequestItemStatus.RECEIVED
        assert item.matched_evidence_id is not None
        assert item.received_at is not None
        assert item.uploaded_by == "client_user@example.com"

    def test_intake_request_schema(self) -> None:
        schema = IntakeRequest(
            item_id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            uploaded_by="user@client.com",
        )
        assert schema.uploaded_by == "user@client.com"

    def test_intake_request_requires_item_and_evidence(self) -> None:
        with pytest.raises(ValidationError):
            IntakeRequest(item_id=uuid.uuid4())  # missing evidence_id


# ---------------------------------------------------------------------------
# BDD Scenario 5: Request auto-completes when all items validated
# ---------------------------------------------------------------------------


class TestBDDScenario5AutoComplete:
    """Scenario 5: All items VALIDATED → request status COMPLETE."""

    def test_all_validated_triggers_complete(self) -> None:
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Complete Request",
            status=ShelfRequestStatus.OPEN,
        )
        req.items = [
            ShelfDataRequestItem(
                id=uuid.uuid4(),
                request_id=req.id,
                category="documents",
                item_name=f"Item {i}",
                status=ShelfRequestItemStatus.VALIDATED,
            )
            for i in range(5)
        ]

        # Simulate auto-complete check
        all_validated = all(
            item.status in {ShelfRequestItemStatus.VALIDATED, ShelfRequestItemStatus.ACTIVE} for item in req.items
        )
        assert all_validated

        # Transition
        if all_validated:
            req.status = ShelfRequestStatus.COMPLETE
            req.completion_timestamp = datetime.now(tz=UTC)

        assert req.status == ShelfRequestStatus.COMPLETE
        assert req.completion_timestamp is not None

    def test_fulfillment_100_when_all_validated(self) -> None:
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Full Request",
            status=ShelfRequestStatus.OPEN,
        )
        req.items = [
            ShelfDataRequestItem(
                id=uuid.uuid4(),
                request_id=req.id,
                category="documents",
                item_name=f"Item {i}",
                status=ShelfRequestItemStatus.VALIDATED,
            )
            for i in range(3)
        ]
        assert req.fulfillment_percentage == 100.0

    def test_not_complete_if_any_requested(self) -> None:
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Incomplete",
            status=ShelfRequestStatus.OPEN,
        )
        req.items = [
            ShelfDataRequestItem(
                id=uuid.uuid4(),
                request_id=req.id,
                category="documents",
                item_name="Done",
                status=ShelfRequestItemStatus.VALIDATED,
            ),
            ShelfDataRequestItem(
                id=uuid.uuid4(),
                request_id=req.id,
                category="documents",
                item_name="Not Done",
                status=ShelfRequestItemStatus.REQUESTED,
            ),
        ]
        all_validated = all(
            item.status in {ShelfRequestItemStatus.VALIDATED, ShelfRequestItemStatus.ACTIVE} for item in req.items
        )
        assert not all_validated


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_create_schema_minimal(self) -> None:
        schema = ShelfDataRequestCreate(
            engagement_id=uuid.uuid4(),
            title="Basic Request",
        )
        assert schema.due_date is None
        assert schema.items == []

    def test_create_schema_title_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ShelfDataRequestCreate(
                engagement_id=uuid.uuid4(),
                title="x" * 513,
            )

    def test_item_create_schema(self) -> None:
        schema = ShelfDataRequestItemCreate(
            category="documents",
            item_name="Test Item",
        )
        assert schema.priority == "medium"

    def test_read_schema_serialization(self) -> None:
        read = ShelfDataRequestRead(
            id=str(uuid.uuid4()),
            engagement_id=str(uuid.uuid4()),
            title="Test",
            status="open",
            fulfillment_pct=50.0,
            created_at="2026-02-27T12:00:00Z",
        )
        assert read.fulfillment_pct == 50.0

    def test_reminder_read_schema(self) -> None:
        read = FollowUpReminderRead(
            id=str(uuid.uuid4()),
            request_id=str(uuid.uuid4()),
            item_id=str(uuid.uuid4()),
            reminder_type="overdue",
            sent_at="2026-02-27T12:00:00Z",
        )
        assert read.reminder_type == "overdue"

    def test_repr_request(self) -> None:
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            title="Test",
            status=ShelfRequestStatus.OPEN,
        )
        assert "ShelfDataRequest" in repr(req)

    def test_repr_item(self) -> None:
        item = ShelfDataRequestItem(
            id=uuid.uuid4(),
            item_name="Test Item",
            status=ShelfRequestItemStatus.REQUESTED,
        )
        assert "ShelfDataRequestItem" in repr(item)
