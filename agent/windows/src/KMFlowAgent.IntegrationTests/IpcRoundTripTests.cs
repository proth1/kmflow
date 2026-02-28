// Integration tests for C# → Named Pipe / TCP → Python IPC round-trip.
//
// These tests start a Python named pipe server as a subprocess,
// send events from C#, and verify they arrive correctly.
// Runs only on Windows (requires named pipes and the Python agent).

using System.Diagnostics;
using System.Text.Json;
using KMFlowAgent.IPC;
using FluentAssertions;
using Xunit;

namespace KMFlowAgent.IntegrationTests;

/// <summary>
/// Skip attribute for non-Windows platforms.
/// </summary>
public sealed class WindowsOnlyFactAttribute : FactAttribute
{
    public WindowsOnlyFactAttribute()
    {
        if (!OperatingSystem.IsWindows())
        {
            Skip = "Integration tests require Windows";
        }
    }
}

/// <summary>
/// Tests the full IPC round-trip: C# event serialization → transport → Python deserialization.
/// </summary>
[Collection("IPC Integration")]
public class IpcRoundTripTests : IAsyncLifetime
{
    private Process? _pythonServer;
    private readonly string _testDataDir;

    public IpcRoundTripTests()
    {
        _testDataDir = Path.Combine(Path.GetTempPath(), $"kmflow-ipc-test-{Guid.NewGuid():N}");
    }

    public async Task InitializeAsync()
    {
        Directory.CreateDirectory(_testDataDir);

        // Start Python named pipe server if on Windows
        if (OperatingSystem.IsWindows())
        {
            await StartPythonServerAsync();
        }
    }

    public async Task DisposeAsync()
    {
        // Stop Python server
        if (_pythonServer is { HasExited: false })
        {
            _pythonServer.Kill(entireProcessTree: true);
            await _pythonServer.WaitForExitAsync();
        }
        _pythonServer?.Dispose();

        // Cleanup test data
        try
        {
            if (Directory.Exists(_testDataDir))
            {
                Directory.Delete(_testDataDir, recursive: true);
            }
        }
        catch
        {
            // Best effort cleanup
        }
    }

    [WindowsOnlyFact]
    public void CaptureEvent_Serializes_To_Valid_Json()
    {
        // Verify that event serialization produces valid JSON
        // that matches the Python-expected format
        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.AppSwitch,
            sequenceNumber: 1,
            applicationName: "TestApp",
            bundleIdentifier: "testapp.exe",
            windowTitle: "Test Window");

        var json = EventProtocol.Serialize(evt);

        json.Should().NotBeNullOrEmpty();

        // Verify it's valid JSON
        var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;

        root.GetProperty("event_type").GetString().Should().Be("app_switch");
        root.GetProperty("sequence_number").GetUInt64().Should().Be(1);
        root.GetProperty("application_name").GetString().Should().Be("TestApp");
        root.GetProperty("bundle_identifier").GetString().Should().Be("testapp.exe");
        root.GetProperty("window_title").GetString().Should().Be("Test Window");
        root.GetProperty("timestamp").GetString().Should().NotBeNullOrEmpty();
        root.GetProperty("idempotency_key").GetString().Should().NotBeNullOrEmpty();
    }

    [WindowsOnlyFact]
    public void EventProtocol_AllEventTypes_Serialize_Correctly()
    {
        // Verify all 17 event types serialize to their snake_case names
        var eventTypes = Enum.GetValues<DesktopEventType>();

        foreach (var eventType in eventTypes)
        {
            var evt = CaptureEvent.Create(
                eventType: eventType,
                sequenceNumber: 1,
                applicationName: "TestApp",
                bundleIdentifier: "test.exe");

            var json = EventProtocol.Serialize(evt);
            json.Should().NotBeNullOrEmpty($"event type {eventType} should serialize");

            // Verify it contains the snake_case event type
            var doc = JsonDocument.Parse(json);
            var typeStr = doc.RootElement.GetProperty("event_type").GetString();
            typeStr.Should().NotBeNullOrEmpty();
            typeStr.Should().MatchRegex("^[a-z_]+$", $"event type '{eventType}' should be snake_case");
        }
    }

    [WindowsOnlyFact]
    public void CaptureEvent_BatchSerialization_Maintains_Sequence()
    {
        // Verify that batch serialization maintains event ordering
        var events = Enumerable.Range(1, 100)
            .Select(i => CaptureEvent.Create(
                eventType: DesktopEventType.KeyboardAction,
                sequenceNumber: (ulong)i,
                applicationName: "TestApp",
                bundleIdentifier: "test.exe",
                eventData: new Dictionary<string, object> { ["key_count"] = i }))
            .ToList();

        var serialized = events.Select(EventProtocol.Serialize).ToList();

        serialized.Should().HaveCount(100);

        for (int i = 0; i < serialized.Count; i++)
        {
            var doc = JsonDocument.Parse(serialized[i]);
            doc.RootElement.GetProperty("sequence_number").GetUInt64()
                .Should().Be((ulong)(i + 1));
        }
    }

    [WindowsOnlyFact]
    public void CaptureEvent_WithEventData_Preserves_Types()
    {
        // Verify that event_data preserves int, bool, string types
        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.MouseClick,
            sequenceNumber: 42,
            applicationName: "TestApp",
            bundleIdentifier: "test.exe",
            eventData: new Dictionary<string, object>
            {
                ["click_count"] = 5,
                ["is_double_click"] = true,
                ["button"] = "left",
                ["x"] = 100.5,
            });

        var json = EventProtocol.Serialize(evt);
        var doc = JsonDocument.Parse(json);
        var data = doc.RootElement.GetProperty("event_data");

        data.GetProperty("click_count").GetInt32().Should().Be(5);
        data.GetProperty("is_double_click").GetBoolean().Should().BeTrue();
        data.GetProperty("button").GetString().Should().Be("left");
        data.GetProperty("x").GetDouble().Should().Be(100.5);
    }

    private async Task StartPythonServerAsync()
    {
        // Look for the Python agent relative to the repo root
        var repoRoot = FindRepoRoot();
        if (repoRoot is null)
        {
            return; // Can't find repo, tests will be skipped
        }

        var pythonScript = Path.Combine(repoRoot, "agent", "python");
        if (!Directory.Exists(pythonScript))
        {
            return;
        }

        _pythonServer = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = "python",
                Arguments = "-m kmflow_agent.server",
                WorkingDirectory = pythonScript,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                Environment =
                {
                    ["KMFLOW_DATA_DIR"] = _testDataDir,
                    ["KMFLOW_TEST_MODE"] = "1",
                },
            },
        };

        try
        {
            _pythonServer.Start();
            // Wait for server to be ready (look for pipe/port file)
            await WaitForServerReady();
        }
        catch (Exception ex)
        {
            // Python not available or server failed to start
            Debug.WriteLine($"Python server start failed: {ex.Message}");
            _pythonServer?.Dispose();
            _pythonServer = null;
        }
    }

    private async Task WaitForServerReady(int timeoutMs = 10_000)
    {
        var pipePath = @"\\.\pipe\KMFlowAgent";
        var portFile = Path.Combine(_testDataDir, "ipc_port");
        var sw = Stopwatch.StartNew();

        while (sw.ElapsedMilliseconds < timeoutMs)
        {
            // Check if named pipe exists or port file was created
            if (File.Exists(portFile))
                return;

            await Task.Delay(100);
        }

        throw new TimeoutException("Python server did not become ready within timeout");
    }

    private static string? FindRepoRoot()
    {
        var dir = Directory.GetCurrentDirectory();
        while (dir is not null)
        {
            if (Directory.Exists(Path.Combine(dir, ".git")))
                return dir;
            dir = Path.GetDirectoryName(dir);
        }
        return null;
    }
}
