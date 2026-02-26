/// Agent configuration pulled from the KMFlow backend or MDM profile.
///
/// Mirrors the CaptureConfig schema from src/api/schemas/taskmining.py.
/// Supports initialization from MDM managed preferences (UserDefaults suite).

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

    /// Initialize from an MDM configuration profile (managed preferences).
    ///
    /// Reads from UserDefaults suite "com.kmflow.agent" which is populated
    /// by the com.kmflow.agent.mobileconfig MDM profile.
    public init?(fromMDMProfile suiteName: String = "com.kmflow.agent") {
        guard let defaults = UserDefaults(suiteName: suiteName) else { return nil }

        // MDM profiles may only set a subset of keys — use defaults for the rest
        let policyString = defaults.string(forKey: "CapturePolicy") ?? "action_level"
        self.captureGranularity = CaptureGranularity(rawValue: policyString) ?? .actionLevel
        self.appAllowlist = defaults.stringArray(forKey: "AppAllowlist")
        self.appBlocklist = defaults.stringArray(forKey: "AppBlocklist")
        self.urlDomainOnly = defaults.object(forKey: "UrlDomainOnly") != nil
            ? defaults.bool(forKey: "UrlDomainOnly") : true
        self.screenshotEnabled = defaults.bool(forKey: "ScreenshotEnabled")
        self.screenshotIntervalSeconds = defaults.object(forKey: "ScreenshotIntervalSeconds") != nil
            ? defaults.integer(forKey: "ScreenshotIntervalSeconds") : 30
        self.batchSize = defaults.object(forKey: "BatchSize") != nil
            ? defaults.integer(forKey: "BatchSize") : 1000
        self.batchIntervalSeconds = defaults.object(forKey: "BatchIntervalSeconds") != nil
            ? defaults.integer(forKey: "BatchIntervalSeconds") : 30
        self.idleTimeoutSeconds = defaults.object(forKey: "IdleTimeoutSeconds") != nil
            ? defaults.integer(forKey: "IdleTimeoutSeconds") : 300
        self.piiPatternsVersion = defaults.string(forKey: "PiiPatternsVersion") ?? "1.0"
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
