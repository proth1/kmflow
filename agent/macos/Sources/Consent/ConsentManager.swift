/// Manages user consent state for desktop activity capture.
///
/// Consent is stored in the macOS Keychain per engagement ID.
/// No capture occurs until consent is explicitly granted.

import Foundation

public enum ConsentState: String, Codable, Sendable {
    case neverConsented = "never_consented"
    case consented = "consented"
    case revoked = "revoked"
}

/// Protocol for consent persistence (testable abstraction over Keychain).
public protocol ConsentStore: Sendable {
    func load(engagementId: String) -> ConsentState
    func save(engagementId: String, state: ConsentState, at: Date)
    func clear(engagementId: String)
}

@MainActor
public final class ConsentManager: ObservableObject {
    @Published public private(set) var state: ConsentState
    private let engagementId: String
    private let store: ConsentStore

    public init(engagementId: String, store: ConsentStore) {
        self.engagementId = engagementId
        self.store = store
        self.state = store.load(engagementId: engagementId)
    }

    /// Grant consent for capture.
    public func grantConsent() {
        state = .consented
        store.save(engagementId: engagementId, state: .consented, at: Date())
    }

    /// Revoke consent. Capture must stop immediately.
    public func revokeConsent() {
        state = .revoked
        store.save(engagementId: engagementId, state: .revoked, at: Date())
    }

    /// Check if capture is allowed.
    public var captureAllowed: Bool {
        state == .consented
    }
}

/// In-memory consent store for testing.
public final class InMemoryConsentStore: ConsentStore, @unchecked Sendable {
    private var storage: [String: ConsentState] = [:]
    private let lock = NSLock()

    public init() {}

    public func load(engagementId: String) -> ConsentState {
        lock.lock()
        defer { lock.unlock() }
        return storage[engagementId] ?? .neverConsented
    }

    public func save(engagementId: String, state: ConsentState, at: Date) {
        lock.lock()
        defer { lock.unlock() }
        storage[engagementId] = state
    }

    public func clear(engagementId: String) {
        lock.lock()
        defer { lock.unlock() }
        storage.removeValue(forKey: engagementId)
    }
}
