/**
 * API client for communicating with the KMFlow backend.
 *
 * Wraps fetch with the base URL from environment variables
 * and provides typed response handling.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ServiceHealth {
  postgres: "up" | "down";
  neo4j: "up" | "down";
  redis: "up" | "down";
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

/**
 * Fetch the health status of the KMFlow backend.
 */
export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, {
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
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    const error: ApiError = await response.json();
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

/**
 * Generic POST request to the KMFlow API.
 */
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error: ApiError = await response.json();
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}
