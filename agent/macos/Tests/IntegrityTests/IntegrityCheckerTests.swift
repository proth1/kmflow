import CryptoKit
import Foundation
@testable import KMFlowAgent
import XCTest

final class IntegrityCheckerTests: XCTestCase {

    private var tempDir: URL!

    override func setUpWithError() throws {
        tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("IntegrityCheckerTests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: tempDir)
    }

    // MARK: - Helper: write manifest + signature

    /// Write a valid manifest and HMAC signature for the given file entries.
    private func writeManifestAndSignature(files: [String: String]) throws {
        let manifest = ["files": files]
        let manifestJSON = try JSONSerialization.data(
            withJSONObject: manifest,
            options: [.sortedKeys, .prettyPrinted]
        )
        let manifestString = String(data: manifestJSON, encoding: .utf8)! + "\n"
        let manifestData = Data(manifestString.utf8)
        try manifestData.write(to: tempDir.appendingPathComponent("integrity.json"))

        // Generate HMAC signature matching the build script's format.
        let hmacKey = SymmetricKey(size: .bits256)
        let hmac = HMAC<SHA256>.authenticationCode(for: manifestData, using: hmacKey)
        let hmacHex = hmac.map { String(format: "%02x", $0) }.joined()
        let sha256 = SHA256.hash(data: manifestData).map { String(format: "%02x", $0) }.joined()
        let keyHex = hmacKey.withUnsafeBytes { Data($0).map { String(format: "%02x", $0) }.joined() }

        let sigPayload: [String: String] = [
            "hmac_sha256": hmacHex,
            "key_hex": keyHex,
            "manifest_sha256": sha256,
        ]
        let sigData = try JSONSerialization.data(withJSONObject: sigPayload, options: .prettyPrinted)
        try sigData.write(to: tempDir.appendingPathComponent("integrity.sig"))
    }

    // MARK: - verify()

    func testVerifyPassed() throws {
        let fileContent = "hello, world\n"
        let filePath = tempDir.appendingPathComponent("test.py")
        try fileContent.write(to: filePath, atomically: true, encoding: .utf8)

        let hash = IntegrityChecker.sha256Hex(data: Data(fileContent.utf8))
        let manifest: [String: [String: String]] = ["files": ["test.py": hash]]
        let manifestData = try JSONEncoder().encode(manifest)
        try manifestData.write(to: tempDir.appendingPathComponent("integrity.json"))

        let result = IntegrityChecker.verify(bundleResourcesPath: tempDir)
        XCTAssertEqual(result, .passed)
    }

    func testVerifyFailedDigestMismatch() throws {
        let filePath = tempDir.appendingPathComponent("test.py")
        try "real content".write(to: filePath, atomically: true, encoding: .utf8)

        let manifest: [String: [String: String]] = ["files": ["test.py": "0000000000000000000000000000000000000000000000000000000000000000"]]
        let manifestData = try JSONEncoder().encode(manifest)
        try manifestData.write(to: tempDir.appendingPathComponent("integrity.json"))

        let result = IntegrityChecker.verify(bundleResourcesPath: tempDir)
        if case .failed(let violations) = result {
            XCTAssertEqual(violations, ["test.py"])
        } else {
            XCTFail("Expected .failed, got \(result)")
        }
    }

    func testVerifyFailedMissingFile() throws {
        let manifest: [String: [String: String]] = ["files": ["missing.py": "abc123"]]
        let manifestData = try JSONEncoder().encode(manifest)
        try manifestData.write(to: tempDir.appendingPathComponent("integrity.json"))

        let result = IntegrityChecker.verify(bundleResourcesPath: tempDir)
        if case .failed(let violations) = result {
            XCTAssertEqual(violations, ["missing.py"])
        } else {
            XCTFail("Expected .failed, got \(result)")
        }
    }

    func testVerifyManifestMissing() {
        let result = IntegrityChecker.verify(bundleResourcesPath: tempDir)
        XCTAssertEqual(result, .manifestMissing)
    }

    // MARK: - HMAC signature verification

    func testVerifyWithValidHMACSignature() throws {
        let fileContent = "module code\n"
        let filePath = tempDir.appendingPathComponent("module.py")
        try fileContent.write(to: filePath, atomically: true, encoding: .utf8)

        let hash = IntegrityChecker.sha256Hex(data: Data(fileContent.utf8))
        try writeManifestAndSignature(files: ["module.py": hash])

        let result = IntegrityChecker.verify(bundleResourcesPath: tempDir)
        XCTAssertEqual(result, .passed)
    }

    func testVerifyWithTamperedHMACSignature() throws {
        let fileContent = "module code\n"
        let filePath = tempDir.appendingPathComponent("module.py")
        try fileContent.write(to: filePath, atomically: true, encoding: .utf8)

        let hash = IntegrityChecker.sha256Hex(data: Data(fileContent.utf8))
        try writeManifestAndSignature(files: ["module.py": hash])

        // Tamper: overwrite integrity.sig with a wrong HMAC.
        let badSig: [String: String] = [
            "hmac_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            "key_hex": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "manifest_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
        ]
        let badSigData = try JSONSerialization.data(withJSONObject: badSig)
        try badSigData.write(to: tempDir.appendingPathComponent("integrity.sig"))

        let result = IntegrityChecker.verify(bundleResourcesPath: tempDir)
        if case .failed(let violations) = result {
            XCTAssertTrue(violations.contains("integrity.json (HMAC mismatch)"))
        } else {
            XCTFail("Expected .failed for tampered HMAC, got \(result)")
        }
    }

    // MARK: - sha256Hex()

    func testSHA256Hex() {
        let data = Data("test".utf8)
        let hex = IntegrityChecker.sha256Hex(data: data)
        XCTAssertEqual(hex, "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08")
    }

    // MARK: - Periodic checks

    func testStartAndStopPeriodicChecks() async throws {
        let fileContent = "data"
        let filePath = tempDir.appendingPathComponent("module.py")
        try fileContent.write(to: filePath, atomically: true, encoding: .utf8)

        let hash = IntegrityChecker.sha256Hex(data: Data(fileContent.utf8))
        let manifest: [String: [String: String]] = ["files": ["module.py": hash]]
        let manifestData = try JSONEncoder().encode(manifest)
        try manifestData.write(to: tempDir.appendingPathComponent("integrity.json"))

        let checker = IntegrityChecker(
            bundleResourcesPath: tempDir,
            checkInterval: 0.1
        )

        await checker.startPeriodicChecks()
        await checker.startPeriodicChecks() // double-start should be no-op

        try await Task.sleep(nanoseconds: 300_000_000)

        await checker.stopPeriodicChecks()
        await checker.stopPeriodicChecks() // double-stop should be no-op
    }
}
