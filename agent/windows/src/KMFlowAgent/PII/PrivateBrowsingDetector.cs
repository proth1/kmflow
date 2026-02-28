// Detects private/incognito browsing windows by title heuristics.
//
// Windows equivalent of PrivateBrowsingDetector in
// agent/macos/Sources/PII/CaptureContextFilter.swift.

namespace KMFlowAgent.PII;

/// <summary>
/// Detects private/incognito browsing by examining window titles.
/// When private browsing is detected, URL capture is suppressed.
/// </summary>
public sealed class PrivateBrowsingDetector
{
    /// <summary>
    /// Check if the current window appears to be a private/incognito browser window.
    /// </summary>
    /// <param name="processIdentifier">Process exe name or identifier.</param>
    /// <param name="windowTitle">Current window title.</param>
    /// <returns>True if private browsing is detected.</returns>
    public bool IsPrivateBrowsing(string? processIdentifier, string? windowTitle)
    {
        if (string.IsNullOrEmpty(windowTitle))
            return false;

        var exeName = Path.GetFileName(processIdentifier ?? "")
            .ToUpperInvariant();

        return exeName switch
        {
            // Google Chrome
            "CHROME.EXE" => windowTitle.EndsWith("- Incognito", StringComparison.Ordinal),

            // Microsoft Edge
            "MSEDGE.EXE" => windowTitle.Contains("InPrivate", StringComparison.Ordinal),

            // Mozilla Firefox
            "FIREFOX.EXE" => windowTitle.Contains("Private Browsing", StringComparison.Ordinal),

            // Brave Browser
            "BRAVE.EXE" => windowTitle.Contains("Private", StringComparison.Ordinal),

            // Opera
            "OPERA.EXE" => windowTitle.Contains("Private", StringComparison.Ordinal),

            // Vivaldi
            "VIVALDI.EXE" => windowTitle.Contains("Private Browsing", StringComparison.Ordinal),

            // Arc
            "ARC.EXE" => windowTitle.Contains("Incognito", StringComparison.Ordinal),

            _ => false,
        };
    }
}
