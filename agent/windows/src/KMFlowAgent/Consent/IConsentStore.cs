// Consent storage interface and types.
//
// Mirrors the consent model in agent/macos/Sources/Consent/KeychainConsentStore.swift.

namespace KMFlowAgent.Consent;

/// <summary>
/// Consent state for a given engagement.
/// </summary>
public enum ConsentState
{
    NeverConsented,
    Consented,
    Revoked,
}

/// <summary>
/// Consent record stored per engagement.
/// </summary>
public sealed class ConsentRecord
{
    public required string EngagementId { get; init; }
    public required ConsentState State { get; init; }
    public required DateTime ConsentedAt { get; init; }
    public required string Version { get; init; }
    public required string CaptureScope { get; init; }
}

/// <summary>
/// Interface for consent storage. Implementations must encrypt at rest
/// and provide tamper detection.
/// </summary>
public interface IConsentStore
{
    /// <summary>Save consent for an engagement.</summary>
    ConsentRecord Save(string engagementId, ConsentState state, string captureScope);

    /// <summary>Load consent for an engagement. Returns NeverConsented if missing or tampered.</summary>
    ConsentRecord Load(string engagementId);

    /// <summary>Revoke consent for an engagement.</summary>
    void Revoke(string engagementId);
}
