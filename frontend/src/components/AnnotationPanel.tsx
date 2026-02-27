/**
 * SME Annotation Panel for gap analysis detail views.
 *
 * Displays and allows creation of annotations attached to specific
 * artifacts (gaps, process elements, evidence items).
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost, apiDelete } from "@/lib/api";

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

  const fetchAnnotations = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const params = new URLSearchParams({
          engagement_id: engagementId,
          target_type: targetType,
          target_id: targetId,
        });
        const data = await apiGet<{ items: Annotation[] }>(
          `/api/v1/annotations/?${params.toString()}`,
          signal,
        );
        setAnnotations(data.items || []);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : "Failed to load annotations");
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [engagementId, targetType, targetId],
  );

  useEffect(() => {
    const controller = new AbortController();
    fetchAnnotations(controller.signal);
    return () => controller.abort();
  }, [fetchAnnotations]);

  const handleSubmit = async () => {
    if (!newContent.trim()) return;
    setSubmitting(true);
    setError(null);

    try {
      await apiPost<Annotation>("/api/v1/annotations/", {
        engagement_id: engagementId,
        target_type: targetType,
        target_id: targetId,
        content: newContent.trim(),
      });

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
      await apiDelete(`/api/v1/annotations/${annotationId}`);
      setAnnotations((prev) => prev.filter((a) => a.id !== annotationId));
    } catch {
      setError("Failed to delete annotation");
    }
  };

  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-5">
      <h3 className="text-[15px] font-semibold mb-4 text-[hsl(var(--foreground))]">
        SME Annotations
      </h3>

      {/* Annotation list */}
      {loading ? (
        <div className="text-[hsl(var(--muted-foreground))] text-sm py-3">
          Loading annotations...
        </div>
      ) : annotations.length > 0 ? (
        <div className="flex flex-col gap-2.5 mb-4">
          {annotations.map((ann) => (
            <div
              key={ann.id}
              className="p-3 bg-gray-50 rounded-lg border border-gray-100"
            >
              <div className="text-sm text-[hsl(var(--foreground))] leading-relaxed whitespace-pre-wrap">
                {ann.content}
              </div>
              <div className="flex justify-between items-center mt-2 text-xs text-[hsl(var(--muted-foreground))]">
                <span>
                  {ann.author_id} &bull;{" "}
                  {new Date(ann.created_at).toLocaleDateString()}
                </span>
                <button
                  onClick={() => handleDelete(ann.id)}
                  aria-label={`Delete annotation by ${ann.author_id}`}
                  className="text-red-600 hover:text-red-700 cursor-pointer bg-transparent border-none text-xs px-1.5 py-0.5"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-[hsl(var(--muted-foreground))] text-sm py-3 mb-4">
          No annotations yet.
        </div>
      )}

      {/* New annotation form */}
      <div className="flex flex-col gap-2">
        <label
          htmlFor="annotation-input"
          className="text-sm font-medium text-[hsl(var(--foreground))]"
        >
          Add annotation
        </label>
        <textarea
          id="annotation-input"
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          placeholder="Add an annotation..."
          rows={3}
          className="w-full px-3 py-2.5 border border-[hsl(var(--input))] rounded-lg text-sm resize-y font-inherit box-border bg-[hsl(var(--background))] text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--ring))] focus:ring-offset-2"
        />
        {error && (
          <div className="text-sm text-red-600">{error}</div>
        )}
        <div className="flex justify-end">
          <button
            onClick={handleSubmit}
            disabled={submitting || !newContent.trim()}
            className="px-4 py-2 bg-blue-500 text-white border-none rounded-md text-sm font-medium cursor-pointer hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "Saving..." : "Add Annotation"}
          </button>
        </div>
      </div>
    </div>
  );
}
