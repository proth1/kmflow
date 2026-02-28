"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useParams, useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { ComponentErrorBoundary } from "@/components/ComponentErrorBoundary";
import ConfidenceHeatmapOverlay, {
  brightnessToOverlayColor,
  type HeatmapElementData,
} from "@/components/ConfidenceHeatmapOverlay";
import {
  fetchBPMNXml,
  fetchProcessElements,
  fetchConfidenceMap,
  fetchConfidenceSummary,
  getConfidenceSummaryCSVUrl,
  type BPMNData,
  type ProcessElementData,
  type ConfidenceMapData,
  type ConfidenceSummaryData,
} from "@/lib/api";

const BPMNViewer = dynamic(() => import("@/components/BPMNViewer"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[400px] text-muted-foreground">
      Loading BPMN viewer...
    </div>
  ),
});

export default function HeatmapPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const modelId = params.modelId as string;
  const engagementId = searchParams.get("engagement_id") ?? "";

  const [bpmnData, setBpmnData] = useState<BPMNData | null>(null);
  const [elements, setElements] = useState<ProcessElementData[]>([]);
  const [confidenceMap, setConfidenceMap] = useState<ConfidenceMapData | null>(null);
  const [summary, setSummary] = useState<ConfidenceSummaryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [heatmapActive, setHeatmapActive] = useState(true);

  // Tooltip state
  const [hoveredElement, setHoveredElement] = useState<HeatmapElementData | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<{ x: number; y: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Load all data
  useEffect(() => {
    if (!modelId || !engagementId) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [bpmn, elemData, confMap, summaryData] = await Promise.all([
          fetchBPMNXml(modelId),
          fetchProcessElements(modelId, 200),
          fetchConfidenceMap(engagementId),
          fetchConfidenceSummary(engagementId),
        ]);
        if (!cancelled) {
          setBpmnData(bpmn);
          setElements(elemData.items);
          setConfidenceMap(confMap);
          setSummary(summaryData);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load data");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();

    return () => { cancelled = true; };
  }, [modelId, engagementId]);

  // Build element confidences map for BPMNViewer (keyed by element name)
  // When heatmap is active, use brightness-based coloring via custom scores
  const elementConfidences: Record<string, number> = {};
  if (heatmapActive && confidenceMap && elements.length > 0) {
    for (const elem of elements) {
      // Map element name to its confidence entry via element ID
      const entry = confidenceMap.elements[elem.id];
      if (entry) {
        elementConfidences[elem.name] = entry.score;
      }
    }
  }

  // Build name->elementId lookup for hover
  const nameToElementId: Record<string, string> = {};
  for (const elem of elements) {
    nameToElementId[elem.name] = elem.id;
  }

  // Handle element hover for tooltip
  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!heatmapActive || !confidenceMap) return;

      const target = e.target as SVGElement;
      // Find the closest BPMN element by traversing up the SVG tree
      const gElement = target.closest("[data-element-id]") as SVGElement | null;

      if (gElement) {
        const elementId = gElement.getAttribute("data-element-id");
        if (elementId && confidenceMap.elements[elementId]) {
          const entry = confidenceMap.elements[elementId];
          setHoveredElement({
            elementId,
            score: entry.score,
            brightness: entry.brightness,
            grade: entry.grade,
          });
          setTooltipPosition({ x: e.clientX, y: e.clientY });
          return;
        }
      }

      // No element under cursor
      setHoveredElement(null);
      setTooltipPosition(null);
    },
    [heatmapActive, confidenceMap],
  );

  const handleMouseLeave = useCallback(() => {
    setHoveredElement(null);
    setTooltipPosition(null);
  }, []);

  if (!engagementId) {
    return (
      <div className="max-w-7xl mx-auto p-8">
        <div className="text-center text-muted-foreground py-12">
          No engagement selected. Add <code>?engagement_id=UUID</code> to the URL.
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto p-8">
        <div className="text-center text-muted-foreground py-12">
          Loading confidence heatmap...
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
    <div className="max-w-7xl mx-auto p-8 space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Confidence Heatmap</h1>
        <p className="text-muted-foreground text-sm">
          Bright/Dim/Dark classification overlay on process model
        </p>
      </div>

      <ConfidenceHeatmapOverlay
        elements={confidenceMap?.elements ?? {}}
        summary={summary}
        active={heatmapActive}
        onToggle={() => setHeatmapActive((v) => !v)}
        csvDownloadUrl={getConfidenceSummaryCSVUrl(engagementId)}
        hoveredElement={hoveredElement}
        tooltipPosition={tooltipPosition}
      />

      <div
        ref={containerRef}
        className="bg-card border rounded-xl overflow-hidden h-[600px] relative"
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
      >
        {bpmnData && (
          <ComponentErrorBoundary componentName="BPMNViewer">
            <BPMNViewer
              bpmnXml={bpmnData.bpmn_xml}
              elementConfidences={heatmapActive ? elementConfidences : {}}
              showConfidenceOverlay={heatmapActive}
              onElementClick={() => {}}
            />
          </ComponentErrorBoundary>
        )}
      </div>
    </div>
  );
}
