"""CIB7 (Camunda 7) REST API client.

Provides async methods for interacting with the CIB7 BPMN engine
for process deployment, instance management, and task queries.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class CamundaClient:
    """Async client for the CIB7 REST API."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Make an HTTP request to the CIB7 REST API."""
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(method, url, json=json, files=files, params=params)
            response.raise_for_status()
            if response.status_code == 204:
                return None
            return response.json()

    async def verify_connectivity(self) -> bool:
        """Check if CIB7 is reachable."""
        try:
            result = await self._request("GET", "/engine")
            return isinstance(result, list) and len(result) > 0
        except (httpx.HTTPError, ConnectionError):
            logger.warning("CIB7 connectivity check failed")
            return False

    async def list_deployments(self) -> list[dict[str, Any]]:
        """List all process deployments."""
        return await self._request("GET", "/deployment")

    async def deploy_process(self, name: str, bpmn_xml: bytes, filename: str = "process.bpmn") -> dict[str, Any]:
        """Deploy a BPMN process model."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/deployment/create",
                data={
                    "deployment-name": name,
                    "enable-duplicate-filtering": "true",
                },
                files={"data": (filename, bpmn_xml, "application/octet-stream")},
            )
            response.raise_for_status()
            return response.json()

    async def list_process_definitions(self) -> list[dict[str, Any]]:
        """List all deployed process definitions."""
        return await self._request("GET", "/process-definition", params={"latestVersion": "true"})

    async def start_process(self, key: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Start a new process instance by process definition key."""
        body: dict[str, Any] = {}
        if variables:
            body["variables"] = {k: {"value": v, "type": "String"} for k, v in variables.items()}
        return await self._request("POST", f"/process-definition/key/{key}/start", json=body)

    async def get_process_instances(self, *, active: bool = True) -> list[dict[str, Any]]:
        """Get process instances, optionally filtered by active status."""
        params: dict[str, Any] = {}
        if active:
            params["active"] = "true"
        return await self._request("GET", "/process-instance", params=params)

    async def get_tasks(self, *, assignee: str | None = None) -> list[dict[str, Any]]:
        """Get user tasks, optionally filtered by assignee."""
        params: dict[str, Any] = {}
        if assignee:
            params["assignee"] = assignee
        return await self._request("GET", "/task", params=params)

    async def complete_task(self, task_id: str, variables: dict[str, Any] | None = None) -> None:
        """Complete a user task."""
        body: dict[str, Any] = {}
        if variables:
            body["variables"] = {k: {"value": v, "type": "String"} for k, v in variables.items()}
        await self._request("POST", f"/task/{task_id}/complete", json=body)

    # -- External Task API ---------------------------------------------------

    async def fetch_and_lock_external_tasks(
        self,
        worker_id: str,
        topics: list[dict[str, Any]],
        max_tasks: int = 10,
        lock_duration: int = 300_000,
    ) -> list[dict[str, Any]]:
        """Fetch and lock external tasks for a worker.

        Args:
            worker_id: Unique worker identifier.
            topics: List of topic subscriptions, each with 'topicName' and optional 'lockDuration'.
            max_tasks: Maximum number of tasks to fetch.
            lock_duration: Default lock duration in milliseconds.
        """
        body = {
            "workerId": worker_id,
            "maxTasks": max_tasks,
            "usePriority": True,
            "topics": [
                {
                    "topicName": t["topicName"],
                    "lockDuration": t.get("lockDuration", lock_duration),
                }
                for t in topics
            ],
        }
        return await self._request("POST", "/external-task/fetchAndLock", json=body)

    async def complete_external_task(
        self,
        task_id: str,
        worker_id: str,
        variables: dict[str, Any] | None = None,
    ) -> None:
        """Report successful completion of an external task."""
        body: dict[str, Any] = {"workerId": worker_id}
        if variables:
            body["variables"] = self._serialize_variables(variables)
        await self._request("POST", f"/external-task/{task_id}/complete", json=body)

    async def fail_external_task(
        self,
        task_id: str,
        worker_id: str,
        error_message: str,
        retries: int = 0,
        retry_timeout: int = 60_000,
    ) -> None:
        """Report failure of an external task."""
        await self._request(
            "POST",
            f"/external-task/{task_id}/failure",
            json={
                "workerId": worker_id,
                "errorMessage": error_message[:500],
                "retries": retries,
                "retryTimeout": retry_timeout,
            },
        )

    async def report_bpmn_error(
        self,
        task_id: str,
        worker_id: str,
        error_code: str,
        error_message: str = "",
    ) -> None:
        """Throw a BPMN error from an external task (triggers error boundary events)."""
        await self._request(
            "POST",
            f"/external-task/{task_id}/bpmnError",
            json={
                "workerId": worker_id,
                "errorCode": error_code,
                "errorMessage": error_message[:500],
            },
        )

    # -- Process Instance API ------------------------------------------------

    async def get_activity_instances(self, process_instance_id: str) -> dict[str, Any]:
        """Get activity instance tree for a process instance."""
        return await self._request("GET", f"/process-instance/{process_instance_id}/activity-instances")

    async def delete_process_instance(self, process_instance_id: str) -> None:
        """Delete (cancel) a process instance."""
        await self._request(
            "DELETE",
            f"/process-instance/{process_instance_id}",
            params={"skipCustomListeners": "true", "skipIoMappings": "true"},
        )

    async def get_incidents(self, *, process_instance_id: str | None = None) -> list[dict[str, Any]]:
        """Get incidents, optionally filtered by process instance."""
        params: dict[str, Any] = {}
        if process_instance_id:
            params["processInstanceId"] = process_instance_id
        return await self._request("GET", "/incident", params=params)

    async def retry_incident(self, incident_id: str) -> None:
        """Set retries to 1 for the external task associated with an incident."""
        # Get the incident to find the execution/task
        incident = await self._request("GET", f"/incident/{incident_id}")
        if incident and incident.get("configuration"):
            # configuration = external task ID for failed job incidents
            await self._request(
                "PUT",
                f"/external-task/{incident['configuration']}/retries",
                json={"retries": 1},
            )

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _serialize_variables(variables: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Serialize Python values to Camunda variable format with type inference."""
        result: dict[str, dict[str, Any]] = {}
        for key, value in variables.items():
            if isinstance(value, bool):
                result[key] = {"value": value, "type": "Boolean"}
            elif isinstance(value, int):
                result[key] = {"value": value, "type": "Long"}
            elif isinstance(value, float):
                result[key] = {"value": value, "type": "Double"}
            elif isinstance(value, dict | list):
                result[key] = {"value": json.dumps(value), "type": "Json"}
            else:
                result[key] = {"value": str(value), "type": "String"}
        return result
