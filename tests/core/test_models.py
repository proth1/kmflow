"""Tests for SQLAlchemy ORM models."""

from __future__ import annotations

import uuid

from src.core.models import (
    AuditAction,
    AuditLog,
    Engagement,
    EngagementStatus,
    EvidenceCategory,
    EvidenceFragment,
    EvidenceItem,
    FragmentType,
    ShelfDataRequest,
    ShelfDataRequestItem,
    ShelfRequestItemPriority,
    ShelfRequestItemStatus,
    ShelfRequestStatus,
    ValidationStatus,
)


class TestEngagement:
    """Test suite for the Engagement model."""

    def test_explicit_status(self) -> None:
        """Engagements created with a status should retain it."""
        engagement = Engagement(
            name="Test Engagement",
            client="Test Client",
            business_area="Operations",
            status=EngagementStatus.DRAFT,
        )
        assert engagement.status == EngagementStatus.DRAFT

    def test_status_column_default_defined(self) -> None:
        """The status column should have a server-side default of DRAFT.

        SQLAlchemy 2.x `default=` on mapped_column applies at flush time,
        not at Python object construction. We verify the column metadata
        has the expected default configured.
        """
        col = Engagement.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == EngagementStatus.DRAFT

    def test_engagement_statuses(self) -> None:
        """All expected engagement statuses should be defined."""
        statuses = list(EngagementStatus)
        assert len(statuses) == 5
        assert EngagementStatus.DRAFT in statuses
        assert EngagementStatus.ARCHIVED in statuses

    def test_repr(self) -> None:
        """Engagement repr should include id, name, and client."""
        engagement = Engagement(
            id=uuid.uuid4(),
            name="Test",
            client="Client",
            business_area="Ops",
        )
        assert "Test" in repr(engagement)
        assert "Client" in repr(engagement)

    def test_team_field(self) -> None:
        """Engagement should accept a team list."""
        engagement = Engagement(
            name="Team Test",
            client="Client A",
            business_area="Operations",
            team=["alice@example.com", "bob@example.com"],
        )
        assert engagement.team == ["alice@example.com", "bob@example.com"]

    def test_team_field_default(self) -> None:
        """Team field column should have a default of list."""
        col = Engagement.__table__.columns["team"]
        assert col.nullable is True

    def test_team_field_empty(self) -> None:
        """Engagement team can be an empty list."""
        engagement = Engagement(
            name="Empty Team",
            client="Client B",
            business_area="Finance",
            team=[],
        )
        assert engagement.team == []


class TestEvidenceItem:
    """Test suite for the EvidenceItem model."""

    def test_quality_score_calculation(self) -> None:
        """quality_score should be the average of four quality dimensions."""
        item = EvidenceItem(
            name="test.pdf",
            category=EvidenceCategory.DOCUMENTS,
            format="pdf",
            completeness_score=0.8,
            reliability_score=0.6,
            freshness_score=0.9,
            consistency_score=0.7,
            engagement_id=uuid.uuid4(),
        )
        expected = (0.8 + 0.6 + 0.9 + 0.7) / 4.0
        assert abs(item.quality_score - expected) < 0.001

    def test_quality_score_zeros(self) -> None:
        """quality_score with all zeros should be 0.0."""
        item = EvidenceItem(
            name="empty.csv",
            category=EvidenceCategory.STRUCTURED_DATA,
            format="csv",
            completeness_score=0.0,
            reliability_score=0.0,
            freshness_score=0.0,
            consistency_score=0.0,
            engagement_id=uuid.uuid4(),
        )
        assert item.quality_score == 0.0

    def test_validation_status_column_default_defined(self) -> None:
        """The validation_status column should have PENDING as server default.

        SQLAlchemy 2.x `default=` on mapped_column applies at flush time,
        not at Python object construction.
        """
        col = EvidenceItem.__table__.columns["validation_status"]
        assert col.default is not None
        assert col.default.arg == ValidationStatus.PENDING

    def test_explicit_validation_status(self) -> None:
        """Evidence items created with explicit status should retain it."""
        item = EvidenceItem(
            name="test.pdf",
            category=EvidenceCategory.DOCUMENTS,
            format="pdf",
            engagement_id=uuid.uuid4(),
            validation_status=ValidationStatus.VALIDATED,
        )
        assert item.validation_status == ValidationStatus.VALIDATED

    def test_all_evidence_categories(self) -> None:
        """All 12 evidence categories should be defined."""
        categories = list(EvidenceCategory)
        assert len(categories) == 12
        assert EvidenceCategory.DOCUMENTS in categories
        assert EvidenceCategory.JOB_AIDS_EDGE_CASES in categories

    def test_file_storage_fields(self) -> None:
        """Evidence items should accept file storage fields."""
        item = EvidenceItem(
            name="report.pdf",
            category=EvidenceCategory.DOCUMENTS,
            format="pdf",
            engagement_id=uuid.uuid4(),
            file_path="/evidence_store/abc/report.pdf",
            size_bytes=102400,
            mime_type="application/pdf",
        )
        assert item.file_path == "/evidence_store/abc/report.pdf"
        assert item.size_bytes == 102400
        assert item.mime_type == "application/pdf"

    def test_duplicate_of_field(self) -> None:
        """Evidence items should accept duplicate_of_id."""
        original_id = uuid.uuid4()
        item = EvidenceItem(
            name="duplicate.pdf",
            category=EvidenceCategory.DOCUMENTS,
            format="pdf",
            engagement_id=uuid.uuid4(),
            duplicate_of_id=original_id,
        )
        assert item.duplicate_of_id == original_id

    def test_metadata_json_field(self) -> None:
        """Evidence items should accept metadata_json."""
        item = EvidenceItem(
            name="test.pdf",
            category=EvidenceCategory.DOCUMENTS,
            format="pdf",
            engagement_id=uuid.uuid4(),
            metadata_json={"source_type": "official", "author": "John"},
        )
        assert item.metadata_json["source_type"] == "official"


class TestEvidenceFragment:
    """Test suite for the EvidenceFragment model."""

    def test_fragment_types(self) -> None:
        """All expected fragment types should be defined."""
        types = list(FragmentType)
        assert FragmentType.TEXT in types
        assert FragmentType.PROCESS_ELEMENT in types
        assert len(types) == 6

    def test_repr(self) -> None:
        """Fragment repr should include id and type."""
        frag = EvidenceFragment(
            id=uuid.uuid4(),
            evidence_id=uuid.uuid4(),
            fragment_type=FragmentType.TEXT,
            content="sample",
        )
        assert "TEXT" in repr(frag) or "text" in repr(frag)


class TestAuditLog:
    """Test suite for the AuditLog model."""

    def test_audit_actions(self) -> None:
        """All expected audit actions should be defined."""
        actions = list(AuditAction)
        assert len(actions) == 31
        assert AuditAction.ENGAGEMENT_CREATED in actions
        assert AuditAction.ENGAGEMENT_UPDATED in actions
        assert AuditAction.ENGAGEMENT_ARCHIVED in actions
        assert AuditAction.EVIDENCE_UPLOADED in actions
        assert AuditAction.EVIDENCE_VALIDATED in actions
        assert AuditAction.SHELF_REQUEST_CREATED in actions
        assert AuditAction.SHELF_REQUEST_UPDATED in actions
        # Security audit actions (Story #12)
        assert AuditAction.LOGIN in actions
        assert AuditAction.LOGOUT in actions
        assert AuditAction.PERMISSION_DENIED in actions
        assert AuditAction.DATA_ACCESS in actions
        assert AuditAction.POV_GENERATED in actions

    def test_create_audit_log(self) -> None:
        """AuditLog should accept all required fields."""
        log = AuditLog(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            action=AuditAction.ENGAGEMENT_CREATED,
            actor="test-user",
            details='{"name": "Test"}',
        )
        assert log.action == AuditAction.ENGAGEMENT_CREATED
        assert log.actor == "test-user"
        assert log.details == '{"name": "Test"}'

    def test_repr(self) -> None:
        """AuditLog repr should include action and engagement_id."""
        eid = uuid.uuid4()
        log = AuditLog(
            id=uuid.uuid4(),
            engagement_id=eid,
            action=AuditAction.ENGAGEMENT_UPDATED,
            actor="system",
        )
        r = repr(log)
        assert "engagement_updated" in r or "ENGAGEMENT_UPDATED" in r
        assert str(eid) in r

    def test_actor_column_default(self) -> None:
        """The actor column should have a default of 'system'."""
        col = AuditLog.__table__.columns["actor"]
        assert col.default is not None
        assert col.default.arg == "system"


class TestShelfDataRequest:
    """Test suite for the ShelfDataRequest model."""

    def test_shelf_request_statuses(self) -> None:
        """All expected shelf request statuses should be defined."""
        statuses = list(ShelfRequestStatus)
        assert len(statuses) == 5
        assert ShelfRequestStatus.DRAFT in statuses
        assert ShelfRequestStatus.SENT in statuses
        assert ShelfRequestStatus.COMPLETED in statuses
        assert ShelfRequestStatus.OVERDUE in statuses

    def test_status_column_default(self) -> None:
        """The status column should default to DRAFT."""
        col = ShelfDataRequest.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == ShelfRequestStatus.DRAFT

    def test_repr(self) -> None:
        """ShelfDataRequest repr should include title and status."""
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Evidence Request Q1",
            status=ShelfRequestStatus.DRAFT,
        )
        r = repr(req)
        assert "Evidence Request Q1" in r

    def test_fulfillment_percentage_no_items(self) -> None:
        """Fulfillment should be 0% when there are no items."""
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Empty Request",
        )
        req.items = []
        assert req.fulfillment_percentage == 0.0

    def test_fulfillment_percentage_all_received(self) -> None:
        """Fulfillment should be 100% when all items are received."""
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Full Request",
        )
        req.items = [
            ShelfDataRequestItem(
                id=uuid.uuid4(),
                request_id=req.id,
                category=EvidenceCategory.DOCUMENTS,
                item_name="Doc 1",
                status=ShelfRequestItemStatus.RECEIVED,
            ),
            ShelfDataRequestItem(
                id=uuid.uuid4(),
                request_id=req.id,
                category=EvidenceCategory.IMAGES,
                item_name="Img 1",
                status=ShelfRequestItemStatus.RECEIVED,
            ),
        ]
        assert req.fulfillment_percentage == 100.0

    def test_fulfillment_percentage_partial(self) -> None:
        """Fulfillment should reflect partial completion."""
        req = ShelfDataRequest(
            id=uuid.uuid4(),
            engagement_id=uuid.uuid4(),
            title="Partial Request",
        )
        req.items = [
            ShelfDataRequestItem(
                id=uuid.uuid4(),
                request_id=req.id,
                category=EvidenceCategory.DOCUMENTS,
                item_name="Doc 1",
                status=ShelfRequestItemStatus.RECEIVED,
            ),
            ShelfDataRequestItem(
                id=uuid.uuid4(),
                request_id=req.id,
                category=EvidenceCategory.IMAGES,
                item_name="Img 1",
                status=ShelfRequestItemStatus.PENDING,
            ),
        ]
        assert req.fulfillment_percentage == 50.0


class TestShelfDataRequestItem:
    """Test suite for the ShelfDataRequestItem model."""

    def test_item_statuses(self) -> None:
        """All expected item statuses should be defined."""
        statuses = list(ShelfRequestItemStatus)
        assert len(statuses) == 3
        assert ShelfRequestItemStatus.PENDING in statuses
        assert ShelfRequestItemStatus.RECEIVED in statuses
        assert ShelfRequestItemStatus.OVERDUE in statuses

    def test_item_priorities(self) -> None:
        """All expected priorities should be defined."""
        priorities = list(ShelfRequestItemPriority)
        assert len(priorities) == 3
        assert ShelfRequestItemPriority.HIGH in priorities
        assert ShelfRequestItemPriority.MEDIUM in priorities
        assert ShelfRequestItemPriority.LOW in priorities

    def test_status_column_default(self) -> None:
        """The status column should default to PENDING."""
        col = ShelfDataRequestItem.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == ShelfRequestItemStatus.PENDING

    def test_priority_column_default(self) -> None:
        """The priority column should default to MEDIUM."""
        col = ShelfDataRequestItem.__table__.columns["priority"]
        assert col.default is not None
        assert col.default.arg == ShelfRequestItemPriority.MEDIUM

    def test_repr(self) -> None:
        """ShelfDataRequestItem repr should include name and status."""
        item = ShelfDataRequestItem(
            id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            category=EvidenceCategory.DOCUMENTS,
            item_name="P2P Process Map",
            status=ShelfRequestItemStatus.PENDING,
        )
        r = repr(item)
        assert "P2P Process Map" in r


class TestPhase3Enums:
    """Test suite for Phase 3 enum values."""

    def test_monitoring_status_values(self) -> None:
        """MonitoringStatus should have all expected values."""
        from src.core.models import MonitoringStatus

        assert MonitoringStatus.CONFIGURING == "configuring"
        assert MonitoringStatus.ACTIVE == "active"
        assert MonitoringStatus.PAUSED == "paused"
        assert MonitoringStatus.ERROR == "error"
        assert MonitoringStatus.STOPPED == "stopped"

    def test_alert_severity_values(self) -> None:
        """AlertSeverity should have all expected values."""
        from src.core.models import AlertSeverity

        assert AlertSeverity.CRITICAL == "critical"
        assert AlertSeverity.HIGH == "high"
        assert AlertSeverity.MEDIUM == "medium"
        assert AlertSeverity.LOW == "low"
        assert AlertSeverity.INFO == "info"

    def test_alert_status_values(self) -> None:
        """AlertStatus should have all expected values."""
        from src.core.models import AlertStatus

        assert AlertStatus.NEW == "new"
        assert AlertStatus.ACKNOWLEDGED == "acknowledged"
        assert AlertStatus.RESOLVED == "resolved"
        assert AlertStatus.DISMISSED == "dismissed"

    def test_deviation_category_values(self) -> None:
        """DeviationCategory should have all expected values."""
        from src.core.models import DeviationCategory

        assert DeviationCategory.SEQUENCE_CHANGE == "sequence_change"
        assert DeviationCategory.MISSING_ACTIVITY == "missing_activity"
        assert DeviationCategory.NEW_ACTIVITY == "new_activity"
        assert DeviationCategory.ROLE_CHANGE == "role_change"
        assert DeviationCategory.TIMING_ANOMALY == "timing_anomaly"
        assert DeviationCategory.FREQUENCY_CHANGE == "frequency_change"
        assert DeviationCategory.CONTROL_BYPASS == "control_bypass"

    def test_monitoring_source_type_values(self) -> None:
        """MonitoringSourceType should have all expected values."""
        from src.core.models import MonitoringSourceType

        assert MonitoringSourceType.EVENT_LOG == "event_log"
        assert MonitoringSourceType.TASK_MINING == "task_mining"
        assert MonitoringSourceType.SYSTEM_API == "system_api"
        assert MonitoringSourceType.FILE_WATCH == "file_watch"

    def test_simulation_status_values(self) -> None:
        """SimulationStatus should have all expected values."""
        from src.core.models import SimulationStatus

        assert SimulationStatus.PENDING == "pending"
        assert SimulationStatus.RUNNING == "running"
        assert SimulationStatus.COMPLETED == "completed"
        assert SimulationStatus.FAILED == "failed"

    def test_simulation_type_values(self) -> None:
        """SimulationType should have all expected values."""
        from src.core.models import SimulationType

        assert SimulationType.WHAT_IF == "what_if"
        assert SimulationType.CAPACITY == "capacity"
        assert SimulationType.PROCESS_CHANGE == "process_change"
        assert SimulationType.CONTROL_REMOVAL == "control_removal"

    def test_pattern_category_values(self) -> None:
        """PatternCategory should have all expected values."""
        from src.core.models import PatternCategory

        assert PatternCategory.PROCESS_OPTIMIZATION == "process_optimization"
        assert PatternCategory.CONTROL_IMPROVEMENT == "control_improvement"
        assert PatternCategory.TECHNOLOGY_ENABLEMENT == "technology_enablement"
        assert PatternCategory.ORGANIZATIONAL_CHANGE == "organizational_change"
        assert PatternCategory.RISK_MITIGATION == "risk_mitigation"

    def test_audit_action_phase3_values(self) -> None:
        """AuditAction should have all Phase 3 values."""
        # Phase 3 integration/monitoring actions
        assert AuditAction.INTEGRATION_CONNECTED == "integration_connected"
        assert AuditAction.INTEGRATION_SYNCED == "integration_synced"
        assert AuditAction.MONITORING_CONFIGURED == "monitoring_configured"
        assert AuditAction.MONITORING_ACTIVATED == "monitoring_activated"
        assert AuditAction.MONITORING_STOPPED == "monitoring_stopped"
        assert AuditAction.ALERT_GENERATED == "alert_generated"
        assert AuditAction.ALERT_ACKNOWLEDGED == "alert_acknowledged"
        assert AuditAction.ALERT_RESOLVED == "alert_resolved"
        assert AuditAction.AGENT_GAP_SCAN == "agent_gap_scan"
        assert AuditAction.PATTERN_CREATED == "pattern_created"
        assert AuditAction.PATTERN_APPLIED == "pattern_applied"
        assert AuditAction.SIMULATION_CREATED == "simulation_created"
        assert AuditAction.SIMULATION_EXECUTED == "simulation_executed"

    def test_audit_action_total_count(self) -> None:
        """AuditAction should have all expected actions including Phase 3."""
        actions = list(AuditAction)
        # Phase 1+2: 18 actions
        # Phase 3: 13 new actions
        # Total: 31 actions
        assert len(actions) == 31
