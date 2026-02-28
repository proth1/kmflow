// DPAPI-backed consent storage with HMAC-SHA256 tamper detection.
//
// Windows equivalent of agent/macos/Sources/Consent/KeychainConsentStore.swift.
// Consent records are encrypted with DPAPI (current user scope) and signed
// with HMAC-SHA256. The HMAC key is stored in a separate DPAPI-encrypted file.
//
// If HMAC verification fails, the record is treated as tampered and the consent
// state returns NeverConsented (forcing re-consent). Stale consent versions
// also trigger re-consent.

using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using KMFlowAgent.Utilities;

namespace KMFlowAgent.Consent;

/// <summary>
/// Stores consent records encrypted with DPAPI and signed with HMAC-SHA256.
/// Thread-safe for concurrent reads; writes are serialized via lock.
/// </summary>
public sealed class DPAPIConsentStore : IConsentStore
{
    /// <summary>Increment when consent scope or terms change to force re-consent.</summary>
    public const string CurrentConsentVersion = "1.0";

    private const string HmacKeyFileName = "consent_hmac.key";
    private const int HmacKeySize = 32;

    private readonly string _consentDir;
    private readonly string _hmacKeyPath;
    private readonly object _writeLock = new();

    public DPAPIConsentStore(string dataDir)
    {
        _consentDir = Path.Combine(dataDir, "consent");
        _hmacKeyPath = Path.Combine(_consentDir, HmacKeyFileName);
        Directory.CreateDirectory(_consentDir);
    }

    public ConsentRecord Save(string engagementId, ConsentState state, string captureScope)
    {
        var record = new ConsentRecord
        {
            EngagementId = engagementId,
            State = state,
            ConsentedAt = DateTime.UtcNow,
            Version = CurrentConsentVersion,
            CaptureScope = captureScope,
        };

        lock (_writeLock)
        {
            var json = JsonSerializer.Serialize(new StoredConsentRecord
            {
                EngagementId = record.EngagementId,
                State = record.State.ToString(),
                ConsentedAt = record.ConsentedAt.ToString("O"),
                Version = record.Version,
                CaptureScope = record.CaptureScope,
            });

            var plainBytes = Encoding.UTF8.GetBytes(json);
            var encrypted = ProtectedData.Protect(plainBytes, null, DataProtectionScope.CurrentUser);
            var hmac = ComputeHmac(encrypted);

            var envelope = new ConsentEnvelope
            {
                EncryptedData = Convert.ToBase64String(encrypted),
                Hmac = Convert.ToBase64String(hmac),
            };

            var envelopeJson = JsonSerializer.Serialize(envelope);
            var filePath = GetConsentFilePath(engagementId);
            File.WriteAllText(filePath, envelopeJson);

            AgentLogger.Info($"Consent saved for engagement {engagementId}: {state}");
        }

        return record;
    }

    public ConsentRecord Load(string engagementId)
    {
        var filePath = GetConsentFilePath(engagementId);

        if (!File.Exists(filePath))
            return MakeNeverConsented(engagementId);

        try
        {
            var envelopeJson = File.ReadAllText(filePath);
            var envelope = JsonSerializer.Deserialize<ConsentEnvelope>(envelopeJson);

            if (envelope is null)
                return MakeNeverConsented(engagementId);

            var encrypted = Convert.FromBase64String(envelope.EncryptedData);
            var storedHmac = Convert.FromBase64String(envelope.Hmac);

            // Verify HMAC before trusting the data
            var computedHmac = ComputeHmac(encrypted);
            if (!CryptographicOperations.FixedTimeEquals(storedHmac, computedHmac))
            {
                AgentLogger.Warn($"HMAC verification failed for engagement {engagementId} — re-consent required");
                return MakeNeverConsented(engagementId);
            }

            // Decrypt
            var plainBytes = ProtectedData.Unprotect(encrypted, null, DataProtectionScope.CurrentUser);
            var json = Encoding.UTF8.GetString(plainBytes);
            var stored = JsonSerializer.Deserialize<StoredConsentRecord>(json);

            if (stored is null)
                return MakeNeverConsented(engagementId);

            // Check version — stale consent requires re-consent
            if (stored.Version != CurrentConsentVersion)
            {
                AgentLogger.Info($"Consent version stale ({stored.Version} != {CurrentConsentVersion}) — re-consent required");
                return MakeNeverConsented(engagementId);
            }

            return new ConsentRecord
            {
                EngagementId = stored.EngagementId,
                State = Enum.TryParse<ConsentState>(stored.State, out var state) ? state : ConsentState.NeverConsented,
                ConsentedAt = DateTime.Parse(stored.ConsentedAt),
                Version = stored.Version,
                CaptureScope = stored.CaptureScope,
            };
        }
        catch (Exception ex)
        {
            AgentLogger.Warn($"Failed to load consent for {engagementId}: {ex.Message}");
            return MakeNeverConsented(engagementId);
        }
    }

    public void Revoke(string engagementId)
    {
        Save(engagementId, ConsentState.Revoked, captureScope: "none");
        AgentLogger.Info($"Consent revoked for engagement {engagementId}");
    }

    private byte[] ComputeHmac(byte[] data)
    {
        var hmacKey = GetOrCreateHmacKey();
        using var hmac = new HMACSHA256(hmacKey);
        return hmac.ComputeHash(data);
    }

    private byte[] GetOrCreateHmacKey()
    {
        if (File.Exists(_hmacKeyPath))
        {
            try
            {
                var encrypted = File.ReadAllBytes(_hmacKeyPath);
                return ProtectedData.Unprotect(encrypted, null, DataProtectionScope.CurrentUser);
            }
            catch
            {
                AgentLogger.Warn("Failed to load HMAC key, generating new one");
            }
        }

        // Generate new HMAC key
        var key = RandomNumberGenerator.GetBytes(HmacKeySize);
        var encryptedKey = ProtectedData.Protect(key, null, DataProtectionScope.CurrentUser);
        File.WriteAllBytes(_hmacKeyPath, encryptedKey);
        return key;
    }

    private string GetConsentFilePath(string engagementId)
    {
        // Sanitize engagement ID for filename
        var safe = string.Join("_", engagementId.Split(Path.GetInvalidFileNameChars()));
        return Path.Combine(_consentDir, $"{safe}.consent");
    }

    private static ConsentRecord MakeNeverConsented(string engagementId) => new()
    {
        EngagementId = engagementId,
        State = ConsentState.NeverConsented,
        ConsentedAt = DateTime.MinValue,
        Version = CurrentConsentVersion,
        CaptureScope = "none",
    };

    /// <summary>Internal JSON shape for storage (no enums in serialization).</summary>
    private sealed class StoredConsentRecord
    {
        [JsonPropertyName("engagement_id")]
        public string EngagementId { get; set; } = "";

        [JsonPropertyName("state")]
        public string State { get; set; } = "";

        [JsonPropertyName("consented_at")]
        public string ConsentedAt { get; set; } = "";

        [JsonPropertyName("version")]
        public string Version { get; set; } = "";

        [JsonPropertyName("capture_scope")]
        public string CaptureScope { get; set; } = "";
    }

    /// <summary>Envelope: encrypted consent data + HMAC signature.</summary>
    private sealed class ConsentEnvelope
    {
        [JsonPropertyName("encrypted_data")]
        public string EncryptedData { get; set; } = "";

        [JsonPropertyName("hmac")]
        public string Hmac { get; set; } = "";
    }
}
