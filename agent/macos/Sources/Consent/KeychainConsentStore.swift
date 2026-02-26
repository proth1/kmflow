/// Keychain-backed implementation of `ConsentStore`.
///
/// Each engagement's consent record is stored as a JSON blob under a
/// per-engagement account key in a dedicated Keychain service, isolating
/// consent data from other agent secrets.
///
/// The implementation is self-contained: it uses the Security framework
/// directly rather than depending on the Utilities module, preserving
/// the Consent target's zero-dependency footprint.

import Foundation
import Security

// MARK: - ConsentRecord

/// Persistent representation of a consent decision for one engagement.
///
/// The JSON payload stored in the Keychain matches this structure exactly,
/// allowing forward-compatible extensions (new optional fields) without
/// breaking existing records.
public struct ConsentRecord: Codable, Sendable {
    /// Engagement this record belongs to.
    public let engagementId: String
    /// Current consent decision.
    public let state: ConsentState
    /// When consent was most recently granted or revoked.
    public let consentedAt: Date?
    /// Identity of the person who authorised capture (e.g. engagement lead email).
    public let authorizedBy: String?
    /// Scope of data captured under this consent (e.g. "full" / "redacted").
    public let captureScope: String?
    /// Version of the consent agreement accepted.
    public let consentVersion: String

    enum CodingKeys: String, CodingKey {
        case engagementId   = "engagementId"
        case state          = "state"
        case consentedAt    = "consentedAt"
        case authorizedBy   = "authorizedBy"
        case captureScope   = "captureScope"
        case consentVersion = "consentVersion"
    }
}

// MARK: - KeychainConsentStore

/// `ConsentStore` backed by the macOS Keychain.
///
/// Thread safety is guaranteed by the immutability of `service`; all
/// Keychain API calls are inherently atomic at the OS level.
public struct KeychainConsentStore: ConsentStore, Sendable {

    // MARK: - Constants

    /// Keychain service bucket for consent records — separate from the main
    /// agent service so that consent data can be audited independently.
    private let service: String = "com.kmflow.agent.consent"

    // MARK: - Init

    public init() {}

    // MARK: - ConsentStore

    /// Load the consent state for `engagementId`.
    ///
    /// Returns `.neverConsented` when no record exists (first-time launch)
    /// or when the stored JSON cannot be decoded.
    public func load(engagementId: String) -> ConsentState {
        guard let data = keychainLoad(account: accountKey(for: engagementId)) else {
            return .neverConsented
        }
        do {
            let record = try jsonDecoder().decode(ConsentRecord.self, from: data)
            return record.state
        } catch {
            // Corrupt record — treat as no consent to be safe.
            return .neverConsented
        }
    }

    /// Persist a consent decision for `engagementId`.
    ///
    /// Overwrites any existing record atomically (delete-then-insert).
    public func save(engagementId: String, state: ConsentState, at date: Date) {
        let record = ConsentRecord(
            engagementId: engagementId,
            state: state,
            consentedAt: date,
            authorizedBy: nil,
            captureScope: nil,
            consentVersion: "1.0"
        )
        guard let data = try? jsonEncoder().encode(record) else { return }
        keychainSave(account: accountKey(for: engagementId), data: data)
    }

    /// Remove the consent record for `engagementId` from the Keychain.
    public func clear(engagementId: String) {
        keychainDelete(account: accountKey(for: engagementId))
    }

    // MARK: - Private helpers

    private func accountKey(for engagementId: String) -> String {
        "consent.\(engagementId)"
    }

    private func jsonDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }

    private func jsonEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.sortedKeys]
        return encoder
    }

    // MARK: - Keychain primitives

    /// Write (or overwrite) a Keychain item.
    private func keychainSave(account: String, data: Data) {
        let deleteQuery: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(deleteQuery as CFDictionary)

        let addQuery: [String: Any] = [
            kSecClass as String:            kSecClassGenericPassword,
            kSecAttrService as String:      service,
            kSecAttrAccount as String:      account,
            kSecValueData as String:        data,
            // Store with "after first unlock" accessibility so the item is
            // readable during background processing after the device is
            // unlocked at least once.
            kSecAttrAccessible as String:   kSecAttrAccessibleAfterFirstUnlock,
        ]
        let status = SecItemAdd(addQuery as CFDictionary, nil)
        if status != errSecSuccess {
            // Non-fatal: consent will fall back to neverConsented on next load.
            // os_log is not available here without importing os; use stderr.
            fputs("[KeychainConsentStore] SecItemAdd failed: \(status)\n", stderr)
        }
    }

    /// Read a Keychain item, returning `nil` if it does not exist.
    private func keychainLoad(account: String) -> Data? {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String:  true,
            kSecMatchLimit as String:  kSecMatchLimitOne,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess else { return nil }
        return result as? Data
    }

    /// Delete a Keychain item (idempotent — ignores errSecItemNotFound).
    private func keychainDelete(account: String) {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
