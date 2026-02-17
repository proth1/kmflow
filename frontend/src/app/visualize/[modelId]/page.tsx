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
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "400px",
        color: "#6b7280",
      }}
    >
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
  const [selectedElement, setSelectedElement] = useState<ElementDetail | null>(
    null,
  );

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
      <main
        style={{
          maxWidth: "1400px",
          margin: "0 auto",
          padding: "32px 24px",
        }}
      >
        <div style={{ textAlign: "center", color: "#6b7280", padding: "48px" }}>
          Loading process model...
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main
        style={{
          maxWidth: "1400px",
          margin: "0 auto",
          padding: "32px 24px",
        }}
      >
        <div
          style={{
            textAlign: "center",
            color: "#dc2626",
            padding: "48px",
            backgroundColor: "#fef2f2",
            borderRadius: "12px",
            border: "1px solid #fecaca",
          }}
        >
          <h2 style={{ margin: "0 0 8px 0" }}>Error</h2>
          <p>{error}</p>
        </div>
      </main>
    );
  }

  return (
    <main
      style={{
        maxWidth: "1400px",
        margin: "0 auto",
        padding: "32px 24px",
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <h1 style={{ fontSize: "28px", fontWeight: 700, margin: "0 0 8px 0" }}>
          Process Visualization
        </h1>
        <p style={{ margin: 0, color: "#6b7280", fontSize: "14px" }}>
          Model ID: {modelId}
        </p>
      </div>

      {/* Overlay Controls */}
      <div
        style={{
          display: "flex",
          gap: "24px",
          alignItems: "center",
          marginBottom: "16px",
          flexWrap: "wrap",
        }}
      >
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "14px",
            color: "#374151",
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={showConfidence}
            onChange={(e) => setShowConfidence(e.target.checked)}
          />
          Confidence Heatmap
        </label>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "14px",
            color: "#374151",
            cursor: "pointer",
          }}
        >
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
        <div style={{ marginBottom: "16px" }}>
          <Legend orientation="horizontal" />
        </div>
      )}

      {/* BPMN Viewer */}
      <div
        style={{
          backgroundColor: "#ffffff",
          border: "1px solid #e5e7eb",
          borderRadius: "12px",
          overflow: "hidden",
          height: "600px",
          position: "relative",
        }}
      >
        {bpmnData && (
          <BPMNViewer
            bpmnXml={bpmnData.bpmn_xml}
            elementConfidences={bpmnData.element_confidences}
            evidenceCounts={evidenceCounts}
            showConfidenceOverlay={showConfidence}
            showEvidenceOverlay={showEvidence}
            onElementClick={handleElementClick}
          />
        )}
      </div>

      {/* Element Detail Sidebar */}
      <Sidebar
        element={selectedElement}
        onClose={() => setSelectedElement(null)}
      />
    </main>
  );
}
