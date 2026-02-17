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
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        width: "360px",
        height: "100vh",
        backgroundColor: "#ffffff",
        borderLeft: "1px solid #e5e7eb",
        boxShadow: "-4px 0 12px rgba(0,0,0,0.08)",
        zIndex: 1000,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
      data-testid="element-sidebar"
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "16px 20px",
          borderBottom: "1px solid #e5e7eb",
        }}
      >
        <h3
          style={{
            margin: 0,
            fontSize: "16px",
            fontWeight: 600,
            color: "#111827",
          }}
        >
          Element Details
        </h3>
        <button
          onClick={onClose}
          style={{
            border: "none",
            background: "none",
            cursor: "pointer",
            fontSize: "20px",
            color: "#6b7280",
            padding: "4px",
            lineHeight: 1,
          }}
          aria-label="Close sidebar"
        >
          \u00d7
        </button>
      </div>

      {/* Content */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "20px",
        }}
      >
        {/* Name */}
        <div style={{ marginBottom: "20px" }}>
          <div
            style={{ fontSize: "12px", color: "#6b7280", marginBottom: "4px" }}
          >
            Name
          </div>
          <div style={{ fontSize: "16px", fontWeight: 600, color: "#111827" }}>
            {element.name}
          </div>
        </div>

        {/* Type */}
        <div style={{ marginBottom: "20px" }}>
          <div
            style={{ fontSize: "12px", color: "#6b7280", marginBottom: "4px" }}
          >
            Type
          </div>
          <div
            style={{
              fontSize: "14px",
              color: "#374151",
              textTransform: "capitalize",
            }}
          >
            {element.elementType}
          </div>
        </div>

        {/* Confidence */}
        <div style={{ marginBottom: "20px" }}>
          <div
            style={{ fontSize: "12px", color: "#6b7280", marginBottom: "8px" }}
          >
            Confidence Score
          </div>
          <ConfidenceBadge score={element.confidenceScore} />
        </div>

        {/* Evidence */}
        <div style={{ marginBottom: "20px" }}>
          <div
            style={{
              fontSize: "12px",
              color: "#6b7280",
              marginBottom: "8px",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            Evidence <EvidenceBadge count={element.evidenceCount} />
          </div>
          {element.evidenceIds && element.evidenceIds.length > 0 ? (
            <ul
              style={{
                margin: 0,
                padding: "0 0 0 16px",
                fontSize: "13px",
                color: "#4b5563",
                lineHeight: 1.8,
              }}
            >
              {element.evidenceIds.map((id) => (
                <li key={id} style={{ wordBreak: "break-all" }}>
                  {id}
                </li>
              ))}
            </ul>
          ) : (
            <div style={{ fontSize: "13px", color: "#9ca3af" }}>
              No evidence items linked.
            </div>
          )}
        </div>

        {/* Contradictions */}
        {element.contradictions && element.contradictions.length > 0 && (
          <div style={{ marginBottom: "20px" }}>
            <div
              style={{
                fontSize: "12px",
                color: "#dc2626",
                marginBottom: "8px",
                fontWeight: 600,
              }}
            >
              Contradictions ({element.contradictions.length})
            </div>
            <ul
              style={{
                margin: 0,
                padding: "0 0 0 16px",
                fontSize: "13px",
                color: "#dc2626",
                lineHeight: 1.8,
              }}
            >
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
