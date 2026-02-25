"""Task mining graph ingestion: creates Application and UserAction nodes.

Transforms completed TaskMiningAction records into Neo4j knowledge graph
nodes and relationships, making observed desktop behavior first-class
evidence alongside documents and interviews.

Story #226 — Part of Epic #225 (Knowledge Graph Integration).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.taskmining import TaskMiningAction
from src.semantic.graph import KnowledgeGraphService

logger = logging.getLogger(__name__)


async def ingest_actions_to_graph(
    db_session: AsyncSession,
    graph_service: KnowledgeGraphService,
    engagement_id: str,
) -> dict[str, int]:
    """Ingest task mining actions into the knowledge graph.

    Creates Application nodes, UserAction nodes, PERFORMED_IN relationships,
    and PRECEDED_BY temporal chains. Uses MERGE-like idempotency by checking
    for existing nodes before creation.

    Args:
        db_session: Database session for reading TaskMiningAction records.
        graph_service: Neo4j knowledge graph service.
        engagement_id: Engagement to process.

    Returns:
        Summary dict with counts of created nodes and relationships.
    """
    # Fetch all actions for the engagement
    stmt = (
        select(TaskMiningAction)
        .where(TaskMiningAction.engagement_id == engagement_id)
        .order_by(TaskMiningAction.started_at.asc())
    )
    result = await db_session.execute(stmt)
    actions = list(result.scalars().all())

    if not actions:
        logger.info("No actions to ingest for engagement %s", engagement_id)
        return {"applications": 0, "user_actions": 0, "performed_in": 0, "preceded_by": 0}

    # Find existing nodes to avoid duplicates
    existing_apps = await graph_service.find_nodes(
        "Application", {"engagement_id": engagement_id}
    )
    existing_app_names = {n.properties.get("name") for n in existing_apps}

    existing_user_actions = await graph_service.find_nodes(
        "UserAction", {"engagement_id": engagement_id}
    )
    existing_action_ids = {n.properties.get("source_action_id") for n in existing_user_actions}

    # -- Application nodes ----------------------------------------------------
    unique_apps = {a.application_name for a in actions if a.application_name}
    new_apps = unique_apps - existing_app_names

    app_node_map: dict[str, str] = {}  # app_name -> node_id
    # Map existing apps
    for node in existing_apps:
        name = node.properties.get("name")
        if name:
            app_node_map[name] = node.id

    if new_apps:
        app_props_list = []
        for app_name in sorted(new_apps):
            node_id = str(uuid.uuid4())
            app_node_map[app_name] = node_id
            app_props_list.append({
                "id": node_id,
                "name": app_name,
                "engagement_id": engagement_id,
                "app_category": _detect_app_category(app_name),
                "source": "task_mining",
            })
        await graph_service.batch_create_nodes("Application", app_props_list)
        logger.info("Created %d Application nodes for engagement %s", len(new_apps), engagement_id)

    # -- UserAction nodes -----------------------------------------------------
    new_actions = [a for a in actions if str(a.id) not in existing_action_ids]

    action_node_map: dict[str, str] = {}  # action.id -> node_id
    # Map existing
    for node in existing_user_actions:
        src_id = node.properties.get("source_action_id")
        if src_id:
            action_node_map[src_id] = node.id

    if new_actions:
        ua_props_list = []
        for action in new_actions:
            node_id = str(uuid.uuid4())
            action_node_map[str(action.id)] = node_id
            ua_props_list.append({
                "id": node_id,
                "name": action.description or f"{action.category} in {action.application_name}",
                "engagement_id": engagement_id,
                "action_category": action.category,
                "duration_seconds": action.duration_seconds,
                "event_count": action.event_count,
                "source_action_id": str(action.id),
                "application_name": action.application_name or "",
                "started_at": action.started_at.isoformat() if action.started_at else "",
                "source": "task_mining",
            })
        await graph_service.batch_create_nodes("UserAction", ua_props_list)
        logger.info("Created %d UserAction nodes for engagement %s", len(new_actions), engagement_id)

    # -- PERFORMED_IN relationships -------------------------------------------
    performed_in_rels = []
    for action in new_actions:
        if action.application_name and action.application_name in app_node_map:
            ua_node_id = action_node_map.get(str(action.id))
            app_node_id = app_node_map[action.application_name]
            if ua_node_id:
                performed_in_rels.append({
                    "from_id": ua_node_id,
                    "to_id": app_node_id,
                })

    performed_in_count = 0
    if performed_in_rels:
        performed_in_count = await graph_service.batch_create_relationships(
            "PERFORMED_IN", performed_in_rels
        )

    # -- PRECEDED_BY temporal chains ------------------------------------------
    # Group new actions by session, build temporal chains
    session_actions: dict[str, list[TaskMiningAction]] = {}
    for action in new_actions:
        sid = str(action.session_id)
        session_actions.setdefault(sid, []).append(action)

    preceded_by_rels = []
    for session_id, session_acts in session_actions.items():
        sorted_acts = sorted(session_acts, key=lambda a: a.started_at)
        for i in range(1, len(sorted_acts)):
            current_id = action_node_map.get(str(sorted_acts[i].id))
            prev_id = action_node_map.get(str(sorted_acts[i - 1].id))
            if current_id and prev_id:
                preceded_by_rels.append({
                    "from_id": current_id,
                    "to_id": prev_id,
                })

    preceded_by_count = 0
    if preceded_by_rels:
        preceded_by_count = await graph_service.batch_create_relationships(
            "PRECEDED_BY", preceded_by_rels
        )

    summary = {
        "applications": len(new_apps),
        "user_actions": len(new_actions),
        "performed_in": performed_in_count,
        "preceded_by": preceded_by_count,
    }
    logger.info("Graph ingestion complete for engagement %s: %s", engagement_id, summary)
    return summary


def _detect_app_category(app_name: str) -> str:
    """Heuristic app category from name."""
    lower = app_name.lower()
    if any(kw in lower for kw in ("excel", "sheets", "calc", "numbers")):
        return "spreadsheet"
    if any(kw in lower for kw in ("chrome", "firefox", "safari", "edge", "browser")):
        return "browser"
    if any(kw in lower for kw in ("outlook", "mail", "thunderbird", "gmail")):
        return "email"
    if any(kw in lower for kw in ("slack", "teams", "zoom", "meet")):
        return "communication"
    if any(kw in lower for kw in ("word", "docs", "pages", "notepad")):
        return "document"
    if any(kw in lower for kw in ("salesforce", "dynamics", "hubspot")):
        return "crm"
    if any(kw in lower for kw in ("jira", "asana", "trello", "monday")):
        return "project_management"
    if any(kw in lower for kw in ("terminal", "iterm", "console", "powershell")):
        return "development"
    if any(kw in lower for kw in ("code", "intellij", "xcode", "pycharm", "vscode")):
        return "development"
    return "other"
