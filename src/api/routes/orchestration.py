"""BPMN Workflow Orchestration routes.

Admin endpoints for batch-deploying BPMN workflows to Camunda,
monitoring process instances, and managing incidents.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from src.core.models import User
from src.core.permissions import require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orchestration", tags=["orchestration"])

# L4 executable BPMN files (flat, no swimlanes)
PLATFORM_BPMN_DIR = Path(__file__).resolve().parents[3] / "platform"
L4_WORKFLOW_FILES = [
    "continuous-monitoring-workflow.bpmn",
    "engagement-lifecycle-orchestration.bpmn",
    "evidence-collection-workflow.bpmn",
    "evidence-lifecycle-workflow.bpmn",
    "pov-generation-workflow.bpmn",
    "shelf-data-request-workflow.bpmn",
    "tom-gap-analysis-workflow.bpmn",
]


def _get_camunda_client(request: Request):
    """Get the Camunda client from app state."""
    client = getattr(request.app.state, "camunda_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Camunda engine is not available")
    return client


@router.post("/deploy")
async def deploy_all_workflows(
    request: Request,
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Deploy all L4 BPMN workflow files to the Camunda engine.

    Reads each .bpmn file from the platform/ directory and deploys it
    via the Camunda REST API. Returns deployment results per workflow.
    """
    client = _get_camunda_client(request)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for filename in L4_WORKFLOW_FILES:
        filepath = PLATFORM_BPMN_DIR / filename
        if not filepath.exists():
            errors.append({"file": filename, "error": "File not found"})
            continue

        try:
            bpmn_xml = filepath.read_bytes()
            deployment_name = filepath.stem.replace("-", " ").title()
            result = await client.deploy_process(
                name=deployment_name,
                bpmn_xml=bpmn_xml,
                filename=filename,
            )
            results.append(
                {
                    "file": filename,
                    "deployment_id": result.get("id"),
                    "name": result.get("name"),
                    "deployed_definitions": list(result.get("deployedProcessDefinitions", {}).keys()),
                }
            )
            logger.info("Deployed %s: deployment_id=%s", filename, result.get("id"))
        except (ConnectionError, OSError, httpx.HTTPError) as e:
            logger.error("Failed to deploy %s: %s", filename, e)
            errors.append({"file": filename, "error": str(e)})

    return {
        "deployed": len(results),
        "failed": len(errors),
        "total": len(L4_WORKFLOW_FILES),
        "results": results,
        "errors": errors,
    }


@router.get("/instances")
async def list_process_instances(
    request: Request,
    active: bool = True,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """List process instances with activity and incident information.

    Returns instances enriched with current activity name and incident count
    for the orchestration dashboard.
    """
    client = _get_camunda_client(request)
    try:
        instances = await client.get_process_instances(active=active)

        # Enrich with incident counts
        enriched: list[dict[str, Any]] = []
        for inst in instances:
            instance_id = inst.get("id", "")
            try:
                incidents = await client.get_incidents(process_instance_id=instance_id)
                incident_count = len(incidents)
            except (httpx.HTTPError, ConnectionError):
                incident_count = 0

            enriched.append(
                {
                    "id": instance_id,
                    "business_key": inst.get("businessKey"),
                    "process_definition_id": inst.get("definitionId"),
                    "suspended": inst.get("suspended", False),
                    "incident_count": incident_count,
                }
            )

        return {"instances": enriched, "total": len(enriched)}
    except (ConnectionError, OSError, httpx.HTTPError) as e:
        logger.error("Failed to list process instances: %s", e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine") from e


@router.get("/instances/{instance_id}")
async def get_process_instance_detail(
    instance_id: str,
    request: Request,
    user: User = Depends(require_permission("engagement:read")),
) -> dict[str, Any]:
    """Get detailed information about a process instance.

    Includes the activity instance tree showing current execution state.
    """
    client = _get_camunda_client(request)
    try:
        activity_tree = await client.get_activity_instances(instance_id)
        incidents = await client.get_incidents(process_instance_id=instance_id)

        return {
            "instance_id": instance_id,
            "activity_tree": activity_tree,
            "incidents": incidents,
            "incident_count": len(incidents),
        }
    except (ConnectionError, OSError, httpx.HTTPError) as e:
        logger.error("Failed to get instance %s: %s", instance_id, e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine") from e


@router.post("/instances/{instance_id}/retry")
async def retry_instance_incidents(
    instance_id: str,
    request: Request,
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Retry all incidents for a process instance.

    Sets retries to 1 on external tasks associated with each incident,
    allowing the engine to re-attempt execution.
    """
    client = _get_camunda_client(request)
    try:
        incidents = await client.get_incidents(process_instance_id=instance_id)
        if not incidents:
            return {"retried": 0, "message": "No incidents found"}

        retried = 0
        errors_list: list[str] = []
        for incident in incidents:
            try:
                await client.retry_incident(incident["id"])
                retried += 1
            except (httpx.HTTPError, ConnectionError, KeyError) as e:
                errors_list.append(f"Incident {incident.get('id', '?')}: {e}")

        return {
            "retried": retried,
            "total_incidents": len(incidents),
            "errors": errors_list,
        }
    except (ConnectionError, OSError, httpx.HTTPError) as e:
        logger.error("Failed to retry incidents for %s: %s", instance_id, e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine") from e


@router.delete("/instances/{instance_id}")
async def cancel_process_instance(
    instance_id: str,
    request: Request,
    user: User = Depends(require_permission("engagement:update")),
) -> dict[str, Any]:
    """Cancel (delete) a process instance."""
    client = _get_camunda_client(request)
    try:
        await client.delete_process_instance(instance_id)
        return {"instance_id": instance_id, "status": "cancelled"}
    except (ConnectionError, OSError, httpx.HTTPError) as e:
        logger.error("Failed to cancel instance %s: %s", instance_id, e)
        raise HTTPException(status_code=502, detail="Failed to communicate with Camunda engine") from e
