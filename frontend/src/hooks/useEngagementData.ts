"use client";

import { useState, useEffect, useRef, useCallback } from "react";

interface UseEngagementDataResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

/**
 * Hook for fetching engagement-scoped data with proper error handling,
 * request cancellation, and debouncing.
 *
 * Replaces the duplicated useEffect + cancelled flag pattern across pages.
 */
export function useEngagementData<T>(
  id: string,
  fetchFn: (id: string, signal: AbortSignal) => Promise<T>,
  minLength = 8,
  debounceMs = 300,
): UseEngagementDataResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trigger, setTrigger] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const refetch = useCallback(() => setTrigger((t) => t + 1), []);

  useEffect(() => {
    if (!id || id.length < minLength) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }

    const timer = setTimeout(() => {
      // Abort any in-flight request
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setLoading(true);
      setError(null);

      fetchFn(id, controller.signal)
        .then((result) => {
          if (!controller.signal.aborted) {
            setData(result);
          }
        })
        .catch((err) => {
          if (!controller.signal.aborted) {
            setError(
              err instanceof Error ? err.message : "Failed to load data",
            );
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setLoading(false);
          }
        });
    }, debounceMs);

    return () => {
      clearTimeout(timer);
      abortRef.current?.abort();
    };
  }, [id, fetchFn, minLength, debounceMs, trigger]);

  return { data, loading, error, refetch };
}
