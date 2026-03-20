"""Seed data for best practices and benchmarks.

Provides 30 best practices across 6 TOM dimensions and
20 benchmarks across 5 industries for baseline comparison.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def get_best_practice_seeds() -> list[dict[str, Any]]:
    """Return 30 best practices across 6 TOM dimensions.

    Data is loaded from ``src/data/seeds/best_practices.yaml`` so that
    the static content can be edited without touching Python source.

    Returns:
        List of dicts matching BestPractice model fields.
    """
    path = Path(__file__).parent / "seeds" / "best_practices.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def get_benchmark_seeds() -> list[dict[str, Any]]:
    """Return 20 benchmarks across 5 industries.

    Returns:
        List of dicts matching Benchmark model fields.
    """
    return [
        # Financial Services (4)
        {
            "metric_name": "Straight-Through Processing Rate",
            "industry": "Financial Services",
            "p25": 45.0,
            "p50": 62.0,
            "p75": 78.0,
            "p90": 91.0,
            "source": "McKinsey Operations Benchmark",
        },
        {
            "metric_name": "Customer Onboarding Time (days)",
            "industry": "Financial Services",
            "p25": 14.0,
            "p50": 7.0,
            "p75": 3.0,
            "p90": 1.0,
            "source": "Deloitte Digital Banking Survey",
        },
        {
            "metric_name": "Process Automation Coverage (%)",
            "industry": "Financial Services",
            "p25": 25.0,
            "p50": 42.0,
            "p75": 60.0,
            "p90": 80.0,
            "source": "Gartner RPA Market Guide",
        },
        {
            "metric_name": "Regulatory Compliance Score (%)",
            "industry": "Financial Services",
            "p25": 72.0,
            "p50": 85.0,
            "p75": 93.0,
            "p90": 98.0,
            "source": "Thomson Reuters Regulatory Intelligence",
        },
        # Insurance (4)
        {
            "metric_name": "Claims Processing Time (days)",
            "industry": "Insurance",
            "p25": 21.0,
            "p50": 12.0,
            "p75": 5.0,
            "p90": 2.0,
            "source": "Accenture Insurance Report",
        },
        {
            "metric_name": "Policy Issuance Automation (%)",
            "industry": "Insurance",
            "p25": 30.0,
            "p50": 50.0,
            "p75": 72.0,
            "p90": 88.0,
            "source": "McKinsey Insurance Practice",
        },
        {
            "metric_name": "Combined Ratio (%)",
            "industry": "Insurance",
            "p25": 102.0,
            "p50": 97.0,
            "p75": 93.0,
            "p90": 88.0,
            "source": "AM Best Industry Report",
        },
        {
            "metric_name": "Digital Channel Adoption (%)",
            "industry": "Insurance",
            "p25": 20.0,
            "p50": 38.0,
            "p75": 55.0,
            "p90": 72.0,
            "source": "JD Power Insurance Digital Experience",
        },
        # Banking (4)
        {
            "metric_name": "Loan Origination Cycle Time (days)",
            "industry": "Banking",
            "p25": 30.0,
            "p50": 18.0,
            "p75": 8.0,
            "p90": 3.0,
            "source": "FICO Benchmark Study",
        },
        {
            "metric_name": "Transaction Error Rate (per 10k)",
            "industry": "Banking",
            "p25": 15.0,
            "p50": 8.0,
            "p75": 3.0,
            "p90": 1.0,
            "source": "SWIFT Transaction Monitoring",
        },
        {
            "metric_name": "Cost-to-Income Ratio (%)",
            "industry": "Banking",
            "p25": 68.0,
            "p50": 58.0,
            "p75": 48.0,
            "p90": 40.0,
            "source": "McKinsey Global Banking Report",
        },
        {
            "metric_name": "Digital Maturity Index (1-5)",
            "industry": "Banking",
            "p25": 2.1,
            "p50": 3.0,
            "p75": 3.8,
            "p90": 4.5,
            "source": "Deloitte Digital Maturity Model",
        },
        # Healthcare (4)
        {
            "metric_name": "Patient Throughput (per day)",
            "industry": "Healthcare",
            "p25": 45.0,
            "p50": 68.0,
            "p75": 92.0,
            "p90": 120.0,
            "source": "ACHE Healthcare Management Report",
        },
        {
            "metric_name": "Clinical Documentation Completeness (%)",
            "industry": "Healthcare",
            "p25": 70.0,
            "p50": 82.0,
            "p75": 91.0,
            "p90": 97.0,
            "source": "AHIMA Best Practices",
        },
        {
            "metric_name": "Revenue Cycle Days Outstanding",
            "industry": "Healthcare",
            "p25": 55.0,
            "p50": 42.0,
            "p75": 32.0,
            "p90": 25.0,
            "source": "HFMA Revenue Cycle Benchmark",
        },
        {
            "metric_name": "EHR Adoption Score (%)",
            "industry": "Healthcare",
            "p25": 65.0,
            "p50": 80.0,
            "p75": 90.0,
            "p90": 96.0,
            "source": "ONC Health IT Dashboard",
        },
        # Manufacturing (4)
        {
            "metric_name": "Overall Equipment Effectiveness (%)",
            "industry": "Manufacturing",
            "p25": 55.0,
            "p50": 72.0,
            "p75": 85.0,
            "p90": 92.0,
            "source": "World Class Manufacturing Institute",
        },
        {
            "metric_name": "First Pass Yield (%)",
            "industry": "Manufacturing",
            "p25": 88.0,
            "p50": 93.0,
            "p75": 97.0,
            "p90": 99.2,
            "source": "ASQ Quality Progress",
        },
        {
            "metric_name": "Order-to-Delivery Time (days)",
            "industry": "Manufacturing",
            "p25": 21.0,
            "p50": 12.0,
            "p75": 7.0,
            "p90": 3.0,
            "source": "APICS Supply Chain Benchmark",
        },
        {
            "metric_name": "Inventory Turns (annual)",
            "industry": "Manufacturing",
            "p25": 4.0,
            "p50": 8.0,
            "p75": 12.0,
            "p90": 18.0,
            "source": "Gartner Supply Chain Top 25",
        },
    ]
