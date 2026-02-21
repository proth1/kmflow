/**
 * Shelf Requests API: evidence data request management.
 */

import { apiGet } from "./client";

// -- Types --------------------------------------------------------------------

export interface ShelfRequestItemData {
  id: string;
  request_id: string;
  category: string;
  item_name: string;
  description: string | null;
  priority: string;
  status: string;
  matched_evidence_id: string | null;
}

export interface ShelfRequestData {
  id: string;
  engagement_id: string;
  title: string;
  description: string | null;
  status: string;
  due_date: string | null;
  items: ShelfRequestItemData[];
  fulfillment_percentage: number;
}

export interface ShelfRequestList {
  items: ShelfRequestData[];
  total: number;
}

// -- API functions ------------------------------------------------------------

export async function fetchShelfRequests(
  engagementId?: string,
): Promise<ShelfRequestList> {
  const params = engagementId ? `?engagement_id=${engagementId}` : "";
  return apiGet<ShelfRequestList>(`/api/v1/shelf-requests${params}`);
}

export async function fetchShelfRequest(
  requestId: string,
): Promise<ShelfRequestData> {
  return apiGet<ShelfRequestData>(`/api/v1/shelf-requests/${requestId}`);
}

export async function fetchShelfRequestStatus(
  requestId: string,
): Promise<{
  id: string;
  title: string;
  status: string;
  total_items: number;
  received_items: number;
  pending_items: number;
  overdue_items: number;
  fulfillment_percentage: number;
}> {
  return apiGet(`/api/v1/shelf-requests/${requestId}/status`);
}
