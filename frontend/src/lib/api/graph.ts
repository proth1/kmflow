/**
 * Graph API: knowledge graph subgraph export for an engagement.
 */

import { apiGet } from "./client";

// -- Types --------------------------------------------------------------------

export interface GraphNode {
  id: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface GraphRelationship {
  id: string;
  from_id: string;
  to_id: string;
  relationship_type: string;
  properties: Record<string, unknown>;
}

export interface GraphExportData {
  nodes: GraphNode[];
  relationships: GraphRelationship[];
}

// -- API functions ------------------------------------------------------------

export async function fetchGraphData(
  engagementId: string,
): Promise<GraphExportData> {
  return apiGet<GraphExportData>(
    `/api/v1/graph/${engagementId}/subgraph`,
  );
}
