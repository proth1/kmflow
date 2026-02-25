"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchAgents,
  approveAgent,
  revokeAgent,
  type TaskMiningAgent,
} from "@/lib/api/taskmining";
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
  Monitor,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  XCircle,
  ShieldAlert,
} from "lucide-react";

const STATUS_CONFIG: Record<
  string,
  { label: string; className: string }
> = {
  pending_approval: {
    label: "Pending",
    className: "bg-yellow-100 text-yellow-800 border-yellow-200",
  },
  approved: {
    label: "Approved",
    className: "bg-green-100 text-green-800 border-green-200",
  },
  revoked: {
    label: "Revoked",
    className: "bg-red-100 text-red-800 border-red-200",
  },
  consent_revoked: {
    label: "Consent Revoked",
    className: "bg-orange-100 text-orange-800 border-orange-200",
  },
};

function AgentStatusBadge({ status }: { status: string }) {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    className: "",
  };
  return (
    <Badge variant="outline" className={config.className}>
      {config.label}
    </Badge>
  );
}

function formatTimeAgo(dateStr: string | null): string {
  if (!dateStr) return "Never";
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function AgentManagementPage() {
  const [agents, setAgents] = useState<TaskMiningAgent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [engagementId, setEngagementId] = useState("");

  const loadAgents = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const result = await fetchAgents(engagementId || undefined);
      setAgents(result.agents);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load agents");
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => loadAgents(true), 30000);
    return () => clearInterval(interval);
  }, [loadAgents]);

  // Auto-clear success messages
  useEffect(() => {
    if (!successMsg) return;
    const timer = setTimeout(() => setSuccessMsg(null), 5000);
    return () => clearTimeout(timer);
  }, [successMsg]);

  async function handleApprove(agentId: string) {
    setActionLoading(agentId);
    setError(null);
    try {
      await approveAgent(agentId);
      setSuccessMsg("Agent approved — capture will begin on next check-in");
      await loadAgents(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve agent");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRevoke(agentId: string) {
    setConfirmRevoke(null);
    setActionLoading(agentId);
    setError(null);
    try {
      await revokeAgent(agentId);
      setSuccessMsg("Agent revoked — capture stopped");
      await loadAgents(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revoke agent");
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Task Mining Agents</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage desktop capture agents — approve, revoke, and monitor status
          </p>
        </div>
        <Monitor className="h-8 w-8 text-muted-foreground" />
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

      {successMsg && (
        <Card className="border-green-200 bg-green-50/50">
          <CardContent className="pt-6">
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-green-600 mt-0.5" />
              <p className="text-sm text-green-800">{successMsg}</p>
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
          onClick={() => loadAgents()}
          disabled={loading}
          aria-label="Refresh agent list"
        >
          <RefreshCw className={`h-3 w-3 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Registered Agents</CardTitle>
          <CardDescription>
            {agents.length} agent{agents.length !== 1 ? "s" : ""} registered
            {engagementId ? ` for engagement ${engagementId.substring(0, 8)}...` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && agents.length === 0 ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
              Loading agents...
            </div>
          ) : agents.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Monitor className="h-8 w-8 mx-auto mb-3 opacity-50" />
              <p>No agents registered yet</p>
              <p className="text-xs mt-1">Agents will appear here when they register with the backend</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Hostname</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Seen</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {agents.map((agent) => (
                  <TableRow key={agent.id}>
                    <TableCell className="font-medium">{agent.hostname}</TableCell>
                    <TableCell className="text-muted-foreground text-xs">
                      {agent.agent_version}
                    </TableCell>
                    <TableCell>
                      <AgentStatusBadge status={agent.status} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatTimeAgo(agent.last_heartbeat_at)}
                    </TableCell>
                    <TableCell className="text-xs">{agent.deployment_mode}</TableCell>
                    <TableCell className="text-right">
                      {agent.status === "pending_approval" && (
                        <Button
                          size="sm"
                          onClick={() => handleApprove(agent.id)}
                          disabled={actionLoading === agent.id}
                          aria-label={`Approve agent ${agent.hostname}`}
                        >
                          {actionLoading === agent.id ? (
                            <RefreshCw className="h-3 w-3 mr-1.5 animate-spin" />
                          ) : (
                            <CheckCircle className="h-3 w-3 mr-1.5" />
                          )}
                          Approve
                        </Button>
                      )}
                      {agent.status === "approved" && (
                        <>
                          {confirmRevoke === agent.id ? (
                            <div className="flex items-center gap-2 justify-end">
                              <span className="text-xs text-muted-foreground">
                                Stop capture?
                              </span>
                              <Button
                                size="sm"
                                variant="destructive"
                                onClick={() => handleRevoke(agent.id)}
                                disabled={actionLoading === agent.id}
                              >
                                Confirm
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => setConfirmRevoke(null)}
                              >
                                Cancel
                              </Button>
                            </div>
                          ) : (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setConfirmRevoke(agent.id)}
                              disabled={actionLoading === agent.id}
                              aria-label={`Revoke agent ${agent.hostname}`}
                            >
                              <XCircle className="h-3 w-3 mr-1.5" />
                              Revoke
                            </Button>
                          )}
                        </>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export { AgentStatusBadge, formatTimeAgo };
