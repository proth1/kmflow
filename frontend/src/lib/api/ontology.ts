/**
 * Ontology Derivation API client (KMFLOW-6).
 *
 * Provides typed access to ontology derivation, viewing, validation,
 * and export endpoints.
 */

import { apiGet, apiPost } from "./client";

// -- Types -------------------------------------------------------------------

export interface OntologyClass {
  id: string;
  name: string;
  description: string | null;
  parent: string | null;
  instance_count: number;
  confidence: number;
  source_seed_terms: Record<string, unknown>;
}

export interface OntologyProperty {
  id: string;
  name: string;
  source_edge_type: string;
  domain: string | null;
  range: string | null;
  usage_count: number;
  confidence: number;
}

export interface OntologyAxiom {
  id: string;
  expression: string;
  type: string;
  confidence: number;
  source_pattern: Record<string, unknown>;
}

export interface OntologyResponse {
  ontology_id: string;
  engagement_id: string;
  version: number;
  status: string;
  completeness_score: number;
  derived_at: string | null;
  classes: OntologyClass[];
  properties: OntologyProperty[];
  axioms: OntologyAxiom[];
}

export interface OntologyDerivationResult {
  ontology_id: string;
  version: number;
  status: string;
  class_count: number;
  property_count: number;
  axiom_count: number;
  completeness_score: number;
}

export interface ValidationReport {
  ontology_id: string;
  completeness_score: number;
  class_count: number;
  property_count: number;
  axiom_count: number;
  orphan_classes: { name: string; instance_count: number }[];
  disconnected_subgraphs: string[][];
  recommendations: string[];
}

export interface ExportResult {
  content: string;
  content_hash: string;
  format: string;
  ontology_id: string;
  version: number;
}

// -- API Functions -----------------------------------------------------------

export function deriveOntology(
  engagementId: string
): Promise<OntologyDerivationResult> {
  return apiPost(`/engagements/${engagementId}/ontology/derive`, {});
}

export function getOntology(
  engagementId: string
): Promise<OntologyResponse> {
  return apiGet(`/engagements/${engagementId}/ontology`);
}

export function validateOntology(
  engagementId: string
): Promise<ValidationReport> {
  return apiGet(`/engagements/${engagementId}/ontology/validation`);
}

export function exportOntology(
  engagementId: string,
  format: "owl" | "yaml" = "yaml"
): Promise<ExportResult> {
  return apiGet(`/engagements/${engagementId}/ontology/export?fmt=${format}`);
}
