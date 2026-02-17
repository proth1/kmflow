/**
 * Confidence color legend component.
 *
 * Displays the color scheme used for confidence heatmap overlays
 * on process visualization views.
 */

interface LegendItem {
  label: string;
  color: string;
  range: string;
}

const LEGEND_ITEMS: LegendItem[] = [
  { label: "Very High", color: "#15803d", range: "\u2265 90%" },
  { label: "High", color: "#22c55e", range: "75-89%" },
  { label: "Medium", color: "#eab308", range: "50-74%" },
  { label: "Low", color: "#f97316", range: "25-49%" },
  { label: "Very Low", color: "#ef4444", range: "< 25%" },
];

interface LegendProps {
  orientation?: "horizontal" | "vertical";
}

export default function Legend({ orientation = "horizontal" }: LegendProps) {
  const isHorizontal = orientation === "horizontal";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: isHorizontal ? "row" : "column",
        gap: isHorizontal ? "16px" : "8px",
        padding: "12px 16px",
        backgroundColor: "#f9fafb",
        borderRadius: "8px",
        border: "1px solid #e5e7eb",
        flexWrap: "wrap",
      }}
      data-testid="confidence-legend"
    >
      <span
        style={{
          fontSize: "12px",
          fontWeight: 600,
          color: "#374151",
          marginRight: isHorizontal ? "4px" : 0,
        }}
      >
        Confidence:
      </span>
      {LEGEND_ITEMS.map((item) => (
        <div
          key={item.label}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "12px",
            color: "#4b5563",
          }}
        >
          <span
            style={{
              width: "14px",
              height: "14px",
              borderRadius: "3px",
              backgroundColor: item.color,
              display: "inline-block",
              flexShrink: 0,
            }}
          />
          <span>
            {item.label} ({item.range})
          </span>
        </div>
      ))}
    </div>
  );
}
