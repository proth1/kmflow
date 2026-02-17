/**
 * Color-coded confidence badge.
 *
 * Displays a confidence score with background color based on
 * the confidence level thresholds:
 * - VERY_HIGH (>=0.9): Dark Green
 * - HIGH (0.75-0.89): Light Green
 * - MEDIUM (0.50-0.74): Yellow
 * - LOW (0.25-0.49): Orange
 * - VERY_LOW (<0.25): Red
 */

interface ConfidenceBadgeProps {
  score: number;
  showLabel?: boolean;
}

interface ConfidenceLevel {
  label: string;
  bg: string;
  text: string;
}

function getConfidenceLevel(score: number): ConfidenceLevel {
  if (score >= 0.9) return { label: "Very High", bg: "#15803d", text: "#ffffff" };
  if (score >= 0.75) return { label: "High", bg: "#22c55e", text: "#ffffff" };
  if (score >= 0.5) return { label: "Medium", bg: "#eab308", text: "#1f2937" };
  if (score >= 0.25) return { label: "Low", bg: "#f97316", text: "#ffffff" };
  return { label: "Very Low", bg: "#ef4444", text: "#ffffff" };
}

export default function ConfidenceBadge({
  score,
  showLabel = true,
}: ConfidenceBadgeProps) {
  const level = getConfidenceLevel(score);
  const pct = Math.round(score * 100);

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        padding: "2px 10px",
        borderRadius: "9999px",
        fontSize: "12px",
        fontWeight: 600,
        backgroundColor: level.bg,
        color: level.text,
        lineHeight: "20px",
      }}
      data-testid="confidence-badge"
      title={`Confidence: ${pct}% (${level.label})`}
    >
      {pct}%{showLabel && ` ${level.label}`}
    </span>
  );
}

export { getConfidenceLevel };
