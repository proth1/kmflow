"""Seed data for best practices and benchmarks.

Provides 30 best practices across 6 TOM dimensions and
20 benchmarks across 5 industries for baseline comparison.
"""

from __future__ import annotations

from typing import Any


def get_best_practice_seeds() -> list[dict[str, Any]]:
    """Return 30 best practices across 6 TOM dimensions.

    Returns:
        List of dicts matching BestPractice model fields.
    """
    return [
        # Process Architecture (5)
        {
            "domain": "Process Standardization",
            "industry": "Financial Services",
            "description": "Implement end-to-end process mapping using BPMN 2.0 for all core business processes",
            "source": "BPM CBOK",
            "tom_dimension": "process_architecture",
        },
        {
            "domain": "Process Automation",
            "industry": "Insurance",
            "description": "Automate straight-through processing for low-risk transactions to achieve 80% automation rate",
            "source": "McKinsey Process Excellence",
            "tom_dimension": "process_architecture",
        },
        {
            "domain": "Process Integration",
            "industry": "Banking",
            "description": "Establish API-driven process orchestration between front-office and back-office systems",
            "source": "Gartner Process Mining Report",
            "tom_dimension": "process_architecture",
        },
        {
            "domain": "Process Optimization",
            "industry": "Healthcare",
            "description": "Apply Lean Six Sigma methodology to reduce clinical process cycle times by 30%",
            "source": "IHI Best Practice Guide",
            "tom_dimension": "process_architecture",
        },
        {
            "domain": "Process Documentation",
            "industry": "Manufacturing",
            "description": "Maintain living process documentation with version control and annual review cycles",
            "source": "ISO 9001:2015",
            "tom_dimension": "process_architecture",
        },
        # People and Organization (5)
        {
            "domain": "Skills Development",
            "industry": "Financial Services",
            "description": "Establish structured competency frameworks with quarterly assessment and development plans",
            "source": "Deloitte Human Capital Trends",
            "tom_dimension": "people_and_organization",
        },
        {
            "domain": "Change Management",
            "industry": "Insurance",
            "description": "Apply ADKAR model for organizational transformation with dedicated change champions per department",
            "source": "Prosci Best Practices",
            "tom_dimension": "people_and_organization",
        },
        {
            "domain": "Role Definition",
            "industry": "Banking",
            "description": "Define RACI matrices for all critical processes with clear escalation paths",
            "source": "PMI PMBOK Guide",
            "tom_dimension": "people_and_organization",
        },
        {
            "domain": "Knowledge Transfer",
            "industry": "Healthcare",
            "description": "Implement structured knowledge transfer programs with mentoring pairs and documentation requirements",
            "source": "APQC Knowledge Management",
            "tom_dimension": "people_and_organization",
        },
        {
            "domain": "Workforce Planning",
            "industry": "Manufacturing",
            "description": "Conduct annual strategic workforce planning aligned with process automation roadmap",
            "source": "SHRM Best Practices",
            "tom_dimension": "people_and_organization",
        },
        # Technology and Data (5)
        {
            "domain": "Data Architecture",
            "industry": "Financial Services",
            "description": "Implement enterprise data lake with governed data catalog and lineage tracking",
            "source": "DAMA DMBOK",
            "tom_dimension": "technology_and_data",
        },
        {
            "domain": "Integration Platform",
            "industry": "Insurance",
            "description": "Deploy event-driven architecture with centralized API gateway for system integration",
            "source": "ThoughtWorks Technology Radar",
            "tom_dimension": "technology_and_data",
        },
        {
            "domain": "Analytics Platform",
            "industry": "Banking",
            "description": "Establish real-time analytics capabilities with ML-driven anomaly detection",
            "source": "Gartner Analytics Maturity Model",
            "tom_dimension": "technology_and_data",
        },
        {
            "domain": "Data Quality",
            "industry": "Healthcare",
            "description": "Implement automated data quality scoring with threshold-based alerting across all critical datasets",
            "source": "DAMA Data Quality Framework",
            "tom_dimension": "technology_and_data",
        },
        {
            "domain": "Cloud Strategy",
            "industry": "Manufacturing",
            "description": "Adopt hybrid cloud architecture with edge computing for real-time manufacturing intelligence",
            "source": "AWS Well-Architected Framework",
            "tom_dimension": "technology_and_data",
        },
        # Governance Structures (5)
        {
            "domain": "Process Governance",
            "industry": "Financial Services",
            "description": "Establish process governance board with quarterly review cadence and escalation authority",
            "source": "COBIT 2019",
            "tom_dimension": "governance_structures",
        },
        {
            "domain": "Policy Framework",
            "industry": "Insurance",
            "description": "Maintain hierarchical policy framework with automated compliance checking",
            "source": "ISO 27001",
            "tom_dimension": "governance_structures",
        },
        {
            "domain": "Decision Rights",
            "industry": "Banking",
            "description": "Define clear decision rights matrix aligned with risk appetite framework",
            "source": "Basel Committee on Banking Supervision",
            "tom_dimension": "governance_structures",
        },
        {
            "domain": "Audit Framework",
            "industry": "Healthcare",
            "description": "Implement continuous auditing with automated control testing for regulatory compliance",
            "source": "IIA Standards",
            "tom_dimension": "governance_structures",
        },
        {
            "domain": "Committee Structure",
            "industry": "Manufacturing",
            "description": "Establish cross-functional steering committees for operational excellence initiatives",
            "source": "Deloitte Operating Model Framework",
            "tom_dimension": "governance_structures",
        },
        # Performance Management (5)
        {
            "domain": "KPI Framework",
            "industry": "Financial Services",
            "description": "Implement balanced scorecard with automated KPI dashboards refreshed in real-time",
            "source": "Kaplan & Norton BSC",
            "tom_dimension": "performance_management",
        },
        {
            "domain": "SLA Management",
            "industry": "Insurance",
            "description": "Define tiered SLAs for all customer-facing processes with automated breach notification",
            "source": "ITIL Service Level Management",
            "tom_dimension": "performance_management",
        },
        {
            "domain": "Process Mining",
            "industry": "Banking",
            "description": "Deploy process mining for continuous conformance checking and bottleneck identification",
            "source": "Celonis Process Intelligence Report",
            "tom_dimension": "performance_management",
        },
        {
            "domain": "Continuous Improvement",
            "industry": "Healthcare",
            "description": "Establish Plan-Do-Check-Act cycles with monthly retrospectives and improvement backlogs",
            "source": "IHI Model for Improvement",
            "tom_dimension": "performance_management",
        },
        {
            "domain": "Benchmarking",
            "industry": "Manufacturing",
            "description": "Conduct annual industry benchmarking with peer comparison across operational metrics",
            "source": "APQC Benchmarking",
            "tom_dimension": "performance_management",
        },
        # Risk and Compliance (5)
        {
            "domain": "Risk Assessment",
            "industry": "Financial Services",
            "description": "Implement enterprise risk management with quantitative risk scoring and heat map visualization",
            "source": "COSO ERM Framework",
            "tom_dimension": "risk_and_compliance",
        },
        {
            "domain": "Regulatory Mapping",
            "industry": "Insurance",
            "description": "Maintain automated regulatory change management with impact assessment workflows",
            "source": "RegTech Industry Report",
            "tom_dimension": "risk_and_compliance",
        },
        {
            "domain": "Control Testing",
            "industry": "Banking",
            "description": "Automate control testing with continuous monitoring and exception-based reporting",
            "source": "SOX Compliance Guide",
            "tom_dimension": "risk_and_compliance",
        },
        {
            "domain": "Compliance Training",
            "industry": "Healthcare",
            "description": "Deliver role-based compliance training with annual certification and knowledge assessments",
            "source": "OIG Compliance Program Guidance",
            "tom_dimension": "risk_and_compliance",
        },
        {
            "domain": "Incident Management",
            "industry": "Manufacturing",
            "description": "Establish integrated incident management with root cause analysis and corrective action tracking",
            "source": "ISO 31000 Risk Management",
            "tom_dimension": "risk_and_compliance",
        },
    ]


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
