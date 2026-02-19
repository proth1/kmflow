import { renderHook, waitFor, act } from "@testing-library/react";
import { useDataLoader } from "@/hooks/useDataLoader";

describe("useDataLoader", () => {
  it("starts in loading state", () => {
    const fetchFn = jest.fn(() => new Promise<string>(() => {})); // never resolves
    const { result } = renderHook(() => useDataLoader(fetchFn));

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("resolves data and stops loading", async () => {
    const fetchFn = jest.fn(async () => "hello");
    const { result } = renderHook(() => useDataLoader(fetchFn));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toBe("hello");
    expect(result.current.error).toBeNull();
  });

  it("sets error on fetch failure (refetch, not initial silent load)", async () => {
    const fetchFn = jest.fn(async () => {
      throw new Error("Network error");
    });
    const { result } = renderHook(() =>
      useDataLoader(fetchFn, "Custom error message"),
    );

    // Initial load is silent — no error set
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
    expect(result.current.error).toBeNull();

    // Refetch is NOT silent — error should appear
    await act(async () => {
      await result.current.refetch();
    });

    expect(result.current.error).toBe("Network error");
    expect(result.current.data).toBeNull();
  });

  it("uses custom error message for non-Error throws on refetch", async () => {
    const fetchFn = jest.fn(async () => {
      throw "string error"; // eslint-disable-line no-throw-literal
    });
    const { result } = renderHook(() =>
      useDataLoader(fetchFn, "Custom fallback"),
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    await act(async () => {
      await result.current.refetch();
    });

    expect(result.current.error).toBe("Custom fallback");
  });

  it("aborts in-flight request on unmount", async () => {
    let capturedSignal: AbortSignal | null = null;
    const fetchFn = jest.fn(
      (signal: AbortSignal) =>
        new Promise<string>((resolve) => {
          capturedSignal = signal;
          // Never resolves — simulates long request
          signal.addEventListener("abort", () => {});
          setTimeout(() => resolve("late"), 10000);
        }),
    );

    const { unmount } = renderHook(() => useDataLoader(fetchFn));

    // Give the effect time to fire
    await act(async () => {
      await new Promise((r) => setTimeout(r, 10));
    });

    expect(capturedSignal).not.toBeNull();
    expect(capturedSignal!.aborted).toBe(false);

    unmount();

    expect(capturedSignal!.aborted).toBe(true);
  });

  it("refetch triggers a new load", async () => {
    let callCount = 0;
    const fetchFn = jest.fn(async () => {
      callCount++;
      return `result-${callCount}`;
    });

    const { result } = renderHook(() => useDataLoader(fetchFn));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
    expect(result.current.data).toBe("result-1");

    await act(async () => {
      await result.current.refetch();
    });

    expect(result.current.data).toBe("result-2");
  });
});
