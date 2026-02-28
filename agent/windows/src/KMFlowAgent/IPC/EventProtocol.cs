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
///
/// JSON serialization uses snake_case strings via DesktopEventTypeConverter.
/// </summary>
[JsonConverter(typeof(DesktopEventTypeConverter))]
public enum DesktopEventType
{
    AppSwitch,
    WindowFocus,
    MouseClick,
    MouseDoubleClick,
    MouseDrag,
    KeyboardAction,
    KeyboardShortcut,
    CopyPaste,
    Scroll,
    TabSwitch,
    FileOpen,
    FileSave,
    UrlNavigation,
    ScreenCapture,
    UiElementInteraction,
    IdleStart,
    IdleEnd,
}

/// <summary>
/// Custom JSON converter for DesktopEventType that serializes to/from snake_case strings.
/// Compatible with .NET 8 and NativeAOT (no reflection).
/// </summary>
public sealed class DesktopEventTypeConverter : JsonConverter<DesktopEventType>
{
    private static readonly Dictionary<DesktopEventType, string> EnumToString = new()
    {
        [DesktopEventType.AppSwitch] = "app_switch",
        [DesktopEventType.WindowFocus] = "window_focus",
        [DesktopEventType.MouseClick] = "mouse_click",
        [DesktopEventType.MouseDoubleClick] = "mouse_double_click",
        [DesktopEventType.MouseDrag] = "mouse_drag",
        [DesktopEventType.KeyboardAction] = "keyboard_action",
        [DesktopEventType.KeyboardShortcut] = "keyboard_shortcut",
        [DesktopEventType.CopyPaste] = "copy_paste",
        [DesktopEventType.Scroll] = "scroll",
        [DesktopEventType.TabSwitch] = "tab_switch",
        [DesktopEventType.FileOpen] = "file_open",
        [DesktopEventType.FileSave] = "file_save",
        [DesktopEventType.UrlNavigation] = "url_navigation",
        [DesktopEventType.ScreenCapture] = "screen_capture",
        [DesktopEventType.UiElementInteraction] = "ui_element_interaction",
        [DesktopEventType.IdleStart] = "idle_start",
        [DesktopEventType.IdleEnd] = "idle_end",
    };

    private static readonly Dictionary<string, DesktopEventType> StringToEnum =
        EnumToString.ToDictionary(kvp => kvp.Value, kvp => kvp.Key);

    public override DesktopEventType Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        var str = reader.GetString();
        if (str is not null && StringToEnum.TryGetValue(str, out var value))
            return value;
        throw new JsonException($"Unknown DesktopEventType: {str}");
    }

    public override void Write(Utf8JsonWriter writer, DesktopEventType value, JsonSerializerOptions options)
    {
        writer.WriteStringValue(EnumToString[value]);
    }
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
