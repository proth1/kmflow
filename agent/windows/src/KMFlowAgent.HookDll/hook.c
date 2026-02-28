/**
 * KMFlowAgent Hook DLL — Low-level keyboard and mouse hooks.
 *
 * This DLL installs WH_KEYBOARD_LL and WH_MOUSE_LL hooks and writes raw
 * events into a lock-free ring buffer. The managed C# process polls this
 * buffer to consume events.
 *
 * WHY a separate C DLL:
 * - WH_KEYBOARD_LL/WH_MOUSE_LL callbacks must complete within ~200ms
 *   or Windows silently removes the hook.
 * - .NET GC pauses can exceed this deadline, causing silent hook loss.
 * - A native C callback with a lock-free ring buffer keeps latency < 1ms.
 *
 * The ring buffer uses a single-producer/single-consumer (SPSC) model:
 * - Producer: this DLL's hook callbacks (always on the hook thread)
 * - Consumer: the C# InputMonitor polling from a managed thread
 */

#include <windows.h>
#include <stdint.h>
#include "ringbuffer.h"

/* Module handle for this DLL, needed for SetWindowsHookEx. */
static HINSTANCE g_hModule = NULL;

/* Global hook handles. */
static HHOOK g_keyboardHook = NULL;
static HHOOK g_mouseHook = NULL;

/* Shared ring buffer for events. */
static RingBuffer g_ringBuffer;
static volatile BOOL g_initialized = FALSE;

/* ---- Hook Callbacks ---- */

static LRESULT CALLBACK LowLevelKeyboardProc(int nCode, WPARAM wParam, LPARAM lParam)
{
    if (nCode >= 0 && g_initialized)
    {
        KBDLLHOOKSTRUCT* pKb = (KBDLLHOOKSTRUCT*)lParam;

        HookEvent evt;
        evt.type = HOOK_EVENT_KEYBOARD;
        evt.timestamp_ms = pKb->time;
        evt.keyboard.vkCode = pKb->vkCode;
        evt.keyboard.scanCode = pKb->scanCode;
        evt.keyboard.flags = pKb->flags;
        evt.keyboard.action = (uint32_t)wParam; /* WM_KEYDOWN, WM_KEYUP, etc. */

        RingBuffer_Write(&g_ringBuffer, &evt);
    }
    return CallNextHookEx(g_keyboardHook, nCode, wParam, lParam);
}

static LRESULT CALLBACK LowLevelMouseProc(int nCode, WPARAM wParam, LPARAM lParam)
{
    if (nCode >= 0 && g_initialized)
    {
        MSLLHOOKSTRUCT* pMs = (MSLLHOOKSTRUCT*)lParam;

        HookEvent evt;
        evt.type = HOOK_EVENT_MOUSE;
        evt.timestamp_ms = pMs->time;
        evt.mouse.x = pMs->pt.x;
        evt.mouse.y = pMs->pt.y;
        evt.mouse.mouseData = pMs->mouseData;
        evt.mouse.action = (uint32_t)wParam; /* WM_LBUTTONDOWN, WM_RBUTTONDOWN, etc. */

        RingBuffer_Write(&g_ringBuffer, &evt);
    }
    return CallNextHookEx(g_mouseHook, nCode, wParam, lParam);
}

/* ---- Exported Functions ---- */

/**
 * Initialize the ring buffer and install hooks.
 * Called by the C# process at startup.
 *
 * @param bufferCapacity Number of events the ring buffer can hold.
 * @return TRUE on success, FALSE on failure.
 */
__declspec(dllexport) BOOL __cdecl HookDll_Initialize(uint32_t bufferCapacity)
{
    if (g_initialized)
        return TRUE;

    if (!RingBuffer_Init(&g_ringBuffer, bufferCapacity))
        return FALSE;

    g_keyboardHook = SetWindowsHookExW(
        WH_KEYBOARD_LL, LowLevelKeyboardProc, g_hModule, 0);

    g_mouseHook = SetWindowsHookExW(
        WH_MOUSE_LL, LowLevelMouseProc, g_hModule, 0);

    if (!g_keyboardHook || !g_mouseHook)
    {
        if (g_keyboardHook) UnhookWindowsHookEx(g_keyboardHook);
        if (g_mouseHook) UnhookWindowsHookEx(g_mouseHook);
        g_keyboardHook = NULL;
        g_mouseHook = NULL;
        RingBuffer_Destroy(&g_ringBuffer);
        return FALSE;
    }

    g_initialized = TRUE;
    return TRUE;
}

/**
 * Read events from the ring buffer.
 * Called by the C# InputMonitor on a polling loop.
 *
 * @param outEvents Pointer to caller-allocated array of HookEvent.
 * @param maxEvents Maximum events to read.
 * @return Number of events actually read.
 */
__declspec(dllexport) uint32_t __cdecl HookDll_ReadEvents(
    HookEvent* outEvents, uint32_t maxEvents)
{
    if (!g_initialized || !outEvents || maxEvents == 0)
        return 0;

    return RingBuffer_ReadBatch(&g_ringBuffer, outEvents, maxEvents);
}

/**
 * Unhook and clean up.
 * Called by the C# process at shutdown.
 */
__declspec(dllexport) void __cdecl HookDll_Shutdown(void)
{
    if (!g_initialized)
        return;

    g_initialized = FALSE;

    if (g_keyboardHook)
    {
        UnhookWindowsHookEx(g_keyboardHook);
        g_keyboardHook = NULL;
    }

    if (g_mouseHook)
    {
        UnhookWindowsHookEx(g_mouseHook);
        g_mouseHook = NULL;
    }

    RingBuffer_Destroy(&g_ringBuffer);
}

/**
 * Check if hooks are still installed.
 * Windows may silently remove hooks if callbacks are too slow.
 *
 * @return TRUE if both hooks are installed.
 */
__declspec(dllexport) BOOL __cdecl HookDll_IsHealthy(void)
{
    return g_initialized && g_keyboardHook && g_mouseHook;
}

/* ---- DLL Entry Point ---- */

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    switch (ul_reason_for_call)
    {
    case DLL_PROCESS_ATTACH:
        g_hModule = hModule;
        DisableThreadLibraryCalls(hModule);
        break;
    case DLL_PROCESS_DETACH:
        HookDll_Shutdown();
        break;
    }
    return TRUE;
}
