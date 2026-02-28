"""Desktop task mining integration (Story #355).

Re-exports from pipeline (capture→activity) and gap_detector (in-between work).
"""

from src.monitoring.desktop.gap_detector import (
    GapAnalysisResult,
    GapItem,
    TimelineEvent,
    detect_gaps,
)
from src.monitoring.desktop.pipeline import (
    Brightness,
    DesktopCapture,
    PipelineResult,
    ProcessedActivity,
    SourceType,
    process_batch,
    process_capture,
)

__all__ = [
    "Brightness",
    "DesktopCapture",
    "GapAnalysisResult",
    "GapItem",
    "PipelineResult",
    "ProcessedActivity",
    "SourceType",
    "TimelineEvent",
    "detect_gaps",
    "process_batch",
    "process_capture",
]
