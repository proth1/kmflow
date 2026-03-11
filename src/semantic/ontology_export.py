"""Ontology export to OWL/XML and YAML formats (KMFLOW-6).

Generates W3C OWL 2 XML and human-readable YAML representations of
derived ontologies, including provenance annotations and version metadata.
Uses standard library xml.etree for OWL (no rdflib dependency required).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.ontology import (
    OntologyAxiom,
    OntologyClass,
    OntologyProperty,
    OntologyStatus,
    OntologyVersion,
)

logger = logging.getLogger(__name__)

OWL_NS = "http://www.w3.org/2002/07/owl#"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS_NS = "http://www.w3.org/2000/01/rdf-schema#"
XSD_NS = "http://www.w3.org/2001/XMLSchema#"
KMFLOW_NS = "https://kmflow.ai/ontology/"


class OntologyExportService:
    """Exports derived ontologies to OWL/XML and YAML formats."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def export(self, ontology_id: uuid.UUID, fmt: str = "yaml") -> dict[str, Any]:
        """Export an ontology in the specified format.

        Args:
            ontology_id: The ontology version to export.
            fmt: Export format — "owl" or "yaml".

        Returns:
            Dict with content (string), content_hash (SHA-256), and format.
        """
        ontology = await self.session.get(OntologyVersion, ontology_id)
        if not ontology:
            return {"error": "Ontology not found"}

        classes = await self._get_classes(ontology_id)
        properties = await self._get_properties(ontology_id)
        axioms = await self._get_axioms(ontology_id)

        if fmt == "owl":
            content = self._generate_owl(ontology, classes, properties, axioms)
        else:
            content = self._generate_yaml(ontology, classes, properties, axioms)

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Update status
        ontology.status = OntologyStatus.EXPORTED
        await self.session.commit()

        return {
            "content": content,
            "content_hash": content_hash,
            "format": fmt,
            "ontology_id": str(ontology_id),
            "version": ontology.version,
        }

    async def _get_classes(self, ontology_id: uuid.UUID) -> list[OntologyClass]:
        result = await self.session.execute(select(OntologyClass).where(OntologyClass.ontology_id == ontology_id))
        return list(result.scalars().all())

    async def _get_properties(self, ontology_id: uuid.UUID) -> list[OntologyProperty]:
        result = await self.session.execute(select(OntologyProperty).where(OntologyProperty.ontology_id == ontology_id))
        return list(result.scalars().all())

    async def _get_axioms(self, ontology_id: uuid.UUID) -> list[OntologyAxiom]:
        result = await self.session.execute(select(OntologyAxiom).where(OntologyAxiom.ontology_id == ontology_id))
        return list(result.scalars().all())

    def _generate_owl(
        self,
        ontology: OntologyVersion,
        classes: list[OntologyClass],
        properties: list[OntologyProperty],
        axioms: list[OntologyAxiom],
    ) -> str:
        """Generate OWL/XML representation."""
        base_uri = f"{KMFLOW_NS}{ontology.engagement_id}/v{ontology.version}"

        root = Element("Ontology")
        root.set("xmlns", OWL_NS)
        root.set("xmlns:rdf", RDF_NS)
        root.set("xmlns:rdfs", RDFS_NS)
        root.set("xmlns:xsd", XSD_NS)
        root.set("xmlns:kmflow", KMFLOW_NS)
        root.set("ontologyIRI", base_uri)

        # Version info
        prefix = SubElement(root, "Prefix")
        prefix.set("name", "kmflow")
        prefix.set("IRI", KMFLOW_NS)

        annotation = SubElement(root, "Annotation")
        prop = SubElement(annotation, "AnnotationProperty")
        prop.set("IRI", f"{RDFS_NS}comment")
        literal = SubElement(annotation, "Literal")
        literal.text = f"KMFlow derived ontology v{ontology.version}, completeness={ontology.completeness_score}"

        # Classes
        class_iris: dict[uuid.UUID, str] = {}
        for cls in classes:
            class_iri = f"{base_uri}#{cls.name.replace(' ', '_')}"
            class_iris[cls.id] = class_iri

            decl = SubElement(root, "Declaration")
            class_el = SubElement(decl, "Class")
            class_el.set("IRI", class_iri)

            # Annotation with provenance
            ann = SubElement(root, "AnnotationAssertion")
            ann_prop = SubElement(ann, "AnnotationProperty")
            ann_prop.set("IRI", f"{RDFS_NS}comment")
            ann_class = SubElement(ann, "IRI")
            ann_class.text = class_iri
            ann_lit = SubElement(ann, "Literal")
            ann_lit.text = f"confidence={cls.confidence}, instances={cls.instance_count}"

            # Subclass axiom
            if cls.parent_class_id and cls.parent_class_id in class_iris:
                sub = SubElement(root, "SubClassOf")
                sub_child = SubElement(sub, "Class")
                sub_child.set("IRI", class_iri)
                sub_parent = SubElement(sub, "Class")
                sub_parent.set("IRI", class_iris[cls.parent_class_id])

        # Properties
        for prop_item in properties:
            prop_iri = f"{base_uri}#{prop_item.name.replace(' ', '_')}"

            decl = SubElement(root, "Declaration")
            obj_prop = SubElement(decl, "ObjectProperty")
            obj_prop.set("IRI", prop_iri)

            if prop_item.domain_class_id and prop_item.domain_class_id in class_iris:
                domain = SubElement(root, "ObjectPropertyDomain")
                dp = SubElement(domain, "ObjectProperty")
                dp.set("IRI", prop_iri)
                dc = SubElement(domain, "Class")
                dc.set("IRI", class_iris[prop_item.domain_class_id])

            if prop_item.range_class_id and prop_item.range_class_id in class_iris:
                range_el = SubElement(root, "ObjectPropertyRange")
                rp = SubElement(range_el, "ObjectProperty")
                rp.set("IRI", prop_iri)
                rc = SubElement(range_el, "Class")
                rc.set("IRI", class_iris[prop_item.range_class_id])

        # Axioms as annotations
        for axiom in axioms:
            ann = SubElement(root, "Annotation")
            ann_prop = SubElement(ann, "AnnotationProperty")
            ann_prop.set("IRI", f"{KMFLOW_NS}axiom")
            ann_lit = SubElement(ann, "Literal")
            ann_lit.text = f"[{axiom.axiom_type}] {axiom.expression} (confidence={axiom.confidence})"

        xml_bytes = tostring(root, encoding="unicode", xml_declaration=False)
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_bytes}'

    def _generate_yaml(
        self,
        ontology: OntologyVersion,
        classes: list[OntologyClass],
        properties: list[OntologyProperty],
        axioms: list[OntologyAxiom],
    ) -> str:
        """Generate human-readable YAML representation."""
        class_map = {c.id: c.name for c in classes}

        data: dict[str, Any] = {
            "ontology": {
                "version": ontology.version,
                "engagement_id": str(ontology.engagement_id),
                "status": ontology.status.value,
                "completeness_score": ontology.completeness_score,
                "derived_at": ontology.derived_at.isoformat() if ontology.derived_at else None,
            },
            "classes": [
                {
                    "name": c.name,
                    "description": c.description,
                    "parent": class_map.get(c.parent_class_id) if c.parent_class_id else None,
                    "instance_count": c.instance_count,
                    "confidence": c.confidence,
                    "source_seed_terms": c.source_seed_terms,
                }
                for c in classes
            ],
            "properties": [
                {
                    "name": p.name,
                    "source_edge_type": p.source_edge_type,
                    "domain": class_map.get(p.domain_class_id) if p.domain_class_id else None,
                    "range": class_map.get(p.range_class_id) if p.range_class_id else None,
                    "usage_count": p.usage_count,
                    "confidence": p.confidence,
                }
                for p in properties
            ],
            "axioms": [
                {
                    "expression": a.expression,
                    "type": a.axiom_type,
                    "confidence": a.confidence,
                    "source_pattern": a.source_pattern,
                }
                for a in axioms
            ],
        }

        return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
