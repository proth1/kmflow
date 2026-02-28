// Window title capture using UI Automation.
//
// Windows equivalent of agent/macos/Sources/Capture/WindowTitleCapture.swift.

using System.Runtime.InteropServices;
using KMFlowAgent.IPC;

namespace KMFlowAgent.Capture;

/// <summary>
/// Captures window titles when focus changes, producing WINDOW_FOCUS events.
/// Uses GetWindowText for efficient title retrieval.
/// </summary>
public sealed class WindowTitleCapture
{
    private readonly Action<CaptureEvent> _onEvent;
    private string? _lastTitle;

    public WindowTitleCapture(Action<CaptureEvent> onEvent)
    {
        _onEvent = onEvent;
    }

    /// <summary>
    /// Capture the title of the given window handle.
    /// Called by AppSwitchMonitor or CaptureStateManager when focus changes.
    /// </summary>
    public void CaptureTitle(IntPtr hwnd)
    {
        var title = GetWindowTitle(hwnd);
        if (string.IsNullOrEmpty(title) || title == _lastTitle)
            return;

        _lastTitle = title;

        var evt = CaptureEvent.Create(
            eventType: DesktopEventType.WindowFocus,
            sequenceNumber: 0,
            windowTitle: title,
            eventData: new Dictionary<string, object>
            {
                ["window_title"] = title,
            });

        _onEvent(evt);
    }

    private static string? GetWindowTitle(IntPtr hwnd)
    {
        int length = GetWindowTextLength(hwnd);
        if (length == 0) return null;

        var sb = new System.Text.StringBuilder(length + 1);
        GetWindowText(hwnd, sb, sb.Capacity);
        return sb.ToString();
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    private static extern int GetWindowTextLength(IntPtr hWnd);
}
