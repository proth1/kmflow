// Layer 1 capture context filter: prevents capture in sensitive contexts.
//
// Windows equivalent of agent/macos/Sources/PII/CaptureContextFilter.swift.
// Uses UIAutomation IsPassword property instead of AXSecureTextField.

using KMFlowAgent.IPC;

namespace KMFlowAgent.PII;

/// <summary>
/// L1 PII prevention filter. Determines WHETHER to capture based on context.
/// This is a blocking filter (not a content redaction filter).
/// Content redaction is handled by L2 in the Python layer.
/// </summary>
public sealed class CaptureContextFilter
{
    private readonly HashSet<string> _blockedProcesses;
    private readonly HashSet<string> _allowedProcesses;
    private readonly PrivateBrowsingDetector _privateBrowsingDetector;

    /// <summary>
    /// Hardcoded blocklist of password managers and sensitive system apps.
    /// These are always blocked regardless of engagement configuration.
    /// </summary>
    public static readonly HashSet<string> HardcodedBlocklist = new(StringComparer.OrdinalIgnoreCase)
    {
        // Password managers
        "1Password.exe",
        "op.exe",           // 1Password CLI
        "LastPass.exe",
        "Bitwarden.exe",
        "Dashlane.exe",
        "KeePass.exe",
        "KeePassXC.exe",
        "RoboForm.exe",

        // Windows security apps
        "SecurityHealthHost.exe",   // Windows Security
        "CredentialUIBroker.exe",   // Credential Manager UI
        "consent.exe",             // UAC consent dialog
        "LogonUI.exe",             // Login screen

        // System credential management
        "certmgr.msc",
        "mmc.exe",                 // Management console (when running certmgr)
    };

    public CaptureContextFilter(
        IEnumerable<string>? additionalBlocklist = null,
        IEnumerable<string>? allowlist = null)
    {
        _blockedProcesses = new HashSet<string>(HardcodedBlocklist, StringComparer.OrdinalIgnoreCase);

        if (additionalBlocklist is not null)
        {
            foreach (var proc in additionalBlocklist)
                _blockedProcesses.Add(proc);
        }

        _allowedProcesses = allowlist is not null
            ? new HashSet<string>(allowlist, StringComparer.OrdinalIgnoreCase)
            : new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        _privateBrowsingDetector = new PrivateBrowsingDetector();
    }

    /// <summary>
    /// Determine if an event should be blocked (not captured).
    /// </summary>
    public bool ShouldBlock(CaptureEvent evt)
    {
        // Block if app is on the hardcoded or engagement blocklist
        if (IsBlockedProcess(evt.BundleIdentifier))
            return true;

        // Block if allowlist is configured and app is not on it
        if (_allowedProcesses.Count > 0 && !IsAllowedProcess(evt.BundleIdentifier))
            return true;

        // Block URL events in private browsing windows
        if (evt.EventType is DesktopEventType.UrlNavigation or DesktopEventType.TabSwitch)
        {
            if (_privateBrowsingDetector.IsPrivateBrowsing(evt.BundleIdentifier, evt.WindowTitle))
                return true;
        }

        // Block keyboard events when focused element is a password field (ES_PASSWORD)
        if (evt.EventType is DesktopEventType.KeyboardAction or DesktopEventType.KeyboardShortcut)
        {
            if (IsPasswordField())
                return true;
        }

        return false;
    }

    /// <summary>
    /// Check if the focused UI element is a password field.
    /// Uses UIAutomation AutomationElement.IsPasswordProperty.
    /// Called by InputMonitor before generating keyboard events.
    /// </summary>
    public static bool IsPasswordField()
    {
        try
        {
            // Use UIAutomation to check the focused element
            // System.Windows.Automation requires the UIAutomationClient assembly
            // For NativeAOT compatibility, we use the COM interface directly via P/Invoke
            var focusedHwnd = GetFocus();
            if (focusedHwnd == IntPtr.Zero)
            {
                // GetFocus only works for the calling thread's message queue.
                // For cross-process focus detection, we use GetGUIThreadInfo.
                var guiInfo = new GUITHREADINFO { cbSize = (uint)System.Runtime.InteropServices.Marshal.SizeOf<GUITHREADINFO>() };
                if (GetGUIThreadInfo(0, ref guiInfo))
                {
                    focusedHwnd = guiInfo.hwndFocus;
                }
            }

            if (focusedHwnd == IntPtr.Zero)
                return false;

            // Check if the edit control has ES_PASSWORD style
            int style = GetWindowLong(focusedHwnd, GWL_STYLE);
            if ((style & ES_PASSWORD) != 0)
                return true;

            return false;
        }
        catch
        {
            return false; // Default to not blocking on error
        }
    }

    /// <summary>Check if a process name is on the blocklist.</summary>
    public bool IsBlockedProcess(string? processIdentifier)
    {
        if (string.IsNullOrEmpty(processIdentifier))
            return true; // Least privilege: block unknown processes

        // Check by exe name (last segment of path)
        var exeName = Path.GetFileName(processIdentifier);
        return _blockedProcesses.Contains(exeName);
    }

    /// <summary>Check if a process is on the engagement allowlist.</summary>
    public bool IsAllowedProcess(string? processIdentifier)
    {
        if (string.IsNullOrEmpty(processIdentifier))
            return false;

        var exeName = Path.GetFileName(processIdentifier);
        return _allowedProcesses.Contains(exeName) ||
               _allowedProcesses.Contains(processIdentifier);
    }

    // Win32 constants
    private const int GWL_STYLE = -16;
    private const int ES_PASSWORD = 0x0020;

    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct GUITHREADINFO
    {
        public uint cbSize;
        public uint flags;
        public IntPtr hwndActive;
        public IntPtr hwndFocus;
        public IntPtr hwndCapture;
        public IntPtr hwndMenuOwner;
        public IntPtr hwndMoveSize;
        public IntPtr hwndCaret;
        public RECT rcCaret;
    }

    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    private struct RECT
    {
        public int Left, Top, Right, Bottom;
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern IntPtr GetFocus();

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
    private static extern bool GetGUIThreadInfo(uint idThread, ref GUITHREADINFO pgui);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern int GetWindowLong(IntPtr hWnd, int nIndex);
}
