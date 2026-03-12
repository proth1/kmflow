/**
 * Shared utility functions for task mining admin pages.
 *
 * Extracted from page files to comply with Next.js 15 page export constraints.
 */

// -- Agent Management utilities -----------------------------------------------

export function formatTimeAgo(dateStr: string | null): string {
  if (!dateStr) return "Never";
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// -- Capture Policy utilities -------------------------------------------------

const BUNDLE_ID_PATTERN = /^[a-zA-Z][a-zA-Z0-9-]*(\.[a-zA-Z0-9][a-zA-Z0-9-]*)+$/;

export function isValidBundleId(id: string): boolean {
  return BUNDLE_ID_PATTERN.test(id);
}

// -- Dashboard utilities ------------------------------------------------------

export type AgentHealth = "healthy" | "warning" | "critical";

export function getAgentHealth(lastHeartbeat: string | null): AgentHealth {
  if (!lastHeartbeat) return "critical";
  const elapsed = Date.now() - new Date(lastHeartbeat).getTime();
  const minutes = elapsed / 60000;
  if (minutes < 15) return "healthy";
  if (minutes < 60) return "warning";
  return "critical";
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

// -- Quarantine utilities -----------------------------------------------------

export function getTimeRemaining(autoDeleteAt: string): { text: string; urgent: boolean; expired: boolean } {
  const remaining = new Date(autoDeleteAt).getTime() - Date.now();
  if (remaining <= 0) return { text: "Expired", urgent: true, expired: true };
  const hours = remaining / 3600000;
  if (hours < 1) {
    const minutes = Math.floor(remaining / 60000);
    return { text: `${minutes}m remaining`, urgent: true, expired: false };
  }
  if (hours < 2) return { text: `${hours.toFixed(1)}h remaining`, urgent: true, expired: false };
  if (hours < 24) return { text: `${Math.floor(hours)}h remaining`, urgent: false, expired: false };
  return { text: `${Math.floor(hours / 24)}d remaining`, urgent: false, expired: false };
}
