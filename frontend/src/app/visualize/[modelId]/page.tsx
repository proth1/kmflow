/**
 * Process Visualization Page.
 *
 * Renders a BPMN process model with interactive overlays for
 * confidence heatmap and evidence counts. Clicking on elements
 * opens a detail sidebar.
 */
"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import Legend from "@/components/Legend";
import Sidebar, { type ElementDetail } from "@/components/Sidebar";
import { ComponentErrorBoundary } from "@/components/ComponentErrorBoundary";
import {
  fetchBPMNXml,
  fetchProcessElements,
  type BPMNData,
  type ProcessElementData,
} from "@/lib/api";

// Dynamic import to avoid SSR issues with bpmn-js
const BPMNViewer = dynamic(() => import("@/components/BPMNViewer"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[400px] text-[hsl(var(--muted-foreground))]">
      Loading BPMN viewer...
    </div>
  ),
});

export default function VisualizePage() {
  const params = useParams();
  const modelId = params.modelId as string;

  const [bpmnData, setBpmnData] = useState<BPMNData | null>(null);
  const [elements, setElements] = useState<ProcessElementData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Overlay toggles
  const [showConfidence, setShowConfidence] = useState(true);
  const [showEvidence, setShowEvidence] = useState(false);

  // Sidebar
  const [selectedElement, setSelectedElement] = useState<ElementDetail | null>(null);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const [bpmn, elemData] = await Promise.all([
          fetchBPMNXml(modelId),
          fetchProcessElements(modelId, 200),
        ]);
        setBpmnData(bpmn);
        setElements(elemData.items);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load process model",
        );
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [modelId]);

  // Build evidence count map from elements
  const evidenceCounts: Record<string, number> = {};
  for (const elem of elements) {
    evidenceCounts[elem.name] = elem.evidence_count;
  }

  const handleElementClick = useCallback(
    (_elementId: string, elementName: string) => {
      const elem = elements.find((e) => e.name === elementName);
      if (elem) {
        setSelectedElement({
          name: elem.name,
          elementType: elem.element_type,
          confidenceScore: elem.confidence_score,
          evidenceCount: elem.evidence_count,
          evidenceIds: elem.evidence_ids ?? undefined,
        });
      }
    },
    [elements],
  );

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto p-8">
        <div className="text-center text-[hsl(var(--muted-foreground))] py-12">
          Loading process model...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-7xl mx-auto p-8">
        <div className="text-center text-red-600 py-12 bg-red-50 rounded-xl border border-red-200">
          <h2 className="text-xl font-semibold mb-2">Error</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Process Visualization</h1>
        <p className="text-[hsl(var(--muted-foreground))] text-sm">
          Model ID: {modelId}
        </p>
      </div>

      {/* Overlay Controls */}
      <div className="flex gap-6 items-center mb-4 flex-wrap">
        <label className="flex items-center gap-2 text-sm text-[hsl(var(--foreground))] cursor-pointer">
          <input
            type="checkbox"
            checked={showConfidence}
            onChange={(e) => setShowConfidence(e.target.checked)}
          />
          Confidence Heatmap
        </label>
        <label className="flex items-center gap-2 text-sm text-[hsl(var(--foreground))] cursor-pointer">
          <input
            type="checkbox"
            checked={showEvidence}
            onChange={(e) => setShowEvidence(e.target.checked)}
          />
          Evidence Overlay
        </label>
      </div>

      {/* Legend */}
      {showConfidence && (
        <div className="mb-4">
          <Legend orientation="horizontal" />
        </div>
      )}

      {/* BPMN Viewer */}
      <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden h-[600px] relative">
        {bpmnData && (
          <ComponentErrorBoundary componentName="BPMNViewer">
            <BPMNViewer
              bpmnXml={bpmnData.bpmn_xml}
              elementConfidences={bpmnData.element_confidences}
              evidenceCounts={evidenceCounts}
              showConfidenceOverlay={showConfidence}
              showEvidenceOverlay={showEvidence}
              onElementClick={handleElementClick}
            />
          </ComponentErrorBoundary>
        )}
      </div>

      {/* Element Detail Sidebar */}
      <Sidebar
        element={selectedElement}
        onClose={() => setSelectedElement(null)}
      />
    </div>
  );
}
