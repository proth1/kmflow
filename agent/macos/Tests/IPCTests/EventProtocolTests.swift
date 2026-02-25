import IPC
import XCTest

final class EventProtocolTests: XCTestCase {
    func testEventRoundTrip() throws {
        let event = CaptureEvent(
            eventType: .appSwitch,
            applicationName: "Excel",
            bundleIdentifier: "com.microsoft.Excel",
            windowTitle: "Budget.xlsx",
            eventData: ["dwell_ms": AnyCodable(1500)],
            idempotencyKey: "test-key-1",
            sequenceNumber: 42
        )

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(event)

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let decoded = try decoder.decode(CaptureEvent.self, from: data)

        XCTAssertEqual(decoded.eventType, .appSwitch)
        XCTAssertEqual(decoded.applicationName, "Excel")
        XCTAssertEqual(decoded.bundleIdentifier, "com.microsoft.Excel")
        XCTAssertEqual(decoded.windowTitle, "Budget.xlsx")
        XCTAssertEqual(decoded.idempotencyKey, "test-key-1")
        XCTAssertEqual(decoded.sequenceNumber, 42)
    }

    func testAllEventTypes() {
        XCTAssertEqual(DesktopEventType.allCases.count, 17)
        XCTAssertEqual(DesktopEventType.appSwitch.rawValue, "app_switch")
        XCTAssertEqual(DesktopEventType.idleEnd.rawValue, "idle_end")
    }

    func testIPCMessageEnvelope() throws {
        let event = CaptureEvent(
            eventType: .mouseClick,
            sequenceNumber: 1
        )
        let message = IPCMessage(event: event)

        XCTAssertEqual(message.version, 1)
        XCTAssertEqual(message.sequenceNumber, 1)
        XCTAssertGreaterThan(message.timestampNs, 0)

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(message)
        XCTAssertGreaterThan(data.count, 0)
    }

    func testAnyCodableTypes() throws {
        let values: [String: AnyCodable] = [
            "int": AnyCodable(42),
            "double": AnyCodable(3.14),
            "bool": AnyCodable(true),
            "string": AnyCodable("hello"),
        ]

        let data = try JSONEncoder().encode(values)
        let decoded = try JSONDecoder().decode([String: AnyCodable].self, from: data)

        XCTAssertEqual(decoded["int"]?.value as? Int, 42)
        XCTAssertEqual(decoded["string"]?.value as? String, "hello")
        XCTAssertEqual(decoded["bool"]?.value as? Bool, true)
    }
}
