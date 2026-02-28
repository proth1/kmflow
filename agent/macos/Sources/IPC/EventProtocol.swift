/// Event types and payloads matching the KMFlow backend DesktopEventType enum.
///
/// These Codable structs are serialized as ndjson over the Unix domain socket
/// to the Python intelligence layer. They MUST match the Python dataclasses
/// in `agent/python/kmflow_agent/ipc/protocol.py`.

import Foundation

// MARK: - Event Types (mirrors src/core/models/taskmining.py DesktopEventType)

public enum DesktopEventType: String, Codable, CaseIterable, Sendable {
    case appSwitch = "app_switch"
    case windowFocus = "window_focus"
    case mouseClick = "mouse_click"
    case mouseDoubleClick = "mouse_double_click"
    case mouseDrag = "mouse_drag"
    case keyboardAction = "keyboard_action"
    case keyboardShortcut = "keyboard_shortcut"
    case copyPaste = "copy_paste"
    case scroll = "scroll"
    case tabSwitch = "tab_switch"
    case fileOpen = "file_open"
    case fileSave = "file_save"
    case urlNavigation = "url_navigation"
    case screenCapture = "screen_capture"
    case uiElementInteraction = "ui_element_interaction"
    case idleStart = "idle_start"
    case idleEnd = "idle_end"
}

// MARK: - Base Event

public struct CaptureEvent: Codable, Sendable {
    public let eventType: DesktopEventType
    public let timestamp: Date
    public let applicationName: String?
    public let bundleIdentifier: String?
    public let windowTitle: String?
    public let eventData: [String: AnyCodable]?
    public let idempotencyKey: String?
    public let sequenceNumber: UInt64

    public init(
        eventType: DesktopEventType,
        timestamp: Date = Date(),
        applicationName: String? = nil,
        bundleIdentifier: String? = nil,
        windowTitle: String? = nil,
        eventData: [String: AnyCodable]? = nil,
        idempotencyKey: String? = nil,
        sequenceNumber: UInt64
    ) {
        self.eventType = eventType
        self.timestamp = timestamp
        self.applicationName = applicationName
        self.bundleIdentifier = bundleIdentifier
        self.windowTitle = windowTitle
        self.eventData = eventData
        self.idempotencyKey = idempotencyKey
        self.sequenceNumber = sequenceNumber
    }

    enum CodingKeys: String, CodingKey {
        case eventType = "event_type"
        case timestamp
        case applicationName = "application_name"
        case bundleIdentifier = "bundle_identifier"
        case windowTitle = "window_title"
        case eventData = "event_data"
        case idempotencyKey = "idempotency_key"
        case sequenceNumber = "sequence_number"
    }
}

// MARK: - AnyCodable (type-erased JSON value)

public struct AnyCodable: Codable, Sendable {
    /// The stored value. Only primitive Sendable types (Int, Double, Bool,
    /// String, [AnyCodable], [String: AnyCodable], NSNull) are stored.
    public let value: any Sendable

    /// Create an AnyCodable from a Sendable value.
    ///
    /// Only Sendable types should be stored to maintain thread safety.
    public init(_ value: any Sendable) {
        self.value = value
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let intVal = try? container.decode(Int.self) {
            value = intVal
        } else if let doubleVal = try? container.decode(Double.self) {
            value = doubleVal
        } else if let boolVal = try? container.decode(Bool.self) {
            value = boolVal
        } else if let stringVal = try? container.decode(String.self) {
            value = stringVal
        } else if let arrayVal = try? container.decode([AnyCodable].self) {
            value = arrayVal
        } else if let dictVal = try? container.decode([String: AnyCodable].self) {
            value = dictVal
        } else if container.decodeNil() {
            value = NSNull()
        } else {
            value = NSNull()
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch value {
        case let intVal as Int:
            try container.encode(intVal)
        case let doubleVal as Double:
            try container.encode(doubleVal)
        case let boolVal as Bool:
            try container.encode(boolVal)
        case let stringVal as String:
            try container.encode(stringVal)
        case let arrayVal as [AnyCodable]:
            try container.encode(arrayVal)
        case let dictVal as [String: AnyCodable]:
            try container.encode(dictVal)
        default:
            try container.encodeNil()
        }
    }
}
