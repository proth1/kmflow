/**
 * Detail sidebar for element information.
 *
 * Slides in from the right to show details about a selected
 * process element including confidence, evidence list, and
 * any contradictions.
 */

import ConfidenceBadge from "./ConfidenceBadge";
import EvidenceBadge from "./EvidenceBadge";

export interface ElementDetail {
  name: string;
  elementType: string;
  confidenceScore: number;
  evidenceCount: number;
  evidenceIds?: string[];
  contradictions?: string[];
  metadata?: Record<string, unknown>;
}

interface SidebarProps {
  element: ElementDetail | null;
  onClose: () => void;
}

export default function Sidebar({ element, onClose }: SidebarProps) {
  if (!element) return null;

  return (
    <div
      className="fixed top-0 right-0 w-[360px] h-screen bg-[hsl(var(--background))] border-l border-[hsl(var(--border))] shadow-[-4px_0_12px_rgba(0,0,0,0.08)] z-[1000] flex flex-col overflow-hidden"
      data-testid="element-sidebar"
    >
      {/* Header */}
      <div className="flex justify-between items-center px-5 py-4 border-b border-[hsl(var(--border))]">
        <h3 className="text-base font-semibold text-[hsl(var(--foreground))]">
          Element Details
        </h3>
        <button
          onClick={onClose}
          className="text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))] text-xl leading-none p-1 cursor-pointer border-none bg-transparent"
          aria-label="Close sidebar"
        >
          &times;
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        {/* Name */}
        <div className="mb-5">
          <div className="text-xs text-[hsl(var(--muted-foreground))] mb-1">Name</div>
          <div className="text-base font-semibold text-[hsl(var(--foreground))]">
            {element.name}
          </div>
        </div>

        {/* Type */}
        <div className="mb-5">
          <div className="text-xs text-[hsl(var(--muted-foreground))] mb-1">Type</div>
          <div className="text-sm capitalize text-[hsl(var(--foreground))]">
            {element.elementType}
          </div>
        </div>

        {/* Confidence */}
        <div className="mb-5">
          <div className="text-xs text-[hsl(var(--muted-foreground))] mb-2">
            Confidence Score
          </div>
          <ConfidenceBadge score={element.confidenceScore} />
        </div>

        {/* Evidence */}
        <div className="mb-5">
          <div className="flex items-center gap-2 text-xs text-[hsl(var(--muted-foreground))] mb-2">
            Evidence <EvidenceBadge count={element.evidenceCount} />
          </div>
          {element.evidenceIds && element.evidenceIds.length > 0 ? (
            <ul className="m-0 pl-4 text-sm text-[hsl(var(--muted-foreground))] leading-relaxed">
              {element.evidenceIds.map((id) => (
                <li key={id} className="break-all">
                  {id}
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-[hsl(var(--muted-foreground))]">
              No evidence items linked.
            </div>
          )}
        </div>

        {/* Contradictions */}
        {element.contradictions && element.contradictions.length > 0 && (
          <div className="mb-5">
            <div className="text-xs font-semibold text-red-600 mb-2">
              Contradictions ({element.contradictions.length})
            </div>
            <ul className="m-0 pl-4 text-sm text-red-600 leading-relaxed">
              {element.contradictions.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
