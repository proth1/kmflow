/**
 * SME Annotation Panel for gap analysis detail views.
 *
 * Displays and allows creation of annotations attached to specific
 * artifacts (gaps, process elements, evidence items).
 */
"use client";

import { useCallback, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Annotation {
  id: string;
  engagement_id: string;
  target_type: string;
  target_id: string;
  author_id: string;
  content: string;
  created_at: string;
  updated_at: string;
}

interface AnnotationPanelProps {
  engagementId: string;
  targetType: string;
  targetId: string;
}

export default function AnnotationPanel({
  engagementId,
  targetType,
  targetId,
}: AnnotationPanelProps) {
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [newContent, setNewContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAnnotations = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        engagement_id: engagementId,
        target_type: targetType,
        target_id: targetId,
      });
      const res = await fetch(
        `${API_BASE}/api/v1/annotations/?${params.toString()}`,
      );
      if (res.ok) {
        const data = await res.json();
        setAnnotations(data.items || []);
      }
    } catch {
      // Silently handle fetch errors
    } finally {
      setLoading(false);
    }
  }, [engagementId, targetType, targetId]);

  useEffect(() => {
    fetchAnnotations();
  }, [fetchAnnotations]);

  const handleSubmit = async () => {
    if (!newContent.trim()) return;
    setSubmitting(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/v1/annotations/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          engagement_id: engagementId,
          target_type: targetType,
          target_id: targetId,
          content: newContent.trim(),
        }),
      });

      if (!res.ok) {
        const errData = await res
          .json()
          .catch(() => ({ detail: "Failed to save" }));
        throw new Error(errData.detail || "Failed to save annotation");
      }

      setNewContent("");
      await fetchAnnotations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (annotationId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/annotations/${annotationId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: "Delete failed" }));
        setError(errData.detail || "Failed to delete annotation");
        return;
      }
      setAnnotations((prev) => prev.filter((a) => a.id !== annotationId));
    } catch {
      setError("Failed to delete annotation");
    }
  };

  return (
    <div
      style={{
        backgroundColor: "#ffffff",
        border: "1px solid #e5e7eb",
        borderRadius: "12px",
        padding: "20px",
      }}
    >
      <h3
        style={{
          fontSize: "15px",
          fontWeight: 600,
          margin: "0 0 16px 0",
          color: "#111827",
        }}
      >
        SME Annotations
      </h3>

      {/* Annotation list */}
      {loading ? (
        <div style={{ color: "#9ca3af", fontSize: "13px", padding: "12px 0" }}>
          Loading annotations...
        </div>
      ) : annotations.length > 0 ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "10px",
            marginBottom: "16px",
          }}
        >
          {annotations.map((ann) => (
            <div
              key={ann.id}
              style={{
                padding: "12px",
                backgroundColor: "#f9fafb",
                borderRadius: "8px",
                border: "1px solid #f3f4f6",
              }}
            >
              <div
                style={{
                  fontSize: "14px",
                  color: "#374151",
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                }}
              >
                {ann.content}
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginTop: "8px",
                  fontSize: "12px",
                  color: "#9ca3af",
                }}
              >
                <span>
                  {ann.author_id} &bull;{" "}
                  {new Date(ann.created_at).toLocaleDateString()}
                </span>
                <button
                  onClick={() => handleDelete(ann.id)}
                  aria-label={`Delete annotation by ${ann.author_id}`}
                  style={{
                    background: "none",
                    border: "none",
                    color: "#dc2626",
                    cursor: "pointer",
                    fontSize: "12px",
                    padding: "2px 6px",
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div
          style={{
            color: "#9ca3af",
            fontSize: "13px",
            padding: "12px 0",
            marginBottom: "16px",
          }}
        >
          No annotations yet.
        </div>
      )}

      {/* New annotation form */}
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        <label htmlFor="annotation-input" style={{ fontSize: "13px", fontWeight: 500, color: "#374151" }}>
          Add annotation
        </label>
        <textarea
          id="annotation-input"
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          placeholder="Add an annotation..."
          rows={3}
          style={{
            width: "100%",
            padding: "10px 12px",
            border: "1px solid #d1d5db",
            borderRadius: "8px",
            fontSize: "14px",
            resize: "vertical",
            fontFamily: "inherit",
            boxSizing: "border-box",
          }}
        />
        {error && (
          <div style={{ fontSize: "13px", color: "#dc2626" }}>{error}</div>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end" }}>
          <button
            onClick={handleSubmit}
            disabled={submitting || !newContent.trim()}
            style={{
              padding: "8px 16px",
              backgroundColor:
                submitting || !newContent.trim() ? "#d1d5db" : "#3b82f6",
              color: "#ffffff",
              border: "none",
              borderRadius: "6px",
              fontSize: "14px",
              fontWeight: 500,
              cursor:
                submitting || !newContent.trim() ? "not-allowed" : "pointer",
            }}
          >
            {submitting ? "Saving..." : "Add Annotation"}
          </button>
        </div>
      </div>
    </div>
  );
}
