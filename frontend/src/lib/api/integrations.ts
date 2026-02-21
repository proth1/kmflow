/**
 * Integrations API: connector types, connections, test, and sync.
 */

import { apiGet, apiPost } from "./client";

// -- Types --------------------------------------------------------------------

export interface ConnectorType {
  type: string;
  description: string;
}

export interface IntegrationConnectionData {
  id: string;
  engagement_id: string;
  connector_type: string;
  name: string;
  status: string;
  config: Record<string, unknown>;
  field_mappings: Record<string, string> | null;
  last_sync: string | null;
  last_sync_records: number;
  error_message: string | null;
}

export interface IntegrationConnectionList {
  items: IntegrationConnectionData[];
  total: number;
}

// -- API functions ------------------------------------------------------------

export async function fetchConnectorTypes(): Promise<ConnectorType[]> {
  return apiGet<ConnectorType[]>("/api/v1/integrations/connectors");
}

export async function fetchConnections(
  engagementId?: string,
): Promise<IntegrationConnectionList> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<IntegrationConnectionList>(
    `/api/v1/integrations/connections${params}`,
  );
}

export async function testConnection(
  connectionId: string,
): Promise<{ connection_id: string; success: boolean; message: string }> {
  return apiPost<{ connection_id: string; success: boolean; message: string }>(
    `/api/v1/integrations/connections/${connectionId}/test`,
    {},
  );
}

export async function syncConnection(
  connectionId: string,
): Promise<{ connection_id: string; records_synced: number; errors: string[] }> {
  return apiPost<{
    connection_id: string;
    records_synced: number;
    errors: string[];
  }>(`/api/v1/integrations/connections/${connectionId}/sync`, {});
}
