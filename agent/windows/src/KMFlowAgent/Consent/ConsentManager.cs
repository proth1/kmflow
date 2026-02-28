// Consent lifecycle state machine.
//
// Gates CaptureStateManager — capture never begins without explicit consent.
// On revocation, all capture subsystems stop and an audit event is emitted.
//
// Windows equivalent of agent/macos/Sources/Consent/ConsentManager.swift.

using System.ComponentModel;
using System.Runtime.CompilerServices;
using KMFlowAgent.Utilities;

namespace KMFlowAgent.Consent;

/// <summary>
/// Interface for consent management. Enables testability by decoupling
/// from the concrete DPAPIConsentStore.
/// </summary>
public interface IConsentManager : INotifyPropertyChanged
{
    ConsentState CurrentState { get; }
    string? EngagementId { get; }
    void Initialize(string engagementId);
    void GrantConsent(string captureScope);
    void RevokeConsent();
}

/// <summary>
/// Manages the consent lifecycle: NeverConsented → Consented → Revoked.
/// Raises PropertyChanged for UI data binding (WPF system tray / onboarding).
/// </summary>
public sealed class ConsentManager : IConsentManager
{
    private readonly IConsentStore _store;
    private readonly Action? _onConsentGranted;
    private readonly Action? _onConsentRevoked;
    private ConsentState _currentState = ConsentState.NeverConsented;
    private string? _engagementId;

    public event PropertyChangedEventHandler? PropertyChanged;

    /// <summary>
    /// Create a ConsentManager with lifecycle callbacks.
    /// </summary>
    /// <param name="store">Consent persistence layer.</param>
    /// <param name="onConsentGranted">Called when consent transitions to Consented (start capture).</param>
    /// <param name="onConsentRevoked">Called when consent transitions to Revoked (stop capture).</param>
    public ConsentManager(
        IConsentStore store,
        Action? onConsentGranted = null,
        Action? onConsentRevoked = null)
    {
        _store = store;
        _onConsentGranted = onConsentGranted;
        _onConsentRevoked = onConsentRevoked;
    }

    public ConsentState CurrentState
    {
        get => _currentState;
        private set
        {
            if (_currentState != value)
            {
                _currentState = value;
                OnPropertyChanged();
            }
        }
    }

    public string? EngagementId => _engagementId;

    /// <summary>
    /// Load existing consent state on startup. If no record exists or
    /// the record is tampered/stale, state is NeverConsented and capture
    /// does not begin.
    /// </summary>
    public void Initialize(string engagementId)
    {
        _engagementId = engagementId;
        var record = _store.Load(engagementId);
        CurrentState = record.State;

        AgentLogger.Info($"Consent initialized for {engagementId}: {CurrentState}");

        if (CurrentState == ConsentState.Consented)
        {
            _onConsentGranted?.Invoke();
        }
    }

    /// <summary>
    /// Transition NeverConsented → Consented. Saves consent record with DPAPI+HMAC.
    /// Triggers capture start via onConsentGranted callback.
    /// </summary>
    public void GrantConsent(string captureScope)
    {
        if (_engagementId is null)
            throw new InvalidOperationException("ConsentManager not initialized. Call Initialize() first.");

        if (CurrentState == ConsentState.Consented)
        {
            AgentLogger.Debug("Consent already granted, ignoring duplicate call");
            return;
        }

        _store.Save(_engagementId, ConsentState.Consented, captureScope);
        CurrentState = ConsentState.Consented;

        AgentLogger.Info($"Consent granted for {_engagementId} (scope: {captureScope})");
        _onConsentGranted?.Invoke();
    }

    /// <summary>
    /// Transition Consented → Revoked. Stops capture and emits audit event.
    /// </summary>
    public void RevokeConsent()
    {
        if (_engagementId is null)
            throw new InvalidOperationException("ConsentManager not initialized. Call Initialize() first.");

        if (CurrentState != ConsentState.Consented)
        {
            AgentLogger.Debug($"Cannot revoke consent in state {CurrentState}");
            return;
        }

        _store.Revoke(_engagementId);
        CurrentState = ConsentState.Revoked;

        AgentLogger.Info($"Consent revoked for {_engagementId}");
        _onConsentRevoked?.Invoke();
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}
