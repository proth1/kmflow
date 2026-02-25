"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchQuarantine,
  quarantineAction,
  type QuarantineItem,
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
  ShieldAlert,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Trash2,
  Unlock,
  Clock,
} from "lucide-react";

type QuarantineFilter = "all" | "expiring_soon" | "expired";

function getTimeRemaining(autoDeleteAt: string): { text: string; urgent: boolean; expired: boolean } {
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

export default function QuarantineReviewPage() {
  const [items, setItems] = useState<QuarantineItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [releaseItem, setReleaseItem] = useState<string | null>(null);
  const [releaseReason, setReleaseReason] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [filter, setFilter] = useState<QuarantineFilter>("all");
  const [engagementId, setEngagementId] = useState("");

  const loadItems = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const result = await fetchQuarantine(engagementId || undefined);
      setItems(result.items);
    } catch (err) {
      if (!silent) {
        setError(err instanceof Error ? err.message : "Failed to load quarantine items");
      }
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  // Refresh every 60 seconds for countdown updates
  useEffect(() => {
    const interval = setInterval(() => loadItems(true), 60000);
    return () => clearInterval(interval);
  }, [loadItems]);

  useEffect(() => {
    if (!successMsg) return;
    const timer = setTimeout(() => setSuccessMsg(null), 5000);
    return () => clearTimeout(timer);
  }, [successMsg]);

  async function handleDelete(itemId: string) {
    setConfirmDelete(null);
    setActionLoading(itemId);
    setError(null);
    try {
      await quarantineAction(itemId, "delete");
      setSuccessMsg("Event deleted — PII confirmed and removed");
      await loadItems(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete quarantine item");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRelease(itemId: string) {
    if (releaseReason.trim().length < 10) return;
    setReleaseItem(null);
    setActionLoading(itemId);
    setError(null);
    try {
      await quarantineAction(itemId, "release", releaseReason.trim());
      setSuccessMsg("Event released — processed normally as false positive");
      setReleaseReason("");
      await loadItems(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to release quarantine item");
    } finally {
      setActionLoading(null);
    }
  }

  const filteredItems = items.filter((item) => {
    if (filter === "all") return true;
    const tr = getTimeRemaining(item.auto_delete_at);
    if (filter === "expiring_soon") return tr.urgent && !tr.expired;
    if (filter === "expired") return tr.expired;
    return true;
  });

  // Sort by expiry ascending (most urgent first)
  const sortedItems = [...filteredItems].sort(
    (a, b) => new Date(a.auto_delete_at).getTime() - new Date(b.auto_delete_at).getTime()
  );

  const expiringCount = items.filter((i) => {
    const tr = getTimeRemaining(i.auto_delete_at);
    return tr.urgent && !tr.expired;
  }).length;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">PII Quarantine Review</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Review, release, or delete events flagged by Layer 3 PII detection
          </p>
        </div>
        <ShieldAlert className="h-8 w-8 text-muted-foreground" />
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

      <div className="flex items-center gap-4 flex-wrap">
        <Input
          placeholder="Filter by engagement ID..."
          value={engagementId}
          onChange={(e) => setEngagementId(e.target.value)}
          className="max-w-sm"
          aria-label="Engagement ID filter"
        />
        <div className="flex gap-1">
          {(["all", "expiring_soon", "expired"] as const).map((f) => (
            <Button
              key={f}
              size="sm"
              variant={filter === f ? "default" : "outline"}
              onClick={() => setFilter(f)}
              className="text-xs"
            >
              {f === "all" && `All (${items.length})`}
              {f === "expiring_soon" && (
                <>
                  Expiring Soon
                  {expiringCount > 0 && (
                    <Badge variant="destructive" className="ml-1.5 text-[10px] px-1.5 py-0">
                      {expiringCount}
                    </Badge>
                  )}
                </>
              )}
              {f === "expired" && "Expired"}
            </Button>
          ))}
        </div>
        <Button
          variant="outline"
          onClick={() => loadItems()}
          disabled={loading}
          aria-label="Refresh quarantine list"
        >
          <RefreshCw className={`h-3 w-3 mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Quarantined Events</CardTitle>
          <CardDescription>
            {sortedItems.length} event{sortedItems.length !== 1 ? "s" : ""} in quarantine
            {expiringCount > 0 && ` — ${expiringCount} expiring soon`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && items.length === 0 ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
              Loading quarantine items...
            </div>
          ) : sortedItems.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <CheckCircle className="h-8 w-8 mx-auto mb-3 opacity-50" />
              <p>No events in quarantine</p>
              <p className="text-xs mt-1">PII filtering is working correctly</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>PII Type</TableHead>
                  <TableHead>Field</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Time Remaining</TableHead>
                  <TableHead>Quarantined</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedItems.map((item) => {
                  const tr = getTimeRemaining(item.auto_delete_at);
                  return (
                    <TableRow key={item.id}>
                      <TableCell>
                        <Badge variant="outline" className="font-mono text-xs">
                          {item.pii_type}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm">{item.pii_field}</TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={
                            item.detection_confidence >= 0.9
                              ? "bg-red-50 text-red-700 border-red-200"
                              : "bg-yellow-50 text-yellow-700 border-yellow-200"
                          }
                        >
                          {(item.detection_confidence * 100).toFixed(0)}%
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <Clock className={`h-3 w-3 ${tr.urgent ? "text-destructive" : "text-muted-foreground"}`} />
                          <span className={`text-xs ${tr.urgent ? "text-destructive font-medium" : "text-muted-foreground"}`}>
                            {tr.text}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(item.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right">
                        {releaseItem === item.id ? (
                          <div className="space-y-2">
                            <Input
                              placeholder="Reason for release (min 10 chars)..."
                              value={releaseReason}
                              onChange={(e) => setReleaseReason(e.target.value)}
                              className="text-xs"
                              aria-label="Release reason"
                            />
                            <div className="flex gap-2 justify-end">
                              <Button
                                size="sm"
                                onClick={() => handleRelease(item.id)}
                                disabled={
                                  releaseReason.trim().length < 10 ||
                                  actionLoading === item.id
                                }
                              >
                                {actionLoading === item.id ? (
                                  <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                                ) : (
                                  <Unlock className="h-3 w-3 mr-1" />
                                )}
                                Release
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                  setReleaseItem(null);
                                  setReleaseReason("");
                                }}
                              >
                                Cancel
                              </Button>
                            </div>
                          </div>
                        ) : confirmDelete === item.id ? (
                          <div className="flex items-center gap-2 justify-end">
                            <span className="text-xs text-muted-foreground">
                              Confirm delete?
                            </span>
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() => handleDelete(item.id)}
                              disabled={actionLoading === item.id}
                            >
                              Delete
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setConfirmDelete(null)}
                            >
                              Cancel
                            </Button>
                          </div>
                        ) : (
                          <div className="flex gap-2 justify-end">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setReleaseItem(item.id)}
                              disabled={actionLoading === item.id}
                              aria-label="Release quarantine item"
                            >
                              <Unlock className="h-3 w-3 mr-1" />
                              Release
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="text-destructive border-destructive/30 hover:bg-destructive/5"
                              onClick={() => setConfirmDelete(item.id)}
                              disabled={actionLoading === item.id}
                              aria-label="Delete quarantine item"
                            >
                              <Trash2 className="h-3 w-3 mr-1" />
                              Delete
                            </Button>
                          </div>
                        )}
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
  );
}

export { getTimeRemaining };
