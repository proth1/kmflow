"""Schema library loader (Story #335).

Loads pre-built schema templates from YAML files for supported SaaS
platforms. Returns None for unsupported platforms, signaling the
connector to activate manual mapping mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class FieldMapping:
    """Maps a source field to a KMFlow attribute."""

    source_field: str
    kmflow_attribute: str
    transform_fn: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_field": self.source_field,
            "kmflow_attribute": self.kmflow_attribute,
            "transform_fn": self.transform_fn,
        }


@dataclass(frozen=True)
class TableTemplate:
    """Schema template for a single source table/object."""

    name: str
    description: str
    fields: list[FieldMapping] = field(default_factory=list)
    lifecycle_states: dict[str, str] = field(default_factory=dict)
    correlation_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "fields": [f.to_dict() for f in self.fields],
            "lifecycle_states": self.lifecycle_states,
            "correlation_keys": self.correlation_keys,
        }


@dataclass(frozen=True)
class SchemaTemplate:
    """Complete schema template for a SaaS platform."""

    platform: str
    version: str
    description: str
    tables: list[TableTemplate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "version": self.version,
            "description": self.description,
            "tables": [t.to_dict() for t in self.tables],
        }

    def get_table(self, name: str) -> TableTemplate | None:
        """Find a table template by name (case-insensitive)."""
        lower = name.lower()
        for t in self.tables:
            if t.name.lower() == lower:
                return t
        return None


class SchemaLibrary:
    """Registry of pre-built schema templates for SaaS platforms.

    Templates are loaded from YAML files in the templates/ directory.
    Platforms not in the library return None, signaling manual mapping mode.
    """

    def __init__(self) -> None:
        self._templates: dict[str, SchemaTemplate] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        """Load all YAML templates from the templates directory."""
        if not TEMPLATES_DIR.exists():
            logger.warning("Schema templates directory not found: %s", TEMPLATES_DIR)
            return

        for yaml_file in sorted(TEMPLATES_DIR.glob("*.yaml")):
            try:
                template = _parse_template_file(yaml_file)
                self._templates[template.platform.lower()] = template
                logger.debug("Loaded schema template: %s", template.platform)
            except Exception:
                logger.exception("Failed to load schema template: %s", yaml_file)

    def get_template(self, platform: str) -> SchemaTemplate | None:
        """Get a schema template by platform name.

        Returns None if the platform is not in the library,
        signaling the connector to activate manual mapping mode.
        """
        return self._templates.get(platform.lower())

    def list_platforms(self) -> list[str]:
        """List all supported platform names."""
        return sorted(self._templates.keys())

    def has_template(self, platform: str) -> bool:
        """Check if a platform has a schema template."""
        return platform.lower() in self._templates


def _parse_template_file(path: Path) -> SchemaTemplate:
    """Parse a YAML template file into a SchemaTemplate."""
    with path.open() as f:
        data = yaml.safe_load(f)

    tables = []
    for table_data in data.get("tables", []):
        fields = [
            FieldMapping(
                source_field=fm["source_field"],
                kmflow_attribute=fm["kmflow_attribute"],
                transform_fn=fm.get("transform_fn", ""),
            )
            for fm in table_data.get("fields", [])
        ]

        tables.append(
            TableTemplate(
                name=table_data["name"],
                description=table_data.get("description", ""),
                fields=fields,
                lifecycle_states=table_data.get("lifecycle_states", {}),
                correlation_keys=table_data.get("correlation_keys", []),
            )
        )

    return SchemaTemplate(
        platform=data["platform"],
        version=data.get("version", "1.0"),
        description=data.get("description", ""),
        tables=tables,
    )
