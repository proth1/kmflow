/**
 * Shared validation utilities for the KMFlow frontend.
 */

const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Returns true if the given string is a valid UUID v4 format.
 */
export function isValidEngagementId(id: string): boolean {
  return UUID_REGEX.test(id);
}

/**
 * Returns true if the string is safe to use as a URL path segment.
 * Rejects path traversal, special chars, and whitespace.
 */
export function isSafePathSegment(segment: string): boolean {
  if (!segment || segment.includes("..") || segment.includes("/")) return false;
  return /^[a-zA-Z0-9_-]+$/.test(segment);
}
