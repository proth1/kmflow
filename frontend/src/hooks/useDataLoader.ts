"use client";

import { useState, useEffect, useRef, useCallback } from "react";

interface UseDataLoaderResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Generic data-loading hook with error handling and silent refresh support.
 *
 * Unlike useEngagementData, this hook does not require an ID parameter
 * and works with any async fetch function. It handles:
 * - Initial load with loading state
 * - Silent refresh (suppresses errors on initial load)
 * - Manual refetch via returned function
 * - Proper cleanup on unmount
 */
export function useDataLoader<T>(
  fetchFn: (signal: AbortSignal) => Promise<T>,
  errorMessage = "Failed to load data",
): UseDataLoaderResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const isInitialLoad = useRef(true);
  const abortRef = useRef<AbortController | null>(null);

  const loadData = useCallback(
    async (silent = false) => {
      if (!silent) {
        setLoading(true);
      }
      setError(null);

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const result = await fetchFn(controller.signal);
        if (!controller.signal.aborted) {
          setData(result);
        }
      } catch (err) {
        if (!controller.signal.aborted && !silent) {
          setError(err instanceof Error ? err.message : errorMessage);
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    },
    [fetchFn, errorMessage],
  );

  useEffect(() => {
    const silent = isInitialLoad.current;
    isInitialLoad.current = false;
    loadData(silent);

    return () => {
      abortRef.current?.abort();
    };
  }, [loadData]);

  const refetch = useCallback(async () => {
    await loadData(false);
  }, [loadData]);

  return { data, loading, error, refetch };
}
