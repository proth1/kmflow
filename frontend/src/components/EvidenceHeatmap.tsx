"use client";

import { Badge } from "@/components/ui/badge";
import type { ElementCoverageData } from "@/lib/api";

interface EvidenceHeatmapProps {
  elements: ElementCoverageData[];
}

const classificationStyles: Record<
  string,
  { bg: string; border: string; text: string; label: string }
> = {
  bright: {
    bg: "bg-emerald-50",
    border: "border-emerald-300",
    text: "text-emerald-800",
    label: "Bright",
  },
  dim: {
    bg: "bg-amber-50",
    border: "border-amber-300",
    text: "text-amber-800",
    label: "Dim",
  },
  dark: {
    bg: "bg-slate-100",
    border: "border-slate-300",
    text: "text-slate-600",
    label: "Dark",
  },
};

export default function EvidenceHeatmap({ elements }: EvidenceHeatmapProps) {
  const activeElements = elements.filter((e) => !e.is_removed);

  if (activeElements.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4 text-center">
        No process elements found for this scenario.
      </p>
    );
  }

  return (
    <div
      className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3"
      data-testid="evidence-heatmap"
    >
      {activeElements.map((el) => {
        const style = classificationStyles[el.classification] || classificationStyles.dark;
        return (
          <div
            key={el.element_id}
            className={`rounded-lg border p-3 ${style.bg} ${style.border}`}
            data-testid={`heatmap-tile-${el.classification}`}
          >
            <div className={`text-sm font-medium truncate ${style.text}`}>
              {el.element_name}
            </div>
            <div className="flex items-center gap-2 mt-2">
              <Badge variant="secondary" className="text-xs">
                {el.evidence_count} source{el.evidence_count !== 1 ? "s" : ""}
              </Badge>
              <span className={`text-xs ${style.text}`}>
                {(el.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <div className="flex items-center gap-1 mt-1.5">
              <span className={`text-xs font-medium ${style.text}`}>
                {style.label}
              </span>
              {el.is_added && (
                <Badge variant="outline" className="text-xs">
                  New
                </Badge>
              )}
              {el.is_modified && (
                <Badge variant="outline" className="text-xs">
                  Modified
                </Badge>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
