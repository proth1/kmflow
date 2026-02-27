"""CIB7 (Camunda 7) REST API client.

Provides async methods for interacting with the CIB7 BPMN engine
for process deployment, instance management, and task queries.
"""

from __future__ import annotations

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
