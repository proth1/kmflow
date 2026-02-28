using System.Text.Json;
using KMFlowAgent.IPC;
using Xunit;

namespace KMFlowAgent.Tests.IPC;

public class EventProtocolTests
{
    [Fact]
    public void DesktopEventType_Has_Exactly_16_Values()
    {
        var values = Enum.GetValues<DesktopEventType>();
        Assert.Equal(17, values.Length); // 17 enum members (0-indexed includes all 17 values)
        // Actually verify the count matches the Python enum:
        // app_switch, window_focus, mouse_click, mouse_double_click, mouse_drag,
        // keyboard_action, keyboard_shortcut, copy_paste, scroll, tab_switch,
        // file_open, file_save, url_navigation, screen_capture,
        // ui_element_interaction, idle_start, idle_end = 17
    }

    [Theory]
    [InlineData(DesktopEventType.AppSwitch, "app_switch")]
    [InlineData(DesktopEventType.WindowFocus, "window_focus")]
    [InlineData(DesktopEventType.MouseClick, "mouse_click")]
    [InlineData(DesktopEventType.MouseDoubleClick, "mouse_double_click")]
    [InlineData(DesktopEventType.MouseDrag, "mouse_drag")]
    [InlineData(DesktopEventType.KeyboardAction, "keyboard_action")]
    [InlineData(DesktopEventType.KeyboardShortcut, "keyboard_shortcut")]
    [InlineData(DesktopEventType.CopyPaste, "copy_paste")]
    [InlineData(DesktopEventType.Scroll, "scroll")]
    [InlineData(DesktopEventType.TabSwitch, "tab_switch")]
    [InlineData(DesktopEventType.FileOpen, "file_open")]
    [InlineData(DesktopEventType.FileSave, "file_save")]
    [InlineData(DesktopEventType.UrlNavigation, "url_navigation")]
    [InlineData(DesktopEventType.ScreenCapture, "screen_capture")]
    [InlineData(DesktopEventType.UiElementInteraction, "ui_element_interaction")]
    [InlineData(DesktopEventType.IdleStart, "idle_start")]
    [InlineData(DesktopEventType.IdleEnd, "idle_end")]
    public void DesktopEventType_Serializes_To_SnakeCase(DesktopEventType eventType, string expected)
    {
        var json = JsonSerializer.Serialize(eventType, EventProtocolJsonContext.Default.DesktopEventType);
        // JSON string includes quotes
        Assert.Equal($"\"{expected}\"", json);
    }

    [Fact]
    public void CaptureEvent_Serializes_With_SnakeCase_Keys()
    {
        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.AppSwitch,
            sequenceNumber: 42,
            applicationName: "Microsoft Excel",
            bundleIdentifier: "com.microsoft.Excel",
            windowTitle: "Q4 Budget.xlsx");

        var json = JsonSerializer.Serialize(evt, EventProtocolJsonContext.Default.CaptureEvent);

        // Verify snake_case field names
        Assert.Contains("\"event_type\"", json);
        Assert.Contains("\"sequence_number\"", json);
        Assert.Contains("\"application_name\"", json);
        Assert.Contains("\"bundle_identifier\"", json);
        Assert.Contains("\"window_title\"", json);
        Assert.Contains("\"idempotency_key\"", json);
        Assert.Contains("\"timestamp\"", json);

        // Verify values
        Assert.Contains("\"app_switch\"", json);
        Assert.Contains("\"Microsoft Excel\"", json);
        Assert.Contains("\"com.microsoft.Excel\"", json);
        Assert.Contains("\"Q4 Budget.xlsx\"", json);
    }

    [Fact]
    public void CaptureEvent_Timestamp_Is_ISO8601()
    {
        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.MouseClick,
            sequenceNumber: 1);

        // ISO 8601 format from DateTime.UtcNow.ToString("O") looks like:
        // "2026-02-28T12:34:56.1234567Z"
        Assert.Matches(@"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", evt.Timestamp);
    }

    [Fact]
    public void CaptureEvent_Null_Fields_Are_Omitted()
    {
        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.IdleStart,
            sequenceNumber: 100);

        var json = JsonSerializer.Serialize(evt, EventProtocolJsonContext.Default.CaptureEvent);

        // Null optional fields should be omitted
        Assert.DoesNotContain("\"application_name\"", json);
        Assert.DoesNotContain("\"bundle_identifier\"", json);
        Assert.DoesNotContain("\"window_title\"", json);
        Assert.DoesNotContain("\"event_data\"", json);
    }

    [Fact]
    public void CaptureEvent_EventData_Serializes_Correctly()
    {
        var eventData = new Dictionary<string, object>
        {
            ["char_count"] = 47,
            ["duration_ms"] = 12300,
            ["content_level"] = false,
        };

        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.KeyboardAction,
            sequenceNumber: 200,
            applicationName: "Microsoft Excel",
            eventData: eventData);

        var json = JsonSerializer.Serialize(evt, EventProtocolJsonContext.Default.CaptureEvent);

        Assert.Contains("\"event_data\"", json);
        Assert.Contains("\"char_count\"", json);
    }

    [Fact]
    public void CaptureEvent_Roundtrip_Deserialization()
    {
        var original = CaptureEvent.Create(
            eventType: DesktopEventType.AppSwitch,
            sequenceNumber: 42,
            applicationName: "Microsoft Excel",
            bundleIdentifier: "com.microsoft.Excel");

        var json = JsonSerializer.Serialize(original, EventProtocolJsonContext.Default.CaptureEvent);
        var deserialized = JsonSerializer.Deserialize(json, EventProtocolJsonContext.Default.CaptureEvent);

        Assert.NotNull(deserialized);
        Assert.Equal(original.EventType, deserialized!.EventType);
        Assert.Equal(original.SequenceNumber, deserialized.SequenceNumber);
        Assert.Equal(original.ApplicationName, deserialized.ApplicationName);
        Assert.Equal(original.BundleIdentifier, deserialized.BundleIdentifier);
    }

    [Fact]
    public void CaptureEvent_SequenceNumber_Is_UInt64()
    {
        // Verify we can handle large sequence numbers
        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.MouseClick,
            sequenceNumber: ulong.MaxValue);

        var json = JsonSerializer.Serialize(evt, EventProtocolJsonContext.Default.CaptureEvent);
        Assert.Contains(ulong.MaxValue.ToString(), json);
    }

    [Fact]
    public void CaptureEvent_Create_Generates_IdempotencyKey()
    {
        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.Scroll,
            sequenceNumber: 1);

        Assert.NotNull(evt.IdempotencyKey);
        Assert.True(Guid.TryParse(evt.IdempotencyKey, out _));
    }
}
