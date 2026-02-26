/// Unified logging wrapper using os_log.

import Foundation
@preconcurrency import os.log

public struct AgentLogger: Sendable {
    private let logger: os.Logger

    public init(category: String) {
        self.logger = os.Logger(subsystem: "com.kmflow.agent", category: category)
    }

    public func info(_ message: String) {
        logger.info("\(message, privacy: .private)")
    }

    public func debug(_ message: String) {
        logger.debug("\(message, privacy: .private)")
    }

    public func warning(_ message: String) {
        logger.warning("\(message, privacy: .private)")
    }

    public func error(_ message: String) {
        logger.error("\(message, privacy: .private)")
    }
}
