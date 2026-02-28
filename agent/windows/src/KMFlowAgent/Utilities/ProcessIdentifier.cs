// Application identity resolution for Windows processes.
//
// Windows lacks macOS bundle identifiers, so we use a layered strategy:
// 1. Process executable name → display name lookup table
// 2. AppUserModelId for UWP/MSIX apps
// 3. Window class name fallback
// 4. Configurable per-engagement mapping table
//
// PRD Section 5.7.

using System.Diagnostics;

namespace KMFlowAgent.Utilities;

/// <summary>
/// Resolves Windows processes to canonical application identifiers and display names.
/// </summary>
public sealed class ProcessIdentifier
{
    private readonly Dictionary<string, (string DisplayName, string CanonicalId)> _mappingTable;

    /// <summary>
    /// Well-known process-to-app mappings for common enterprise applications.
    /// Maps exe name (case-insensitive) to (DisplayName, CanonicalId).
    /// CanonicalId uses reverse-domain format to align with macOS bundle IDs.
    /// </summary>
    private static readonly Dictionary<string, (string DisplayName, string CanonicalId)> DefaultMappings =
        new(StringComparer.OrdinalIgnoreCase)
        {
            // Microsoft Office
            ["EXCEL.EXE"] = ("Microsoft Excel", "com.microsoft.Excel"),
            ["WINWORD.EXE"] = ("Microsoft Word", "com.microsoft.Word"),
            ["POWERPNT.EXE"] = ("Microsoft PowerPoint", "com.microsoft.PowerPoint"),
            ["OUTLOOK.EXE"] = ("Microsoft Outlook", "com.microsoft.Outlook"),
            ["ONENOTE.EXE"] = ("Microsoft OneNote", "com.microsoft.onenote"),
            ["MSTEAMS.EXE"] = ("Microsoft Teams", "com.microsoft.teams"),
            ["ms-teams.exe"] = ("Microsoft Teams", "com.microsoft.teams"),

            // Browsers
            ["CHROME.EXE"] = ("Google Chrome", "com.google.Chrome"),
            ["MSEDGE.EXE"] = ("Microsoft Edge", "com.microsoft.edgemac"),
            ["FIREFOX.EXE"] = ("Mozilla Firefox", "org.mozilla.firefox"),
            ["BRAVE.EXE"] = ("Brave Browser", "com.brave.Browser"),
            ["OPERA.EXE"] = ("Opera", "com.operasoftware.Opera"),
            ["VIVALDI.EXE"] = ("Vivaldi", "com.vivaldi.Vivaldi"),

            // SAP
            ["SAPLOGON.EXE"] = ("SAP Logon", "com.sap.gui"),
            ["SAPGUI.EXE"] = ("SAP GUI", "com.sap.gui"),

            // Development
            ["DEVENV.EXE"] = ("Visual Studio", "com.microsoft.visualstudio"),
            ["CODE.EXE"] = ("Visual Studio Code", "com.microsoft.vscode"),
            ["IDEA64.EXE"] = ("IntelliJ IDEA", "com.jetbrains.intellij"),

            // Other enterprise
            ["SLACK.EXE"] = ("Slack", "com.tinyspeck.slackmacgap"),
            ["SALESFORCE.EXE"] = ("Salesforce", "com.salesforce.desktop"),
            ["EXPLORER.EXE"] = ("Windows Explorer", "com.microsoft.explorer"),
            ["NOTEPAD.EXE"] = ("Notepad", "com.microsoft.notepad"),
            ["CALC.EXE"] = ("Calculator", "com.microsoft.calculator"),
        };

    public ProcessIdentifier(
        Dictionary<string, (string DisplayName, string CanonicalId)>? engagementMappings = null)
    {
        _mappingTable = new Dictionary<string, (string, string)>(
            DefaultMappings, StringComparer.OrdinalIgnoreCase);

        if (engagementMappings is not null)
        {
            foreach (var (key, value) in engagementMappings)
            {
                _mappingTable[key] = value;
            }
        }
    }

    /// <summary>
    /// Identify a process and return (DisplayName, CanonicalId).
    /// </summary>
    public (string DisplayName, string CanonicalId) Identify(Process process)
    {
        string? exeName = null;

        try
        {
            exeName = Path.GetFileName(process.MainModule?.FileName ?? process.ProcessName);
        }
        catch
        {
            exeName = process.ProcessName;
        }

        if (string.IsNullOrEmpty(exeName))
            return ("Unknown", "unknown");

        // 1. Check mapping table (includes defaults + engagement overrides)
        if (_mappingTable.TryGetValue(exeName, out var mapped))
            return mapped;

        // 2. Use process name as fallback
        var displayName = Path.GetFileNameWithoutExtension(exeName);
        var canonicalId = exeName.ToLowerInvariant();

        return (displayName, canonicalId);
    }
}
