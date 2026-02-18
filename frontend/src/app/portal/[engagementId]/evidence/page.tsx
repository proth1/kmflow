"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchPortalEvidenceStatus, type PortalEvidenceCategory } from "@/lib/api";

function qualityColor(avg: number): string {
  if (avg >= 0.8) return "bg-green-500";
  if (avg >= 0.5) return "bg-yellow-500";
  return "bg-red-500";
}

export default function EvidenceStatusPage() {
  const params = useParams();
  const engagementId = params.engagementId as string;
  const [categories, setCategories] = useState<PortalEvidenceCategory[]>([]);
  const [totalItems, setTotalItems] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const result = await fetchPortalEvidenceStatus(engagementId);
        if (!cancelled) {
          setCategories(result.categories);
          setTotalItems(result.total_items);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load evidence status");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [engagementId]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-gray-500">Loading evidence status...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6">
        <p className="text-sm text-red-600">{error}</p>
      </div>
    );
  }

  const maxCount = Math.max(...categories.map((c) => c.count), 1);

  return (
    <div>
      <h2 className="mb-6 text-xl font-bold text-gray-900">
        Evidence Status
      </h2>
      <div className="rounded-lg bg-white p-6 shadow">
        <p className="mb-4 text-sm text-gray-500">
          {totalItems} evidence items across {categories.length} categories
        </p>
        <div className="space-y-3">
          {categories.map((cat) => {
            const widthPct = Math.round((cat.count / maxCount) * 100);
            return (
              <div key={cat.category} className="flex items-center gap-4">
                <span className="w-48 text-sm font-medium text-gray-700">
                  {cat.category.replace(/_/g, " ")}
                </span>
                <div className="h-4 flex-1 rounded bg-gray-200">
                  <div
                    className={`h-4 rounded ${qualityColor(cat.avg_quality)}`}
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
                <span className="w-12 text-right text-sm text-gray-500">
                  {cat.count}
                </span>
                <span className="w-16 text-right text-xs text-gray-400">
                  {Math.round(cat.avg_quality * 100)}% quality
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
