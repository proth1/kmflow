"use client";

import { useState, useEffect } from "react";

/**
 * Returns a debounced version of the input value.
 * The returned value only updates after the specified delay
 * of inactivity on the source value.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
