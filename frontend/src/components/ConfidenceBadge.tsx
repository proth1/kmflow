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
  className: string;
}

function getConfidenceLevel(score: number): ConfidenceLevel {
  if (score >= 0.9) return { label: "Very High", className: "bg-green-700 text-white" };
  if (score >= 0.75) return { label: "High", className: "bg-green-500 text-white" };
  if (score >= 0.5) return { label: "Medium", className: "bg-yellow-400 text-gray-800" };
  if (score >= 0.25) return { label: "Low", className: "bg-orange-400 text-white" };
  return { label: "Very Low", className: "bg-red-500 text-white" };
}

export default function ConfidenceBadge({
  score,
  showLabel = true,
}: ConfidenceBadgeProps) {
  const level = getConfidenceLevel(score);
  const pct = Math.round(score * 100);

  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold leading-5 ${level.className}`}
      data-testid="confidence-badge"
      title={`Confidence: ${pct}% (${level.label})`}
    >
      {pct}%{showLabel && ` ${level.label}`}
    </span>
  );
}

export { getConfidenceLevel };
