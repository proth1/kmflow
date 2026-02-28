// Detects application foreground changes using SetWinEventHook.
//
// Windows equivalent of agent/macos/Sources/Capture/AppSwitchMonitor.swift.

using System.Diagnostics;
using System.Runtime.InteropServices;
using KMFlowAgent.IPC;
using KMFlowAgent.Utilities;

namespace KMFlowAgent.Capture;

/// <summary>
/// Monitors foreground application changes using SetWinEventHook(EVENT_SYSTEM_FOREGROUND).
/// Produces APP_SWITCH and WINDOW_FOCUS events.
/// </summary>
public sealed class AppSwitchMonitor : IDisposable
{
    private const uint EVENT_SYSTEM_FOREGROUND = 0x0003;
    private const uint WINEVENT_OUTOFCONTEXT = 0x0000;

    private readonly Action<CaptureEvent> _onEvent;
    private readonly ProcessIdentifier _processIdentifier;
    private IntPtr _hookHandle;
    private WinEventDelegate? _hookDelegate; // prevent GC of delegate
    private string? _currentApp;
    private string? _currentAppId;
    private DateTime _lastSwitchTime;
    private bool _disposed;

    private delegate void WinEventDelegate(
        IntPtr hWinEventHook, uint eventType, IntPtr hwnd,
        int idObject, int idChild, uint dwEventThread, uint dwmsEventTime);

    public AppSwitchMonitor(Action<CaptureEvent> onEvent, ProcessIdentifier processIdentifier)
    {
        _onEvent = onEvent;
        _processIdentifier = processIdentifier;
        _lastSwitchTime = DateTime.UtcNow;
    }

    /// <summary>Install the foreground change hook.</summary>
    public void Start()
    {
        _hookDelegate = OnForegroundChanged;
        _hookHandle = SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
            IntPtr.Zero, _hookDelegate, 0, 0, WINEVENT_OUTOFCONTEXT);

        if (_hookHandle == IntPtr.Zero)
        {
            throw new InvalidOperationException("Failed to install foreground event hook");
        }

        // Capture initial foreground app
        CaptureCurrentForeground();
    }

    /// <summary>Remove the hook.</summary>
    public void Stop()
    {
        if (_hookHandle != IntPtr.Zero)
        {
            UnhookWinEvent(_hookHandle);
            _hookHandle = IntPtr.Zero;
        }
    }

    private void OnForegroundChanged(
        IntPtr hWinEventHook, uint eventType, IntPtr hwnd,
        int idObject, int idChild, uint dwEventThread, uint dwmsEventTime)
    {
        try
        {
            GetWindowThreadProcessId(hwnd, out uint processId);
            if (processId == 0) return;

            using var process = Process.GetProcessById((int)processId);
            var (appName, appId) = _processIdentifier.Identify(process);

            if (appId == _currentAppId) return; // Same app, no switch

            var now = DateTime.UtcNow;
            var dwellMs = (int)(now - _lastSwitchTime).TotalMilliseconds;

            var eventData = new Dictionary<string, object>
            {
                ["from_app"] = _currentApp ?? "unknown",
                ["to_app"] = appName,
                ["dwell_ms"] = dwellMs,
            };

            var evt = CaptureEvent.Create(
                eventType: DesktopEventType.AppSwitch,
                sequenceNumber: 0, // Set by CaptureStateManager
                applicationName: appName,
                bundleIdentifier: appId,
                eventData: eventData);

            _onEvent(evt);

            _currentApp = appName;
            _currentAppId = appId;
            _lastSwitchTime = now;
        }
        catch
        {
            // Process may have exited between GetWindowThreadProcessId and GetProcessById
        }
    }

    private void CaptureCurrentForeground()
    {
        try
        {
            var hwnd = GetForegroundWindow();
            if (hwnd == IntPtr.Zero) return;

            GetWindowThreadProcessId(hwnd, out uint processId);
            if (processId == 0) return;

            using var process = Process.GetProcessById((int)processId);
            var (appName, appId) = _processIdentifier.Identify(process);

            _currentApp = appName;
            _currentAppId = appId;
            _lastSwitchTime = DateTime.UtcNow;
        }
        catch
        {
            // Best effort
        }
    }

    [DllImport("user32.dll")]
    private static extern IntPtr SetWinEventHook(
        uint eventMin, uint eventMax, IntPtr hmodWinEventProc,
        WinEventDelegate lpfnWinEventProc, uint idProcess, uint idThread,
        uint dwFlags);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UnhookWinEvent(IntPtr hWinEventHook);

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    public void Dispose()
    {
        if (!_disposed)
        {
            Stop();
            _disposed = true;
        }
    }
}
