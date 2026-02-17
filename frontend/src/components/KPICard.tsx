/**
 * KPI metric card for dashboard display.
 *
 * Shows a label, value, and optional status indicator with
 * color-coding based on threshold states (good/warning/critical).
 */

export type KPIStatus = "good" | "warning" | "critical" | "neutral";

interface KPICardProps {
  label: string;
  value: string | number;
  status?: KPIStatus;
  subtitle?: string;
}

const STATUS_COLORS: Record<KPIStatus, string> = {
  good: "#22c55e",
  warning: "#eab308",
  critical: "#ef4444",
  neutral: "#6b7280",
};

export default function KPICard({
  label,
  value,
  status = "neutral",
  subtitle,
}: KPICardProps) {
  return (
    <div
      style={{
        backgroundColor: "#ffffff",
        border: "1px solid #e5e7eb",
        borderRadius: "12px",
        padding: "20px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        minWidth: "160px",
      }}
      data-testid="kpi-card"
    >
      <div
        style={{
          fontSize: "13px",
          color: "#6b7280",
          fontWeight: 500,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}
      >
        {label}
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <span
          style={{
            width: "10px",
            height: "10px",
            borderRadius: "50%",
            backgroundColor: STATUS_COLORS[status],
            display: "inline-block",
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontSize: "28px",
            fontWeight: 700,
            color: "#111827",
            lineHeight: 1,
          }}
        >
          {value}
        </span>
      </div>
      {subtitle && (
        <div style={{ fontSize: "12px", color: "#9ca3af" }}>{subtitle}</div>
      )}
    </div>
  );
}
