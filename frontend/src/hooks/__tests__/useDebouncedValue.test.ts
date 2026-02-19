import { renderHook, act } from "@testing-library/react";
import { useDebouncedValue } from "../useDebouncedValue";

beforeEach(() => {
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

describe("useDebouncedValue", () => {
  it("returns initial value immediately", () => {
    const { result } = renderHook(() => useDebouncedValue("hello", 300));
    expect(result.current).toBe("hello");
  });

  it("does not update until delay passes", () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 300),
      { initialProps: { value: "a" } },
    );

    rerender({ value: "ab" });
    expect(result.current).toBe("a");

    act(() => { jest.advanceTimersByTime(150); });
    expect(result.current).toBe("a");
  });

  it("updates after delay passes", () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 300),
      { initialProps: { value: "a" } },
    );

    rerender({ value: "ab" });

    act(() => { jest.advanceTimersByTime(300); });
    expect(result.current).toBe("ab");
  });

  it("resets timer on rapid changes", () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 300),
      { initialProps: { value: "a" } },
    );

    rerender({ value: "ab" });
    act(() => { jest.advanceTimersByTime(200); });

    rerender({ value: "abc" });
    act(() => { jest.advanceTimersByTime(200); });
    // Still "a" because timer reset
    expect(result.current).toBe("a");

    act(() => { jest.advanceTimersByTime(100); });
    expect(result.current).toBe("abc");
  });
});
