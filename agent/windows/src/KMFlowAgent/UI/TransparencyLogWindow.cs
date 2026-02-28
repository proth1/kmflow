// Transparency log viewer — displays recent capture events for user inspection.
//
// Shows the last N events in reverse chronological order so the user can
// see exactly what the agent captured. This is a key privacy affordance:
// users can verify that PII is being redacted and that no unexpected
// data is leaving their machine.
//
// The view model is separate from the UI layer to enable unit testing
// and NativeAOT compatibility.

using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using KMFlowAgent.IPC;
using KMFlowAgent.Utilities;

namespace KMFlowAgent.UI;

/// <summary>
/// A single entry in the transparency log.
/// </summary>
public sealed class TransparencyLogEntry
{
    public required DateTime Timestamp { get; init; }
    public required string EventType { get; init; }
    public required string Application { get; init; }
    public required string WindowTitle { get; init; }
    public required ulong SequenceNumber { get; init; }

    /// <summary>
    /// Format for display in the log viewer.
    /// </summary>
    public string DisplayText =>
        $"[{Timestamp:HH:mm:ss}] {EventType} — {Application}: {WindowTitle}";
}

/// <summary>
/// View model for the transparency log window.
/// Maintains a bounded ring buffer of recent events for display.
/// </summary>
public sealed class TransparencyLogViewModel : INotifyPropertyChanged
{
    private readonly int _maxEntries;
    private readonly object _lock = new();

    public event PropertyChangedEventHandler? PropertyChanged;

    /// <summary>
    /// Observable collection of log entries (most recent first).
    /// </summary>
    public ObservableCollection<TransparencyLogEntry> Entries { get; } = [];

    /// <summary>Total events captured since agent start.</summary>
    public ulong TotalEventCount { get; private set; }

    /// <summary>Total events filtered by L1 PII rules.</summary>
    public ulong FilteredEventCount { get; private set; }

    public TransparencyLogViewModel(int maxEntries = 500)
    {
        _maxEntries = maxEntries;
    }

    /// <summary>
    /// Add a capture event to the transparency log.
    /// Thread-safe: called from capture event handlers.
    /// </summary>
    public void AddEvent(CaptureEvent evt)
    {
        var entry = new TransparencyLogEntry
        {
            Timestamp = DateTime.Now,
            EventType = evt.EventType.ToString(),
            Application = evt.ApplicationName ?? "(unknown)",
            WindowTitle = evt.WindowTitle ?? "",
            SequenceNumber = evt.SequenceNumber,
        };

        lock (_lock)
        {
            TotalEventCount++;

            // Insert at the beginning (most recent first)
            Entries.Insert(0, entry);

            // Trim if over capacity
            while (Entries.Count > _maxEntries)
            {
                Entries.RemoveAt(Entries.Count - 1);
            }
        }

        OnPropertyChanged(nameof(TotalEventCount));
    }

    /// <summary>
    /// Record that an event was filtered by L1 PII rules.
    /// </summary>
    public void RecordFiltered()
    {
        lock (_lock)
        {
            FilteredEventCount++;
        }
        OnPropertyChanged(nameof(FilteredEventCount));
    }

    /// <summary>
    /// Clear all log entries.
    /// </summary>
    public void Clear()
    {
        lock (_lock)
        {
            Entries.Clear();
        }
        AgentLogger.Debug("Transparency log cleared");
    }

    /// <summary>
    /// Export log entries as CSV text.
    /// </summary>
    public string ExportCsv()
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("Timestamp,SequenceNumber,EventType,Application,WindowTitle");

        lock (_lock)
        {
            foreach (var entry in Entries)
            {
                var title = entry.WindowTitle.Replace("\"", "\"\"");
                sb.AppendLine($"\"{entry.Timestamp:O}\",{entry.SequenceNumber},\"{entry.EventType}\",\"{entry.Application}\",\"{title}\"");
            }
        }

        return sb.ToString();
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}
