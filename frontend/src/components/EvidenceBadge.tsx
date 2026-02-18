/**
 * Evidence count indicator badge.
 *
 * Displays a small count badge showing the number of evidence
 * items associated with an element.
 */

interface EvidenceBadgeProps {
  count: number;
}

export default function EvidenceBadge({ count }: EvidenceBadgeProps) {
  return (
    <span
      className={`inline-flex items-center justify-center min-w-[22px] h-[22px] px-1.5 rounded-full text-[11px] font-bold text-white leading-none ${count > 0 ? "bg-blue-500" : "bg-gray-400"}`}
      data-testid="evidence-badge"
      title={`${count} evidence item${count !== 1 ? "s" : ""}`}
    >
      {count}
    </span>
  );
}
