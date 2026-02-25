"""Tests for task mining graph ingestion (Story #226)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.semantic.graph import GraphNode
from src.taskmining.graph_ingest import _detect_app_category, ingest_actions_to_graph


def _make_action(
    action_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    engagement_id: str = "eng-1",
    app_name: str = "Excel",
    category: str = "data_entry",
    description: str = "Edited spreadsheet",
    started_at: datetime | None = None,
    duration_seconds: float = 30.0,
    event_count: int = 5,
) -> MagicMock:
    action = MagicMock()
    action.id = action_id or uuid.uuid4()
    action.session_id = session_id or uuid.uuid4()
    action.engagement_id = engagement_id
    action.application_name = app_name
    action.category = category
    action.description = description
    action.started_at = started_at or datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    action.duration_seconds = duration_seconds
    action.event_count = event_count
    return action


def _make_graph_node(
    node_id: str = "node-1",
    label: str = "Application",
    props: dict | None = None,
) -> GraphNode:
    return GraphNode(id=node_id, label=label, properties=props or {})


@pytest.fixture
def mock_db_session():
    session = AsyncMock()
    return session


@pytest.fixture
def mock_graph_service():
    service = AsyncMock()
    service.find_nodes = AsyncMock(return_value=[])
    service.batch_create_nodes = AsyncMock(return_value=[])
    service.batch_create_relationships = AsyncMock(return_value=0)
    return service


class TestIngestActionsToGraph:
    @pytest.mark.asyncio
    async def test_no_actions_returns_zeros(self, mock_db_session, mock_graph_service):
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        summary = await ingest_actions_to_graph(mock_db_session, mock_graph_service, "eng-1")

        assert summary == {"applications": 0, "user_actions": 0, "performed_in": 0, "preceded_by": 0}
        mock_graph_service.batch_create_nodes.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_application_nodes(self, mock_db_session, mock_graph_service):
        actions = [
            _make_action(app_name="Excel"),
            _make_action(app_name="Chrome"),
            _make_action(app_name="Excel"),  # duplicate
        ]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = actions
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        summary = await ingest_actions_to_graph(mock_db_session, mock_graph_service, "eng-1")

        assert summary["applications"] == 2
        # batch_create_nodes called for Application and UserAction
        calls = mock_graph_service.batch_create_nodes.call_args_list
        app_call = [c for c in calls if c[0][0] == "Application"]
        assert len(app_call) == 1
        app_props = app_call[0][0][1]
        app_names = {p["name"] for p in app_props}
        assert app_names == {"Chrome", "Excel"}

    @pytest.mark.asyncio
    async def test_creates_user_action_nodes(self, mock_db_session, mock_graph_service):
        a1 = _make_action(description="Edited doc")
        a2 = _make_action(description="Browsed web")
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [a1, a2]
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        summary = await ingest_actions_to_graph(mock_db_session, mock_graph_service, "eng-1")

        assert summary["user_actions"] == 2
        ua_calls = [c for c in mock_graph_service.batch_create_nodes.call_args_list if c[0][0] == "UserAction"]
        assert len(ua_calls) == 1
        assert len(ua_calls[0][0][1]) == 2

    @pytest.mark.asyncio
    async def test_creates_performed_in_relationships(self, mock_db_session, mock_graph_service):
        a1 = _make_action(app_name="Excel")
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [a1]
        mock_db_session.execute = AsyncMock(return_value=result_mock)
        mock_graph_service.batch_create_relationships = AsyncMock(return_value=1)

        summary = await ingest_actions_to_graph(mock_db_session, mock_graph_service, "eng-1")

        assert summary["performed_in"] == 1
        rel_calls = [c for c in mock_graph_service.batch_create_relationships.call_args_list if c[0][0] == "PERFORMED_IN"]
        assert len(rel_calls) == 1

    @pytest.mark.asyncio
    async def test_creates_preceded_by_chains(self, mock_db_session, mock_graph_service):
        sid = uuid.uuid4()
        a1 = _make_action(session_id=sid, started_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc))
        a2 = _make_action(session_id=sid, started_at=datetime(2026, 1, 1, 10, 5, 0, tzinfo=timezone.utc))
        a3 = _make_action(session_id=sid, started_at=datetime(2026, 1, 1, 10, 10, 0, tzinfo=timezone.utc))
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [a1, a2, a3]
        mock_db_session.execute = AsyncMock(return_value=result_mock)
        mock_graph_service.batch_create_relationships = AsyncMock(return_value=2)

        summary = await ingest_actions_to_graph(mock_db_session, mock_graph_service, "eng-1")

        assert summary["preceded_by"] == 2
        prec_calls = [c for c in mock_graph_service.batch_create_relationships.call_args_list if c[0][0] == "PRECEDED_BY"]
        assert len(prec_calls) == 1
        assert len(prec_calls[0][0][1]) == 2  # 2 PRECEDED_BY links for 3 actions

    @pytest.mark.asyncio
    async def test_idempotent_skips_existing_apps(self, mock_db_session, mock_graph_service):
        existing_app = _make_graph_node(node_id="existing-app", props={"name": "Excel"})
        mock_graph_service.find_nodes = AsyncMock(side_effect=[
            [existing_app],  # existing Application nodes
            [],              # existing UserAction nodes
        ])

        a1 = _make_action(app_name="Excel")
        a2 = _make_action(app_name="Chrome")
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [a1, a2]
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        summary = await ingest_actions_to_graph(mock_db_session, mock_graph_service, "eng-1")

        # Only Chrome should be new
        assert summary["applications"] == 1
        app_calls = [c for c in mock_graph_service.batch_create_nodes.call_args_list if c[0][0] == "Application"]
        assert len(app_calls) == 1
        assert app_calls[0][0][1][0]["name"] == "Chrome"

    @pytest.mark.asyncio
    async def test_idempotent_skips_existing_user_actions(self, mock_db_session, mock_graph_service):
        a1 = _make_action()
        existing_ua = _make_graph_node(
            node_id="existing-ua",
            label="UserAction",
            props={"source_action_id": str(a1.id)},
        )
        mock_graph_service.find_nodes = AsyncMock(side_effect=[
            [],            # existing Application nodes
            [existing_ua], # existing UserAction nodes
        ])

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [a1]
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        summary = await ingest_actions_to_graph(mock_db_session, mock_graph_service, "eng-1")

        # Action already exists, should not create
        assert summary["user_actions"] == 0

    @pytest.mark.asyncio
    async def test_action_without_app_name_skips_performed_in(self, mock_db_session, mock_graph_service):
        a1 = _make_action(app_name="")
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [a1]
        mock_db_session.execute = AsyncMock(return_value=result_mock)

        summary = await ingest_actions_to_graph(mock_db_session, mock_graph_service, "eng-1")

        assert summary["performed_in"] == 0


class TestDetectAppCategory:
    @pytest.mark.parametrize("app_name,expected", [
        ("Microsoft Excel", "spreadsheet"),
        ("Google Sheets", "spreadsheet"),
        ("Google Chrome", "browser"),
        ("Firefox", "browser"),
        ("Safari", "browser"),
        ("Microsoft Edge", "browser"),
        ("Outlook", "email"),
        ("Gmail", "email"),
        ("Thunderbird", "email"),
        ("Slack", "communication"),
        ("Microsoft Teams", "communication"),
        ("Zoom", "communication"),
        ("Microsoft Word", "document"),
        ("Google Docs", "document"),
        ("Notepad", "document"),
        ("Salesforce", "crm"),
        ("HubSpot", "crm"),
        ("Jira", "project_management"),
        ("Trello", "project_management"),
        ("Asana", "project_management"),
        ("Terminal", "development"),
        ("iTerm", "development"),
        ("VS Code", "development"),
        ("IntelliJ IDEA", "development"),
        ("PyCharm", "development"),
        ("Calculator", "spreadsheet"),  # "calc" matches spreadsheet heuristic
        ("Custom App", "other"),
    ])
    def test_categorizes_app(self, app_name: str, expected: str):
        assert _detect_app_category(app_name) == expected
