// Unit tests for TransparencyLogViewModel.

using KMFlowAgent.IPC;
using KMFlowAgent.UI;
using Xunit;

namespace KMFlowAgent.Tests.UI;

public class TransparencyLogViewModelTests
{
    [Fact]
    public void AddEvent_InsertsAtBeginning()
    {
        var vm = new TransparencyLogViewModel();

        vm.AddEvent(MakeEvent(1, "First"));
        vm.AddEvent(MakeEvent(2, "Second"));

        Assert.Equal(2, vm.Entries.Count);
        Assert.Equal("Second", vm.Entries[0].Application);
        Assert.Equal("First", vm.Entries[1].Application);
    }

    [Fact]
    public void AddEvent_IncrementsCount()
    {
        var vm = new TransparencyLogViewModel();

        vm.AddEvent(MakeEvent(1));
        vm.AddEvent(MakeEvent(2));

        Assert.Equal(2UL, vm.TotalEventCount);
    }

    [Fact]
    public void AddEvent_TrimsBeyondCapacity()
    {
        var vm = new TransparencyLogViewModel(maxEntries: 3);

        vm.AddEvent(MakeEvent(1, "A"));
        vm.AddEvent(MakeEvent(2, "B"));
        vm.AddEvent(MakeEvent(3, "C"));
        vm.AddEvent(MakeEvent(4, "D"));

        Assert.Equal(3, vm.Entries.Count);
        Assert.Equal("D", vm.Entries[0].Application);
        Assert.Equal("C", vm.Entries[1].Application);
        Assert.Equal("B", vm.Entries[2].Application);
    }

    [Fact]
    public void RecordFiltered_IncrementsFilteredCount()
    {
        var vm = new TransparencyLogViewModel();

        vm.RecordFiltered();
        vm.RecordFiltered();

        Assert.Equal(2UL, vm.FilteredEventCount);
    }

    [Fact]
    public void Clear_RemovesAllEntries()
    {
        var vm = new TransparencyLogViewModel();
        vm.AddEvent(MakeEvent(1));
        vm.AddEvent(MakeEvent(2));

        vm.Clear();

        Assert.Empty(vm.Entries);
    }

    [Fact]
    public void ExportCsv_IncludesHeader()
    {
        var vm = new TransparencyLogViewModel();

        var csv = vm.ExportCsv();

        Assert.StartsWith("Timestamp,SequenceNumber,EventType,Application,WindowTitle", csv);
    }

    [Fact]
    public void ExportCsv_IncludesEntries()
    {
        var vm = new TransparencyLogViewModel();
        vm.AddEvent(MakeEvent(1, "TestApp", "Test Window"));

        var csv = vm.ExportCsv();

        Assert.Contains("TestApp", csv);
        Assert.Contains("Test Window", csv);
    }

    [Fact]
    public void ExportCsv_EscapesQuotes()
    {
        var vm = new TransparencyLogViewModel();
        vm.AddEvent(CaptureEvent.Create(
            eventType: DesktopEventType.AppSwitch,
            sequenceNumber: 1,
            applicationName: "App",
            bundleIdentifier: "app.exe",
            windowTitle: "Title with \"quotes\""));

        var csv = vm.ExportCsv();

        Assert.Contains("\"\"quotes\"\"", csv);
    }

    [Fact]
    public void DisplayText_FormatsCorrectly()
    {
        var entry = new TransparencyLogEntry
        {
            Timestamp = new DateTime(2026, 2, 28, 14, 30, 45),
            EventType = "AppSwitch",
            Application = "chrome.exe",
            WindowTitle = "Google",
            SequenceNumber = 42,
        };

        Assert.Equal("[14:30:45] AppSwitch — chrome.exe: Google", entry.DisplayText);
    }

    private static CaptureEvent MakeEvent(
        ulong seq,
        string app = "TestApp",
        string title = "Window")
    {
        return CaptureEvent.Create(
            eventType: DesktopEventType.AppSwitch,
            sequenceNumber: seq,
            applicationName: app,
            bundleIdentifier: $"{app.ToLowerInvariant()}.exe",
            windowTitle: title);
    }
}
