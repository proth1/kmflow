import { isValidEngagementId, isSafePathSegment } from "../validation";

describe("isValidEngagementId", () => {
  it("accepts a valid UUID v4", () => {
    expect(isValidEngagementId("550e8400-e29b-41d4-a716-446655440000")).toBe(true);
  });

  it("accepts uppercase UUIDs", () => {
    expect(isValidEngagementId("550E8400-E29B-41D4-A716-446655440000")).toBe(true);
  });

  it("rejects an empty string", () => {
    expect(isValidEngagementId("")).toBe(false);
  });

  it("rejects a short string", () => {
    expect(isValidEngagementId("550e8400")).toBe(false);
  });

  it("rejects path traversal", () => {
    expect(isValidEngagementId("../../admin")).toBe(false);
  });

  it("rejects script injection", () => {
    expect(isValidEngagementId("<script>alert(1)</script>")).toBe(false);
  });

  it("rejects a string with spaces", () => {
    expect(isValidEngagementId("550e8400 e29b 41d4 a716 446655440000")).toBe(false);
  });
});

describe("isSafePathSegment", () => {
  it("accepts alphanumeric with hyphens and underscores", () => {
    expect(isSafePathSegment("my-segment_123")).toBe(true);
  });

  it("rejects path traversal", () => {
    expect(isSafePathSegment("..")).toBe(false);
    expect(isSafePathSegment("../etc")).toBe(false);
  });

  it("rejects slashes", () => {
    expect(isSafePathSegment("a/b")).toBe(false);
  });

  it("rejects empty string", () => {
    expect(isSafePathSegment("")).toBe(false);
  });

  it("rejects special characters", () => {
    expect(isSafePathSegment("<script>")).toBe(false);
  });
});
