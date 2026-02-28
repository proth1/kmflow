// Idle detection using GetLastInputInfo().
//
// Simpler than the macOS approach (event cadence monitoring) because
// Windows provides a direct API for last user input time.

using System.Runtime.InteropServices;
using KMFlowAgent.IPC;

namespace KMFlowAgent.Capture;

/// <summary>
/// Detects user idle/active state transitions using GetLastInputInfo().
/// Emits IDLE_START when no input for threshold period, IDLE_END when activity resumes.
/// </summary>
public sealed class IdleDetector : IDisposable
{
    private readonly Action<CaptureEvent> _onEvent;
    private readonly int _thresholdSeconds;
    private readonly CancellationTokenSource _cts = new();

    private Task? _pollTask;
    private bool _isIdle;
    private DateTime _idleStartTime;
    private bool _disposed;

    public IdleDetector(Action<CaptureEvent> onEvent, int thresholdSeconds = 300)
    {
        _onEvent = onEvent;
        _thresholdSeconds = thresholdSeconds;
    }

    /// <summary>Whether the user is currently idle.</summary>
    public bool IsIdle => _isIdle;

    /// <summary>Start monitoring idle state.</summary>
    public void Start()
    {
        _pollTask = Task.Factory.StartNew(
            PollLoop, _cts.Token, TaskCreationOptions.LongRunning, TaskScheduler.Default);
    }

    /// <summary>Stop monitoring.</summary>
    public void Stop()
    {
        _cts.Cancel();
        _pollTask?.Wait(TimeSpan.FromSeconds(5));
    }

    private void PollLoop()
    {
        while (!_cts.Token.IsCancellationRequested)
        {
            var idleSeconds = GetIdleTimeSeconds();

            if (!_isIdle && idleSeconds >= _thresholdSeconds)
            {
                // Transition to idle
                _isIdle = true;
                _idleStartTime = DateTime.UtcNow.AddSeconds(-idleSeconds);

                var evt = CaptureEvent.Create(
                    eventType: DesktopEventType.IdleStart,
                    sequenceNumber: 0,
                    eventData: new Dictionary<string, object>
                    {
                        ["idle_threshold_s"] = _thresholdSeconds,
                    });

                _onEvent(evt);
            }
            else if (_isIdle && idleSeconds < _thresholdSeconds)
            {
                // Transition to active
                var idleDuration = (int)(DateTime.UtcNow - _idleStartTime).TotalSeconds;
                _isIdle = false;

                var evt = CaptureEvent.Create(
                    eventType: DesktopEventType.IdleEnd,
                    sequenceNumber: 0,
                    eventData: new Dictionary<string, object>
                    {
                        ["idle_duration_s"] = idleDuration,
                    });

                _onEvent(evt);
            }

            Thread.Sleep(1000); // Check every second
        }
    }

    private static double GetIdleTimeSeconds()
    {
        var lastInput = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf<LASTINPUTINFO>() };

        if (!GetLastInputInfo(ref lastInput))
            return 0;

        var idleMs = (uint)Environment.TickCount - lastInput.dwTime;
        return idleMs / 1000.0;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct LASTINPUTINFO
    {
        public uint cbSize;
        public uint dwTime;
    }

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);

    public void Dispose()
    {
        if (!_disposed)
        {
            Stop();
            _cts.Dispose();
            _disposed = true;
        }
    }
}
