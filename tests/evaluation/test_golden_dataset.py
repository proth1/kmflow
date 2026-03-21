"""Tests for golden dataset CRUD functions in src.evaluation.golden_dataset.

Uses a mocked async SQLAlchemy session to avoid any real DB connections.
A temporary YAML file is created for import/export tests.
"""

from __future__ import annotations

import textwrap
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from src.core.models.pipeline_quality import GoldenEvalQuery
from src.evaluation.golden_dataset import (
    create_query,
    export_to_yaml,
    import_from_yaml,
)


def _make_session() -> AsyncMock:
    """Return a mock async session that tracks add/flush calls."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    # execute returns an empty scalar result by default
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)
    return session


class TestCreateQuery:
    @pytest.mark.asyncio
    async def test_creates_record_with_correct_fields(self) -> None:
        session = _make_session()

        record = await create_query(
            session,
            query="What is the approval SLA?",
            expected_answer="3 business days",
            expected_source_ids=["src-1", "src-2"],
            query_type="factual",
            difficulty="easy",
        )

        assert record.query == "What is the approval SLA?"
        assert record.expected_answer == "3 business days"
        assert record.expected_source_ids == ["src-1", "src-2"]
        assert record.query_type == "factual"
        assert record.difficulty == "easy"
        assert record.is_active is True
        assert record.source == "manual"
        session.add.assert_called_once_with(record)
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_record_with_optional_fields(self) -> None:
        session = _make_session()
        eid = uuid.uuid4()

        record = await create_query(
            session,
            query="How many steps?",
            expected_answer="Five steps.",
            expected_source_ids=[],
            query_type="multi-hop",
            difficulty="hard",
            engagement_id=eid,
            tags=["steps", "process"],
            source="synthetic",
        )

        assert record.engagement_id == eid
        assert record.tags == ["steps", "process"]
        assert record.source == "synthetic"

    @pytest.mark.asyncio
    async def test_record_id_is_uuid(self) -> None:
        session = _make_session()

        record = await create_query(
            session,
            query="Q",
            expected_answer="A",
            expected_source_ids=[],
            query_type="factual",
            difficulty="easy",
        )

        assert isinstance(record.id, uuid.UUID)


class TestImportFromYaml:
    @pytest.mark.asyncio
    async def test_imports_two_queries_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = textwrap.dedent("""\
            queries:
              - query: "First question?"
                expected_answer: "First answer."
                expected_source_ids:
                  - "aaaaaaaa-bbbb-cccc-dddd-000000000001"
                query_type: "factual"
                difficulty: "easy"
              - query: "Second question?"
                expected_answer: "Second answer."
                expected_source_ids: []
                query_type: "comparative"
                difficulty: "medium"
        """)
        yaml_file = tmp_path / "golden.yaml"
        yaml_file.write_text(yaml_content)

        session = _make_session()
        count = await import_from_yaml(session, yaml_file)

        assert count == 2
        # session.add should have been called once per query
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_imports_zero_queries_from_empty_list(self, tmp_path: Path) -> None:
        yaml_content = "queries: []\n"
        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text(yaml_content)

        session = _make_session()
        count = await import_from_yaml(session, yaml_file)

        assert count == 0
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_imports_with_optional_engagement_id(self, tmp_path: Path) -> None:
        eid = uuid.uuid4()
        yaml_content = textwrap.dedent(f"""\
            queries:
              - query: "Q?"
                expected_answer: "A."
                expected_source_ids: []
                query_type: "factual"
                difficulty: "easy"
                engagement_id: "{eid}"
                tags:
                  - "tag1"
                source: "synthetic"
        """)
        yaml_file = tmp_path / "with_opts.yaml"
        yaml_file.write_text(yaml_content)

        session = _make_session()
        count = await import_from_yaml(session, yaml_file)

        assert count == 1
        # Verify the created record has the engagement_id
        record: GoldenEvalQuery = session.add.call_args[0][0]
        assert record.engagement_id == eid


class TestExportToYaml:
    @pytest.mark.asyncio
    async def test_export_returns_valid_yaml_string(self) -> None:
        # Build two fake GoldenEvalQuery objects
        def _fake_record(query_text: str) -> MagicMock:
            rec = MagicMock(spec=GoldenEvalQuery)
            rec.id = uuid.uuid4()
            rec.query = query_text
            rec.expected_answer = "Some answer."
            rec.expected_source_ids = ["src-1"]
            rec.query_type = "factual"
            rec.difficulty = "easy"
            rec.source = "manual"
            rec.engagement_id = None
            rec.tags = None
            return rec

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            _fake_record("First Q?"),
            _fake_record("Second Q?"),
        ]

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        yaml_str = await export_to_yaml(session)

        # Must be parseable YAML
        parsed = yaml.safe_load(yaml_str)
        assert "queries" in parsed
        assert len(parsed["queries"]) == 2

    @pytest.mark.asyncio
    async def test_export_empty_dataset_returns_empty_queries(self) -> None:
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        yaml_str = await export_to_yaml(session)
        parsed = yaml.safe_load(yaml_str)
        assert parsed["queries"] == []

    @pytest.mark.asyncio
    async def test_export_includes_engagement_id_when_present(self) -> None:
        eid = uuid.uuid4()
        rec = MagicMock(spec=GoldenEvalQuery)
        rec.id = uuid.uuid4()
        rec.query = "Q?"
        rec.expected_answer = "A."
        rec.expected_source_ids = []
        rec.query_type = "factual"
        rec.difficulty = "easy"
        rec.source = "manual"
        rec.engagement_id = eid
        rec.tags = ["t1"]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [rec]

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        yaml_str = await export_to_yaml(session)
        parsed = yaml.safe_load(yaml_str)
        entry = parsed["queries"][0]
        assert entry["engagement_id"] == str(eid)
        assert entry["tags"] == ["t1"]
