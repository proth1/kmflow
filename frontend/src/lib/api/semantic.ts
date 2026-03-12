/**
 * Semantic service API client (KMFLOW-67).
 *
 * Provides typed access to entity extraction, embedding generation,
 * semantic search, and confidence scoring endpoints.
 */

import { apiRequest } from './client';

// -- Types ------------------------------------------------------------------

export interface ExtractedEntity {
  id: string;
  entity_type: string;
  name: string;
  confidence: number;
  source_span: string;
  aliases: string[];
  metadata: Record<string, string>;
}

export interface EntityExtractionResponse {
  entities: ExtractedEntity[];
  entity_count: number;
  by_type: Record<string, number>;
  raw_text_length: number;
}

export interface EntityResolutionResponse {
  resolved_entities: ExtractedEntity[];
  duplicates_found: {
    entity_a_id: string;
    entity_b_id: string;
    entity_a_name: string;
    entity_b_name: string;
    entity_type: string;
    similarity_reason: string;
  }[];
  merged_count: number;
}

export interface EmbeddingResponse {
  embeddings: number[][];
  dimension: number;
  count: number;
}

export interface SemanticSearchResult {
  content: string;
  source_id: string;
  source_type: string;
  similarity_score: number;
  metadata: Record<string, unknown>;
}

export interface SemanticSearchResponse {
  results: SemanticSearchResult[];
  query: string;
  total_results: number;
}

export interface ConfidenceResult {
  final_score: number;
  strength: number;
  quality_score: number;
  evidence_grade: string;
  brightness: string;
}

export interface GraphMetrics {
  engagement_id: string;
  total_nodes: number;
  total_relationships: number;
  nodes_by_label: Record<string, number>;
  relationships_by_type: Record<string, number>;
  avg_degree: number;
  density: number;
}

// -- API Functions ----------------------------------------------------------

export async function extractEntities(
  text: string,
  options?: { use_llm?: boolean; seed_terms?: string[] }
): Promise<EntityExtractionResponse> {
  return apiRequest('/api/v1/semantic/extract', {
    method: 'POST',
    body: JSON.stringify({ text, ...options }),
  });
}

export async function resolveEntities(
  entities: ExtractedEntity[]
): Promise<EntityResolutionResponse> {
  return apiRequest('/api/v1/semantic/resolve', {
    method: 'POST',
    body: JSON.stringify({ entities }),
  });
}

export async function generateEmbeddings(
  texts: string[]
): Promise<EmbeddingResponse> {
  return apiRequest('/api/v1/semantic/embed', {
    method: 'POST',
    body: JSON.stringify({ texts }),
  });
}

export async function semanticSearch(
  engagementId: string,
  query: string,
  topK: number = 10
): Promise<SemanticSearchResponse> {
  return apiRequest(`/api/v1/semantic/search/${engagementId}`, {
    method: 'POST',
    body: JSON.stringify({ query, top_k: topK }),
  });
}

export async function computeConfidence(params: {
  coverage: number;
  agreement: number;
  quality: number;
  reliability: number;
  recency: number;
  evidence_count?: number;
  source_plane_count?: number;
  has_sme_validation?: boolean;
}): Promise<ConfidenceResult> {
  return apiRequest('/api/v1/confidence/compute', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}

export async function getGraphMetrics(
  engagementId: string
): Promise<GraphMetrics> {
  return apiRequest(`/api/v1/graph/metrics/${engagementId}`);
}
