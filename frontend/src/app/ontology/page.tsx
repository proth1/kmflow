"use client";

import { useState, useCallback } from "react";
import dynamic from "next/dynamic";
import {
  getOntology,
  deriveOntology,
  validateOntology,
  exportOntology,
  type OntologyResponse,
  type ValidationReport,
} from "@/lib/api/ontology";
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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const OntologyGraph = dynamic(() => import("./OntologyGraph"), { ssr: false });

interface OntologyData {
  ontology: OntologyResponse;
}

function confidenceBadge(confidence: number): string {
  if (confidence >= 0.8) return "bg-green-100 text-green-800";
  if (confidence >= 0.5) return "bg-yellow-100 text-yellow-800";
  return "bg-red-100 text-red-800";
}

export default function OntologyPage() {
  const [engagementId, setEngagementId] = useState("");
  const [deriving, setDeriving] = useState(false);
  const [deriveError, setDeriveError] = useState<string | null>(null);
  const [validateError, setValidateError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationReport | null>(null);

  const fetchData = useCallback(
    async (id: string, _signal: AbortSignal) => {
      const ontology = await getOntology(id);
      return { ontology } as OntologyData;
    },
    [],
  );

  const { data, loading, error, refetch } = useEngagementData<OntologyData>(
    engagementId,
    fetchData,
  );

  const handleDerive = async () => {
    if (!engagementId) return;
    setDeriving(true);
    setDeriveError(null);
    try {
      await deriveOntology(engagementId);
      refetch();
    } catch (e) {
      setDeriveError(e instanceof Error ? e.message : "Derivation failed");
    } finally {
      setDeriving(false);
    }
  };

  const handleValidate = async () => {
    if (!engagementId) return;
    setValidateError(null);
    try {
      const report = await validateOntology(engagementId);
      setValidation(report);
    } catch (e) {
      setValidateError(e instanceof Error ? e.message : "Validation failed");
    }
  };

  const handleExport = async (format: "owl" | "yaml") => {
    if (!engagementId) return;
    setExportError(null);
    try {
      const result = await exportOntology(engagementId, format);
      const blob = new Blob([result.content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ontology-v${result.version}.${format === "owl" ? "owl.xml" : "yaml"}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    }
  };

  const ontology = data?.ontology;

  return (
    <PageLayout title="Domain Ontology" description="Derived domain ontology from knowledge graph">
      <div className="space-y-6">
        {/* Engagement selector */}
        <Card>
          <CardHeader>
            <CardTitle>Engagement</CardTitle>
            <CardDescription>Enter engagement ID to view or derive ontology</CardDescription>
          </CardHeader>
          <CardContent className="flex gap-4">
            <Input
              value={engagementId}
              onChange={(e) => setEngagementId(e.target.value)}
              placeholder="Engagement ID"
              className="max-w-md"
            />
            <Button onClick={handleDerive} disabled={!engagementId || deriving}>
              {deriving ? "Deriving..." : "Derive Ontology"}
            </Button>
          </CardContent>
          {deriveError && <CardContent><p className="text-red-600 text-sm">{deriveError}</p></CardContent>}
        </Card>

        {loading && <p className="text-muted-foreground">Loading ontology...</p>}
        {error && <p className="text-red-600">Failed to load ontology</p>}

        {ontology && (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Version</CardDescription>
                  <CardTitle className="text-2xl">{ontology.version}</CardTitle>
                </CardHeader>
                <CardContent>
                  <Badge variant="outline">{ontology.status}</Badge>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Classes</CardDescription>
                  <CardTitle className="text-2xl">{ontology.classes.length}</CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Properties</CardDescription>
                  <CardTitle className="text-2xl">{ontology.properties.length}</CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Completeness</CardDescription>
                  <CardTitle className="text-2xl">{(ontology.completeness_score * 100).toFixed(0)}%</CardTitle>
                </CardHeader>
              </Card>
            </div>

            {/* Actions */}
            <div className="flex gap-2">
              <Button variant="outline" onClick={handleValidate}>Validate</Button>
              <Button variant="outline" onClick={() => handleExport("yaml")}>Export YAML</Button>
              <Button variant="outline" onClick={() => handleExport("owl")}>Export OWL</Button>
            </div>
            {validateError && <p className="text-red-600 text-sm">{validateError}</p>}
            {exportError && <p className="text-red-600 text-sm">{exportError}</p>}

            {/* Validation report */}
            {validation && (
              <Card>
                <CardHeader>
                  <CardTitle>Validation Report</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {validation.orphan_classes.length > 0 && (
                    <div>
                      <p className="font-medium text-sm mb-1">Orphan Classes</p>
                      <div className="flex gap-2 flex-wrap">
                        {validation.orphan_classes.map((o) => (
                          <Badge key={o.name} variant="destructive">{o.name} ({o.instance_count})</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  {validation.recommendations.length > 0 && (
                    <div>
                      <p className="font-medium text-sm mb-1">Recommendations</p>
                      <ul className="list-disc pl-5 text-sm text-muted-foreground space-y-1">
                        {validation.recommendations.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Tabbed detail view */}
            <Tabs defaultValue="graph">
              <TabsList>
                <TabsTrigger value="graph">Graph</TabsTrigger>
                <TabsTrigger value="classes">Classes ({ontology.classes.length})</TabsTrigger>
                <TabsTrigger value="properties">Properties ({ontology.properties.length})</TabsTrigger>
                <TabsTrigger value="axioms">Axioms ({ontology.axioms.length})</TabsTrigger>
              </TabsList>

              <TabsContent value="graph">
                <Card>
                  <CardContent className="pt-6">
                    <OntologyGraph classes={ontology.classes} properties={ontology.properties} />
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="classes">
                <Card>
                  <CardContent className="pt-6">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Name</TableHead>
                          <TableHead>Parent</TableHead>
                          <TableHead>Instances</TableHead>
                          <TableHead>Confidence</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {ontology.classes.map((c) => (
                          <TableRow key={c.id}>
                            <TableCell className="font-medium">{c.name}</TableCell>
                            <TableCell>{c.parent ?? "-"}</TableCell>
                            <TableCell>{c.instance_count}</TableCell>
                            <TableCell>
                              <Badge className={confidenceBadge(c.confidence)}>
                                {(c.confidence * 100).toFixed(0)}%
                              </Badge>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="properties">
                <Card>
                  <CardContent className="pt-6">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Name</TableHead>
                          <TableHead>Edge Type</TableHead>
                          <TableHead>Domain</TableHead>
                          <TableHead>Range</TableHead>
                          <TableHead>Usage</TableHead>
                          <TableHead>Confidence</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {ontology.properties.map((p) => (
                          <TableRow key={p.id}>
                            <TableCell className="font-medium">{p.name}</TableCell>
                            <TableCell><code className="text-xs">{p.source_edge_type}</code></TableCell>
                            <TableCell>{p.domain ?? "-"}</TableCell>
                            <TableCell>{p.range ?? "-"}</TableCell>
                            <TableCell>{p.usage_count}</TableCell>
                            <TableCell>
                              <Badge className={confidenceBadge(p.confidence)}>
                                {(p.confidence * 100).toFixed(0)}%
                              </Badge>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="axioms">
                <Card>
                  <CardContent className="pt-6">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Expression</TableHead>
                          <TableHead>Type</TableHead>
                          <TableHead>Confidence</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {ontology.axioms.map((a) => (
                          <TableRow key={a.id}>
                            <TableCell className="font-medium">{a.expression}</TableCell>
                            <TableCell><Badge variant="outline">{a.type}</Badge></TableCell>
                            <TableCell>
                              <Badge className={confidenceBadge(a.confidence)}>
                                {(a.confidence * 100).toFixed(0)}%
                              </Badge>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </>
        )}
      </div>
    </PageLayout>
  );
}
