/// Agent configuration pulled from the KMFlow backend.
///
/// Mirrors the CaptureConfig schema from src/api/schemas/taskmining.py.

import Foundation

public struct AgentConfig: Codable, Sendable {
    public var captureGranularity: CaptureGranularity
    public var appAllowlist: [String]?
    public var appBlocklist: [String]?
    public var urlDomainOnly: Bool
    public var screenshotEnabled: Bool
    public var screenshotIntervalSeconds: Int
    public var batchSize: Int
    public var batchIntervalSeconds: Int
    public var idleTimeoutSeconds: Int
    public var piiPatternsVersion: String

    public init(
        captureGranularity: CaptureGranularity = .actionLevel,
        appAllowlist: [String]? = nil,
        appBlocklist: [String]? = nil,
        urlDomainOnly: Bool = true,
        screenshotEnabled: Bool = false,
        screenshotIntervalSeconds: Int = 30,
        batchSize: Int = 1000,
        batchIntervalSeconds: Int = 30,
        idleTimeoutSeconds: Int = 300,
        piiPatternsVersion: String = "1.0"
    ) {
        self.captureGranularity = captureGranularity
        self.appAllowlist = appAllowlist
        self.appBlocklist = appBlocklist
        self.urlDomainOnly = urlDomainOnly
        self.screenshotEnabled = screenshotEnabled
        self.screenshotIntervalSeconds = screenshotIntervalSeconds
        self.batchSize = batchSize
        self.batchIntervalSeconds = batchIntervalSeconds
        self.idleTimeoutSeconds = idleTimeoutSeconds
        self.piiPatternsVersion = piiPatternsVersion
    }

    enum CodingKeys: String, CodingKey {
        case captureGranularity = "capture_granularity"
        case appAllowlist = "app_allowlist"
        case appBlocklist = "app_blocklist"
        case urlDomainOnly = "url_domain_only"
        case screenshotEnabled = "screenshot_enabled"
        case screenshotIntervalSeconds = "screenshot_interval_seconds"
        case batchSize = "batch_size"
        case batchIntervalSeconds = "batch_interval_seconds"
        case idleTimeoutSeconds = "idle_timeout_seconds"
        case piiPatternsVersion = "pii_patterns_version"
    }
}

public enum CaptureGranularity: String, Codable, Sendable {
    case actionLevel = "action_level"
    case contentLevel = "content_level"
}
