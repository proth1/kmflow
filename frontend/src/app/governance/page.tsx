"use client";

import { useState, useEffect, useCallback } from "react";
import {
  fetchCatalogEntries,
  fetchGovernanceHealth,
  fetchPolicies,
  type CatalogEntryData,
  type GovernanceHealthData,
  type PolicyData,
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
import { Shield, CheckCircle2, XCircle } from "lucide-react";

interface GovernanceData {
  catalog: CatalogEntryData[];
  health: GovernanceHealthData;
}

export default function GovernancePage() {
  const [engagementId, setEngagementId] = useState("");
  const [policies, setPolicies] = useState<PolicyData | null>(null);

  const fetchGovernanceData = useCallback(
    async (id: string, signal: AbortSignal) => {
      const [catalogResult, healthResult] = await Promise.all([
        fetchCatalogEntries(id),
        fetchGovernanceHealth(id),
      ]);
      return { catalog: catalogResult, health: healthResult } as GovernanceData;
    },
    [],
  );

  const { data, loading, error } = useEngagementData<GovernanceData>(
    engagementId,
    fetchGovernanceData,
  );

  const catalog = data?.catalog ?? [];
  const health = data?.health ?? null;

  useEffect(() => {
    fetchPolicies()
      .then(setPolicies)
      .catch((err) => {
        console.error("Failed to load policies:", err);
      });
  }, []);

  const idError =
    engagementId.length > 0 && !isValidEngagementId(engagementId)
      ? "Invalid engagement ID format"
      : null;

  return (
    <PageLayout
      title="Data Governance"
      description="Catalog management, policy compliance, and SLA monitoring"
      icon={<Shield className="h-8 w-8 text-muted-foreground" />}
      engagementId={engagementId}
      onEngagementIdChange={setEngagementId}
      engagementIdError={idError}
      error={error}
      loading={loading}
      loadingText="Loading governance data..."
    >
      {health && (
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Total Entries</CardDescription>
              <CardTitle className="text-3xl">{health.total_entries}</CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Passing SLA</CardDescription>
              <CardTitle className="text-3xl text-green-600">
                {health.passing_count}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Failing SLA</CardDescription>
              <CardTitle className="text-3xl text-red-600">
                {health.failing_count}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Compliance</CardDescription>
              <CardTitle className="text-3xl">
                {health.compliance_percentage}%
              </CardTitle>
            </CardHeader>
          </Card>
        </div>
      )}

      <Tabs defaultValue="catalog">
        <TabsList>
          <TabsTrigger value="catalog">Data Catalog</TabsTrigger>
          <TabsTrigger value="health">SLA Health</TabsTrigger>
          <TabsTrigger value="policies">Policies</TabsTrigger>
        </TabsList>

        <TabsContent value="catalog">
          <Card>
            <CardHeader>
              <CardTitle>Data Catalog Entries</CardTitle>
              <CardDescription>
                All datasets registered in the governance catalog
              </CardDescription>
            </CardHeader>
            <CardContent>
              {catalog.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  {engagementId
                    ? "No catalog entries found"
                    : "Enter an engagement ID to view catalog"}
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Dataset Name</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Layer</TableHead>
                      <TableHead>Classification</TableHead>
                      <TableHead>Owner</TableHead>
                      <TableHead>Retention</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {catalog.map((entry) => (
                      <TableRow key={entry.id}>
                        <TableCell className="font-medium">
                          {entry.dataset_name}
                        </TableCell>
                        <TableCell>{entry.dataset_type}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{entry.layer}</Badge>
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              entry.classification === "confidential"
                                ? "destructive"
                                : "default"
                            }
                          >
                            {entry.classification}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {entry.owner || (
                            <span className="text-muted-foreground">&mdash;</span>
                          )}
                        </TableCell>
                        <TableCell>
                          {entry.retention_days
                            ? `${entry.retention_days}d`
                            : "\u2014"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="health">
          <Card>
            <CardHeader>
              <CardTitle>SLA Compliance Status</CardTitle>
              <CardDescription>
                Per-entry quality SLA pass/fail status
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!health || health.entries.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  No SLA data available
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Dataset</TableHead>
                      <TableHead>Classification</TableHead>
                      <TableHead>SLA Status</TableHead>
                      <TableHead>Violations</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {health.entries.map((entry) => (
                      <TableRow key={entry.entry_id}>
                        <TableCell className="font-medium">
                          {entry.name}
                        </TableCell>
                        <TableCell>{entry.classification}</TableCell>
                        <TableCell>
                          {entry.sla_passing ? (
                            <span className="flex items-center gap-1.5 text-green-600">
                              <CheckCircle2 className="h-4 w-4" />
                              Passing
                            </span>
                          ) : (
                            <span className="flex items-center gap-1.5 text-red-600">
                              <XCircle className="h-4 w-4" />
                              Failing
                            </span>
                          )}
                        </TableCell>
                        <TableCell>
                          {entry.violation_count > 0 ? (
                            <Badge variant="destructive">
                              {entry.violation_count}
                            </Badge>
                          ) : (
                            <span className="text-muted-foreground">0</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="policies">
          <Card>
            <CardHeader>
              <CardTitle>Active Governance Policies</CardTitle>
              <CardDescription>
                Policy definitions enforced across the platform
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!policies ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  Unable to load policies
                </p>
              ) : (
                <div className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Policy file: <code className="bg-muted px-1.5 py-0.5 rounded text-xs">{policies.policy_file}</code>
                  </p>
                  <pre className="bg-muted rounded-lg p-4 text-xs overflow-auto max-h-96">
                    {JSON.stringify(policies.policies, null, 2)}
                  </pre>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </PageLayout>
  );
}
