// Consumes raw hook events from the C hook DLL ring buffer and produces
// CaptureEvent structs classified into the 16-type event taxonomy.
//
// This is the Windows equivalent of agent/macos/Sources/Capture/InputMonitor.swift.

using System.Runtime.InteropServices;
using KMFlowAgent.IPC;

namespace KMFlowAgent.Capture;

/// <summary>
/// Raw hook event from the C DLL ring buffer.
/// Layout must match HookEvent in ringbuffer.h exactly.
/// </summary>
[StructLayout(LayoutKind.Explicit, Size = 24)]
internal struct HookEvent
{
    [FieldOffset(0)] public int Type;       // 1 = keyboard, 2 = mouse
    [FieldOffset(4)] public uint TimestampMs;

    // Keyboard fields (when Type == 1)
    [FieldOffset(8)] public uint VkCode;
    [FieldOffset(12)] public uint ScanCode;
    [FieldOffset(16)] public uint Flags;
    [FieldOffset(20)] public uint KeyAction;

    // Mouse fields (when Type == 2)
    [FieldOffset(8)] public int MouseX;
    [FieldOffset(12)] public int MouseY;
    [FieldOffset(16)] public uint MouseData;
    [FieldOffset(20)] public uint MouseAction;
}

/// <summary>
/// P/Invoke declarations for the hook DLL.
/// </summary>
internal static partial class HookDllInterop
{
    private const string DllName = "KMFlowAgent.HookDll.dll";

    [LibraryImport(DllName, EntryPoint = "HookDll_Initialize")]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static partial bool Initialize(uint bufferCapacity);

    [LibraryImport(DllName, EntryPoint = "HookDll_ReadEvents")]
    internal static partial uint ReadEvents(
        [Out] HookEvent[] outEvents, uint maxEvents);

    [LibraryImport(DllName, EntryPoint = "HookDll_Shutdown")]
    internal static partial void Shutdown();

    [LibraryImport(DllName, EntryPoint = "HookDll_IsHealthy")]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static partial bool IsHealthy();
}

/// <summary>
/// Polls the hook DLL ring buffer and translates raw input events into
/// typed CaptureEvents. Runs on a dedicated thread to avoid blocking
/// the main message loop.
/// </summary>
public sealed class InputMonitor : IDisposable
{
    // Windows message constants
    private const uint WM_KEYDOWN = 0x0100;
    private const uint WM_KEYUP = 0x0101;
    private const uint WM_SYSKEYDOWN = 0x0104;
    private const uint WM_LBUTTONDOWN = 0x0201;
    private const uint WM_LBUTTONUP = 0x0202;
    private const uint WM_RBUTTONDOWN = 0x0204;
    private const uint WM_MBUTTONDOWN = 0x0207;
    private const uint WM_MOUSEWHEEL = 0x020A;

    private const uint DefaultBufferCapacity = 10_000;
    private const int PollIntervalMs = 5;

    private readonly CancellationTokenSource _cts = new();
    private readonly Action<CaptureEvent> _onEvent;
    private Task? _pollTask;
    private ulong _sequenceNumber;
    private bool _disposed;

    // Keystroke aggregation state
    private uint _currentCharCount;
    private DateTime _typingStarted;
    private uint _backspaceCount;
    private uint _specialKeyCount;
    private string? _lastApp;

    public InputMonitor(Action<CaptureEvent> onEvent)
    {
        _onEvent = onEvent ?? throw new ArgumentNullException(nameof(onEvent));
    }

    /// <summary>Start polling the hook DLL ring buffer.</summary>
    public void Start()
    {
        if (!HookDllInterop.Initialize(DefaultBufferCapacity))
        {
            throw new InvalidOperationException("Failed to initialize hook DLL");
        }

        _pollTask = Task.Factory.StartNew(
            PollLoop, _cts.Token, TaskCreationOptions.LongRunning, TaskScheduler.Default);
    }

    /// <summary>Stop polling and unhook.</summary>
    public void Stop()
    {
        _cts.Cancel();
        _pollTask?.Wait(TimeSpan.FromSeconds(5));
        HookDllInterop.Shutdown();
    }

    private void PollLoop()
    {
        var buffer = new HookEvent[256];

        while (!_cts.Token.IsCancellationRequested)
        {
            var count = HookDllInterop.ReadEvents(buffer, (uint)buffer.Length);

            for (uint i = 0; i < count; i++)
            {
                ProcessHookEvent(ref buffer[i]);
            }

            if (count == 0)
            {
                Thread.Sleep(PollIntervalMs);
            }
        }

        // Flush any pending keyboard aggregation
        FlushKeyboardAction();
    }

    private void ProcessHookEvent(ref HookEvent evt)
    {
        if (evt.Type == 1) // Keyboard
        {
            ProcessKeyboardEvent(ref evt);
        }
        else if (evt.Type == 2) // Mouse
        {
            ProcessMouseEvent(ref evt);
        }
    }

    private void ProcessKeyboardEvent(ref HookEvent evt)
    {
        // Only process key-down events for action counting
        if (evt.KeyAction != WM_KEYDOWN && evt.KeyAction != WM_SYSKEYDOWN)
            return;

        // Check for keyboard shortcuts (modifier + key)
        bool isCtrl = (GetAsyncKeyState(0x11) & 0x8000) != 0;  // VK_CONTROL
        bool isAlt = (GetAsyncKeyState(0x12) & 0x8000) != 0;   // VK_MENU
        bool isWin = (GetAsyncKeyState(0x5B) & 0x8000) != 0;   // VK_LWIN

        if (isCtrl || isAlt || isWin)
        {
            FlushKeyboardAction();
            EmitKeyboardShortcut(evt.VkCode, isCtrl, isAlt, isWin);
            return;
        }

        // Aggregate character typing
        if (evt.VkCode == 0x08) // VK_BACK
            _backspaceCount++;
        else if (evt.VkCode is >= 0x70 and <= 0x87 or >= 0x21 and <= 0x2E) // Function keys, nav keys
            _specialKeyCount++;
        else
            _currentCharCount++;

        if (_currentCharCount == 1)
            _typingStarted = DateTime.UtcNow;
    }

    private void ProcessMouseEvent(ref HookEvent evt)
    {
        // Flush any pending keyboard action before mouse event
        FlushKeyboardAction();

        var eventType = evt.MouseAction switch
        {
            WM_LBUTTONDOWN => DesktopEventType.MouseClick,
            WM_RBUTTONDOWN => DesktopEventType.MouseClick,
            WM_MBUTTONDOWN => DesktopEventType.MouseClick,
            WM_MOUSEWHEEL => DesktopEventType.Scroll,
            _ => (DesktopEventType?)null,
        };

        if (eventType is null)
            return;

        var eventData = new Dictionary<string, object>();

        if (eventType == DesktopEventType.MouseClick)
        {
            string button = evt.MouseAction switch
            {
                WM_LBUTTONDOWN => "left",
                WM_RBUTTONDOWN => "right",
                WM_MBUTTONDOWN => "middle",
                _ => "unknown",
            };
            eventData["button"] = button;
            eventData["x"] = evt.MouseX;
            eventData["y"] = evt.MouseY;
        }
        else if (eventType == DesktopEventType.Scroll)
        {
            short delta = (short)((evt.MouseData >> 16) & 0xFFFF);
            eventData["direction"] = delta > 0 ? "up" : "down";
            eventData["delta_units"] = Math.Abs(delta / 120);
        }

        EmitEvent(eventType.Value, eventData);
    }

    private void EmitKeyboardShortcut(uint vkCode, bool ctrl, bool alt, bool win)
    {
        var keys = new List<string>();
        if (ctrl) keys.Add("Ctrl");
        if (alt) keys.Add("Alt");
        if (win) keys.Add("Win");
        keys.Add(VkCodeToString(vkCode));

        var eventData = new Dictionary<string, object>
        {
            ["shortcut_keys"] = string.Join("+", keys),
        };

        EmitEvent(DesktopEventType.KeyboardShortcut, eventData);
    }

    private void FlushKeyboardAction()
    {
        if (_currentCharCount == 0 && _backspaceCount == 0 && _specialKeyCount == 0)
            return;

        var durationMs = (int)(DateTime.UtcNow - _typingStarted).TotalMilliseconds;

        var eventData = new Dictionary<string, object>
        {
            ["char_count"] = _currentCharCount,
            ["duration_ms"] = durationMs,
            ["backspace_count"] = _backspaceCount,
            ["special_key_count"] = _specialKeyCount,
            ["content_level"] = false, // Action-level only
        };

        EmitEvent(DesktopEventType.KeyboardAction, eventData);

        _currentCharCount = 0;
        _backspaceCount = 0;
        _specialKeyCount = 0;
    }

    private void EmitEvent(DesktopEventType eventType, Dictionary<string, object>? eventData = null)
    {
        var seq = Interlocked.Increment(ref _sequenceNumber);

        var evt = CaptureEvent.Create(
            eventType: eventType,
            sequenceNumber: seq,
            eventData: eventData);

        _onEvent(evt);
    }

    private static string VkCodeToString(uint vkCode)
    {
        // Map common VK codes to readable names
        return vkCode switch
        {
            0x41 => "A", 0x42 => "B", 0x43 => "C", 0x44 => "D", 0x45 => "E",
            0x46 => "F", 0x47 => "G", 0x48 => "H", 0x49 => "I", 0x4A => "J",
            0x56 => "V", 0x58 => "X", 0x5A => "Z", 0x53 => "S",
            0x09 => "Tab", 0x0D => "Enter", 0x1B => "Escape",
            0x2E => "Delete", 0x74 => "F5", 0x77 => "F8",
            _ => $"VK_{vkCode:X2}",
        };
    }

    [DllImport("user32.dll")]
    private static extern short GetAsyncKeyState(int vKey);

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
