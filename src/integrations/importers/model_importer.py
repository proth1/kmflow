"""Base interface and data model for process model importers (Story #328).

Provides the ``ModelImporter`` abstract base class and ``ImportedModel``
data structure used by ARIS AML and Visio VSDX importers.

``ImportedModel`` is a pre-graph-commit intermediate that holds lists of
process elements (nodes) and edges before they are written to Neo4j.
"""

from __future__ import annotations

import abc
import enum
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ElementType(enum.StrEnum):
    """BPMN-equivalent element types for imported process models."""

    TASK = "task"
    GATEWAY = "gateway"
    START_EVENT = "start_event"
    END_EVENT = "end_event"
    INTERMEDIATE_EVENT = "intermediate_event"
    SUBPROCESS = "subprocess"
    UNKNOWN = "unknown"


class EdgeType(enum.StrEnum):
    """Relationship types between process elements."""

    PRECEDES = "precedes"
    PERFORMED_BY = "performed_by"


class ImportFormatError(Exception):
    """Raised when an import file has an unsupported format or version.

    Attributes:
        format_name: The file format (e.g., "aris_aml", "visio_vsdx").
        detected_version: The version detected in the file (if any).
        supported_versions: List of supported versions.
    """

    def __init__(
        self,
        message: str,
        format_name: str = "",
        detected_version: str = "",
        supported_versions: list[str] | None = None,
    ) -> None:
        self.format_name = format_name
        self.detected_version = detected_version
        self.supported_versions = supported_versions or []
        full_msg = message
        if detected_version:
            full_msg += f" (detected: {detected_version})"
        if supported_versions:
            full_msg += f". Supported: {', '.join(supported_versions)}"
        super().__init__(full_msg)


@dataclass
class ProcessElement:
    """A single process element extracted from a model.

    Attributes:
        id: Unique identifier within the source model.
        name: Human-readable element name (label text).
        element_type: BPMN-equivalent classification.
        lane: Swim lane name this element belongs to (if any).
        source_format: Format the element was imported from.
        attributes: Additional format-specific attributes.
    """

    id: str
    name: str
    element_type: ElementType = ElementType.UNKNOWN
    lane: str = ""
    source_format: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessEdge:
    """A directed edge between two process elements.

    Attributes:
        source_id: ID of the source element.
        target_id: ID of the target element.
        edge_type: Relationship type (PRECEDES or PERFORMED_BY).
        label: Optional label on the edge.
    """

    source_id: str
    target_id: str
    edge_type: EdgeType = EdgeType.PRECEDES
    label: str = ""


@dataclass
class ImportedModel:
    """Result of parsing a process model file.

    Contains lists of elements and edges ready for graph commit.
    No partial data should be written if parsing fails.
    """

    elements: list[ProcessElement] = field(default_factory=list)
    edges: list[ProcessEdge] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    source_format: str = ""
    source_file: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.elements) > 0 and len(self.errors) == 0

    @property
    def element_count(self) -> int:
        return len(self.elements)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def get_elements_by_type(self, element_type: ElementType) -> list[ProcessElement]:
        """Filter elements by type."""
        return [e for e in self.elements if e.element_type == element_type]

    def get_performed_by_edges(self) -> list[ProcessEdge]:
        """Get all PERFORMED_BY edges (role assignments)."""
        return [e for e in self.edges if e.edge_type == EdgeType.PERFORMED_BY]


class ModelImporter(abc.ABC):
    """Abstract base class for process model importers.

    Subclasses must implement ``parse()`` to extract process elements
    and edges from their respective file formats.
    """

    @abc.abstractmethod
    def parse(self, file_path: str | Path) -> ImportedModel:
        """Parse a process model file and extract elements and edges.

        Args:
            file_path: Path to the model file.

        Returns:
            ImportedModel with extracted elements and edges.

        Raises:
            ImportFormatError: If the file format is unsupported or corrupt.
        """
        ...
