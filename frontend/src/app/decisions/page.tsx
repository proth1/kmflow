"use client";

import { useState, useCallback } from "react";
import {
  fetchDecisions,
  fetchDecisionCoverage,
  type DecisionListResponse,
  type CoverageResponse,
} from "@/lib/api/decisions";
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

interface DecisionData {
  decisions: DecisionListResponse;
  coverage: CoverageResponse;
}

function brightnessColor(brightness: string): string {
  switch (brightness) {
    case "BRIGHT":
      return "bg-green-100 text-green-800";
    case "DIM":
      return "bg-yellow-100 text-yellow-800";
    case "DARK":
      return "bg-red-100 text-red-800";
    default:
      return "bg-gray-100 text-gray-800";
  }
}

export default function DecisionsPage() {
  const [engagementId, setEngagementId] = useState("");

  const fetchData = useCallback(
    async (id: string, signal: AbortSignal) => {
      const [decisions, coverage] = await Promise.all([
        fetchDecisions(id, { limit: 100 }, signal),
        fetchDecisionCoverage(id, signal),
      ]);
      return { decisions, coverage } as DecisionData;
    },
    [],
  );

  const { data, loading, error } = useEngagementData<DecisionData>(
    engagementId,
    fetchData,
  );

  const decisions = data?.decisions?.decisions ?? [];
  const coverage = data?.coverage ?? null;

  return (
    <PageLayout
      title="Decision Intelligence"
      description="Discover decision points, business rules, and coverage gaps"
    >
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          <input
            type="text"
            placeholder="Engagement ID"
            value={engagementId}
            onChange={(e) => setEngagementId(e.target.value)}
            className="border rounded px-3 py-2 w-80"
          />
        </div>

        {loading && <p className="text-muted-foreground">Loading...</p>}
        {error && <p className="text-red-600">{error}</p>}

        {data && (
          <Tabs defaultValue="decisions">
            <TabsList>
              <TabsTrigger value="decisions">
                Decision Points ({decisions.length})
              </TabsTrigger>
              <TabsTrigger value="coverage">
                Coverage Gaps ({coverage?.gaps?.length ?? 0})
              </TabsTrigger>
            </TabsList>

            <TabsContent value="decisions">
              <Card>
                <CardHeader>
                  <CardTitle>Discovered Decision Points</CardTitle>
                  <CardDescription>
                    Decision points extracted from evidence with confidence scoring
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Decision</TableHead>
                        <TableHead>Confidence</TableHead>
                        <TableHead>Brightness</TableHead>
                        <TableHead>Rules</TableHead>
                        <TableHead>Sources</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {decisions.map((d) => (
                        <TableRow key={d.id}>
                          <TableCell className="font-medium">{d.name}</TableCell>
                          <TableCell>{(d.confidence * 100).toFixed(1)}%</TableCell>
                          <TableCell>
                            <Badge className={brightnessColor(d.brightness)}>
                              {d.brightness}
                            </Badge>
                          </TableCell>
                          <TableCell>{d.rule_count}</TableCell>
                          <TableCell>{d.evidence_sources}</TableCell>
                        </TableRow>
                      ))}
                      {decisions.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={5} className="text-center text-muted-foreground">
                            No decision points discovered yet
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="coverage">
              <Card>
                <CardHeader>
                  <CardTitle>Form 5 (Rules) Coverage</CardTitle>
                  <CardDescription>
                    Activities missing business rules —{" "}
                    {coverage?.coverage_percentage?.toFixed(1) ?? 0}% covered
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Activity</TableHead>
                        <TableHead>Has Rules</TableHead>
                        <TableHead>Gap Weight</TableHead>
                        <TableHead>Probe Generated</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(coverage?.gaps ?? []).map((g) => (
                        <TableRow key={g.activity_name}>
                          <TableCell className="font-medium">{g.activity_name}</TableCell>
                          <TableCell>
                            <Badge variant={g.has_rules ? "default" : "destructive"}>
                              {g.has_rules ? "Yes" : "No"}
                            </Badge>
                          </TableCell>
                          <TableCell>{g.gap_weight}</TableCell>
                          <TableCell>
                            {g.probe_generated ? "Yes" : "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                      {(coverage?.gaps ?? []).length === 0 && (
                        <TableRow>
                          <TableCell colSpan={4} className="text-center text-muted-foreground">
                            No coverage gaps — all activities have rules
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        )}
      </div>
    </PageLayout>
  );
}
