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
  const bg = count > 0 ? "#3b82f6" : "#9ca3af";

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        minWidth: "22px",
        height: "22px",
        padding: "0 6px",
        borderRadius: "9999px",
        fontSize: "11px",
        fontWeight: 700,
        backgroundColor: bg,
        color: "#ffffff",
        lineHeight: 1,
      }}
      data-testid="evidence-badge"
      title={`${count} evidence item${count !== 1 ? "s" : ""}`}
    >
      {count}
    </span>
  );
}
