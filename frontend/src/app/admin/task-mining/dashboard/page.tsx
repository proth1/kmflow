"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  fetchDashboardStats,
  fetchAgents,
  fetchAppUsage,
  type DashboardStats,
  type TaskMiningAgent,
  type AppUsageEntry,
} from "@/lib/api/taskmining";
import { API_BASE_URL } from "@/lib/api/client";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import {
  BarChart3,
  RefreshCw,
  AlertCircle,
  Monitor,
  Activity,
  Shield,
  Zap,
  Wifi,
  WifiOff,
} from "lucide-react";

type AgentHealth = "healthy" | "warning" | "critical";

function getAgentHealth(lastHeartbeat: string | null): AgentHealth {
  if (!lastHeartbeat) return "critical";
  const elapsed = Date.now() - new Date(lastHeartbeat).getTime();
  const minutes = elapsed / 60000;
  if (minutes < 15) return "healthy";
  if (minutes < 60) return "warning";
  return "critical";
}

const HEALTH_CONFIG: Record<AgentHealth, { label: string; className: string }> = {
  healthy: { label: "Active", className: "bg-green-100 text-green-800 border-green-200" },
  warning: { label: "Stale", className: "bg-yellow-100 text-yellow-800 border-yellow-200" },
  critical: { label: "Offline", className: "bg-red-100 text-red-800 border-red-200" },
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

const DATE_RANGES = [
  { label: "Today", days: 1 },
  { label: "7 days", days: 7 },
  { label: "30 days", days: 30 },
] as const;

export default function TaskMiningDashboard() {
  const [engagementId, setEngagementId] = useState("");
  const debouncedEngagementId = useDebouncedValue(engagementId, 400);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [agents, setAgents] = useState<TaskMiningAgent[]>([]);
  const [appUsage, setAppUsage] = useState<AppUsageEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState(7);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);

  const loadData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const [statsResult, agentsResult] = await Promise.all([
        fetchDashboardStats(debouncedEngagementId || undefined),
        fetchAgents(debouncedEngagementId || undefined),
      ]);
      setStats(statsResult);
      setAgents(agentsResult.agents.filter((a) => a.status === "approved"));

      if (debouncedEngagementId) {
        const usage = await fetchAppUsage(debouncedEngagementId, dateRange);
        setAppUsage(usage);
      }
    } catch (err) {
      if (!silent) {
        setError(err instanceof Error ? err.message : "Failed to load dashboard data");
      }
    } finally {
      setLoading(false);
    }
  }, [debouncedEngagementId, dateRange]);

  // Initial load + periodic refresh
  useEffect(() => {
    loadData();
    const interval = setInterval(() => loadData(true), 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  // WebSocket for real-time stats updates
  useEffect(() => {
    const wsUrl = API_BASE_URL.replace(/^http/, "ws") + "/ws/taskmining/events";
    let retryDelay = 1000;

    function connect() {
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setWsConnected(true);
          retryDelay = 1000; // Reset backoff
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === "stats_update" && data.stats) {
              setStats(data.stats);
            }
          } catch {
            // Ignore malformed messages
          }
        };

        ws.onclose = () => {
          setWsConnected(false);
          // Exponential backoff reconnection
          reconnectTimerRef.current = setTimeout(() => {
            retryDelay = Math.min(retryDelay * 2, 30000);
            connect();
          }, retryDelay);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch {
        // WebSocket construction failed — retry
        reconnectTimerRef.current = setTimeout(() => {
          retryDelay = Math.min(retryDelay * 2, 30000);
          connect();
        }, retryDelay);
      }
    }

    connect();

    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const attentionAgents = agents.filter(
    (a) => getAgentHealth(a.last_heartbeat_at) !== "healthy"
  );

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Activity Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time task mining metrics and agent health
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge
            variant="outline"
            className={wsConnected
              ? "bg-green-50 text-green-700 border-green-200"
              : "bg-yellow-50 text-yellow-700 border-yellow-200"
            }
          >
            {wsConnected ? (
              <><Wifi className="h-3 w-3 mr-1" /> Live</>
            ) : (
              <><WifiOff className="h-3 w-3 mr-1" /> Reconnecting...</>
            )}
          </Badge>
          <BarChart3 className="h-8 w-8 text-muted-foreground" />
        </div>
      </div>

      {error && (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-destructive mt-0.5" />
              <p className="text-sm text-destructive">{error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex items-center gap-4">
        <Input
          placeholder="Filter by engagement ID..."
          value={engagementId}
          onChange={(e) => setEngagementId(e.target.value)}
          className="max-w-sm"
          aria-label="Engagement ID filter"
        />
        <Button
          variant="outline"
          onClick={() => loadData()}
          disabled={loading}
          aria-label="Refresh dashboard"
        >
          <RefreshCw className={`h-3 w-3 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold">{stats?.active_agents ?? "—"}</p>
                <p className="text-xs text-muted-foreground">Active Agents</p>
              </div>
              <Monitor className="h-8 w-8 text-muted-foreground opacity-50" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold">
                  {stats?.events_today != null ? stats.events_today.toLocaleString() : "—"}
                </p>
                <p className="text-xs text-muted-foreground">Events Today</p>
              </div>
              <Zap className="h-8 w-8 text-muted-foreground opacity-50" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold">
                  {stats?.actions_today != null ? stats.actions_today.toLocaleString() : "—"}
                </p>
                <p className="text-xs text-muted-foreground">Actions Today</p>
              </div>
              <Activity className="h-8 w-8 text-muted-foreground opacity-50" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-2xl font-bold">{stats?.quarantine_pending ?? "—"}</p>
                <p className="text-xs text-muted-foreground">Quarantine Pending</p>
              </div>
              <Shield className="h-8 w-8 text-muted-foreground opacity-50" />
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* App Usage Heatmap */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg">Application Usage</CardTitle>
                <CardDescription>Top apps by total session duration</CardDescription>
              </div>
              <div className="flex gap-1">
                {DATE_RANGES.map((range) => (
                  <Button
                    key={range.days}
                    size="sm"
                    variant={dateRange === range.days ? "default" : "outline"}
                    onClick={() => setDateRange(range.days)}
                    className="text-xs"
                  >
                    {range.label}
                  </Button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {appUsage.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <BarChart3 className="h-6 w-6 mx-auto mb-2 opacity-50" />
                <p className="text-sm">
                  {engagementId
                    ? "No app usage data for this period"
                    : "Enter an engagement ID to view usage"}
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {appUsage.slice(0, 10).map((app, idx) => {
                  const maxDuration = appUsage[0]?.total_duration_seconds ?? 1;
                  const pct = (app.total_duration_seconds / maxDuration) * 100;
                  return (
                    <div key={app.application_name} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium truncate max-w-[200px]">
                          {app.application_name}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {app.session_count} sessions &middot;{" "}
                          {formatDuration(app.total_duration_seconds)}
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-primary transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Agent Health */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Agent Health</CardTitle>
            <CardDescription>
              {agents.length} approved agent{agents.length !== 1 ? "s" : ""}
              {attentionAgents.length > 0 && (
                <Badge variant="outline" className="ml-2 bg-yellow-50 text-yellow-800 border-yellow-200">
                  {attentionAgents.length} need attention
                </Badge>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {agents.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Monitor className="h-6 w-6 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No active agents</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Hostname</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Last Seen</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {agents.map((agent) => {
                    const health = getAgentHealth(agent.last_heartbeat_at);
                    const hConfig = HEALTH_CONFIG[health];
                    return (
                      <TableRow key={agent.id}>
                        <TableCell className="font-medium text-sm">
                          {agent.hostname}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline" className={hConfig.className}>
                            {hConfig.label}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right text-xs text-muted-foreground">
                          {agent.last_heartbeat_at
                            ? new Date(agent.last_heartbeat_at).toLocaleTimeString()
                            : "Never"}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export { getAgentHealth, formatDuration };
