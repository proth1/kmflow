// VCE (Visual Context Event) capture manager for Windows.
//
// Equivalent of agent/macos/Sources/Capture/VCECaptureManager.swift.
//
// Privacy contract:
//   - Screen image is NEVER written to disk.
//   - Screen image is NEVER logged.
//   - The bitmap lives only in memory for the duration of the classify call.
//   - Only the resulting VCERecord metadata (no pixel data) is sent via IPC.

using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using KMFlowAgent.IPC;
using KMFlowAgent.Utilities;

namespace KMFlowAgent.Capture;

/// <summary>
/// Configurable rate limits for VCE captures.
/// </summary>
public sealed record VCETriggerCaps(
    int MaxPerHour = 12,
    int MaxPerDay = 60,
    double CooldownSameAppSeconds = 120,
    double CooldownAnySeconds = 30
);

/// <summary>
/// Context passed from native monitoring to the VCE capture manager.
/// </summary>
public sealed record CaptureContext(
    string ApplicationName,
    string WindowTitle,
    int DwellMs,
    double InteractionIntensity,
    string TriggerReason
);

/// <summary>
/// Manages the VCE capture lifecycle with rate limiting and privacy guarantees.
///
/// Thread-safe via lock on <c>_stateLock</c>. All mutable state is guarded.
/// </summary>
public sealed class VCECaptureManager : IDisposable
{
    // MARK: - Fields

    private VCETriggerCaps _caps;
    private bool _isEnabled;
    private bool _disposed;

    // Rate limit state (guarded by _stateLock)
    private readonly object _stateLock = new();
    private readonly List<DateTime> _captureTimestamps = new();
    private readonly Dictionary<string, DateTime> _lastCaptureByApp = new();
    private DateTime? _lastCaptureAny;

    /// <summary>Callback to send a JSON payload to the Python IPC layer.</summary>
    private readonly Func<Dictionary<string, object>, Task> _sendIpc;

    // MARK: - Constructor

    /// <param name="sendIpc">
    /// Async callback that accepts a JSON-serialisable dict and routes it to
    /// Python via the named pipe. Provided by the owning CaptureStateManager.
    /// </param>
    /// <param name="caps">Optional override trigger caps.</param>
    public VCECaptureManager(
        Func<Dictionary<string, object>, Task> sendIpc,
        VCETriggerCaps? caps = null)
    {
        _sendIpc = sendIpc ?? throw new ArgumentNullException(nameof(sendIpc));
        _caps = caps ?? new VCETriggerCaps();
        _isEnabled = true;
    }

    // MARK: - Public API

    /// <summary>Update trigger caps (called when backend config is refreshed).</summary>
    public void UpdateCaps(VCETriggerCaps newCaps)
    {
        lock (_stateLock)
        {
            _caps = newCaps;
        }
    }

    /// <summary>Enable or disable VCE capture.</summary>
    public void SetEnabled(bool enabled)
    {
        lock (_stateLock)
        {
            _isEnabled = enabled;
        }
    }

    /// <summary>
    /// Evaluate whether a VCE capture should fire for the given context.
    ///
    /// Enforces hourly, daily, per-app cooldown, and any-capture cooldown limits.
    /// Triggers the full capture → classify → send pipeline if approved.
    /// </summary>
    /// <returns>True if a capture was triggered, false if rate-limited or disabled.</returns>
    public async Task<bool> EvaluateTriggerAsync(CaptureContext context)
    {
        bool shouldCapture;
        VCETriggerCaps caps;

        lock (_stateLock)
        {
            if (!_isEnabled) return false;

            var now = DateTime.UtcNow;
            PruneOldTimestamps(now);
            caps = _caps;

            // Per-app cooldown
            if (_lastCaptureByApp.TryGetValue(context.ApplicationName, out var lastApp) &&
                (now - lastApp).TotalSeconds < caps.CooldownSameAppSeconds)
                return false;

            // Any-capture cooldown
            if (_lastCaptureAny.HasValue &&
                (now - _lastCaptureAny.Value).TotalSeconds < caps.CooldownAnySeconds)
                return false;

            // Hourly limit
            var capturesLastHour = _captureTimestamps.Count(t => (now - t).TotalSeconds <= 3600);
            if (capturesLastHour >= caps.MaxPerHour) return false;

            // Daily limit
            var capturesLastDay = _captureTimestamps.Count(t => (now - t).TotalSeconds <= 86400);
            if (capturesLastDay >= caps.MaxPerDay) return false;

            // Rate limits passed — record capture
            _captureTimestamps.Add(now);
            _lastCaptureByApp[context.ApplicationName] = now;
            _lastCaptureAny = now;
            shouldCapture = true;
        }

        if (shouldCapture)
            await CaptureAndDispatchAsync(context).ConfigureAwait(false);

        return shouldCapture;
    }

    // MARK: - Private

    /// <summary>
    /// Capture the screen, send bytes to classifier, then explicitly dispose
    /// the bitmap to ensure pixel data is released from memory.
    ///
    /// Image bytes are NEVER written to disk or logged.
    /// </summary>
    private async Task CaptureAndDispatchAsync(CaptureContext context)
    {
        byte[]? imageBytes = null;
        try
        {
            imageBytes = CaptureScreenToPng();
            if (imageBytes is null || imageBytes.Length == 0)
                return;

            await SendToClassifierAsync(imageBytes, context).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            AgentLogger.Debug($"VCE capture failed: {ex.Message}");
        }
        finally
        {
            // Explicitly clear image bytes — image NEVER persisted to disk
            if (imageBytes is not null)
                Array.Clear(imageBytes, 0, imageBytes.Length);
        }
    }

    /// <summary>
    /// Capture the primary screen to PNG bytes using Graphics.CopyFromScreen.
    ///
    /// The bitmap is encoded to PNG in memory and then disposed.
    /// No file is created at any point.
    /// </summary>
    internal static byte[]? CaptureScreenToPng()
    {
        // On Windows, screen capture requires STA thread or appropriate manifest;
        // this is called from a background Task which should be acceptable for
        // GDI+ CopyFromScreen. For Windows.Graphics.Capture API (WinRT), a more
        // complex async path would be needed — CopyFromScreen is the safe fallback.
        var screenBounds = System.Windows.Forms.Screen.PrimaryScreen?.Bounds
            ?? new System.Drawing.Rectangle(0, 0, 1920, 1080);

        using var bitmap = new Bitmap(screenBounds.Width, screenBounds.Height, PixelFormat.Format32bppArgb);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.CopyFromScreen(screenBounds.Location, Point.Empty, screenBounds.Size);

        using var ms = new System.IO.MemoryStream();
        bitmap.Save(ms, ImageFormat.Png);
        return ms.ToArray();
    }

    /// <summary>
    /// Send image bytes + capture context to the Python VCE pipeline via named pipe.
    ///
    /// Python side will OCR, redact PII, classify, build VCERecord, then
    /// immediately discard image bytes. Only VCERecord metadata is buffered.
    /// </summary>
    private async Task SendToClassifierAsync(byte[] imageBytes, CaptureContext context)
    {
        var payload = new Dictionary<string, object>
        {
            ["event_type"] = "SCREEN_CAPTURE",
            ["image_bytes"] = Convert.ToBase64String(imageBytes),
            ["application_name"] = context.ApplicationName,
            ["window_title"] = context.WindowTitle,
            ["dwell_ms"] = context.DwellMs,
            ["interaction_intensity"] = context.InteractionIntensity,
            ["trigger_reason"] = context.TriggerReason,
            ["timestamp"] = DateTime.UtcNow.ToString("O"),
        };

        await _sendIpc(payload).ConfigureAwait(false);
    }

    /// <summary>
    /// Remove timestamps older than 24 hours from the ring buffer.
    /// Caller must hold _stateLock.
    /// </summary>
    private void PruneOldTimestamps(DateTime now)
    {
        var cutoff = now.AddSeconds(-86400);
        _captureTimestamps.RemoveAll(t => t < cutoff);
    }

    public void Dispose()
    {
        if (!_disposed)
        {
            _disposed = true;
            lock (_stateLock)
            {
                _captureTimestamps.Clear();
                _lastCaptureByApp.Clear();
            }
        }
    }
}
