"use client";

import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { ComponentErrorBoundary } from "@/components/ComponentErrorBoundary";

const GraphExplorer = dynamic(() => import("@/components/GraphExplorer"), {
  ssr: false,
  loading: () => <p className="text-sm text-gray-500">Loading graph component...</p>,
});

interface CytoscapeData {
  nodes: Array<{ data: Record<string, unknown> }>;
  edges: Array<{ data: Record<string, unknown> }>;
}

export default function GraphExplorerPage() {
  const params = useParams();
  const engagementId = params.engagementId as string;
  const [data, setData] = useState<CytoscapeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const result = await apiGet<CytoscapeData>(
          `/api/v1/graph/${engagementId}/export/cytoscape`,
        );
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load graph data");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [engagementId]);

  if (loading) {
    return (
      <main className="min-h-screen bg-gray-50 p-8">
        <div className="mx-auto max-w-7xl">
          <h1 className="mb-6 text-2xl font-bold text-gray-900">Knowledge Graph Explorer</h1>
          <p className="text-sm text-gray-500">Loading graph data...</p>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="min-h-screen bg-gray-50 p-8">
        <div className="mx-auto max-w-7xl">
          <h1 className="mb-6 text-2xl font-bold text-gray-900">Knowledge Graph Explorer</h1>
          <div className="rounded-lg border border-red-200 bg-red-50 p-6">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="mx-auto max-w-7xl">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">
          Knowledge Graph Explorer
        </h1>
        <p className="mb-4 text-sm text-gray-500">
          Engagement: {engagementId} | Nodes: {data?.nodes.length ?? 0} | Edges: {data?.edges.length ?? 0}
        </p>
        <div style={{ height: "calc(100vh - 250px)" }}>
          <ComponentErrorBoundary componentName="GraphExplorer">
            <GraphExplorer
              nodes={(data?.nodes ?? []) as any}
              edges={(data?.edges ?? []) as any}
            />
          </ComponentErrorBoundary>
        </div>
      </div>
    </main>
  );
}
