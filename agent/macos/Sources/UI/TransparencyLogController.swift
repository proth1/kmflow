/// Controller that reads captured events from the local SQLite buffer
/// and publishes them for display in `TransparencyLogView`.
///
/// The buffer's sensitive columns (window_title, app_name) are encrypted
/// with AES-256-GCM using a per-install key stored in the macOS Keychain.
/// This controller decrypts rows for display in the transparency log UI.
///
/// This controller opens a **read-only** SQLite connection so it cannot
/// corrupt the live capture buffer.

import CommonCrypto
import Foundation
import Security
import SQLite3
import SwiftUI

// MARK: - TransparencyEvent

/// A display-friendly snapshot of one row from the SQLite capture buffer.
public struct TransparencyEvent: Identifiable, Sendable {
    /// UUID primary key from the buffer row.
    public let id: String
    /// Wall-clock time the event was recorded.
    public let timestamp: Date
    /// Matches `DesktopEventType.rawValue` (e.g. `"app_switch"`).
    public let eventType: String
    /// Application that was active when the event fired.
    public let appName: String?
    /// Window title at the time of the event (may be nil or already redacted).
    public let windowTitle: String?
    /// `true` if the Python PII filter redacted one or more fields.
    public let piiRedacted: Bool
}

// MARK: - TransparencyLogController

/// `ObservableObject` that drives `TransparencyLogView`.
///
/// Polling is intentionally coarse (5 s) to avoid contending with the
/// Python writer.  The controller stops the timer automatically when
/// deallocated.
@MainActor
public final class TransparencyLogController: ObservableObject {

    // MARK: - Published state

    /// Most-recent batch of events from the buffer, newest first.
    @Published public private(set) var events: [TransparencyEvent] = []

    /// Human-readable status message shown in the footer when the buffer
    /// is absent or unreadable.
    @Published public private(set) var statusMessage: String = ""

    // MARK: - Configuration

    private let databaseURL: URL
    private let bufferEncryptionKeyKeychainKey = "buffer_encryption_key"
    private let keychainService = "com.kmflow.agent"

    // MARK: - Timer

    private var refreshTimer: Timer?
    private let refreshInterval: TimeInterval = 5

    // MARK: - Init / deinit

    public init() {
        let appSupport = FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask
        ).first!
        databaseURL = appSupport
            .appendingPathComponent("KMFlowAgent")
            .appendingPathComponent("buffer.db")
    }

    deinit {
        refreshTimer?.invalidate()
    }

    // MARK: - Public API

    /// Start the 5-second polling timer and perform an immediate load.
    public func startRefreshing() {
        loadEvents()
        refreshTimer = Timer.scheduledTimer(
            withTimeInterval: refreshInterval,
            repeats: true
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.loadEvents()
            }
        }
    }

    /// Stop polling (call when the view disappears).
    public func stopRefreshing() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }

    /// Synchronously read up to `limit` events from the SQLite buffer.
    ///
    /// Events are returned newest-first so the list scrolls to the top
    /// when new activity arrives.
    public func loadEvents(limit: Int = 200) {
        guard FileManager.default.fileExists(atPath: databaseURL.path) else {
            events = []
            statusMessage = "No events captured yet."
            return
        }

        // Load the AES-256-GCM encryption key from Keychain for decryption.
        // If no key exists yet (first launch, or pre-encryption data), rows
        // are read as plaintext for backward compatibility.
        let encryptionKey = loadBufferKeyFromKeychain()

        var db: OpaquePointer?
        let openFlags = SQLITE_OPEN_READONLY | SQLITE_OPEN_NOMUTEX
        let openResult = sqlite3_open_v2(databaseURL.path, &db, openFlags, nil)
        guard openResult == SQLITE_OK, let database = db else {
            statusMessage = "Cannot open event buffer."
            sqlite3_close(db)
            return
        }
        defer { sqlite3_close(database) }

        let sql = """
            SELECT id, timestamp, event_type, app_name, window_title, pii_redacted
            FROM events
            ORDER BY timestamp DESC
            LIMIT ?;
            """

        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(database, sql, -1, &stmt, nil) == SQLITE_OK,
              let statement = stmt else {
            statusMessage = "Cannot read event buffer."
            return
        }
        defer { sqlite3_finalize(statement) }

        sqlite3_bind_int(statement, 1, Int32(limit))

        var loaded: [TransparencyEvent] = []
        loaded.reserveCapacity(limit)

        while sqlite3_step(statement) == SQLITE_ROW {
            guard let event = row(from: statement, encryptionKey: encryptionKey) else { continue }
            loaded.append(event)
        }

        events = loaded
        statusMessage = loaded.isEmpty ? "No events captured yet." : ""
    }

    // MARK: - Private helpers

    /// Decode one SQLite row into a `TransparencyEvent`.
    /// If `encryptionKey` is provided, attempts AES-256-GCM decryption of
    /// app_name and window_title columns. Falls back to plaintext on failure.
    private func row(from stmt: OpaquePointer, encryptionKey: Data? = nil) -> TransparencyEvent? {
        // Column 0: id (TEXT)
        guard let idCStr = sqlite3_column_text(stmt, 0) else { return nil }
        let id = String(cString: idCStr)

        // Column 1: timestamp (REAL — Unix epoch seconds, or TEXT ISO8601)
        let tsRaw: Date
        switch sqlite3_column_type(stmt, 1) {
        case SQLITE_FLOAT, SQLITE_INTEGER:
            let epochSeconds = sqlite3_column_double(stmt, 1)
            tsRaw = Date(timeIntervalSince1970: epochSeconds)
        case SQLITE_TEXT:
            if let tsCStr = sqlite3_column_text(stmt, 1) {
                let tsString = String(cString: tsCStr)
                tsRaw = ISO8601DateFormatter().date(from: tsString) ?? Date()
            } else {
                tsRaw = Date()
            }
        default:
            tsRaw = Date()
        }

        // Column 2: event_type (TEXT)
        let eventType: String
        if let etCStr = sqlite3_column_text(stmt, 2) {
            eventType = String(cString: etCStr)
        } else {
            eventType = "unknown"
        }

        // Column 3: app_name (TEXT, nullable — may be AES-256-GCM encrypted)
        let appName: String?
        if let anCStr = sqlite3_column_text(stmt, 3) {
            let raw = String(cString: anCStr)
            appName = decryptIfNeeded(raw, key: encryptionKey)
        } else {
            appName = nil
        }

        // Column 4: window_title (TEXT, nullable — may be AES-256-GCM encrypted)
        let windowTitle: String?
        if let wtCStr = sqlite3_column_text(stmt, 4) {
            let raw = String(cString: wtCStr)
            windowTitle = decryptIfNeeded(raw, key: encryptionKey)
        } else {
            windowTitle = nil
        }

        // Column 5: pii_redacted (INTEGER 0/1)
        let piiRedacted = sqlite3_column_int(stmt, 5) != 0

        return TransparencyEvent(
            id: id,
            timestamp: tsRaw,
            eventType: eventType,
            appName: appName,
            windowTitle: windowTitle,
            piiRedacted: piiRedacted
        )
    }

    /// Retrieve the buffer encryption key from the Keychain.
    ///
    /// Returns `nil` if the key has not yet been provisioned (e.g. first
    /// launch before Python writes its first event).
    private func loadBufferKeyFromKeychain() -> Data? {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: bufferEncryptionKeyKeychainKey,
            kSecReturnData as String:  true,
            kSecMatchLimit as String:  kSecMatchLimitOne,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess else { return nil }
        return result as? Data
    }

    /// Provision a new AES-256-GCM encryption key in the Keychain.
    ///
    /// Called once during initial setup. The Python layer reads this same
    /// key to encrypt buffer rows; the Swift layer reads it to decrypt.
    @discardableResult
    public func provisionEncryptionKey() -> Data? {
        // Don't overwrite an existing key
        if let existing = loadBufferKeyFromKeychain() {
            return existing
        }
        // Generate 256-bit random key
        var keyData = Data(count: 32)
        let result = keyData.withUnsafeMutableBytes { ptr in
            SecRandomCopyBytes(kSecRandomDefault, 32, ptr.baseAddress!)
        }
        guard result == errSecSuccess else { return nil }

        let addQuery: [String: Any] = [
            kSecClass as String:          kSecClassGenericPassword,
            kSecAttrService as String:    keychainService,
            kSecAttrAccount as String:    bufferEncryptionKeyKeychainKey,
            kSecValueData as String:      keyData,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
            // Prevent iCloud Keychain sync — encryption key must stay device-local.
            kSecAttrSynchronizable as String: kCFBooleanFalse as Any,
        ]
        let status = SecItemAdd(addQuery as CFDictionary, nil)
        guard status == errSecSuccess else { return nil }
        return keyData
    }

    /// Attempt to decrypt a base64-encoded AES-256-GCM ciphertext.
    ///
    /// Expected format: base64(nonce‖ciphertext‖tag) where nonce = 12 bytes,
    /// tag = 16 bytes (appended by Python's `cryptography` library).
    /// Returns the plaintext string on success, or the original string if
    /// decryption fails (backward compat with pre-encryption data).
    private func decryptIfNeeded(_ value: String, key: Data?) -> String {
        guard let key = key,
              let cipherData = Data(base64Encoded: value),
              cipherData.count > 28 // 12 (nonce) + 0 (min plaintext) + 16 (tag)
        else {
            return value // plaintext or no key — return as-is
        }

        let nonceSize = 12
        let tagSize = 16
        let nonce = cipherData.prefix(nonceSize)
        let ciphertextAndTag = cipherData.dropFirst(nonceSize)
        let ciphertext = ciphertextAndTag.dropLast(tagSize)
        let tag = ciphertextAndTag.suffix(tagSize)

        // Use CommonCrypto's CCCryptorGCM for AES-256-GCM decryption
        var plaintext = Data(count: ciphertext.count)
        var tagBuffer = [UInt8](tag)

        let status = plaintext.withUnsafeMutableBytes { ptPtr in
            ciphertext.withUnsafeBytes { ctPtr in
                nonce.withUnsafeBytes { noncePtr in
                    key.withUnsafeBytes { keyPtr in
                        CCCryptorGCMOneshotDecrypt(
                            CCAlgorithm(kCCAlgorithmAES),
                            keyPtr.baseAddress!, key.count,
                            noncePtr.baseAddress!, nonceSize,
                            nil, 0, // no additional authenticated data
                            ctPtr.baseAddress!, ciphertext.count,
                            ptPtr.baseAddress!,
                            &tagBuffer, tagSize
                        )
                    }
                }
            }
        }

        if status == kCCSuccess, let decrypted = String(data: plaintext, encoding: .utf8) {
            return decrypted
        }
        // Decryption failed — likely plaintext data from before encryption was enabled
        return value
    }
}
