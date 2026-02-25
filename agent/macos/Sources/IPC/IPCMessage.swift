/// IPC message envelope wrapping capture events with metadata.

import Foundation

public struct IPCMessage: Codable, Sendable {
    public let version: Int
    public let sequenceNumber: UInt64
    public let timestampNs: UInt64
    public let event: CaptureEvent

    public init(event: CaptureEvent) {
        self.version = 1
        self.sequenceNumber = event.sequenceNumber
        self.timestampNs = UInt64(Date().timeIntervalSince1970 * 1_000_000_000)
        self.event = event
    }

    enum CodingKeys: String, CodingKey {
        case version
        case sequenceNumber = "sequence_number"
        case timestampNs = "timestamp_ns"
        case event
    }
}
