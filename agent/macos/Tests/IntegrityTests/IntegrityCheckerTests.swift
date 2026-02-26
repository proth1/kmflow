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

    // MARK: - verify()

    func testVerifyPassed() throws {
        // Create a test file and matching manifest.
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

        // Write manifest with a wrong hash.
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
        // Manifest references a file that doesn't exist.
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
        // No integrity.json in tempDir.
        let result = IntegrityChecker.verify(bundleResourcesPath: tempDir)
        XCTAssertEqual(result, .manifestMissing)
    }

    // MARK: - sha256Hex()

    func testSHA256Hex() {
        let data = Data("test".utf8)
        let hex = IntegrityChecker.sha256Hex(data: data)
        // Known SHA-256 of "test"
        XCTAssertEqual(hex, "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08")
    }

    // MARK: - Periodic checks

    func testStartAndStopPeriodicChecks() async throws {
        // Create a valid manifest so periodic checks pass.
        let fileContent = "data"
        let filePath = tempDir.appendingPathComponent("module.py")
        try fileContent.write(to: filePath, atomically: true, encoding: .utf8)

        let hash = IntegrityChecker.sha256Hex(data: Data(fileContent.utf8))
        let manifest: [String: [String: String]] = ["files": ["module.py": hash]]
        let manifestData = try JSONEncoder().encode(manifest)
        try manifestData.write(to: tempDir.appendingPathComponent("integrity.json"))

        let checker = IntegrityChecker(
            bundleResourcesPath: tempDir,
            checkInterval: 0.1 // very short for testing
        )

        checker.startPeriodicChecks()
        // Starting again should be a no-op (no crash).
        checker.startPeriodicChecks()

        // Let one cycle run.
        try await Task.sleep(nanoseconds: 300_000_000) // 300ms

        checker.stopPeriodicChecks()
        // Stopping again should be a no-op.
        checker.stopPeriodicChecks()
    }
}
