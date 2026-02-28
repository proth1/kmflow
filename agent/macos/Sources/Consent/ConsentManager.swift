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

/// Closure invoked when consent is revoked so resources can be cleaned up.
/// Implementors should: stop capture, delete local buffer, disconnect IPC.
public typealias ConsentRevocationHandler = @MainActor (String) -> Void

@MainActor
public final class ConsentManager: ObservableObject {
    @Published public private(set) var state: ConsentState
    private let engagementId: String
    private let store: ConsentStore
    private var revocationHandlers: [ConsentRevocationHandler] = []

    public init(engagementId: String, store: ConsentStore) {
        self.engagementId = engagementId
        self.store = store
        self.state = store.load(engagementId: engagementId)
    }

    /// Register a handler invoked when consent is revoked.
    /// Use this to wire cleanup actions (stop capture, delete buffer, disconnect IPC).
    public func onRevocation(_ handler: @escaping ConsentRevocationHandler) {
        revocationHandlers.append(handler)
    }

    /// Grant consent for capture.
    public func grantConsent() {
        state = .consented
        store.save(engagementId: engagementId, state: .consented, at: Date())
    }

    /// Revoke consent. Capture stops immediately and local data is cleaned up.
    ///
    /// Notifies all registered revocation handlers to:
    /// - Stop all event monitors and disconnect IPC
    /// - Delete the local SQLite event buffer
    /// - Remove engagement-specific Keychain entries
    public func revokeConsent() {
        state = .revoked
        store.save(engagementId: engagementId, state: .revoked, at: Date())
        for handler in revocationHandlers {
            handler(engagementId)
        }
    }

    /// Check if capture is allowed.
    public var captureAllowed: Bool {
        state == .consented
    }
}

/// In-memory consent store for testing.
///
/// Marked `@unchecked Sendable` because this is only used in single-threaded
/// test contexts. Using a class (not actor) avoids the protocol conformance
/// issue where actor-isolated methods cannot satisfy non-async protocol
/// requirements.
public final class InMemoryConsentStore: ConsentStore, @unchecked Sendable {
    private var storage: [String: ConsentState] = [:]

    public init() {}

    public func load(engagementId: String) -> ConsentState {
        return storage[engagementId] ?? .neverConsented
    }

    public func save(engagementId: String, state: ConsentState, at: Date) {
        storage[engagementId] = state
    }

    public func clear(engagementId: String) {
        storage.removeValue(forKey: engagementId)
    }
}
