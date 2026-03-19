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
interface BpmnCanvas {
  zoom(value: string): void;
  viewbox(): { x: number; y: number; width: number; height: number };
  viewbox(vb: { x: number; y: number; width: number; height: number }): void;
}
interface BpmnOverlays {
  add(elementId: string, type: string, overlay: object): void;
  remove(options: { type: string }): void;
}
interface BpmnElementRegistry {
  forEach(fn: (element: { id: string; type: string; businessObject?: { name?: string } }) => void): void;
}
interface BpmnEventBus {
  on(event: string, handler: (event: { element: { id: string; businessObject?: { name?: string } } }) => void): void;
}
interface BpmnViewer {
  importXML(xml: string): Promise<void>;
  get(service: "canvas"): BpmnCanvas;
  get(service: "overlays"): BpmnOverlays;
  get(service: "elementRegistry"): BpmnElementRegistry;
  get(service: "eventBus"): BpmnEventBus;
  destroy(): void;
}

  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<BpmnViewer | null>(null);
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

      viewerRef.current = viewer as unknown as BpmnViewer;

      await (viewer as unknown as BpmnViewer).importXML(bpmnXml);

      // Fit the diagram to the container
      const canvas = (viewer as unknown as BpmnViewer).get("canvas");
      canvas.zoom("fit-viewport");

      // Add padding so overlays and pool headers aren't clipped
      const vb = canvas.viewbox();
      const pad = 30;
      canvas.viewbox({
        x: vb.x - pad,
        y: vb.y - pad,
        width: vb.width + pad * 2,
        height: vb.height + pad * 2,
      });

      // Apply overlays
      if (showConfidenceOverlay || showEvidenceOverlay) {
        const overlays = (viewer as unknown as BpmnViewer).get("overlays");
        const elementRegistry = (viewer as unknown as BpmnViewer).get("elementRegistry");

        elementRegistry.forEach((element) => {
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
        const eventBus = (viewer as unknown as BpmnViewer).get("eventBus");
        eventBus.on("element.click", (event) => {
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
        className="p-6 bg-red-50 border border-red-200 rounded-lg text-red-600 text-center"
        data-testid="bpmn-error"
      >
        <strong>Failed to render BPMN diagram</strong>
        <div className="text-[13px] mt-2">{error}</div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full">
      {loading && (
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-gray-500 text-sm"
          data-testid="bpmn-loading"
        >
          Loading diagram...
        </div>
      )}
      <div
        ref={containerRef}
        className="w-full h-full min-h-[400px]"
        data-testid="bpmn-container"
      />
    </div>
  );
}
