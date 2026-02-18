/**
 * Transformation roadmap timeline visualization.
 *
 * Displays a 4-phase roadmap with initiatives grouped by phase,
 * showing dependencies, durations, and priority indicators.
 */
"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RoadmapPhase, RoadmapInitiative } from "@/lib/api";

interface RoadmapTimelineProps {
  phases: RoadmapPhase[];
  totalInitiatives: number;
  estimatedMonths: number;
}

const PHASE_CLASSES: Record<number, { bg: string; accent: string; text: string; border: string }> = {
  1: { bg: "bg-green-50", accent: "border-l-green-500", text: "text-green-700", border: "bg-green-500" },
  2: { bg: "bg-blue-50", accent: "border-l-blue-500", text: "text-blue-700", border: "bg-blue-500" },
  3: { bg: "bg-purple-50", accent: "border-l-purple-500", text: "text-purple-700", border: "bg-purple-500" },
  4: { bg: "bg-orange-50", accent: "border-l-orange-400", text: "text-orange-700", border: "bg-orange-400" },
};

function PriorityIndicator({ score }: { score: number }) {
  const dotClass =
    score > 0.7 ? "bg-red-600" : score > 0.4 ? "bg-amber-500" : "bg-green-500";
  return (
    <span className={`inline-block w-2 h-2 rounded-full mr-1.5 shrink-0 ${dotClass}`} />
  );
}

function InitiativeRow({ initiative }: { initiative: RoadmapInitiative }) {
  return (
    <div className="flex items-start gap-2 p-3 bg-gray-50 rounded-lg text-sm">
      <PriorityIndicator score={initiative.priority_score} />
      <div className="flex-1">
        <div className="text-[hsl(var(--foreground))] font-medium">
          {initiative.dimension.replace(/_/g, " ")}
        </div>
        <div className="text-[hsl(var(--muted-foreground))] mt-0.5">
          {initiative.recommendation}
        </div>
      </div>
      <div className="text-[11px] text-[hsl(var(--muted-foreground))] whitespace-nowrap">
        {initiative.gap_type.replace(/_/g, " ")}
      </div>
    </div>
  );
}

export default function RoadmapTimeline({
  phases,
  totalInitiatives,
  estimatedMonths,
}: RoadmapTimelineProps) {
  const [expandedPhase, setExpandedPhase] = useState<number | null>(1);

  return (
    <div data-testid="roadmap-timeline">
      {/* Summary bar */}
      <div className="flex gap-6 mb-6 text-sm text-[hsl(var(--muted-foreground))]">
        <span>
          <strong className="text-[hsl(var(--foreground))]">{totalInitiatives}</strong>{" "}
          initiatives
        </span>
        <span>
          <strong className="text-[hsl(var(--foreground))]">{estimatedMonths}</strong> months
          estimated
        </span>
        <span>
          <strong className="text-[hsl(var(--foreground))]">{phases.length}</strong> phases
        </span>
      </div>

      {/* Timeline */}
      <div className="flex flex-col">
        {phases.map((phase) => {
          const colors = PHASE_CLASSES[phase.phase_number] ?? PHASE_CLASSES[1];
          const isExpanded = expandedPhase === phase.phase_number;

          return (
            <div key={phase.phase_number}>
              {/* Phase header */}
              <button
                onClick={() =>
                  setExpandedPhase(isExpanded ? null : phase.phase_number)
                }
                className={cn(
                  "w-full flex items-center gap-4 p-4 px-5 border-none cursor-pointer text-left border-l-4",
                  colors.bg,
                  colors.accent
                )}
              >
                {/* Phase number circle */}
                <div
                  className={cn(
                    "w-8 h-8 rounded-full text-white flex items-center justify-center font-bold text-sm shrink-0",
                    colors.border
                  )}
                >
                  {phase.phase_number}
                </div>
                <div className="flex-1">
                  <div className={cn("text-[15px] font-semibold", colors.text)}>
                    {phase.name}
                  </div>
                  <div className="text-xs text-[hsl(var(--muted-foreground))]">
                    {phase.duration_months} months &middot;{" "}
                    {phase.initiatives.length} initiative
                    {phase.initiatives.length !== 1 ? "s" : ""}
                  </div>
                </div>
                <ChevronDown
                  className={cn(
                    "h-4 w-4 text-[hsl(var(--muted-foreground))] transition-transform duration-200",
                    isExpanded && "rotate-180"
                  )}
                />
              </button>

              {/* Phase initiatives */}
              {isExpanded && (
                <div
                  className={cn(
                    "border-l-4 px-5 py-3 flex flex-col gap-2 bg-[hsl(var(--background))]",
                    colors.accent
                  )}
                >
                  {phase.initiatives.length > 0 ? (
                    phase.initiatives.map((init, idx) => (
                      <InitiativeRow key={idx} initiative={init} />
                    ))
                  ) : (
                    <div className="p-4 text-[hsl(var(--muted-foreground))] text-center text-sm">
                      No initiatives in this phase.
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
