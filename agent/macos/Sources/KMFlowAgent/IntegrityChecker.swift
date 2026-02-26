/// Verifies the SHA-256 manifest of bundled Python files at agent launch.
///
/// The integrity manifest (`integrity.json`) is generated during the build
/// pipeline and embedded in the app bundle alongside the Python layer.
/// Verifying it at startup prevents tampered Python code from running under
/// the agent's entitlements.

import CryptoKit
import Foundation
import os.log

// MARK: - IntegrityResult

/// The outcome of a manifest verification pass.
public enum IntegrityResult: Sendable, Equatable {
    /// All files matched their expected SHA-256 digests.
    case passed

    /// One or more files failed the digest check.
    ///
    /// - Parameter violations: Relative file paths whose digests did not match.
    case failed(violations: [String])

    /// `integrity.json` was not found in the resources directory.
    case manifestMissing
}

// MARK: - ManifestPayload (private JSON shape)

private struct ManifestPayload: Decodable {
    /// Map of relative file path → lowercase hex SHA-256 digest.
    let files: [String: String]
}

// MARK: - IntegrityChecker

/// Stateless utility for verifying the Python layer's file integrity.
public struct IntegrityChecker: Sendable {

    private static let log = os.Logger(
        subsystem: "com.kmflow.agent",
        category: "IntegrityChecker"
    )

    // Prevent instantiation — use the static API.
    private init() {}

    // MARK: - Public API

    /// Verify every file listed in `integrity.json` against its expected digest.
    ///
    /// - Parameter bundleResourcesPath: The directory that contains both
    ///   `integrity.json` and the Python source tree (typically
    ///   `Bundle.main.resourceURL`).
    /// - Returns: `.passed`, `.failed(violations:)`, or `.manifestMissing`.
    public static func verify(bundleResourcesPath: URL) -> IntegrityResult {
        let manifestURL = bundleResourcesPath.appendingPathComponent("integrity.json")

        // Read manifest.
        guard let manifestData = try? Data(contentsOf: manifestURL) else {
            log.error("integrity.json not found at \(manifestURL.path, privacy: .public)")
            return .manifestMissing
        }

        // Decode manifest.
        let manifest: ManifestPayload
        do {
            manifest = try JSONDecoder().decode(ManifestPayload.self, from: manifestData)
        } catch {
            log.error("Failed to decode integrity.json: \(error.localizedDescription, privacy: .public)")
            return .manifestMissing
        }

        var violations: [String] = []

        for (relativePath, expectedHex) in manifest.files.sorted(by: { $0.key < $1.key }) {
            let fileURL = bundleResourcesPath.appendingPathComponent(relativePath)

            guard let fileData = try? Data(contentsOf: fileURL) else {
                log.error("Integrity violation — file missing: \(relativePath, privacy: .public)")
                violations.append(relativePath)
                continue
            }

            let actualHex = sha256Hex(data: fileData)
            if actualHex != expectedHex.lowercased() {
                log.error(
                    "Integrity violation — digest mismatch: \(relativePath, privacy: .public) expected=\(expectedHex, privacy: .public) actual=\(actualHex, privacy: .public)"
                )
                violations.append(relativePath)
            }
        }

        if violations.isEmpty {
            log.info("Integrity check passed (\(manifest.files.count, privacy: .public) files verified)")
            return .passed
        } else {
            log.error("Integrity check FAILED — \(violations.count, privacy: .public) violation(s)")
            return .failed(violations: violations)
        }
    }

    // MARK: - Private

    /// Compute the lowercase hex-encoded SHA-256 digest of `data`.
    private static func sha256Hex(data: Data) -> String {
        let digest = SHA256.hash(data: data)
        return digest.map { String(format: "%02x", $0) }.joined()
    }
}
