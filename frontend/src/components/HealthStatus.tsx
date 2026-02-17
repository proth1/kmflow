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
      <div className="health-status" data-testid="health-loading">
        Checking backend health...
      </div>
    );
  }

  if (error) {
    return (
      <div className="health-status health-error" data-testid="health-error">
        <span className="status-indicator status-down" />
        Backend unreachable: {error}
      </div>
    );
  }

  if (!health) {
    return null;
  }

  const statusColor =
    health.status === "healthy"
      ? "#22c55e"
      : health.status === "degraded"
        ? "#f59e0b"
        : "#ef4444";

  return (
    <div className="health-status" data-testid="health-status">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          marginBottom: "16px",
        }}
      >
        <span
          style={{
            width: "12px",
            height: "12px",
            borderRadius: "50%",
            backgroundColor: statusColor,
            display: "inline-block",
          }}
        />
        <strong>
          System: {health.status} (v{health.version})
        </strong>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: "12px",
        }}
      >
        {Object.entries(health.services).map(([service, status]) => (
          <div
            key={service}
            style={{
              padding: "12px",
              borderRadius: "8px",
              border: "1px solid #e5e7eb",
              textAlign: "center",
            }}
          >
            <span
              style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                backgroundColor: status === "up" ? "#22c55e" : "#ef4444",
                display: "inline-block",
                marginRight: "6px",
              }}
            />
            <span style={{ textTransform: "capitalize" }}>{service}</span>
            <div
              style={{
                fontSize: "12px",
                color: status === "up" ? "#16a34a" : "#dc2626",
                marginTop: "4px",
              }}
            >
              {status}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
