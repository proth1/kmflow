// Event types and payloads matching the KMFlow backend DesktopEventType enum.
//
// These C# types are serialized as ndjson over a named pipe to the Python
// intelligence layer. They MUST match the Python dataclasses in
// agent/python/kmflow_agent/ipc/protocol.py and the Swift structs in
// agent/macos/Sources/IPC/EventProtocol.swift.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace KMFlowAgent.IPC;

/// <summary>
/// Desktop event types — mirrors src/core/models/taskmining.py DesktopEventType
/// and agent/python/kmflow_agent/ipc/protocol.py DesktopEventType.
/// </summary>
[JsonConverter(typeof(JsonStringEnumConverter<DesktopEventType>))]
public enum DesktopEventType
{
    [JsonStringEnumMemberName("app_switch")]
    AppSwitch,

    [JsonStringEnumMemberName("window_focus")]
    WindowFocus,

    [JsonStringEnumMemberName("mouse_click")]
    MouseClick,

    [JsonStringEnumMemberName("mouse_double_click")]
    MouseDoubleClick,

    [JsonStringEnumMemberName("mouse_drag")]
    MouseDrag,

    [JsonStringEnumMemberName("keyboard_action")]
    KeyboardAction,

    [JsonStringEnumMemberName("keyboard_shortcut")]
    KeyboardShortcut,

    [JsonStringEnumMemberName("copy_paste")]
    CopyPaste,

    [JsonStringEnumMemberName("scroll")]
    Scroll,

    [JsonStringEnumMemberName("tab_switch")]
    TabSwitch,

    [JsonStringEnumMemberName("file_open")]
    FileOpen,

    [JsonStringEnumMemberName("file_save")]
    FileSave,

    [JsonStringEnumMemberName("url_navigation")]
    UrlNavigation,

    [JsonStringEnumMemberName("screen_capture")]
    ScreenCapture,

    [JsonStringEnumMemberName("ui_element_interaction")]
    UiElementInteraction,

    [JsonStringEnumMemberName("idle_start")]
    IdleStart,

    [JsonStringEnumMemberName("idle_end")]
    IdleEnd,
}

/// <summary>
/// A single desktop capture event sent from C# to the Python intelligence layer.
///
/// Field names and JSON keys exactly match the Python CaptureEvent dataclass
/// and Swift CaptureEvent struct. All JSON keys use snake_case.
/// </summary>
public sealed class CaptureEvent
{
    /// <summary>Type of desktop event.</summary>
    [JsonPropertyName("event_type")]
    public required DesktopEventType EventType { get; init; }

    /// <summary>ISO 8601 timestamp when the event was captured.</summary>
    [JsonPropertyName("timestamp")]
    public required string Timestamp { get; init; }

    /// <summary>Monotonically increasing sequence number for ordering and dedup.</summary>
    [JsonPropertyName("sequence_number")]
    public required ulong SequenceNumber { get; init; }

    /// <summary>Display name of the application (e.g., "Microsoft Excel").</summary>
    [JsonPropertyName("application_name")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ApplicationName { get; init; }

    /// <summary>
    /// Canonical application identifier. On macOS this is the bundle ID
    /// (com.microsoft.Excel). On Windows this is resolved by ProcessIdentifier
    /// from exe path, AppUserModelId, or mapping table.
    /// </summary>
    [JsonPropertyName("bundle_identifier")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? BundleIdentifier { get; init; }

    /// <summary>Title of the focused window (may contain [PII_REDACTED] tokens after L2).</summary>
    [JsonPropertyName("window_title")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? WindowTitle { get; init; }

    /// <summary>
    /// Event-specific payload data. Keys and value types vary by event type.
    /// Examples: char_count, duration_ms, shortcut_keys, button, x, y.
    /// </summary>
    [JsonPropertyName("event_data")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public Dictionary<string, object>? EventData { get; init; }

    /// <summary>UUID for idempotent event processing.</summary>
    [JsonPropertyName("idempotency_key")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? IdempotencyKey { get; init; }

    /// <summary>Create a CaptureEvent with the current timestamp in ISO 8601 format.</summary>
    public static CaptureEvent Create(
        DesktopEventType eventType,
        ulong sequenceNumber,
        string? applicationName = null,
        string? bundleIdentifier = null,
        string? windowTitle = null,
        Dictionary<string, object>? eventData = null,
        string? idempotencyKey = null)
    {
        return new CaptureEvent
        {
            EventType = eventType,
            Timestamp = DateTime.UtcNow.ToString("O"),
            SequenceNumber = sequenceNumber,
            ApplicationName = applicationName,
            BundleIdentifier = bundleIdentifier,
            WindowTitle = windowTitle,
            EventData = eventData,
            IdempotencyKey = idempotencyKey ?? Guid.NewGuid().ToString(),
        };
    }
}

/// <summary>
/// JSON serialization context for NativeAOT-compatible source generation.
/// System.Text.Json source generators avoid reflection, which NativeAOT
/// does not fully support.
/// </summary>
[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower,
    WriteIndented = false,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
[JsonSerializable(typeof(CaptureEvent))]
[JsonSerializable(typeof(DesktopEventType))]
[JsonSerializable(typeof(Dictionary<string, object>))]
public partial class EventProtocolJsonContext : JsonSerializerContext
{
}
