"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchMetricDefinitions,
  fetchMetricSummary,
  type SuccessMetricData,
  type MetricSummaryData,
} from "@/lib/api";
import { isValidEngagementId } from "@/lib/validation";
import { PageLayout } from "@/components/layout/PageLayout";
import { useEngagementData } from "@/hooks/useEngagementData";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  TrendingUp,
  CheckCircle2,
  XCircle,
  Target,
} from "lucide-react";

export default function AnalyticsPage() {
  const [engagementId, setEngagementId] = useState("");
  const [metrics, setMetrics] = useState<SuccessMetricData[]>([]);

  const fetchSummary = useCallback(
    (id: string) => fetchMetricSummary(id),
    [],
  );

  const { data: summary, loading, error } = useEngagementData<MetricSummaryData>(
    engagementId,
    fetchSummary,
  );

  useEffect(() => {
    let mounted = true;
    fetchMetricDefinitions()
      .then((result) => {
        if (mounted) setMetrics(result.items);
      })
      .catch((err) => {
        if (mounted) console.error("Failed to load metric definitions:", err);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const idError =
    engagementId.length > 0 && !isValidEngagementId(engagementId)
      ? "Invalid engagement ID format"
      : null;

  return (
    <PageLayout
      title="Engagement Analytics"
      description="Track success metrics and platform KPIs across engagements"
      icon={<TrendingUp className="h-8 w-8 text-muted-foreground" />}
      engagementId={engagementId}
      onEngagementIdChange={setEngagementId}
      engagementIdError={idError}
      error={error}
      loading={loading}
      loadingText="Loading metrics..."
    >
      {summary && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Total Metrics</CardDescription>
              <CardTitle className="text-3xl">{summary.total}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>On Target</CardDescription>
              <CardTitle className="text-3xl text-green-600">
                {summary.on_target_count}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Below Target</CardDescription>
              <CardTitle className="text-3xl text-red-600">
                {summary.total - summary.on_target_count}
              </CardTitle>
            </CardHeader>
          </Card>
        </div>
      )}

      <Tabs defaultValue="summary">
        <TabsList>
          <TabsTrigger value="summary">
            <Target className="h-4 w-4 mr-1.5" />
            Performance Summary
          </TabsTrigger>
          <TabsTrigger value="definitions">
            <TrendingUp className="h-4 w-4 mr-1.5" />
            Metric Definitions
          </TabsTrigger>
        </TabsList>

        <TabsContent value="summary">
          <Card>
            <CardHeader>
              <CardTitle>Metric Performance</CardTitle>
              <CardDescription>
                Latest values, averages, and target compliance
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!summary || summary.metrics.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  {engagementId
                    ? "No metric readings found for this engagement"
                    : "Enter an engagement ID to view metrics"}
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Metric</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Latest</TableHead>
                      <TableHead>Average</TableHead>
                      <TableHead>Target</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Readings</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {summary.metrics.map((m) => (
                      <TableRow key={m.metric_id}>
                        <TableCell className="font-medium">
                          {m.metric_name}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{m.category}</Badge>
                        </TableCell>
                        <TableCell>
                          {m.latest_value !== null
                            ? `${m.latest_value} ${m.unit}`
                            : "\u2014"}
                        </TableCell>
                        <TableCell>
                          {m.avg_value !== null
                            ? `${m.avg_value} ${m.unit}`
                            : "\u2014"}
                        </TableCell>
                        <TableCell>
                          {m.target_value} {m.unit}
                        </TableCell>
                        <TableCell>
                          {m.on_target ? (
                            <span className="flex items-center gap-1 text-green-600">
                              <CheckCircle2 className="h-4 w-4" />
                              On Target
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-red-600">
                              <XCircle className="h-4 w-4" />
                              Below
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {m.reading_count}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="definitions">
          <Card>
            <CardHeader>
              <CardTitle>Success Metric Definitions</CardTitle>
              <CardDescription>
                Platform-wide metric definitions and targets
              </CardDescription>
            </CardHeader>
            <CardContent>
              {metrics.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No metrics defined. Seed via POST /api/v1/metrics/seed.
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Unit</TableHead>
                      <TableHead>Target</TableHead>
                      <TableHead>Description</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {metrics.map((m) => (
                      <TableRow key={m.id}>
                        <TableCell className="font-medium">
                          {m.name}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{m.category}</Badge>
                        </TableCell>
                        <TableCell>{m.unit}</TableCell>
                        <TableCell>{m.target_value}</TableCell>
                        <TableCell className="text-sm text-muted-foreground max-w-xs truncate">
                          {m.description || "\u2014"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageLayout>
  );
}
