// Registry-based configuration reader for enterprise MDM deployment.
//
// Reads agent configuration from HKLM (machine-level, set by GPO/Intune)
// and HKCU (user-level, for engagement-specific overrides).
//
// Registry path: HKLM\SOFTWARE\KMFlowAgent or HKCU\SOFTWARE\KMFlowAgent
// GPO ADMX templates write to HKLM; user preferences write to HKCU.
// HKLM takes precedence for security-sensitive settings (server URL, blocklist).

using Microsoft.Win32;
using KMFlowAgent.Utilities;

namespace KMFlowAgent.Config;

/// <summary>
/// Reads agent configuration from Windows Registry.
/// Supports machine-level (GPO/Intune) and user-level overrides.
/// Falls back to defaults when registry keys are not present.
/// </summary>
public sealed class AgentConfig
{
    private const string RegistryKeyPath = @"SOFTWARE\KMFlowAgent";

    /// <summary>Backend API server URL.</summary>
    public string ServerUrl { get; init; } = "https://api.kmflow.io";

    /// <summary>Engagement ID for this deployment.</summary>
    public string? EngagementId { get; init; }

    /// <summary>Device ID (auto-generated if not set).</summary>
    public string DeviceId { get; init; } = Guid.NewGuid().ToString();

    /// <summary>Comma-separated list of additional blocked process names.</summary>
    public string[] AdditionalBlocklist { get; init; } = [];

    /// <summary>Comma-separated list of allowed process names (empty = all allowed).</summary>
    public string[] Allowlist { get; init; } = [];

    /// <summary>Idle timeout in seconds before idle detection triggers.</summary>
    public int IdleTimeoutSeconds { get; init; } = 300;

    /// <summary>Whether to require Authenticode signature at startup.</summary>
    public bool RequireSignature { get; init; }

    /// <summary>Capture scope: "action_level" or "content_level".</summary>
    public string CaptureScope { get; init; } = "action_level";

    /// <summary>Whether the agent is enabled (false = installed but not running).</summary>
    public bool Enabled { get; init; } = true;

    /// <summary>Log level: Debug, Info, Warn, Error.</summary>
    public string LogLevel { get; init; } = "Info";

    /// <summary>
    /// Load configuration from the registry. Machine-level (HKLM) settings
    /// take precedence over user-level (HKCU) for security-sensitive values.
    /// Falls back to defaults when keys are not present.
    /// </summary>
    public static AgentConfig LoadFromRegistry()
    {
        try
        {
            // Read machine-level settings (GPO/Intune)
            var machineValues = ReadRegistryValues(Registry.LocalMachine);

            // Read user-level settings (engagement overrides)
            var userValues = ReadRegistryValues(Registry.CurrentUser);

            // Machine-level takes precedence for security-sensitive settings
            var serverUrl = GetString(machineValues, "ServerUrl")
                ?? GetString(userValues, "ServerUrl")
                ?? "https://api.kmflow.io";

            var engagementId = GetString(machineValues, "EngagementId")
                ?? GetString(userValues, "EngagementId");

            var deviceId = GetString(machineValues, "DeviceId")
                ?? GetString(userValues, "DeviceId")
                ?? GetOrCreateDeviceId();

            var blocklist = GetString(machineValues, "AdditionalBlocklist")
                ?? GetString(userValues, "AdditionalBlocklist")
                ?? "";

            var allowlist = GetString(machineValues, "Allowlist")
                ?? GetString(userValues, "Allowlist")
                ?? "";

            return new AgentConfig
            {
                ServerUrl = serverUrl,
                EngagementId = engagementId,
                DeviceId = deviceId,
                AdditionalBlocklist = ParseCsvList(blocklist),
                Allowlist = ParseCsvList(allowlist),
                IdleTimeoutSeconds = GetInt(machineValues, "IdleTimeoutSeconds")
                    ?? GetInt(userValues, "IdleTimeoutSeconds")
                    ?? 300,
                RequireSignature = GetBool(machineValues, "RequireSignature") ?? false,
                CaptureScope = GetString(machineValues, "CaptureScope")
                    ?? GetString(userValues, "CaptureScope")
                    ?? "action_level",
                Enabled = GetBool(machineValues, "Enabled") ?? true,
                LogLevel = GetString(userValues, "LogLevel")
                    ?? GetString(machineValues, "LogLevel")
                    ?? "Info",
            };
        }
        catch (Exception ex)
        {
            AgentLogger.Warn($"Failed to read registry config, using defaults: {ex.Message}");
            return new AgentConfig();
        }
    }

    private static Dictionary<string, object?> ReadRegistryValues(RegistryKey root)
    {
        var values = new Dictionary<string, object?>(StringComparer.OrdinalIgnoreCase);
        try
        {
            using var key = root.OpenSubKey(RegistryKeyPath);
            if (key is null) return values;

            foreach (var name in key.GetValueNames())
            {
                values[name] = key.GetValue(name);
            }
        }
        catch
        {
            // Registry access may be denied for HKLM
        }
        return values;
    }

    private static string? GetString(Dictionary<string, object?> values, string key)
    {
        if (values.TryGetValue(key, out var val) && val is string s && !string.IsNullOrEmpty(s))
            return s;
        return null;
    }

    private static int? GetInt(Dictionary<string, object?> values, string key)
    {
        if (values.TryGetValue(key, out var val))
        {
            if (val is int i) return i;
            if (val is string s && int.TryParse(s, out var parsed)) return parsed;
        }
        return null;
    }

    private static bool? GetBool(Dictionary<string, object?> values, string key)
    {
        if (values.TryGetValue(key, out var val))
        {
            if (val is int i) return i != 0;
            if (val is string s) return s == "1" || string.Equals(s, "true", StringComparison.OrdinalIgnoreCase);
        }
        return null;
    }

    private static string[] ParseCsvList(string csv)
    {
        if (string.IsNullOrWhiteSpace(csv)) return [];
        return csv.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
    }

    private static string GetOrCreateDeviceId()
    {
        try
        {
            using var key = Registry.CurrentUser.CreateSubKey(RegistryKeyPath);
            var existing = key.GetValue("DeviceId") as string;
            if (!string.IsNullOrEmpty(existing)) return existing;

            var newId = Guid.NewGuid().ToString();
            key.SetValue("DeviceId", newId, RegistryValueKind.String);
            return newId;
        }
        catch
        {
            return Guid.NewGuid().ToString();
        }
    }
}
