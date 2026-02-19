"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { fetchLineageChain, LineageChainData } from "@/lib/api";
import { GitBranch, ArrowRight } from "lucide-react";

export default function LineagePage() {
  const [engagementId, setEngagementId] = useState("");
  const [evidenceId, setEvidenceId] = useState("");
  const [lineage, setLineage] = useState<LineageChainData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLookup() {
    if (!engagementId.trim() || !evidenceId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLineageChain(engagementId.trim(), evidenceId.trim());
      setLineage(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch lineage");
      setLineage(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Data Lineage</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Trace the provenance and transformation history of evidence items
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Lineage Lookup</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-3">
            <Input
              placeholder="Engagement ID"
              value={engagementId}
              onChange={(e) => setEngagementId(e.target.value)}
            />
            <Input
              placeholder="Evidence Item ID"
              value={evidenceId}
              onChange={(e) => setEvidenceId(e.target.value)}
            />
            <Button onClick={handleLookup} disabled={loading || !engagementId.trim() || !evidenceId.trim()}>
              {loading ? "Loading..." : "Trace Lineage"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <Card className="border-red-200">
          <CardContent className="pt-6">
            <p className="text-sm text-red-600">{error}</p>
          </CardContent>
        </Card>
      )}

      {lineage && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <CardContent className="pt-6 text-center">
                <p className="text-2xl font-bold">{lineage.total_versions}</p>
                <p className="text-xs text-muted-foreground">Total Versions</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6 text-center">
                <p className="text-sm font-medium truncate">{lineage.evidence_name}</p>
                <p className="text-xs text-muted-foreground">Evidence Item</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6 text-center">
                <Badge variant="outline">{lineage.source_system || "Unknown"}</Badge>
                <p className="text-xs text-muted-foreground mt-1">Source System</p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <GitBranch className="h-4 w-4" />
                Transformation Chain
              </CardTitle>
            </CardHeader>
            <CardContent>
              {lineage.lineage.length === 0 ? (
                <p className="text-sm text-muted-foreground">No lineage records found.</p>
              ) : (
                <div className="space-y-4">
                  {lineage.lineage.map((record, idx) => (
                    <div key={record.id} className="flex items-start gap-3">
                      <div className="flex flex-col items-center">
                        <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold">
                          v{record.version}
                        </div>
                        {idx < lineage.lineage.length - 1 && (
                          <div className="w-px h-8 bg-border" />
                        )}
                      </div>
                      <div className="flex-1 border rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-medium">
                            {record.source_system}
                          </span>
                          {record.source_identifier && (
                            <>
                              <ArrowRight className="h-3 w-3 text-muted-foreground" />
                              <span className="text-xs text-muted-foreground">
                                {record.source_identifier}
                              </span>
                            </>
                          )}
                        </div>
                        {record.version_hash && (
                          <p className="text-xs text-muted-foreground font-mono">
                            Hash: {record.version_hash.slice(0, 12)}...
                          </p>
                        )}
                        {record.transformation_chain && record.transformation_chain.length > 0 && (
                          <div className="mt-2 space-y-1">
                            {record.transformation_chain.map((step, i) => (
                              <div key={i} className="text-xs bg-muted rounded px-2 py-1">
                                {(step as Record<string, string>).action || (step as Record<string, string>).step || JSON.stringify(step)}
                              </div>
                            ))}
                          </div>
                        )}
                        <p className="text-xs text-muted-foreground mt-1">
                          {new Date(record.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {!lineage && !error && !loading && (
        <Card>
          <CardContent className="pt-6 text-center text-muted-foreground">
            <GitBranch className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">Enter an engagement and evidence ID to trace lineage</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
