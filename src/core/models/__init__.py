"""SQLAlchemy models for the KMFlow platform.

This package re-exports all models and enums from domain-specific modules
so that existing code using ``from src.core.models import X`` continues to work.
"""

from src.core.models.audit import AuditAction, AuditLog, HttpAuditEvent
from src.core.models.auth import (
    CopilotMessage,
    EngagementMember,
    MCPAPIKey,
    User,
    UserConsent,
    UserRole,
)
from src.core.models.conflict import (
    ConflictObject,
    MismatchType,
    ResolutionStatus,
    ResolutionType,
)
from src.core.models.conformance import ConformanceResult, ReferenceProcessModel
from src.core.models.engagement import (
    Engagement,
    EngagementStatus,
    FollowUpReminder,
    ShelfDataRequest,
    ShelfDataRequestItem,
    ShelfDataRequestToken,
    ShelfRequestItemPriority,
    ShelfRequestItemStatus,
    ShelfRequestStatus,
    UploadFileStatus,
)
from src.core.models.evidence import (
    DataCatalogEntry,
    DataClassification,
    DataLayer,
    EvidenceCategory,
    EvidenceFragment,
    EvidenceItem,
    EvidenceLineage,
    FragmentType,
    ValidationStatus,
)
from src.core.models.governance import (
    ComplianceLevel,
    Control,
    ControlEffectiveness,
    Policy,
    PolicyType,
    Regulation,
)
from src.core.models.monitoring import (
    AlertSeverity,
    AlertStatus,
    Annotation,
    DeviationCategory,
    DeviationSeverity,
    IntegrationConnection,
    MetricCategory,
    MetricReading,
    MonitoringAlert,
    MonitoringJob,
    MonitoringSourceType,
    MonitoringStatus,
    ProcessBaseline,
    ProcessDeviation,
    SuccessMetric,
)
from src.core.models.pattern import (
    PatternAccessRule,
    PatternCategory,
    PatternLibraryEntry,
)
from src.core.models.pov import (
    BrightnessClassification,
    Contradiction,
    CorroborationLevel,
    EvidenceGap,
    EvidenceGrade,
    GapSeverity,
    GapType,
    ProcessElement,
    ProcessElementType,
    ProcessModel,
    ProcessModelStatus,
)
from src.core.models.raci import (
    RACIAssignment,
    RACICell,
    RACIStatus,
)
from src.core.models.seed_term import (
    SeedTerm,
    TermCategory,
    TermSource,
    TermStatus,
)
from src.core.models.semantic_relationship import SemanticRelationship
from src.core.models.simulation import (
    AlternativeSuggestion,
    EpistemicAction,
    FinancialAssumption,
    FinancialAssumptionType,
    ModificationType,
    ScenarioModification,
    SimulationResult,
    SimulationScenario,
    SimulationStatus,
    SimulationType,
    SuggestionDisposition,
)
from src.core.models.survey import (
    CertaintyTier,
    EpistemicFrame,
    FrameKind,
    ProbeType,
    SurveyClaim,
)
from src.core.models.taskmining import (
    ActionCategory,
    AgentStatus,
    CaptureGranularity,
    DeploymentMode,
    DesktopEventType,
    PIIQuarantine,
    PIIType,
    QuarantineStatus,
    SessionStatus,
    TaskMiningAction,
    TaskMiningAgent,
    TaskMiningEvent,
    TaskMiningSession,
)
from src.core.models.tom import (
    Benchmark,
    BestPractice,
    GapAnalysisResult,
    ProcessMaturity,
    TargetOperatingModel,
    TOMDimension,
    TOMGapType,
)

__all__ = [
    # audit
    "AuditAction",
    "AuditLog",
    "HttpAuditEvent",
    # auth
    "CopilotMessage",
    "EngagementMember",
    "MCPAPIKey",
    "User",
    "UserConsent",
    "UserRole",
    # conflict
    "ConflictObject",
    "MismatchType",
    "ResolutionStatus",
    "ResolutionType",
    # conformance
    "ConformanceResult",
    "ReferenceProcessModel",
    # engagement
    "Engagement",
    "EngagementStatus",
    "FollowUpReminder",
    "ShelfDataRequest",
    "ShelfDataRequestItem",
    "ShelfDataRequestToken",
    "ShelfRequestItemPriority",
    "ShelfRequestItemStatus",
    "ShelfRequestStatus",
    "UploadFileStatus",
    # evidence
    "DataCatalogEntry",
    "DataClassification",
    "DataLayer",
    "EvidenceCategory",
    "EvidenceFragment",
    "EvidenceItem",
    "EvidenceLineage",
    "FragmentType",
    "ValidationStatus",
    # governance
    "ComplianceLevel",
    "Control",
    "ControlEffectiveness",
    "Policy",
    "PolicyType",
    "Regulation",
    # monitoring
    "AlertSeverity",
    "AlertStatus",
    "Annotation",
    "DeviationCategory",
    "DeviationSeverity",
    "IntegrationConnection",
    "MetricCategory",
    "MetricReading",
    "MonitoringAlert",
    "MonitoringJob",
    "MonitoringSourceType",
    "MonitoringStatus",
    "ProcessBaseline",
    "ProcessDeviation",
    "SuccessMetric",
    # raci
    "RACIAssignment",
    "RACICell",
    "RACIStatus",
    # pattern
    "PatternAccessRule",
    "PatternCategory",
    "PatternLibraryEntry",
    # pov
    "BrightnessClassification",
    "Contradiction",
    "CorroborationLevel",
    "EvidenceGap",
    "EvidenceGrade",
    "GapSeverity",
    "GapType",
    "ProcessElement",
    "ProcessElementType",
    "ProcessModel",
    "ProcessModelStatus",
    # seed_term
    "SeedTerm",
    "TermCategory",
    "TermSource",
    "TermStatus",
    # semantic_relationship
    "SemanticRelationship",
    # simulation
    "AlternativeSuggestion",
    "EpistemicAction",
    "FinancialAssumption",
    "FinancialAssumptionType",
    "ModificationType",
    "ScenarioModification",
    "SimulationResult",
    "SimulationScenario",
    "SimulationStatus",
    "SimulationType",
    "SuggestionDisposition",
    # survey
    "CertaintyTier",
    "EpistemicFrame",
    "FrameKind",
    "ProbeType",
    "SurveyClaim",
    # taskmining
    "ActionCategory",
    "AgentStatus",
    "CaptureGranularity",
    "DeploymentMode",
    "DesktopEventType",
    "PIIQuarantine",
    "PIIType",
    "QuarantineStatus",
    "SessionStatus",
    "TaskMiningAction",
    "TaskMiningAgent",
    "TaskMiningEvent",
    "TaskMiningSession",
    # tom
    "Benchmark",
    "BestPractice",
    "GapAnalysisResult",
    "ProcessMaturity",
    "TargetOperatingModel",
    "TOMDimension",
    "TOMGapType",
]
