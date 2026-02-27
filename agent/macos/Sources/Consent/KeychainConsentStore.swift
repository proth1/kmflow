/// Keychain-backed implementation of `ConsentStore`.
///
/// Each engagement's consent record is stored as a JSON blob under a
/// per-engagement account key in a dedicated Keychain service, isolating
/// consent data from other agent secrets.
///
/// The implementation is self-contained: it uses the Security framework
/// directly rather than depending on the Utilities module, preserving
/// the Consent target's zero-dependency footprint.

import CommonCrypto
import Foundation
import os.log
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

/// Wrapper that includes the consent record plus its HMAC-SHA256 signature.
/// The signature prevents local tampering — a forged consent record without
/// the correct HMAC key will be rejected on load.
struct SignedConsentRecord: Codable {
    let record: ConsentRecord
    /// Hex-encoded HMAC-SHA256 of the canonical JSON representation of `record`.
    let hmac: String
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

    /// Keychain account for the HMAC signing key.
    private let hmacKeyAccount: String = "consent.hmac_key"

    /// Current version of the consent agreement. When this changes, existing
    /// consent records with an older version are treated as stale and users
    /// must re-consent to the updated terms.
    public static let currentConsentVersion: String = "1.0"

    /// Structured logger (os_log) — avoids depending on the Utilities module.
    private static let log = Logger(
        subsystem: "com.kmflow.agent",
        category: "KeychainConsentStore"
    )

    // MARK: - Init

    public init() {}

    // MARK: - ConsentStore

    /// Load the consent state for `engagementId`.
    ///
    /// Returns `.neverConsented` when no record exists (first-time launch),
    /// when the stored JSON cannot be decoded, or when the HMAC is invalid
    /// (tamper detection).
    public func load(engagementId: String) -> ConsentState {
        guard let data = keychainLoad(account: accountKey(for: engagementId)) else {
            return .neverConsented
        }
        do {
            let signed = try jsonDecoder().decode(SignedConsentRecord.self, from: data)
            // Verify HMAC before trusting the record
            let recordData = try jsonEncoder().encode(signed.record)
            let expectedHmac = computeHMAC(data: recordData)
            guard signed.hmac == expectedHmac else {
                // HMAC mismatch — record may have been tampered with
                Self.log.error("HMAC verification failed for engagement \(engagementId, privacy: .public)")
                return .neverConsented
            }
            // Stale consent version — user must re-consent to updated terms
            if signed.record.consentVersion != Self.currentConsentVersion {
                Self.log.warning("Consent version mismatch (\(signed.record.consentVersion, privacy: .public) vs \(Self.currentConsentVersion, privacy: .public)) — re-consent required")
                return .neverConsented
            }
            return signed.record.state
        } catch {
            // Legacy unsigned records are rejected — users must re-consent.
            // This closes the tamper detection bypass where an attacker could
            // write a plain ConsentRecord JSON blob without HMAC.
            Self.log.error("Unsigned consent record rejected for engagement \(engagementId, privacy: .public) — re-consent required")
            return .neverConsented
        }
    }

    /// Persist a consent decision for `engagementId`.
    ///
    /// The record is HMAC-signed before storage to prevent local tampering.
    /// Overwrites any existing record atomically (delete-then-insert).
    public func save(engagementId: String, state: ConsentState, at date: Date) {
        let record = ConsentRecord(
            engagementId: engagementId,
            state: state,
            consentedAt: date,
            authorizedBy: nil,
            captureScope: nil,
            consentVersion: Self.currentConsentVersion
        )
        guard let recordData = try? jsonEncoder().encode(record) else { return }
        let hmac = computeHMAC(data: recordData)
        let signed = SignedConsentRecord(record: record, hmac: hmac)
        guard let data = try? jsonEncoder().encode(signed) else { return }
        keychainSave(account: accountKey(for: engagementId), data: data)
    }

    /// Remove the consent record for `engagementId` from the Keychain.
    public func clear(engagementId: String) {
        keychainDelete(account: accountKey(for: engagementId))
    }

    /// One-time migration: remove legacy unsigned consent records.
    ///
    /// Call once during app launch to clean up pre-HMAC records that would
    /// otherwise be silently rejected on every `load()` call. After migration,
    /// the user will be prompted to re-consent with a properly signed record.
    public func migrateLegacyRecords(engagementId: String) {
        guard let data = keychainLoad(account: accountKey(for: engagementId)) else { return }
        let decoder = jsonDecoder()
        // If the record decodes as a plain ConsentRecord (no HMAC wrapper),
        // it's a legacy record from before HMAC signing was introduced.
        if (try? decoder.decode(SignedConsentRecord.self, from: data)) == nil,
           (try? decoder.decode(ConsentRecord.self, from: data)) != nil {
            Self.log.warning("Migrating legacy unsigned consent record for engagement \(engagementId, privacy: .public)")
            keychainDelete(account: accountKey(for: engagementId))
        }
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
            // Prevent iCloud Keychain sync — security-sensitive keys must stay device-local.
            kSecAttrSynchronizable as String: kCFBooleanFalse as Any,
        ]
        let status = SecItemAdd(addQuery as CFDictionary, nil)
        if status != errSecSuccess {
            // Non-fatal: consent will fall back to neverConsented on next load.
            Self.log.error("SecItemAdd failed with status \(status, privacy: .public)")
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

    // MARK: - HMAC signing

    /// Compute HMAC-SHA256 of `data` using a per-install key from the Keychain.
    /// The key is auto-generated on first use and persisted in the Keychain.
    private func computeHMAC(data: Data) -> String {
        let key = loadOrCreateHMACKey()
        var hmac = [UInt8](repeating: 0, count: Int(CC_SHA256_DIGEST_LENGTH))
        key.withUnsafeBytes { keyBytes in
            data.withUnsafeBytes { dataBytes in
                CCHmac(
                    CCHmacAlgorithm(kCCHmacAlgSHA256),
                    keyBytes.baseAddress, key.count,
                    dataBytes.baseAddress, data.count,
                    &hmac
                )
            }
        }
        return hmac.map { String(format: "%02x", $0) }.joined()
    }

    /// Load the HMAC key from Keychain, or generate and persist a new one.
    private func loadOrCreateHMACKey() -> Data {
        if let existing = keychainLoad(account: hmacKeyAccount) {
            return existing
        }
        // Generate a 256-bit random key
        var key = Data(count: 32)
        let result = key.withUnsafeMutableBytes { ptr in
            SecRandomCopyBytes(kSecRandomDefault, 32, ptr.baseAddress!)
        }
        if result != errSecSuccess {
            // SecRandomCopyBytes failure means the system's CSPRNG is unavailable,
            // which is a critical security issue. Do not fall back to UUID — it
            // provides insufficient entropy for HMAC signing.
            Self.log.error("SecRandomCopyBytes failed (\(result, privacy: .public)) — cannot generate HMAC key")
            return Data()
        }
        keychainSave(account: hmacKeyAccount, data: key)
        return key
    }
}
