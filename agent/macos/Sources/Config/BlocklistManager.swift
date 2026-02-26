/// Manages app allowlist/blocklist filtering based on server configuration.

import Foundation
import PII

public final class BlocklistManager: @unchecked Sendable {
    private var blocklist: Set<String>
    private var allowlist: Set<String>?
    private let lock = NSLock()

    public init(config: AgentConfig? = nil) {
        var blocked = CaptureContextFilter.hardcodedBlocklist
        if let configBlocked = config?.appBlocklist {
            blocked.formUnion(configBlocked)
        }
        self.blocklist = blocked
        self.allowlist = config?.appAllowlist.map { Set($0) }
    }

    /// Update blocklist/allowlist from new server config.
    public func update(config: AgentConfig) {
        lock.lock()
        defer { lock.unlock() }
        var blocked = CaptureContextFilter.hardcodedBlocklist
        if let configBlocked = config.appBlocklist {
            blocked.formUnion(configBlocked)
        }
        self.blocklist = blocked
        self.allowlist = config.appAllowlist.map { Set($0) }
    }

    /// Returns true if the bundle ID should be captured (not blocked).
    public func shouldCapture(bundleId: String?) -> Bool {
        guard let bid = bundleId else { return true }
        lock.lock()
        defer { lock.unlock() }

        // If allowlist is set, only allow listed apps
        if let allow = allowlist, !allow.isEmpty {
            return allow.contains(bid)
        }

        // Otherwise, block listed apps
        return !blocklist.contains(bid)
    }
}
