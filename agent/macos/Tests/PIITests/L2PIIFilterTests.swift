import Capture
import XCTest

final class L2PIIFilterTests: XCTestCase {

    // MARK: - Existing patterns

    func testScrubSSN() {
        XCTAssertEqual(L2PIIFilter.scrub("SSN: 123-45-6789"), "SSN: [PII_REDACTED]")
    }

    func testScrubEmail() {
        XCTAssertEqual(L2PIIFilter.scrub("Contact: user@example.com"), "Contact: [PII_REDACTED]")
    }

    func testScrubPhone() {
        XCTAssertEqual(L2PIIFilter.scrub("Call (555) 123-4567"), "Call [PII_REDACTED]")
    }

    func testScrubCreditCard() {
        XCTAssertEqual(L2PIIFilter.scrub("Card: 4111-1111-1111-1111"), "Card: [PII_REDACTED]")
    }

    func testScrubAmex() {
        XCTAssertEqual(L2PIIFilter.scrub("Amex: 3782 822463 10005"), "Amex: [PII_REDACTED]")
    }

    // MARK: - New patterns (IBAN, file path, UK NINO)

    func testScrubIBAN() {
        XCTAssertEqual(
            L2PIIFilter.scrub("Account: DE89 3704 0044 0532 0130 00"),
            "Account: [PII_REDACTED]"
        )
    }

    func testScrubIBANCompact() {
        XCTAssertEqual(
            L2PIIFilter.scrub("IBAN: GB29NWBK60161331926819"),
            "IBAN: [PII_REDACTED]"
        )
    }

    func testScrubFilePath() {
        XCTAssertEqual(
            L2PIIFilter.scrub("Editing /Users/jdoe/Documents/secret.docx"),
            "Editing [PII_REDACTED]"
        )
    }

    func testScrubWindowsFilePath() {
        XCTAssertEqual(
            L2PIIFilter.scrub("Open C:\\Users\\jdoe\\report.xlsx"),
            "Open [PII_REDACTED]"
        )
    }

    func testScrubUKNINO() {
        XCTAssertEqual(
            L2PIIFilter.scrub("NI Number: AB 12 34 56 C"),
            "NI Number: [PII_REDACTED]"
        )
    }

    // MARK: - Negative cases

    func testNoFalsePositiveOnShortNumber() {
        let text = "Page 42 of 100"
        XCTAssertEqual(L2PIIFilter.scrub(text), text, "Short numbers should not trigger PII detection")
    }

    func testNoFalsePositiveOnNormalText() {
        let text = "Quarterly Report - Q4 2025"
        XCTAssertEqual(L2PIIFilter.scrub(text), text)
    }

    // MARK: - containsPII

    func testContainsPIIDetectsIBAN() {
        XCTAssertTrue(L2PIIFilter.containsPII("DE89 3704 0044 0532 0130 00"))
    }

    func testContainsPIIReturnsFalseForCleanText() {
        XCTAssertFalse(L2PIIFilter.containsPII("Budget Report 2025"))
    }
}
