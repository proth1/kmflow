"""MCP tool definitions.

Defines the 8 MCP tools available for consulting platform integration.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_engagement",
        "description": "Retrieve engagement details including status, evidence counts, and team info",
        "parameters": {
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string", "description": "UUID of the engagement"},
            },
            "required": ["engagement_id"],
        },
    },
    {
        "name": "list_evidence",
        "description": "List evidence items for an engagement with optional category filter",
        "parameters": {
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string", "description": "UUID of the engagement"},
                "category": {"type": "string", "description": "Evidence category filter"},
                "limit": {"type": "integer", "description": "Max items to return", "default": 20},
            },
            "required": ["engagement_id"],
        },
    },
    {
        "name": "get_process_model",
        "description": "Get the latest process model with confidence scores",
        "parameters": {
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string", "description": "UUID of the engagement"},
            },
            "required": ["engagement_id"],
        },
    },
    {
        "name": "get_gaps",
        "description": "Retrieve evidence gaps and TOM alignment gaps",
        "parameters": {
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string", "description": "UUID of the engagement"},
                "severity": {"type": "string", "description": "Filter by gap severity"},
            },
            "required": ["engagement_id"],
        },
    },
    {
        "name": "get_monitoring_status",
        "description": "Get real-time monitoring status including active jobs and alerts",
        "parameters": {
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string", "description": "UUID of the engagement"},
            },
            "required": ["engagement_id"],
        },
    },
    {
        "name": "get_deviations",
        "description": "List detected process deviations from baseline",
        "parameters": {
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string", "description": "UUID of the engagement"},
                "category": {"type": "string", "description": "Deviation category filter"},
                "limit": {"type": "integer", "description": "Max items", "default": 20},
            },
            "required": ["engagement_id"],
        },
    },
    {
        "name": "search_patterns",
        "description": "Search the cross-engagement pattern library",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "industry": {"type": "string", "description": "Industry filter"},
                "category": {"type": "string", "description": "Pattern category filter"},
            },
        },
    },
    {
        "name": "run_simulation",
        "description": "Execute a what-if simulation on a process model",
        "parameters": {
            "type": "object",
            "properties": {
                "engagement_id": {"type": "string", "description": "UUID of the engagement"},
                "scenario_name": {"type": "string", "description": "Name for the scenario"},
                "simulation_type": {
                    "type": "string",
                    "description": "Type: what_if, capacity, process_change, control_removal",
                },
                "parameters": {"type": "object", "description": "Simulation parameters"},
            },
            "required": ["engagement_id", "scenario_name", "simulation_type"],
        },
    },
]
