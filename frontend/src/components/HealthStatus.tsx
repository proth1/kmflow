"use client";

import { useEffect, useState } from "react";
import type { HealthResponse } from "@/lib/api";
import { fetchHealth } from "@/lib/api";

/**
 * Displays the health status of the KMFlow backend services.
 * Polls the /health endpoint and shows per-service status indicators.
 */
export default function HealthStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function checkHealth() {
      try {
        const data = await fetchHealth();
        if (mounted) {
          setHealth(data);
          setError(null);
        }
      } catch (err) {
        if (mounted) {
          setError(
            err instanceof Error ? err.message : "Failed to reach backend"
          );
          setHealth(null);
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    checkHealth();

    // Poll every 30 seconds
    const interval = setInterval(checkHealth, 30000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  if (loading) {
    return (
      <div className="text-[hsl(var(--muted-foreground))] text-sm" data-testid="health-loading">
        Checking backend health...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 text-sm text-red-600" data-testid="health-error">
        <span className="w-3 h-3 rounded-full bg-red-500 shrink-0" />
        Backend unreachable: {error}
      </div>
    );
  }

  if (!health) {
    return null;
  }

  const statusDotClass =
    health.status === "healthy"
      ? "bg-green-500"
      : health.status === "degraded"
        ? "bg-amber-500"
        : "bg-red-500";

  return (
    <div data-testid="health-status">
      <div className="flex items-center gap-2 mb-4">
        <span className={`w-3 h-3 rounded-full ${statusDotClass}`} />
        <strong className="text-sm">
          System: {health.status} (v{health.version})
        </strong>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {Object.entries(health.services).map(([service, status]) => (
          <div
            key={service}
            className="p-3 rounded-lg border border-[hsl(var(--border))] text-center"
          >
            <span
              className={`w-2 h-2 rounded-full inline-block mr-1.5 ${status === "up" ? "bg-green-500" : "bg-red-500"}`}
            />
            <span className="capitalize text-sm">{service}</span>
            <div
              className={`text-xs mt-1 ${status === "up" ? "text-green-600" : "text-red-600"}`}
            >
              {status}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
