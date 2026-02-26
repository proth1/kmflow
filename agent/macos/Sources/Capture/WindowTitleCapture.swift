/// Captures window titles via AXUIElement with L1+L2 PII filtering.
///
/// L1: Suppresses password fields and private browsing windows.
/// L2: Regex-based PII scrubbing (SSN, email, phone, credit card, IBAN,
///     file paths) before the title crosses the IPC boundary to Python.

import Foundation
import PII

/// L2 PII patterns for Swift-side scrubbing. These MUST match the patterns
/// in src/taskmining/pii/patterns.py to ensure consistent filtering.
public struct L2PIIFilter: Sendable {
    /// SSN with dashes: 123-45-6789
    private static let ssnDashed: NSRegularExpression? = {
        try? NSRegularExpression(pattern: #"\b\d{3}-\d{2}-\d{4}\b"#)
    }()

    /// Email address
    private static let email: NSRegularExpression? = {
        try? NSRegularExpression(pattern: #"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"#)
    }()

    /// US phone numbers: (555) 123-4567, 555-123-4567, +1-555-123-4567
    private static let phone: NSRegularExpression? = {
        try? NSRegularExpression(pattern: #"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"#)
    }()

    /// Credit card: 4 groups of 4 digits (Visa, MC, Discover, JCB)
    private static let creditCard: NSRegularExpression? = {
        try? NSRegularExpression(pattern: #"\b(?:4\d{3}|5[1-5]\d{2}|6011|35\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"#)
    }()

    /// AmEx: 15-digit (3[47]xx-xxxxxx-xxxxx)
    private static let amex: NSRegularExpression? = {
        try? NSRegularExpression(pattern: #"\b3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}\b"#)
    }()

    /// IBAN: 2-letter country code + 2 check digits + up to 30 alphanumeric chars
    private static let iban: NSRegularExpression? = {
        try? NSRegularExpression(pattern: #"\b[A-Z]{2}\d{2}[\s]?[\dA-Z]{4}[\s]?(?:[\dA-Z]{4}[\s]?){1,7}[\dA-Z]{1,4}\b"#)
    }()

    /// Absolute file paths: /Users/username/..., /home/..., C:\Users\...
    private static let filePath: NSRegularExpression? = {
        try? NSRegularExpression(pattern: #"(?:/(?:Users|home)/\S{2,}|[A-Z]:\\(?:Users|Documents)\\\S{2,})"#)
    }()

    /// UK National Insurance Number: AB 12 34 56 C
    private static let ukNino: NSRegularExpression? = {
        try? NSRegularExpression(pattern: #"\b[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b"#)
    }()

    private static let redactionMarker = "[PII_REDACTED]"

    /// All compiled patterns. nil entries are excluded (indicates a regex compilation failure).
    private static let allPatterns: [NSRegularExpression] = {
        [ssnDashed, email, phone, creditCard, amex, iban, filePath, ukNino].compactMap { $0 }
    }()

    /// Scrub PII from a string, replacing matches with redaction markers.
    public static func scrub(_ text: String) -> String {
        var result = text

        for pattern in allPatterns {
            result = pattern.stringByReplacingMatches(
                in: result,
                range: NSRange(result.startIndex..., in: result),
                withTemplate: redactionMarker
            )
        }

        return result
    }

    /// Returns true if the text contains any PII pattern.
    public static func containsPII(_ text: String) -> Bool {
        let range = NSRange(text.startIndex..., in: text)
        return allPatterns.contains { $0.firstMatch(in: text, range: range) != nil }
    }
}

/// Captures and sanitizes window titles.
public struct WindowTitleCapture: Sendable {
    /// Maximum length for captured window titles.
    public static let maxTitleLength = 512

    /// Sanitize a window title: truncate, apply L2 PII filter.
    public static func sanitize(
        title: String?,
        bundleId: String?
    ) -> String? {
        guard var t = title else { return nil }

        // Private browsing: suppress entirely
        if PrivateBrowsingDetector.isPrivateBrowsing(bundleId: bundleId, windowTitle: t) {
            return "[PRIVATE_BROWSING]"
        }

        // Truncate
        if t.count > maxTitleLength {
            t = String(t.prefix(maxTitleLength))
        }

        // L2 PII scrub
        t = L2PIIFilter.scrub(t)

        return t
    }
}
