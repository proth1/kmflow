"""Seed data for success metric definitions.

Provides 15 standard metric definitions across 6 categories
for baseline engagement measurement.
"""

from __future__ import annotations

from typing import Any


def get_metric_seeds() -> list[dict[str, Any]]:
    """Return 15 standard success metric definitions.

    Returns:
        List of dicts matching SuccessMetric model fields.
    """
    return [
        # Process Efficiency (3)
        {
            "name": "Process Cycle Time Reduction",
            "unit": "percent",
            "target_value": 25.0,
            "category": "process_efficiency",
            "description": "Percentage reduction in average end-to-end process cycle time",
        },
        {
            "name": "Straight-Through Processing Rate",
            "unit": "percent",
            "target_value": 70.0,
            "category": "process_efficiency",
            "description": "Percentage of transactions processed without manual intervention",
        },
        {
            "name": "Process Automation Coverage",
            "unit": "percent",
            "target_value": 60.0,
            "category": "process_efficiency",
            "description": "Percentage of process steps that are fully automated",
        },
        # Quality (3)
        {
            "name": "First Pass Yield",
            "unit": "percent",
            "target_value": 95.0,
            "category": "quality",
            "description": "Percentage of outputs meeting quality standards on first attempt",
        },
        {
            "name": "Error Rate",
            "unit": "per_thousand",
            "target_value": 5.0,
            "category": "quality",
            "description": "Number of errors per 1000 transactions processed",
        },
        {
            "name": "Rework Rate",
            "unit": "percent",
            "target_value": 3.0,
            "category": "quality",
            "description": "Percentage of work items requiring rework after initial completion",
        },
        # Compliance (2)
        {
            "name": "Regulatory Compliance Score",
            "unit": "percent",
            "target_value": 95.0,
            "category": "compliance",
            "description": "Percentage compliance with applicable regulatory requirements",
        },
        {
            "name": "Control Effectiveness Rate",
            "unit": "percent",
            "target_value": 90.0,
            "category": "compliance",
            "description": "Percentage of controls rated as effective in latest assessment",
        },
        # Customer Satisfaction (2)
        {
            "name": "Customer Satisfaction Score",
            "unit": "score_1_10",
            "target_value": 8.0,
            "category": "customer_satisfaction",
            "description": "Average customer satisfaction rating on 1-10 scale",
        },
        {
            "name": "Net Promoter Score",
            "unit": "score",
            "target_value": 40.0,
            "category": "customer_satisfaction",
            "description": "NPS calculated from customer likelihood-to-recommend surveys",
        },
        # Cost (3)
        {
            "name": "Cost per Transaction",
            "unit": "currency",
            "target_value": 5.0,
            "category": "cost",
            "description": "Average cost to process a single transaction end-to-end",
        },
        {
            "name": "Cost Reduction Achieved",
            "unit": "percent",
            "target_value": 20.0,
            "category": "cost",
            "description": "Percentage reduction in operational costs compared to baseline",
        },
        {
            "name": "Cost-to-Income Ratio",
            "unit": "percent",
            "target_value": 55.0,
            "category": "cost",
            "description": "Operating costs as a percentage of total revenue",
        },
        # Timeliness (2)
        {
            "name": "SLA Achievement Rate",
            "unit": "percent",
            "target_value": 95.0,
            "category": "timeliness",
            "description": "Percentage of service level agreements met within target timeframes",
        },
        {
            "name": "Average Response Time",
            "unit": "hours",
            "target_value": 4.0,
            "category": "timeliness",
            "description": "Average time to initial response for customer requests",
        },
    ]
