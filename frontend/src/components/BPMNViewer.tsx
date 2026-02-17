/**
 * BPMN process diagram viewer component.
 *
 * Uses the bpmn-js library to render BPMN XML with optional
 * confidence heatmap and evidence count overlays. This component
 * must be loaded client-side only (no SSR) because bpmn-js
 * requires the DOM.
 */
"use client";

import { useEffect, useRef, useCallback, useState } from "react";

// Confidence level color mapping
const CONFIDENCE_COLORS: Record<string, string> = {
  VERY_HIGH: "#15803d",
  HIGH: "#22c55e",
  MEDIUM: "#eab308",
  LOW: "#f97316",
  VERY_LOW: "#ef4444",
};

function getConfidenceColor(score: number): string {
  if (score >= 0.9) return CONFIDENCE_COLORS.VERY_HIGH;
  if (score >= 0.75) return CONFIDENCE_COLORS.HIGH;
  if (score >= 0.5) return CONFIDENCE_COLORS.MEDIUM;
  if (score >= 0.25) return CONFIDENCE_COLORS.LOW;
  return CONFIDENCE_COLORS.VERY_LOW;
}

interface BPMNViewerProps {
  bpmnXml: string;
  elementConfidences?: Record<string, number>;
  evidenceCounts?: Record<string, number>;
  showConfidenceOverlay?: boolean;
  showEvidenceOverlay?: boolean;
  onElementClick?: (elementId: string, elementName: string) => void;
}

export default function BPMNViewerComponent({
  bpmnXml,
  elementConfidences = {},
  evidenceCounts = {},
  showConfidenceOverlay = false,
  showEvidenceOverlay = false,
  onElementClick,
}: BPMNViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const initViewer = useCallback(async () => {
    if (!containerRef.current || !bpmnXml) return;

    setLoading(true);
    setError(null);

    try {
      // Dynamic import to avoid SSR issues
      const BpmnJS = (await import("bpmn-js")).default;

      // Clean up previous instance
      if (viewerRef.current) {
        viewerRef.current.destroy();
      }

      const viewer = new BpmnJS({
        container: containerRef.current,
      });

      viewerRef.current = viewer;

      await viewer.importXML(bpmnXml);

      // Fit the diagram to the container
      const canvas = viewer.get("canvas") as any;
      canvas.zoom("fit-viewport");

      // Apply overlays
      if (showConfidenceOverlay || showEvidenceOverlay) {
        const overlays = viewer.get("overlays") as any;
        const elementRegistry = viewer.get("elementRegistry") as any;

        elementRegistry.forEach((element: any) => {
          if (!element.businessObject) return;
          const name = element.businessObject.name;
          if (!name) return;

          // Confidence heatmap overlay
          if (showConfidenceOverlay && elementConfidences[name] !== undefined) {
            const score = elementConfidences[name];
            const color = getConfidenceColor(score);
            const pct = Math.round(score * 100);

            try {
              overlays.add(element.id, "confidence", {
                position: { top: -14, left: 0 },
                html: `<div style="
                  background: ${color};
                  color: white;
                  padding: 1px 6px;
                  border-radius: 8px;
                  font-size: 10px;
                  font-weight: 700;
                  white-space: nowrap;
                  pointer-events: none;
                ">${pct}%</div>`,
              });
            } catch {
              // Overlay add can fail for certain element types
            }
          }

          // Evidence count overlay
          if (showEvidenceOverlay && evidenceCounts[name] !== undefined) {
            const count = evidenceCounts[name];
            try {
              overlays.add(element.id, "evidence", {
                position: { top: -14, right: 0 },
                html: `<div style="
                  background: #3b82f6;
                  color: white;
                  min-width: 18px;
                  height: 18px;
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  border-radius: 9px;
                  font-size: 10px;
                  font-weight: 700;
                  pointer-events: none;
                  padding: 0 4px;
                ">${count}</div>`,
              });
            } catch {
              // Overlay add can fail for certain element types
            }
          }
        });
      }

      // Element click handler
      if (onElementClick) {
        const eventBus = viewer.get("eventBus") as any;
        eventBus.on("element.click", (event: any) => {
          const element = event.element;
          if (element.businessObject?.name) {
            onElementClick(element.id, element.businessObject.name);
          }
        });
      }

      setLoading(false);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to render BPMN diagram",
      );
      setLoading(false);
    }
  }, [
    bpmnXml,
    elementConfidences,
    evidenceCounts,
    showConfidenceOverlay,
    showEvidenceOverlay,
    onElementClick,
  ]);

  useEffect(() => {
    initViewer();

    return () => {
      if (viewerRef.current) {
        viewerRef.current.destroy();
        viewerRef.current = null;
      }
    };
  }, [initViewer]);

  if (error) {
    return (
      <div
        style={{
          padding: "24px",
          backgroundColor: "#fef2f2",
          border: "1px solid #fecaca",
          borderRadius: "8px",
          color: "#dc2626",
          textAlign: "center",
        }}
        data-testid="bpmn-error"
      >
        <strong>Failed to render BPMN diagram</strong>
        <div style={{ fontSize: "13px", marginTop: "8px" }}>{error}</div>
      </div>
    );
  }

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      {loading && (
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            color: "#6b7280",
            fontSize: "14px",
          }}
          data-testid="bpmn-loading"
        >
          Loading diagram...
        </div>
      )}
      <div
        ref={containerRef}
        style={{
          width: "100%",
          height: "100%",
          minHeight: "400px",
        }}
        data-testid="bpmn-container"
      />
    </div>
  );
}
