/**
 * API client core: base URL, auth headers, and generic fetch helpers.
 *
 * Auth is handled exclusively via the HttpOnly ``kmflow_access`` cookie set
 * by the backend on login (Issue #156).  The cookie is transmitted
 * automatically by the browser on every fetch that includes
 * ``credentials: "include"``.  No Authorization header injection is needed
 * for browser sessions.
 *
 * API/MCP clients that use Bearer tokens can pass them via the ``extra``
 * parameter if they need to inject an Authorization header.
 */

export const API_BASE_URL =
  typeof window === "undefined"
    ? process.env.API_URL || "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8002";

export function authHeaders(extra?: Record<string, string>): Record<string, string> {
  return { ...extra };
}

// -- Shared error / health types ----------------------------------------------

export interface ServiceHealth {
  postgres: "up" | "down";
  neo4j: "up" | "down";
  redis: "up" | "down";
  camunda?: "up" | "down";
}

export interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  services: ServiceHealth;
  version: string;
}

export interface ApiError {
  detail: string;
  status_code: number;
}

// -- Generic HTTP helpers -----------------------------------------------------

/**
 * Fetch the health status of the KMFlow backend.
 */
export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, {
    headers: authHeaders(),
    credentials: "include",
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }

  return response.json() as Promise<HealthResponse>;
}

/**
 * Generic GET request to the KMFlow API.
 */
export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: authHeaders(),
    credentials: "include",
    signal,
  });

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({ detail: `Request failed: ${response.status}`, status_code: response.status }));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

/**
 * Generic POST request to the KMFlow API.
 */
export async function apiPost<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({ detail: `Request failed: ${response.status}`, status_code: response.status }));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function apiPut<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({ detail: `Request failed: ${response.status}`, status_code: response.status }));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function apiPatch<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PATCH",
    headers: authHeaders({ "Content-Type": "application/json" }),
    credentials: "include",
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({ detail: `Request failed: ${response.status}`, status_code: response.status }));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function apiDelete(path: string, signal?: AbortSignal): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "DELETE",
    headers: authHeaders(),
    credentials: "include",
    signal,
  });
  if (!response.ok) {
    const error: ApiError = await response.json().catch(() => ({ detail: `Request failed: ${response.status}`, status_code: response.status }));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }
}
