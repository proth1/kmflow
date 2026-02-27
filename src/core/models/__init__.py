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
from src.core.models.canonical_event import CanonicalActivityEvent, EventMappingStatus
from src.core.models.conflict import (
    ConflictObject,
    MismatchType,
    ResolutionStatus,
    ResolutionType,
)
from src.core.models.conformance import ConformanceResult, ReferenceProcessModel
from src.core.models.dark_room import DarkRoomSnapshot
from src.core.models.engagement import (
    Engagement,
    EngagementStatus,
    FollowUpReminder,
    ShelfDataRequest,
    ShelfDataRequestItem,
    ShelfDataRequestToken,
    ShelfRequestItemPriority,
    ShelfRequestItemSource,
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
    ComplianceAssessment,
    ComplianceLevel,
    Control,
    ControlEffectiveness,
    ControlEffectivenessScore,
    GapFinding,
    GovernanceGapSeverity,
    GovernanceGapStatus,
    GovernanceGapType,
    Policy,
    PolicyType,
    Regulation,
)
from src.core.models.illumination import (
    IlluminationAction,
    IlluminationActionStatus,
    IlluminationActionType,
)
from src.core.models.incident import (
    Incident,
    IncidentClassification,
    IncidentEvent,
    IncidentEventType,
    IncidentStatus,
)
from src.core.models.llm_audit import LLMAuditLog
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
    MicroSurvey,
    MicroSurveyStatus,
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
    MATURITY_LEVEL_NUMBER,
    AlignmentRunStatus,
    Benchmark,
    BestPractice,
    GapAnalysisResult,
    MaturityScore,
    ProcessMaturity,
    RoadmapStatus,
    TargetOperatingModel,
    TOMAlignmentResult,
    TOMAlignmentRun,
    TOMDimension,
    TOMDimensionRecord,
    TOMGapType,
    TOMVersion,
    TransformationRoadmapModel,
)
from src.core.models.pdp import (
    ObligationType,
    OperationType,
    PDPAuditEntry,
    PDPDecisionType,
    PDPPolicy,
)
from src.core.models.transfer import (
    DataResidencyRestriction,
    DataTransferLog,
    StandardContractualClause,
    TIAStatus,
    TransferDecision,
    TransferImpactAssessment,
)
from src.core.models.uplift_projection import UpliftProjection
from src.core.models.validation import (
    ReviewPack,
    ReviewPackStatus,
)

__all__ = [
    # audit
    "AuditAction",
    "AuditLog",
    "HttpAuditEvent",
    # llm_audit
    "LLMAuditLog",
    # auth
    "CopilotMessage",
    "EngagementMember",
    "MCPAPIKey",
    "User",
    "UserConsent",
    "UserRole",
    # canonical_event
    "CanonicalActivityEvent",
    "EventMappingStatus",
    # conflict
    "ConflictObject",
    "MismatchType",
    "ResolutionStatus",
    "ResolutionType",
    # conformance
    "ConformanceResult",
    "ReferenceProcessModel",
    # dark_room
    "DarkRoomSnapshot",
    # engagement
    "Engagement",
    "EngagementStatus",
    "FollowUpReminder",
    "ShelfDataRequest",
    "ShelfDataRequestItem",
    "ShelfDataRequestToken",
    "ShelfRequestItemPriority",
    "ShelfRequestItemSource",
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
    # illumination
    "IlluminationAction",
    "IlluminationActionStatus",
    "IlluminationActionType",
    # incident
    "Incident",
    "IncidentClassification",
    "IncidentEvent",
    "IncidentEventType",
    "IncidentStatus",
    # governance
    "ComplianceAssessment",
    "ComplianceLevel",
    "Control",
    "ControlEffectiveness",
    "ControlEffectivenessScore",
    "GapFinding",
    "GovernanceGapSeverity",
    "GovernanceGapStatus",
    "GovernanceGapType",
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
    "MicroSurvey",
    "MicroSurveyStatus",
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
    # uplift_projection
    "UpliftProjection",
    # validation
    "ReviewPack",
    "ReviewPackStatus",
    # tom
    "MATURITY_LEVEL_NUMBER",
    "AlignmentRunStatus",
    "Benchmark",
    "BestPractice",
    "GapAnalysisResult",
    "MaturityScore",
    "ProcessMaturity",
    "RoadmapStatus",
    "TargetOperatingModel",
    "TOMAlignmentResult",
    "TOMAlignmentRun",
    "TOMDimension",
    "TOMDimensionRecord",
    "TOMGapType",
    "TOMVersion",
    "TransformationRoadmapModel",
    # pdp
    "ObligationType",
    "OperationType",
    "PDPAuditEntry",
    "PDPDecisionType",
    "PDPPolicy",
    # transfer
    "DataResidencyRestriction",
    "DataTransferLog",
    "StandardContractualClause",
    "TIAStatus",
    "TransferDecision",
    "TransferImpactAssessment",
]
