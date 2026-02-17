/**
 * TOM dimension maturity card.
 *
 * Displays current vs target maturity for a TOM dimension with
 * a visual progress bar and gap indicator.
 */

export interface TOMDimensionProps {
  dimension: string;
  currentMaturity: number;
  targetMaturity: number;
  gapType: string;
  severity: number;
}

const DIMENSION_LABELS: Record<string, string> = {
  process_architecture: "Process Architecture",
  people_and_organization: "People & Organization",
  technology_and_data: "Technology & Data",
  governance_structures: "Governance Structures",
  performance_management: "Performance Management",
  risk_and_compliance: "Risk & Compliance",
};

const GAP_COLORS: Record<string, { bg: string; text: string; border: string }> =
  {
    no_gap: { bg: "#f0fdf4", text: "#15803d", border: "#bbf7d0" },
    deviation: { bg: "#fefce8", text: "#a16207", border: "#fef08a" },
    partial_gap: { bg: "#fff7ed", text: "#c2410c", border: "#fed7aa" },
    full_gap: { bg: "#fef2f2", text: "#dc2626", border: "#fecaca" },
  };

export default function TOMDimensionCard({
  dimension,
  currentMaturity,
  targetMaturity,
  gapType,
  severity,
}: TOMDimensionProps) {
  const label = DIMENSION_LABELS[dimension] ?? dimension.replace(/_/g, " ");
  const colors = GAP_COLORS[gapType] ?? GAP_COLORS.deviation;
  const currentPct = Math.min((currentMaturity / 5) * 100, 100);
  const targetPct = Math.min((targetMaturity / 5) * 100, 100);

  return (
    <div
      style={{
        backgroundColor: "#ffffff",
        border: `1px solid ${colors.border}`,
        borderRadius: "12px",
        padding: "20px",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
      data-testid="tom-dimension-card"
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span
          style={{
            fontSize: "14px",
            fontWeight: 600,
            color: "#111827",
          }}
        >
          {label}
        </span>
        <span
          style={{
            display: "inline-block",
            padding: "2px 10px",
            borderRadius: "9999px",
            fontSize: "11px",
            fontWeight: 600,
            backgroundColor: colors.bg,
            color: colors.text,
            textTransform: "uppercase",
          }}
        >
          {gapType.replace(/_/g, " ")}
        </span>
      </div>

      {/* Maturity Bar */}
      <div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: "12px",
            color: "#6b7280",
            marginBottom: "6px",
          }}
        >
          <span>Current: {currentMaturity.toFixed(1)}</span>
          <span>Target: {targetMaturity.toFixed(1)}</span>
        </div>
        <div
          style={{
            position: "relative",
            height: "12px",
            backgroundColor: "#f3f4f6",
            borderRadius: "6px",
            overflow: "visible",
          }}
        >
          {/* Current maturity bar */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              height: "100%",
              width: `${currentPct}%`,
              backgroundColor: colors.text,
              borderRadius: "6px",
              opacity: 0.7,
              transition: "width 0.3s ease",
            }}
          />
          {/* Target marker */}
          <div
            style={{
              position: "absolute",
              top: "-2px",
              left: `${targetPct}%`,
              width: "3px",
              height: "16px",
              backgroundColor: "#111827",
              borderRadius: "2px",
              transform: "translateX(-1px)",
            }}
          />
        </div>
      </div>

      {/* Severity */}
      {severity > 0 && (
        <div style={{ fontSize: "12px", color: "#6b7280" }}>
          Severity: {(severity * 100).toFixed(0)}%
        </div>
      )}
    </div>
  );
}
