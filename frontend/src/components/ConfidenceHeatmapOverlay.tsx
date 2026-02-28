"use client";

import { useState, useCallback } from "react";
import { Download, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type {
  BrightnessLevel,
  EvidenceGrade,
  ElementConfidenceEntry,
  ConfidenceSummaryData,
} from "@/lib/api/dashboard";

// -- Brightness color mapping ------------------------------------------------

const BRIGHTNESS_COLORS: Record<string, { fill: string; label: string }> = {
  bright: { fill: "#22c55e", label: "Bright" },
  dim: { fill: "#eab308", label: "Dim" },
  dark: { fill: "#ef4444", label: "Dark" },
};

function brightnessToOverlayColor(brightness: string): string {
  return BRIGHTNESS_COLORS[brightness]?.fill ?? "#94a3b8";
}

function brightnessLabel(brightness: string): string {
  return BRIGHTNESS_COLORS[brightness]?.label ?? brightness;
}

// -- Types -------------------------------------------------------------------

export interface HeatmapElementData {
  elementId: string;
  score: number;
  brightness: BrightnessLevel;
  grade: EvidenceGrade;
}

interface ConfidenceHeatmapOverlayProps {
  /** Map of element_id to confidence entry */
  elements: Record<string, ElementConfidenceEntry>;
  /** Pre-fetched summary data for export */
  summary: ConfidenceSummaryData | null;
  /** Whether overlay is currently active */
  active: boolean;
  /** Toggle callback */
  onToggle: () => void;
  /** CSV download URL */
  csvDownloadUrl: string;
  /** Currently hovered element (for tooltip) */
  hoveredElement: HeatmapElementData | null;
  /** Position for tooltip */
  tooltipPosition: { x: number; y: number } | null;
}

/**
 * Heatmap controls overlay: toggle button, legend, tooltip, export.
 *
 * This component renders the UI controls around the BPMNViewer.
 * The actual color application to BPMN elements is handled by the
 * parent page via BPMNViewer's elementConfidences prop.
 */
export default function ConfidenceHeatmapOverlay({
  elements,
  summary,
  active,
  onToggle,
  csvDownloadUrl,
  hoveredElement,
  tooltipPosition,
}: ConfidenceHeatmapOverlayProps) {
  const [exporting, setExporting] = useState(false);

  const handleJSONExport = useCallback(async () => {
    if (!summary) return;
    setExporting(true);
    try {
      const blob = new Blob([JSON.stringify(summary, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `confidence-summary-${summary.engagement_id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [summary]);

  const handleCSVExport = useCallback(() => {
    window.open(csvDownloadUrl, "_blank");
  }, [csvDownloadUrl]);

  const totalElements = Object.keys(elements).length;

  return (
    <div className="space-y-3">
      {/* Toggle + Export Controls */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <Button
          variant={active ? "default" : "outline"}
          size="sm"
          onClick={onToggle}
          data-testid="heatmap-toggle"
        >
          {active ? (
            <EyeOff className="h-4 w-4 mr-2" />
          ) : (
            <Eye className="h-4 w-4 mr-2" />
          )}
          {active ? "Hide Heatmap" : "Show Heatmap"}
        </Button>

        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleJSONExport}
            disabled={!summary || exporting}
            data-testid="export-json-btn"
          >
            <Download className="h-4 w-4 mr-2" />
            Export JSON
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleCSVExport}
            data-testid="export-csv-btn"
          >
            <Download className="h-4 w-4 mr-2" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* Legend */}
      {active && (
        <div className="flex items-center gap-4" data-testid="heatmap-legend">
          {Object.entries(BRIGHTNESS_COLORS).map(([key, { fill, label }]) => (
            <div key={key} className="flex items-center gap-1.5">
              <div
                className="w-3 h-3 rounded-sm"
                style={{ backgroundColor: fill }}
              />
              <span className="text-xs text-muted-foreground">{label}</span>
            </div>
          ))}
          <span className="text-xs text-muted-foreground ml-2">
            {totalElements} elements
          </span>
        </div>
      )}

      {/* Summary Card (when heatmap active) */}
      {active && summary && (
        <Card data-testid="heatmap-summary-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Confidence Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-3">
              <div>
                <div className="text-lg font-bold">{summary.total_elements}</div>
                <div className="text-xs text-muted-foreground">Total</div>
              </div>
              <div>
                <div className="text-lg font-bold text-emerald-600">
                  {summary.bright_count}
                </div>
                <div className="text-xs text-muted-foreground">
                  Bright ({summary.bright_percentage}%)
                </div>
              </div>
              <div>
                <div className="text-lg font-bold text-yellow-600">
                  {summary.dim_count}
                </div>
                <div className="text-xs text-muted-foreground">
                  Dim ({summary.dim_percentage}%)
                </div>
              </div>
              <div>
                <div className="text-lg font-bold text-red-600">
                  {summary.dark_count}
                </div>
                <div className="text-xs text-muted-foreground">
                  Dark ({summary.dark_percentage}%)
                </div>
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2">
              <span className="text-xs text-muted-foreground">
                Overall Confidence:
              </span>
              <Badge variant="secondary">
                {(summary.overall_confidence * 100).toFixed(0)}%
              </Badge>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Hover Tooltip */}
      {active && hoveredElement && tooltipPosition && (
        <div
          className="fixed z-50 bg-popover border rounded-lg shadow-md px-3 py-2 pointer-events-none"
          style={{
            left: tooltipPosition.x + 12,
            top: tooltipPosition.y - 40,
          }}
          data-testid="heatmap-tooltip"
        >
          <div className="text-sm font-medium">
            Confidence: {(hoveredElement.score * 100).toFixed(0)}%
          </div>
          <div className="text-xs text-muted-foreground">
            {brightnessLabel(hoveredElement.brightness)}
          </div>
          <div className="text-xs text-muted-foreground">
            Grade: {hoveredElement.grade}
          </div>
        </div>
      )}
    </div>
  );
}

export { brightnessToOverlayColor, brightnessLabel, BRIGHTNESS_COLORS };
