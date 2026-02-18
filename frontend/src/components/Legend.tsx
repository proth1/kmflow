/**
 * Confidence color legend component.
 *
 * Displays the color scheme used for confidence heatmap overlays
 * on process visualization views.
 */

interface LegendItem {
  label: string;
  colorClass: string;
  range: string;
}

const LEGEND_ITEMS: LegendItem[] = [
  { label: "Very High", colorClass: "bg-green-700", range: "\u2265 90%" },
  { label: "High", colorClass: "bg-green-500", range: "75-89%" },
  { label: "Medium", colorClass: "bg-yellow-400", range: "50-74%" },
  { label: "Low", colorClass: "bg-orange-400", range: "25-49%" },
  { label: "Very Low", colorClass: "bg-red-500", range: "< 25%" },
];

interface LegendProps {
  orientation?: "horizontal" | "vertical";
}

export default function Legend({ orientation = "horizontal" }: LegendProps) {
  const isHorizontal = orientation === "horizontal";

  return (
    <div
      className={`flex ${isHorizontal ? "flex-row gap-4 flex-wrap" : "flex-col gap-2"} p-3 px-4 bg-gray-50 rounded-lg border border-[hsl(var(--border))]`}
      data-testid="confidence-legend"
    >
      <span
        className={`text-xs font-semibold text-[hsl(var(--foreground))] ${isHorizontal ? "mr-1" : ""}`}
      >
        Confidence:
      </span>
      {LEGEND_ITEMS.map((item) => (
        <div
          key={item.label}
          className="flex items-center gap-1.5 text-xs text-[hsl(var(--muted-foreground))]"
        >
          <span
            className={`w-3.5 h-3.5 rounded-sm inline-block shrink-0 ${item.colorClass}`}
          />
          <span>
            {item.label} ({item.range})
          </span>
        </div>
      ))}
    </div>
  );
}
