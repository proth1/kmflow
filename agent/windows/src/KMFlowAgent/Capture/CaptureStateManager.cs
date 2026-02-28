// Coordinates all capture subsystems and manages lifecycle.
//
// Windows equivalent of agent/macos/Sources/Capture/CaptureStateManager.swift.

using KMFlowAgent.IPC;
using KMFlowAgent.PII;
using KMFlowAgent.Utilities;

namespace KMFlowAgent.Capture;

/// <summary>
/// Orchestrates capture subsystems: InputMonitor, AppSwitchMonitor,
/// WindowTitleCapture, and IdleDetector. Assigns sequence numbers,
/// applies L1 PII filtering, and routes events to the named pipe client.
/// </summary>
public sealed class CaptureStateManager : IDisposable
{
    private readonly NamedPipeClient _pipeClient;
    private readonly CaptureContextFilter _contextFilter;
    private readonly ProcessIdentifier _processIdentifier;

    private InputMonitor? _inputMonitor;
    private AppSwitchMonitor? _appSwitchMonitor;
    private IdleDetector? _idleDetector;
    private WindowTitleCapture? _windowTitleCapture;

    private ulong _globalSequenceNumber;
    private volatile bool _isPaused;
    private bool _disposed;

    public CaptureStateManager(
        NamedPipeClient pipeClient,
        CaptureContextFilter contextFilter,
        ProcessIdentifier processIdentifier)
    {
        _pipeClient = pipeClient;
        _contextFilter = contextFilter;
        _processIdentifier = processIdentifier;
    }

    /// <summary>Whether capture is currently paused.</summary>
    public bool IsPaused => _isPaused;

    /// <summary>Total events captured in this session.</summary>
    public ulong EventCount => _globalSequenceNumber;

    /// <summary>Start all capture subsystems.</summary>
    public void Start()
    {
        _inputMonitor = new InputMonitor(OnRawEvent);
        _appSwitchMonitor = new AppSwitchMonitor(OnRawEvent, _processIdentifier);
        _idleDetector = new IdleDetector(OnRawEvent);
        _windowTitleCapture = new WindowTitleCapture(OnRawEvent);

        _inputMonitor.Start();
        _appSwitchMonitor.Start();
        _idleDetector.Start();
    }

    /// <summary>Pause capture without destroying subsystems.</summary>
    public void Pause()
    {
        _isPaused = true;
    }

    /// <summary>Resume capture after pause.</summary>
    public void Resume()
    {
        _isPaused = false;
    }

    /// <summary>Stop all capture subsystems.</summary>
    public void Stop()
    {
        _inputMonitor?.Stop();
        _appSwitchMonitor?.Stop();
        _idleDetector?.Stop();
    }

    /// <summary>
    /// Central event handler. Applies L1 filtering, assigns sequence numbers,
    /// and sends events to the Python layer via named pipe.
    /// </summary>
    private void OnRawEvent(CaptureEvent rawEvent)
    {
        if (_isPaused) return;

        // L1 PII filtering: check if event should be suppressed
        if (_contextFilter.ShouldBlock(rawEvent))
            return;

        // Assign global sequence number
        var seq = Interlocked.Increment(ref _globalSequenceNumber);

        // Create final event with assigned sequence number
        var finalEvent = CaptureEvent.Create(
            eventType: rawEvent.EventType,
            sequenceNumber: seq,
            applicationName: rawEvent.ApplicationName,
            bundleIdentifier: rawEvent.BundleIdentifier,
            windowTitle: rawEvent.WindowTitle,
            eventData: rawEvent.EventData,
            idempotencyKey: rawEvent.IdempotencyKey);

        // Fire-and-forget send to Python via named pipe
        _ = Task.Run(async () =>
        {
            try
            {
                await _pipeClient.SendEventAsync(finalEvent).ConfigureAwait(false);
            }
            catch
            {
                // Best effort — event will be logged but not block capture
            }
        });
    }

    public void Dispose()
    {
        if (!_disposed)
        {
            Stop();
            _inputMonitor?.Dispose();
            _appSwitchMonitor?.Dispose();
            _idleDetector?.Dispose();
            _disposed = true;
        }
    }
}
