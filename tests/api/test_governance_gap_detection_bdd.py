"""BDD tests for Story #340 — Gap Detection for Ungoverned Processes.

Scenario 1: Financial Transaction Activities Flagged as Ungoverned
Scenario 2: Gap Detection Clears on Full Governance Coverage
Scenario 3: Gap list endpoint with status filtering
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import create_app
from src.core.auth import get_current_user
from src.core.models import (
    GovernanceGapSeverity,
    GovernanceGapStatus,
    GovernanceGapType,
    User,
    UserRole,
)
from src.governance.gap_detection import (
    GovernanceGapDetectionService,
    derive_severity,
)

ENGAGEMENT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
ACTIVITY_1 = uuid.uuid4()
ACTIVITY_2 = uuid.uuid4()
ACTIVITY_3 = uuid.uuid4()
REGULATION_ID = uuid.uuid4()


def _mock_user() -> User:
    u = MagicMock(spec=User)
    u.id = USER_ID
    u.role = UserRole.PLATFORM_ADMIN
    return u


def _make_plain_mock(**kwargs: Any) -> MagicMock:
    """Create a MagicMock that stores kwargs as regular attributes."""
    m = MagicMock()
    if "id" not in kwargs:
        m.id = uuid.uuid4()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def _make_app_with_session(mock_session: AsyncMock) -> Any:
    """Create app with overridden dependencies."""
    from src.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: mock_session
    app.dependency_overrides[get_current_user] = lambda: _mock_user()
    return app


# ---------------------------------------------------------------------------
# Unit tests for derive_severity
# ---------------------------------------------------------------------------


class TestDeriveSeverity:
    """Tests for severity derivation from regulation obligations."""

    def test_critical_with_financial_penalty(self) -> None:
        obligations = {"regulatory": True, "financial_penalty": True}
        assert derive_severity(obligations) == GovernanceGapSeverity.CRITICAL

    def test_high_regulatory_no_penalty(self) -> None:
        obligations = {"regulatory": True, "financial_penalty": False}
        assert derive_severity(obligations) == GovernanceGapSeverity.HIGH

    def test_medium_non_regulatory(self) -> None:
        obligations = {"regulatory": False, "financial_penalty": False}
        assert derive_severity(obligations) == GovernanceGapSeverity.MEDIUM

    def test_medium_when_no_obligations(self) -> None:
        assert derive_severity(None) == GovernanceGapSeverity.MEDIUM

    def test_medium_when_empty_obligations(self) -> None:
        assert derive_severity({}) == GovernanceGapSeverity.MEDIUM


# ---------------------------------------------------------------------------
# Unit tests for GovernanceGapDetectionService
# ---------------------------------------------------------------------------


class TestGapDetectionService:
    """Tests for the gap detection service."""

    @pytest.mark.asyncio
    async def test_detect_two_ungoverned_financial_activities(self) -> None:
        """Scenario 1: 4 financial activities, 2 without ENFORCED_BY → 2 gaps."""
        mock_graph = AsyncMock()

        # First call: get_regulated_activities → 4 activities
        regulated_records = [
            {
                "activity_id": str(ACTIVITY_1),
                "activity_name": "Wire Transfer",
                "activity_category": "financial_transaction",
            },
            {
                "activity_id": str(ACTIVITY_2),
                "activity_name": "Payment Processing",
                "activity_category": "financial_transaction",
            },
            {
                "activity_id": str(ACTIVITY_3),
                "activity_name": "Ledger Entry",
                "activity_category": "financial_transaction",
            },
            {
                "activity_id": str(uuid.uuid4()),
                "activity_name": "Reconciliation",
                "activity_category": "financial_transaction",
            },
        ]

        # Second call: get_ungoverned_activity_ids → 2 ungoverned
        ungoverned_records = [
            {"activity_id": str(ACTIVITY_1)},
            {"activity_id": str(ACTIVITY_2)},
        ]

        mock_graph.run_query = AsyncMock(side_effect=[regulated_records, ungoverned_records])

        service = GovernanceGapDetectionService(mock_graph)
        regulations = [
            {
                "id": str(REGULATION_ID),
                "name": "SOX",
                "obligations": {
                    "required_categories": ["financial_transaction"],
                    "regulatory": True,
                    "financial_penalty": True,
                },
            }
        ]

        gaps = await service.detect_gaps(str(ENGAGEMENT_ID), regulations)

        assert len(gaps) == 2
        assert gaps[0]["activity_id"] == str(ACTIVITY_1)
        assert gaps[0]["regulation_id"] == str(REGULATION_ID)
        assert gaps[0]["gap_type"] == GovernanceGapType.CONTROL_GAP
        assert gaps[0]["severity"] == GovernanceGapSeverity.CRITICAL
        assert gaps[1]["activity_id"] == str(ACTIVITY_2)

    @pytest.mark.asyncio
    async def test_detect_no_gaps_all_governed(self) -> None:
        """All regulated activities have controls → no gaps."""
        mock_graph = AsyncMock()

        regulated_records = [
            {"activity_id": "act1", "activity_name": "A1", "activity_category": "financial_transaction"},
        ]
        ungoverned_records: list[dict[str, Any]] = []  # All governed

        mock_graph.run_query = AsyncMock(side_effect=[regulated_records, ungoverned_records])

        service = GovernanceGapDetectionService(mock_graph)
        gaps = await service.detect_gaps(
            "eng1",
            [
                {"id": "reg1", "name": "SOX", "obligations": {"required_categories": ["financial_transaction"]}},
            ],
        )

        assert gaps == []

    @pytest.mark.asyncio
    async def test_detect_skips_regulation_without_categories(self) -> None:
        """Regulation with no required_categories → no graph queries."""
        mock_graph = AsyncMock()
        mock_graph.run_query = AsyncMock()

        service = GovernanceGapDetectionService(mock_graph)
        gaps = await service.detect_gaps(
            "eng1",
            [
                {"id": "reg1", "name": "Policy A", "obligations": {}},
            ],
        )

        assert gaps == []
        mock_graph.run_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_detect_graph_failure_returns_empty(self) -> None:
        """Graph query failure → empty gaps list (graceful degradation)."""
        mock_graph = AsyncMock()
        mock_graph.run_query = AsyncMock(side_effect=Exception("Connection refused"))

        service = GovernanceGapDetectionService(mock_graph)
        gaps = await service.detect_gaps(
            "eng1",
            [
                {"id": "reg1", "name": "SOX", "obligations": {"required_categories": ["financial_transaction"]}},
            ],
        )

        assert gaps == []

    @pytest.mark.asyncio
    async def test_resolve_covered_gaps(self) -> None:
        """Scenario 3: Previously open gap is now covered → returns its ID."""
        mock_graph = AsyncMock()

        reg_id = str(uuid.uuid4())

        # get_ungoverned_activity_ids returns only ACTIVITY_1 (ACTIVITY_2 is now covered)
        mock_graph.run_query = AsyncMock(return_value=[{"activity_id": str(ACTIVITY_1)}])

        gap1_id = str(uuid.uuid4())
        gap2_id = str(uuid.uuid4())

        service = GovernanceGapDetectionService(mock_graph)
        resolved = await service.resolve_covered_gaps(
            str(ENGAGEMENT_ID),
            [
                {"id": gap1_id, "activity_id": str(ACTIVITY_1), "regulation_id": reg_id},
                {"id": gap2_id, "activity_id": str(ACTIVITY_2), "regulation_id": reg_id},
            ],
        )

        # ACTIVITY_2 is no longer ungoverned, so gap2 should be resolved
        assert gap2_id in resolved
        assert gap1_id not in resolved

        # Verify regulation-aware query was used (regulation_id param in query params dict)
        call_args = mock_graph.run_query.call_args
        query_params = call_args[0][1]  # second positional arg is the params dict
        assert query_params["regulation_id"] == reg_id

    @pytest.mark.asyncio
    async def test_resolve_gaps_multi_regulation(self) -> None:
        """Gaps from different regulations are checked per-regulation."""
        mock_graph = AsyncMock()

        reg_a = str(uuid.uuid4())
        reg_b = str(uuid.uuid4())
        gap_a = str(uuid.uuid4())
        gap_b = str(uuid.uuid4())

        # First call (reg_a): ACTIVITY_1 still ungoverned for reg_a
        # Second call (reg_b): ACTIVITY_1 now governed for reg_b
        mock_graph.run_query = AsyncMock(
            side_effect=[
                [{"activity_id": str(ACTIVITY_1)}],  # reg_a: still ungoverned
                [],  # reg_b: governed
            ]
        )

        service = GovernanceGapDetectionService(mock_graph)
        resolved = await service.resolve_covered_gaps(
            str(ENGAGEMENT_ID),
            [
                {"id": gap_a, "activity_id": str(ACTIVITY_1), "regulation_id": reg_a},
                {"id": gap_b, "activity_id": str(ACTIVITY_1), "regulation_id": reg_b},
            ],
        )

        # gap_a stays open (still ungoverned for reg_a), gap_b resolved (governed for reg_b)
        assert gap_b in resolved
        assert gap_a not in resolved

    @pytest.mark.asyncio
    async def test_resolve_empty_gaps_list(self) -> None:
        """No existing open gaps → nothing to resolve."""
        mock_graph = AsyncMock()

        service = GovernanceGapDetectionService(mock_graph)
        resolved = await service.resolve_covered_gaps(str(ENGAGEMENT_ID), [])

        assert resolved == []


# ---------------------------------------------------------------------------
# API endpoint tests — Detect Gaps
# ---------------------------------------------------------------------------


class TestDetectGapsEndpoint:
    """POST /api/v1/governance/engagements/{id}/governance-gaps/detect"""

    @pytest.mark.asyncio
    async def test_detect_returns_201_with_findings(self) -> None:
        """Scenario 1: Returns 201 with new gap findings."""
        mock_session = AsyncMock()

        # 1. Engagement exists
        engagement = _make_plain_mock(id=ENGAGEMENT_ID)
        eng_result = MagicMock()
        eng_result.scalar_one_or_none.return_value = engagement

        # 2. Regulations for engagement
        reg = _make_plain_mock(
            id=REGULATION_ID,
            engagement_id=ENGAGEMENT_ID,
            obligations={
                "required_categories": ["financial_transaction"],
                "regulatory": True,
                "financial_penalty": True,
            },
        )
        reg.name = "SOX"
        reg_result = MagicMock()
        reg_result.scalars.return_value.all.return_value = [reg]

        # 3. Existing open gaps → empty
        existing_result = MagicMock()
        existing_result.scalars.return_value.all.return_value = []

        # 4. After commit: count open gaps
        open_count_result = MagicMock()
        open_count_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[eng_result, reg_result, existing_result, open_count_result])
        mock_session.commit = AsyncMock()

        _added_objects: list[Any] = []

        def _fake_add(obj: Any) -> None:
            _added_objects.append(obj)

        mock_session.add = _fake_add

        async def _fake_refresh(obj: Any) -> None:
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(UTC)

        mock_session.refresh = _fake_refresh

        app = _make_app_with_session(mock_session)
        app.state.neo4j_driver = MagicMock()

        mock_gap_data = [
            {
                "engagement_id": str(ENGAGEMENT_ID),
                "activity_id": str(ACTIVITY_1),
                "activity_name": "Wire Transfer",
                "regulation_id": str(REGULATION_ID),
                "regulation_name": "SOX",
                "gap_type": GovernanceGapType.CONTROL_GAP,
                "severity": GovernanceGapSeverity.CRITICAL,
                "status": GovernanceGapStatus.OPEN,
                "description": "Activity lacks controls",
            },
        ]

        with (
            mock.patch("src.api.routes.governance.GovernanceGapDetectionService") as mock_svc_cls,
            mock.patch("src.api.routes.governance.log_audit", new_callable=AsyncMock),
        ):
            mock_svc = AsyncMock()
            mock_svc.detect_gaps = AsyncMock(return_value=mock_gap_data)
            mock_svc.resolve_covered_gaps = AsyncMock(return_value=[])
            mock_svc_cls.return_value = mock_svc

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    f"/api/v1/governance/engagements/{ENGAGEMENT_ID}/governance-gaps/detect",
                    json={"auto_generate_shelf_requests": False},
                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["new_gaps"] == 1
        assert data["resolved_gaps"] == 0
        assert len(data["findings"]) == 1

    @pytest.mark.asyncio
    async def test_detect_404_engagement_not_found(self) -> None:
        """Returns 404 when engagement does not exist."""
        mock_session = AsyncMock()

        eng_result = MagicMock()
        eng_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=eng_result)

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                f"/api/v1/governance/engagements/{ENGAGEMENT_ID}/governance-gaps/detect",
                json={"auto_generate_shelf_requests": False},
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API endpoint tests — List Gaps
# ---------------------------------------------------------------------------


class TestListGapsEndpoint:
    """GET /api/v1/governance/engagements/{id}/governance-gaps"""

    @pytest.mark.asyncio
    async def test_list_open_gaps(self) -> None:
        """Returns only OPEN gaps when status filter applied."""
        mock_session = AsyncMock()

        # 1. Engagement exists
        engagement = _make_plain_mock(id=ENGAGEMENT_ID)
        eng_result = MagicMock()
        eng_result.scalar_one_or_none.return_value = engagement

        # 2. Count
        count_result = MagicMock()
        count_result.scalar.return_value = 2

        # 3. Findings
        findings = [
            _make_plain_mock(
                id=uuid.uuid4(),
                engagement_id=ENGAGEMENT_ID,
                activity_id=ACTIVITY_1,
                regulation_id=REGULATION_ID,
                gap_type=GovernanceGapType.CONTROL_GAP,
                severity=GovernanceGapSeverity.CRITICAL,
                status=GovernanceGapStatus.OPEN,
                description="Activity lacks controls",
                resolved_at=None,
                created_at=datetime.now(UTC),
            ),
            _make_plain_mock(
                id=uuid.uuid4(),
                engagement_id=ENGAGEMENT_ID,
                activity_id=ACTIVITY_2,
                regulation_id=REGULATION_ID,
                gap_type=GovernanceGapType.CONTROL_GAP,
                severity=GovernanceGapSeverity.HIGH,
                status=GovernanceGapStatus.OPEN,
                description="Activity lacks controls",
                resolved_at=None,
                created_at=datetime.now(UTC),
            ),
        ]
        findings_result = MagicMock()
        findings_result.scalars.return_value.all.return_value = findings

        mock_session.execute = AsyncMock(side_effect=[eng_result, count_result, findings_result])

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/governance/engagements/{ENGAGEMENT_ID}/governance-gaps",
                params={"status": "OPEN"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["findings"]) == 2
        assert data["findings"][0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_list_gaps_404_engagement_not_found(self) -> None:
        """Returns 404 when engagement does not exist."""
        mock_session = AsyncMock()

        eng_result = MagicMock()
        eng_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=eng_result)

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/governance/engagements/{ENGAGEMENT_ID}/governance-gaps",
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_gaps_empty(self) -> None:
        """No gaps → empty list."""
        mock_session = AsyncMock()

        engagement = _make_plain_mock(id=ENGAGEMENT_ID)
        eng_result = MagicMock()
        eng_result.scalar_one_or_none.return_value = engagement

        count_result = MagicMock()
        count_result.scalar.return_value = 0

        findings_result = MagicMock()
        findings_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(side_effect=[eng_result, count_result, findings_result])

        app = _make_app_with_session(mock_session)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.get(
                f"/api/v1/governance/engagements/{ENGAGEMENT_ID}/governance-gaps",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["findings"] == []
