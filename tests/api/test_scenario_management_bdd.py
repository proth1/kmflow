"""BDD tests for Story #373: Scenario Definition and Management.

Covers all 4 acceptance scenarios:
1. Scenario creation with status=DRAFT
2. Modification storage and retrieval
3. Maximum 5 scenario enforcement
4. Scenario listing with modification_count
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.routes.scenarios import (
    MAX_SCENARIOS_PER_ENGAGEMENT,
    _modification_to_detail,
    _scenario_to_summary,
)
from src.api.schemas.scenarios import ScenarioStatus
from src.core.models import ModificationType, ScenarioModification, SimulationScenario, SimulationType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scenario(
    *,
    engagement_id: str | None = None,
    name: str = "Test Scenario",
    status: str = "draft",
    scenario_id: str | None = None,
) -> MagicMock:
    """Create a mock SimulationScenario."""
    mock = MagicMock(spec=SimulationScenario)
    mock.id = uuid.UUID(scenario_id) if scenario_id else uuid.uuid4()
    mock.engagement_id = uuid.UUID(engagement_id) if engagement_id else uuid.uuid4()
    mock.name = name
    mock.description = "A test scenario"
    mock.status = status
    mock.simulation_type = SimulationType.PROCESS_CHANGE
    mock.created_at = datetime(2026, 2, 27, tzinfo=UTC)
    return mock


def _make_modification(
    *,
    scenario_id: uuid.UUID | None = None,
    mod_type: ModificationType = ModificationType.TASK_REMOVE,
    element_id: str = "task_001",
) -> MagicMock:
    """Create a mock ScenarioModification."""
    mock = MagicMock(spec=ScenarioModification)
    mock.id = uuid.uuid4()
    mock.scenario_id = scenario_id or uuid.uuid4()
    mock.modification_type = mod_type
    mock.element_id = element_id
    mock.element_name = element_id
    mock.change_data = {"reason": "redundant step"}
    mock.applied_at = datetime(2026, 2, 27, tzinfo=UTC)
    return mock


# ===========================================================================
# Scenario 1: Scenario Creation
# ===========================================================================


class TestScenarioCreation:
    """Given an engagement with an active POV."""

    def test_scenario_to_summary_has_required_fields(self) -> None:
        """When a scenario is serialized, it includes id, name, status, modification_count."""
        scenario = _make_scenario()
        result = _scenario_to_summary(scenario, mod_count=0)

        assert result["id"] == str(scenario.id)
        assert result["engagement_id"] == str(scenario.engagement_id)
        assert result["name"] == "Test Scenario"
        assert result["status"] == "draft"
        assert result["modification_count"] == 0
        assert "created_at" in result

    def test_new_scenario_status_is_draft(self) -> None:
        """When a scenario is created, its status is DRAFT."""
        scenario = _make_scenario(status="draft")
        result = _scenario_to_summary(scenario, mod_count=0)
        assert result["status"] == "draft"

    def test_scenario_status_enum_values(self) -> None:
        """ScenarioStatus enum has expected values."""
        assert ScenarioStatus.DRAFT == "draft"
        assert ScenarioStatus.SIMULATED == "simulated"
        assert ScenarioStatus.ARCHIVED == "archived"

    def test_scenario_linked_to_engagement(self) -> None:
        """The scenario is linked to the engagement."""
        eng_id = str(uuid.uuid4())
        scenario = _make_scenario(engagement_id=eng_id)
        result = _scenario_to_summary(scenario, mod_count=0)
        assert result["engagement_id"] == eng_id


# ===========================================================================
# Scenario 2: Modification Storage
# ===========================================================================


class TestModificationStorage:
    """Given a scenario in DRAFT status."""

    def test_modification_serialization(self) -> None:
        """Modifications are serialized with type, element_id, and payload."""
        sid = uuid.uuid4()
        mod = _make_modification(scenario_id=sid, mod_type=ModificationType.TASK_REMOVE)
        result = _modification_to_detail(mod)

        assert result["scenario_id"] == str(sid)
        assert result["modification_type"] == "task_remove"
        assert result["element_id"] == "task_001"
        assert result["payload"] == {"reason": "redundant step"}
        assert "applied_at" in result

    def test_role_reassignment_modification(self) -> None:
        """A role reassignment modification is stored correctly."""
        mod = _make_modification(mod_type=ModificationType.ROLE_REASSIGN, element_id="act_review")
        mod.change_data = {"from_role": "Analyst", "to_role": "Senior Analyst"}
        result = _modification_to_detail(mod)

        assert result["modification_type"] == "role_reassign"
        assert result["payload"]["from_role"] == "Analyst"

    def test_multiple_modification_types(self) -> None:
        """Different modification types are supported."""
        types = [
            ModificationType.TASK_ADD,
            ModificationType.TASK_REMOVE,
            ModificationType.ROLE_REASSIGN,
            ModificationType.GATEWAY_RESTRUCTURE,
            ModificationType.CONTROL_ADD,
            ModificationType.CONTROL_REMOVE,
        ]
        for mt in types:
            mod = _make_modification(mod_type=mt)
            result = _modification_to_detail(mod)
            assert result["modification_type"] == mt.value


# ===========================================================================
# Scenario 3: Maximum Scenario Enforcement
# ===========================================================================


class TestMaxScenarioEnforcement:
    """Given an engagement that already has scenarios."""

    def test_max_limit_constant(self) -> None:
        """MAX_SCENARIOS_PER_ENGAGEMENT is 5."""
        assert MAX_SCENARIOS_PER_ENGAGEMENT == 5

    @pytest.mark.asyncio
    async def test_fifth_scenario_allowed(self) -> None:
        """5th scenario is allowed (count=4 before insert)."""
        from src.api.routes.scenarios import create_scenario
        from src.api.schemas.scenarios import ScenarioCreatePayload

        eng_id = uuid.uuid4()
        payload = ScenarioCreatePayload(
            engagement_id=eng_id,
            name="Scenario 5",
        )

        # Mock session: count returns 4 (room for one more)
        mock_session = AsyncMock()
        count_mock = MagicMock()
        count_mock.scalar.return_value = 4

        new_scenario = _make_scenario(engagement_id=str(eng_id), name="Scenario 5")

        mock_session.execute.side_effect = [
            count_mock,  # count query
        ]
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock(side_effect=lambda s: setattr(s, "id", new_scenario.id))

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        with patch("src.api.routes.scenarios.log_audit", new_callable=AsyncMock):
            result = await create_scenario(
                payload=payload,
                session=mock_session,
                user=mock_user,
            )

        assert result["name"] == "Scenario 5"
        assert result["status"] == "draft"

    @pytest.mark.asyncio
    async def test_sixth_scenario_rejected(self) -> None:
        """6th scenario returns HTTP 422."""
        from src.api.routes.scenarios import create_scenario
        from src.api.schemas.scenarios import ScenarioCreatePayload

        eng_id = uuid.uuid4()
        payload = ScenarioCreatePayload(
            engagement_id=eng_id,
            name="Scenario 6",
        )

        mock_session = AsyncMock()
        count_mock = MagicMock()
        count_mock.scalar.return_value = 5  # Already at max

        mock_session.execute.return_value = count_mock

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        with pytest.raises(Exception) as exc_info:
            await create_scenario(
                payload=payload,
                session=mock_session,
                user=mock_user,
            )

        assert exc_info.value.status_code == 422
        assert "Maximum of 5 scenarios per engagement reached" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_first_scenario_allowed(self) -> None:
        """First scenario (count=0) is allowed."""
        from src.api.routes.scenarios import create_scenario
        from src.api.schemas.scenarios import ScenarioCreatePayload

        eng_id = uuid.uuid4()
        payload = ScenarioCreatePayload(
            engagement_id=eng_id,
            name="First Scenario",
        )

        mock_session = AsyncMock()
        count_mock = MagicMock()
        count_mock.scalar.return_value = 0

        mock_session.execute.return_value = count_mock
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        with patch("src.api.routes.scenarios.log_audit", new_callable=AsyncMock):
            result = await create_scenario(
                payload=payload,
                session=mock_session,
                user=mock_user,
            )

        assert result["status"] == "draft"
        mock_session.add.assert_called_once()


# ===========================================================================
# Scenario 4: Scenario Listing
# ===========================================================================


class TestScenarioListing:
    """Given an engagement with scenarios in various statuses."""

    def test_summary_includes_modification_count(self) -> None:
        """Each entry includes modification_count."""
        scenario = _make_scenario(name="Scenario A")
        result = _scenario_to_summary(scenario, mod_count=3)
        assert result["modification_count"] == 3

    def test_summary_includes_all_required_fields(self) -> None:
        """Each entry includes id, name, status, modification_count, created_at."""
        scenario = _make_scenario(name="My Scenario", status="simulated")
        result = _scenario_to_summary(scenario, mod_count=2)

        assert "id" in result
        assert result["name"] == "My Scenario"
        assert result["status"] == "simulated"
        assert result["modification_count"] == 2
        assert "created_at" in result

    def test_zero_modification_count(self) -> None:
        """A scenario with no modifications has modification_count=0."""
        scenario = _make_scenario()
        result = _scenario_to_summary(scenario, mod_count=0)
        assert result["modification_count"] == 0


# ===========================================================================
# Additional Tests: Route Structure and Edge Cases
# ===========================================================================


class TestRouteStructure:
    """Verify route configuration and schemas."""

    def test_router_prefix(self) -> None:
        """Router uses /api/v1/scenarios prefix."""
        from src.api.routes.scenarios import router

        assert router.prefix == "/api/v1/scenarios"

    def test_router_has_expected_routes(self) -> None:
        """Router has CRUD routes for scenarios and modifications."""
        from src.api.routes.scenarios import router

        paths = [r.path for r in router.routes]
        prefix = "/api/v1/scenarios"
        assert f"{prefix}" in paths  # POST /scenarios, GET /scenarios
        assert f"{prefix}/{{scenario_id}}" in paths  # GET /scenarios/{id}
        assert f"{prefix}/{{scenario_id}}/modifications" in paths  # POST, GET mods
        assert f"{prefix}/{{scenario_id}}/modifications/{{modification_id}}" in paths  # DELETE

    def test_scenario_status_values_complete(self) -> None:
        """ScenarioStatus has exactly 3 values."""
        values = list(ScenarioStatus)
        assert len(values) == 3
        assert set(v.value for v in values) == {"draft", "simulated", "archived"}


class TestModificationDraftEnforcement:
    """Modifications can only be added to DRAFT scenarios."""

    @pytest.mark.asyncio
    async def test_modification_on_non_draft_rejected(self) -> None:
        """Adding a modification to a non-DRAFT scenario raises 422."""
        from src.api.routes.scenarios import add_modification
        from src.api.schemas.scenarios import ModificationCreatePayload

        sid = uuid.uuid4()
        payload = ModificationCreatePayload(
            modification_type=ModificationType.TASK_REMOVE,
            element_id="task_001",
            payload={"reason": "test"},
        )

        # Mock scenario with status=simulated
        scenario = _make_scenario(scenario_id=str(sid), status="simulated")

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = scenario
        mock_session.execute.return_value = result_mock

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        with pytest.raises(Exception) as exc_info:
            await add_modification(
                scenario_id=sid,
                payload=payload,
                session=mock_session,
                user=mock_user,
            )

        assert exc_info.value.status_code == 422
        assert "DRAFT" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_modification_on_draft_allowed(self) -> None:
        """Adding a modification to a DRAFT scenario succeeds."""
        from src.api.routes.scenarios import add_modification
        from src.api.schemas.scenarios import ModificationCreatePayload

        sid = uuid.uuid4()
        payload = ModificationCreatePayload(
            modification_type=ModificationType.TASK_REMOVE,
            element_id="task_001",
            payload={"reason": "test"},
        )

        scenario = _make_scenario(scenario_id=str(sid), status="draft")

        mock_session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = scenario
        mock_session.execute.return_value = result_mock
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()

        with patch("src.api.routes.scenarios.log_audit", new_callable=AsyncMock):
            result = await add_modification(
                scenario_id=sid,
                payload=payload,
                session=mock_session,
                user=mock_user,
            )

        assert result["modification_type"] == "task_remove"
        mock_session.add.assert_called_once()
