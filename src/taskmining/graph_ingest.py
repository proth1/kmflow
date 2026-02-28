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

from src.core.models.canonical_event import CanonicalActivityEvent
from src.core.models.correlation import CaseLinkEdge
from src.core.models.taskmining import SwitchingTrace, TaskMiningAction, VisualContextEvent
from src.semantic.graph import KnowledgeGraphService
from src.taskmining.app_categories import detect_app_category as _detect_app_category

logger = logging.getLogger(__name__)

# Friction threshold above which INDICATES_FRICTION edges are created
HIGH_FRICTION_THRESHOLD = 0.6


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


async def ingest_vce_events(
    db_session: AsyncSession,
    graph_service: KnowledgeGraphService,
    engagement_id: str,
) -> dict[str, int]:
    """Ingest VisualContextEvent records into the knowledge graph.

    Creates VisualContextEvent nodes, ScreenState nodes (deduped per
    engagement), and the following relationships:
    - CLASSIFIED_AS  : VisualContextEvent → ScreenState
    - OBSERVED_DURING: VisualContextEvent → Application (existing nodes)
    - CAPTURED_IN    : VisualContextEvent → Session (if session_id set)

    Args:
        db_session: Database session for reading VisualContextEvent records.
        graph_service: Neo4j knowledge graph service.
        engagement_id: Engagement to process.

    Returns:
        Summary dict with counts of created nodes and relationships.
    """
    # Fetch all VCE records for the engagement
    stmt = (
        select(VisualContextEvent)
        .where(VisualContextEvent.engagement_id == engagement_id)
        .order_by(VisualContextEvent.timestamp.asc())
    )
    result = await db_session.execute(stmt)
    vce_events = list(result.scalars().all())

    if not vce_events:
        logger.info("No VCE events to ingest for engagement %s", engagement_id)
        return {
            "vce_nodes": 0,
            "screen_state_nodes": 0,
            "classified_as": 0,
            "observed_during": 0,
            "captured_in": 0,
        }

    # Existing VCE graph nodes
    existing_vce_nodes = await graph_service.find_nodes(
        "VisualContextEvent", {"engagement_id": engagement_id}
    )
    existing_vce_source_ids = {n.properties.get("source_vce_id") for n in existing_vce_nodes}

    # Existing ScreenState nodes (keyed by screen_state_class)
    existing_screen_states = await graph_service.find_nodes(
        "ScreenState", {"engagement_id": engagement_id}
    )
    screen_state_node_map: dict[str, str] = {}
    for node in existing_screen_states:
        cls = node.properties.get("screen_state_class")
        if cls:
            screen_state_node_map[cls] = node.id

    # Existing Application nodes
    existing_apps = await graph_service.find_nodes(
        "Application", {"engagement_id": engagement_id}
    )
    app_node_map: dict[str, str] = {
        n.properties.get("name"): n.id
        for n in existing_apps
        if n.properties.get("name")
    }

    # -- ScreenState nodes (dedup per engagement) -----------------------------
    new_screen_states: list[dict[str, Any]] = []
    for vce in vce_events:
        cls_val = str(vce.screen_state_class)
        if cls_val not in screen_state_node_map:
            node_id = str(uuid.uuid4())
            screen_state_node_map[cls_val] = node_id
            new_screen_states.append({
                "id": node_id,
                "name": cls_val,
                "engagement_id": engagement_id,
                "screen_state_class": cls_val,
                "source": "vce",
            })

    if new_screen_states:
        await graph_service.batch_create_nodes("ScreenState", new_screen_states)
        logger.info(
            "Created %d ScreenState nodes for engagement %s",
            len(new_screen_states),
            engagement_id,
        )

    # -- VisualContextEvent nodes ---------------------------------------------
    new_vce_events = [v for v in vce_events if str(v.id) not in existing_vce_source_ids]
    vce_node_map: dict[str, str] = {}

    if new_vce_events:
        vce_props_list: list[dict[str, Any]] = []
        for vce in new_vce_events:
            node_id = str(uuid.uuid4())
            vce_node_map[str(vce.id)] = node_id
            vce_props_list.append({
                "id": node_id,
                "name": f"VCE:{vce.screen_state_class}@{vce.timestamp.isoformat()}",
                "engagement_id": engagement_id,
                "screen_state_class": str(vce.screen_state_class),
                "confidence": vce.confidence,
                "trigger_reason": str(vce.trigger_reason),
                "dwell_ms": vce.dwell_ms,
                "interaction_intensity": vce.interaction_intensity,
                "application_name": vce.application_name,
                "timestamp": vce.timestamp.isoformat(),
                "source_vce_id": str(vce.id),
                "source": "vce",
            })
        await graph_service.batch_create_nodes("VisualContextEvent", vce_props_list)
        logger.info(
            "Created %d VisualContextEvent nodes for engagement %s",
            len(new_vce_events),
            engagement_id,
        )

    # -- CLASSIFIED_AS relationships (VCE → ScreenState) ----------------------
    classified_as_rels = []
    for vce in new_vce_events:
        vce_node_id = vce_node_map.get(str(vce.id))
        ss_node_id = screen_state_node_map.get(str(vce.screen_state_class))
        if vce_node_id and ss_node_id:
            classified_as_rels.append({"from_id": vce_node_id, "to_id": ss_node_id})

    classified_as_count = 0
    if classified_as_rels:
        classified_as_count = await graph_service.batch_create_relationships(
            "CLASSIFIED_AS", classified_as_rels
        )

    # -- OBSERVED_DURING relationships (VCE → Application) -------------------
    observed_during_rels = []
    for vce in new_vce_events:
        vce_node_id = vce_node_map.get(str(vce.id))
        app_node_id = app_node_map.get(vce.application_name)
        if vce_node_id and app_node_id:
            observed_during_rels.append({"from_id": vce_node_id, "to_id": app_node_id})

    observed_during_count = 0
    if observed_during_rels:
        observed_during_count = await graph_service.batch_create_relationships(
            "OBSERVED_DURING", observed_during_rels
        )

    # -- CAPTURED_IN relationships (VCE → Session) ---------------------------
    # Sessions are not graph nodes in the current ontology; we create lightweight
    # Session stub nodes keyed by session_id to hold these relationships.
    session_node_map: dict[str, str] = {}
    existing_session_nodes = await graph_service.find_nodes(
        "Session", {"engagement_id": engagement_id}
    )
    for node in existing_session_nodes:
        sid = node.properties.get("session_id")
        if sid:
            session_node_map[sid] = node.id

    new_session_stubs: list[dict[str, Any]] = []
    for vce in new_vce_events:
        if not vce.session_id:
            continue
        sid = str(vce.session_id)
        if sid not in session_node_map:
            node_id = str(uuid.uuid4())
            session_node_map[sid] = node_id
            new_session_stubs.append({
                "id": node_id,
                "name": f"Session:{sid[:8]}",
                "engagement_id": engagement_id,
                "session_id": sid,
                "source": "vce",
            })

    if new_session_stubs:
        await graph_service.batch_create_nodes("Session", new_session_stubs)

    captured_in_rels = []
    for vce in new_vce_events:
        if not vce.session_id:
            continue
        vce_node_id = vce_node_map.get(str(vce.id))
        sess_node_id = session_node_map.get(str(vce.session_id))
        if vce_node_id and sess_node_id:
            captured_in_rels.append({"from_id": vce_node_id, "to_id": sess_node_id})

    captured_in_count = 0
    if captured_in_rels:
        captured_in_count = await graph_service.batch_create_relationships(
            "CAPTURED_IN", captured_in_rels
        )

    summary = {
        "vce_nodes": len(new_vce_events),
        "screen_state_nodes": len(new_screen_states),
        "classified_as": classified_as_count,
        "observed_during": observed_during_count,
        "captured_in": captured_in_count,
    }
    logger.info("VCE graph ingestion complete for engagement %s: %s", engagement_id, summary)
    return summary


async def ingest_case_link_edges(
    db_session: AsyncSession,
    graph_service: KnowledgeGraphService,
    engagement_id: str,
) -> dict[str, int]:
    """Ingest correlation CaseLinkEdge records as CASE_HAS_EVENT relationships.

    For each CaseLinkEdge that links a canonical event to a real case (not a
    role-aggregate), this function:
    1. Ensures a Case node exists for the case_id (MERGE-like idempotency).
    2. Finds the CanonicalEvent graph node (keyed by source_event_id).
    3. Creates a CASE_HAS_EVENT relationship with method and confidence props.

    Args:
        db_session: Database session for reading CaseLinkEdge records.
        graph_service: Neo4j knowledge graph service.
        engagement_id: Engagement to process.

    Returns:
        Summary dict with case_nodes, canonical_event_nodes, case_has_event counts.
    """
    from src.taskmining.correlation.role_association import ROLE_AGGREGATE_PREFIX

    # Fetch all non-role-aggregate links for the engagement
    stmt = (
        select(CaseLinkEdge, CanonicalActivityEvent)
        .join(CanonicalActivityEvent, CaseLinkEdge.event_id == CanonicalActivityEvent.id)
        .where(
            CaseLinkEdge.engagement_id == engagement_id,
            ~CaseLinkEdge.case_id.startswith(ROLE_AGGREGATE_PREFIX),
        )
        .order_by(CaseLinkEdge.created_at.asc())
    )
    result = await db_session.execute(stmt)
    rows = list(result.all())

    if not rows:
        logger.info("No CaseLinkEdge rows to ingest for engagement %s", engagement_id)
        return {"case_nodes": 0, "case_has_event": 0}

    # Existing Case nodes
    existing_case_nodes = await graph_service.find_nodes("Case", {"engagement_id": engagement_id})
    case_node_map: dict[str, str] = {
        n.properties.get("case_id"): n.id
        for n in existing_case_nodes
        if n.properties.get("case_id")
    }

    # Existing CanonicalEvent graph nodes
    existing_ce_nodes = await graph_service.find_nodes(
        "CanonicalEvent", {"engagement_id": engagement_id}
    )
    ce_node_map: dict[str, str] = {
        n.properties.get("source_event_id"): n.id
        for n in existing_ce_nodes
        if n.properties.get("source_event_id")
    }

    # -- Create missing Case nodes --------------------------------------------
    new_case_props: list[dict[str, Any]] = []
    for link, _event in rows:
        if link.case_id not in case_node_map:
            node_id = str(uuid.uuid4())
            case_node_map[link.case_id] = node_id
            new_case_props.append({
                "id": node_id,
                "name": link.case_id,
                "engagement_id": engagement_id,
                "case_id": link.case_id,
                "source": "correlation",
            })

    new_case_props_deduped: list[dict[str, Any]] = list(
        {p["case_id"]: p for p in new_case_props}.values()
    )
    if new_case_props_deduped:
        await graph_service.batch_create_nodes("Case", new_case_props_deduped)
        logger.info(
            "Created %d Case nodes for engagement %s", len(new_case_props_deduped), engagement_id
        )

    # -- Create missing CanonicalEvent nodes ----------------------------------
    new_ce_props: list[dict[str, Any]] = []
    for link, event in rows:
        source_event_id = str(event.id)
        if source_event_id not in ce_node_map:
            node_id = str(uuid.uuid4())
            ce_node_map[source_event_id] = node_id
            new_ce_props.append({
                "id": node_id,
                "name": f"{event.activity_name}@{event.timestamp_utc.isoformat()}",
                "engagement_id": engagement_id,
                "activity_name": event.activity_name,
                "source_system": event.source_system,
                "timestamp_utc": event.timestamp_utc.isoformat(),
                "source_event_id": source_event_id,
                "source": "correlation",
            })

    new_ce_props_deduped: list[dict[str, Any]] = list(
        {p["source_event_id"]: p for p in new_ce_props}.values()
    )
    if new_ce_props_deduped:
        await graph_service.batch_create_nodes("CanonicalEvent", new_ce_props_deduped)
        logger.info(
            "Created %d CanonicalEvent nodes for engagement %s",
            len(new_ce_props_deduped),
            engagement_id,
        )

    # -- CASE_HAS_EVENT relationships ------------------------------------------
    case_has_event_rels: list[dict[str, Any]] = []
    for link, event in rows:
        case_node_id = case_node_map.get(link.case_id)
        ce_node_id = ce_node_map.get(str(event.id))
        if case_node_id and ce_node_id:
            case_has_event_rels.append({
                "from_id": case_node_id,
                "to_id": ce_node_id,
                "method": link.method,
                "confidence": link.confidence,
            })

    case_has_event_count = 0
    if case_has_event_rels:
        case_has_event_count = await graph_service.batch_create_relationships(
            "CASE_HAS_EVENT", case_has_event_rels
        )

    summary = {
        "case_nodes": len(new_case_props_deduped),
        "case_has_event": case_has_event_count,
    }
    logger.info("Correlation graph ingestion complete for engagement %s: %s", engagement_id, summary)
    return summary


async def ingest_switching_traces(
    db_session: AsyncSession,
    graph_service: KnowledgeGraphService,
    engagement_id: str,
) -> dict[str, int]:
    """Ingest SwitchingTrace records into the knowledge graph.

    Creates SwitchingTrace nodes, OBSERVED_IN edges to sessions,
    INVOLVES edges to each Application in the trace sequence, and
    INDICATES_FRICTION edges for high-friction (>= 0.6) traces.

    Args:
        db_session: Database session for reading SwitchingTrace records.
        graph_service: Neo4j knowledge graph service.
        engagement_id: Engagement to process.

    Returns:
        Summary dict with counts of created nodes and relationships.
    """
    # Fetch all switching traces for the engagement
    stmt = (
        select(SwitchingTrace)
        .where(SwitchingTrace.engagement_id == engagement_id)
        .order_by(SwitchingTrace.started_at.asc())
    )
    result = await db_session.execute(stmt)
    traces = list(result.scalars().all())

    if not traces:
        logger.info("No switching traces to ingest for engagement %s", engagement_id)
        return {"switching_traces": 0, "observed_in": 0, "involves": 0, "indicates_friction": 0}

    # Find existing SwitchingTrace nodes to avoid duplicates
    existing_trace_nodes = await graph_service.find_nodes(
        "SwitchingTrace", {"engagement_id": engagement_id}
    )
    existing_trace_source_ids = {n.properties.get("source_trace_id") for n in existing_trace_nodes}

    # Find existing Application nodes to link INVOLVES edges
    existing_app_nodes = await graph_service.find_nodes(
        "Application", {"engagement_id": engagement_id}
    )
    app_node_map: dict[str, str] = {}
    for node in existing_app_nodes:
        name = node.properties.get("name")
        if name:
            app_node_map[name] = node.id

    new_traces = [t for t in traces if str(t.id) not in existing_trace_source_ids]

    trace_node_map: dict[str, str] = {}  # trace.id (str) -> graph node_id

    # -- SwitchingTrace nodes -------------------------------------------------
    if new_traces:
        trace_props_list = []
        for trace in new_traces:
            node_id = str(uuid.uuid4())
            trace_node_map[str(trace.id)] = node_id
            trace_props_list.append({
                "id": node_id,
                "name": f"SwitchingTrace {trace.started_at.isoformat()}",
                "engagement_id": engagement_id,
                "source_trace_id": str(trace.id),
                "friction_score": trace.friction_score,
                "is_ping_pong": trace.is_ping_pong,
                "total_duration_ms": trace.total_duration_ms,
                "app_count": trace.app_count,
                "trace_sequence": trace.trace_sequence,
                "source": "task_mining_switching",
            })
        await graph_service.batch_create_nodes("SwitchingTrace", trace_props_list)
        logger.info("Created %d SwitchingTrace nodes for engagement %s", len(new_traces), engagement_id)

    # -- OBSERVED_IN: SwitchingTrace → Session --------------------------------
    observed_in_rels = []
    for trace in new_traces:
        if trace.session_id is None:
            continue
        trace_node_id = trace_node_map.get(str(trace.id))
        if not trace_node_id:
            continue
        # Look up the session node (if it exists in the graph)
        session_nodes = await graph_service.find_nodes(
            "UserAction", {"source_session_id": str(trace.session_id), "engagement_id": engagement_id}
        )
        # If no session node exists, skip (the session may not be in the graph yet)
        if session_nodes:
            observed_in_rels.append({
                "from_id": trace_node_id,
                "to_id": session_nodes[0].id,
            })

    observed_in_count = 0
    if observed_in_rels:
        observed_in_count = await graph_service.batch_create_relationships(
            "OBSERVED_IN", observed_in_rels
        )

    # -- INVOLVES: SwitchingTrace → Application (one per unique app in trace) -
    involves_rels = []
    indicates_friction_rels = []
    for trace in new_traces:
        trace_node_id = trace_node_map.get(str(trace.id))
        if not trace_node_id or not trace.trace_sequence:
            continue
        unique_apps_in_trace = set(trace.trace_sequence)
        for app_name in unique_apps_in_trace:
            app_node_id = app_node_map.get(app_name)
            if app_node_id:
                involves_rels.append({
                    "from_id": trace_node_id,
                    "to_id": app_node_id,
                })
                # High-friction traces indicate friction on the involved apps
                if trace.friction_score >= HIGH_FRICTION_THRESHOLD:
                    indicates_friction_rels.append({
                        "from_id": trace_node_id,
                        "to_id": app_node_id,
                    })

    involves_count = 0
    if involves_rels:
        involves_count = await graph_service.batch_create_relationships(
            "INVOLVES", involves_rels
        )

    indicates_friction_count = 0
    if indicates_friction_rels:
        indicates_friction_count = await graph_service.batch_create_relationships(
            "INDICATES_FRICTION", indicates_friction_rels
        )

    summary = {
        "switching_traces": len(new_traces),
        "observed_in": observed_in_count,
        "involves": involves_count,
        "indicates_friction": indicates_friction_count,
    }
    logger.info("Switching trace graph ingestion complete for engagement %s: %s", engagement_id, summary)
    return summary


