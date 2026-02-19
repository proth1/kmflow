"use client";

import { useState, useEffect } from "react";
import {
  fetchShelfRequests,
  type ShelfRequestData,
} from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ClipboardList, RefreshCw, AlertCircle } from "lucide-react";

function statusBadge(status: string) {
  switch (status) {
    case "completed":
      return <Badge className="bg-green-100 text-green-800">Completed</Badge>;
    case "sent":
      return <Badge className="bg-blue-100 text-blue-800">Sent</Badge>;
    case "draft":
      return <Badge variant="outline">Draft</Badge>;
    case "overdue":
      return <Badge variant="destructive">Overdue</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

export default function ShelfRequestsPage() {
  const [engagementId, setEngagementId] = useState("");
  const [requests, setRequests] = useState<ShelfRequestData[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!engagementId || engagementId.length < 8) return;

    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchShelfRequests(engagementId);
        if (!cancelled) setRequests(result.items);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to load shelf requests",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [engagementId]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Shelf Data Requests</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Track evidence requests sent to clients and monitor fulfillment
          </p>
        </div>
        <ClipboardList className="h-8 w-8 text-muted-foreground" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Engagement</CardTitle>
          <CardDescription>
            Enter an engagement ID to view its shelf requests
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Input
            type="text"
            value={engagementId}
            onChange={(e) => setEngagementId(e.target.value)}
            placeholder="Enter engagement UUID"
            className="max-w-md"
          />
        </CardContent>
      </Card>

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

      {loading && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin" />
          Loading shelf requests...
        </div>
      )}

      {requests.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Total Requests</CardDescription>
              <CardTitle className="text-3xl">{requests.length}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Total Items</CardDescription>
              <CardTitle className="text-3xl">
                {requests.reduce((s, r) => s + r.items.length, 0)}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Avg Fulfillment</CardDescription>
              <CardTitle className="text-3xl">
                {requests.length > 0
                  ? (
                      requests.reduce(
                        (s, r) => s + r.fulfillment_percentage,
                        0,
                      ) / requests.length
                    ).toFixed(0)
                  : 0}
                %
              </CardTitle>
            </CardHeader>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Shelf Requests</CardTitle>
          <CardDescription>
            Evidence collection requests and their fulfillment status
          </CardDescription>
        </CardHeader>
        <CardContent>
          {requests.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              {engagementId
                ? "No shelf requests found for this engagement"
                : "Enter an engagement ID to view shelf requests"}
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Items</TableHead>
                  <TableHead>Fulfillment</TableHead>
                  <TableHead>Due Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {requests.map((req) => (
                  <TableRow key={req.id}>
                    <TableCell>
                      <div>
                        <p className="font-medium">{req.title}</p>
                        {req.description && (
                          <p className="text-xs text-muted-foreground line-clamp-1">
                            {req.description}
                          </p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>{statusBadge(req.status)}</TableCell>
                    <TableCell>{req.items.length}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary rounded-full"
                            style={{
                              width: `${req.fulfillment_percentage}%`,
                            }}
                          />
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {req.fulfillment_percentage.toFixed(0)}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {req.due_date
                        ? new Date(req.due_date).toLocaleDateString()
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Expanded request items */}
      {requests.map(
        (req) =>
          req.items.length > 0 && (
            <Card key={`items-${req.id}`}>
              <CardHeader>
                <CardTitle className="text-base">
                  Items: {req.title}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Item Name</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Priority</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {req.items.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell className="font-medium">
                          {item.item_name}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{item.category}</Badge>
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              item.priority === "high"
                                ? "destructive"
                                : item.priority === "medium"
                                  ? "default"
                                  : "secondary"
                            }
                          >
                            {item.priority}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {item.status === "received" ? (
                            <span className="text-green-600 text-sm">
                              Received
                            </span>
                          ) : (
                            <span className="text-muted-foreground text-sm">
                              {item.status}
                            </span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          ),
      )}
    </div>
  );
}
