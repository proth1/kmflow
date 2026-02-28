using KMFlowAgent.Consent;
using Xunit;

namespace KMFlowAgent.Tests.Consent;

/// <summary>
/// Tests for ConsentManager state machine using a mock IConsentStore.
/// Verifies state transitions: NeverConsented → Consented → Revoked.
/// </summary>
public class ConsentManagerTests
{
    private readonly MockConsentStore _store = new();
    private bool _consentGrantedCalled;
    private bool _consentRevokedCalled;

    private ConsentManager CreateManager() => new(
        _store,
        onConsentGranted: () => _consentGrantedCalled = true,
        onConsentRevoked: () => _consentRevokedCalled = true);

    [Fact]
    public void Initialize_No_Record_Returns_NeverConsented()
    {
        var manager = CreateManager();
        manager.Initialize("eng-123");

        Assert.Equal(ConsentState.NeverConsented, manager.CurrentState);
        Assert.False(_consentGrantedCalled);
    }

    [Fact]
    public void Initialize_Existing_Consent_Returns_Consented()
    {
        _store.Save("eng-123", ConsentState.Consented, "action_level");

        var manager = CreateManager();
        manager.Initialize("eng-123");

        Assert.Equal(ConsentState.Consented, manager.CurrentState);
        Assert.True(_consentGrantedCalled);
    }

    [Fact]
    public void GrantConsent_Transitions_To_Consented()
    {
        var manager = CreateManager();
        manager.Initialize("eng-123");
        Assert.Equal(ConsentState.NeverConsented, manager.CurrentState);

        manager.GrantConsent("action_level");

        Assert.Equal(ConsentState.Consented, manager.CurrentState);
        Assert.True(_consentGrantedCalled);
    }

    [Fact]
    public void GrantConsent_Persists_To_Store()
    {
        var manager = CreateManager();
        manager.Initialize("eng-123");
        manager.GrantConsent("action_level");

        var record = _store.Load("eng-123");
        Assert.Equal(ConsentState.Consented, record.State);
        Assert.Equal("action_level", record.CaptureScope);
    }

    [Fact]
    public void GrantConsent_Duplicate_Is_Idempotent()
    {
        var manager = CreateManager();
        manager.Initialize("eng-123");
        manager.GrantConsent("action_level");
        _consentGrantedCalled = false;

        manager.GrantConsent("action_level"); // duplicate

        Assert.Equal(ConsentState.Consented, manager.CurrentState);
        Assert.False(_consentGrantedCalled); // not called again
    }

    [Fact]
    public void RevokeConsent_Transitions_To_Revoked()
    {
        var manager = CreateManager();
        manager.Initialize("eng-123");
        manager.GrantConsent("action_level");

        manager.RevokeConsent();

        Assert.Equal(ConsentState.Revoked, manager.CurrentState);
        Assert.True(_consentRevokedCalled);
    }

    [Fact]
    public void RevokeConsent_From_NeverConsented_Is_NoOp()
    {
        var manager = CreateManager();
        manager.Initialize("eng-123");

        manager.RevokeConsent(); // should be no-op

        Assert.Equal(ConsentState.NeverConsented, manager.CurrentState);
        Assert.False(_consentRevokedCalled);
    }

    [Fact]
    public void GrantConsent_Without_Initialize_Throws()
    {
        var manager = CreateManager();
        Assert.Throws<InvalidOperationException>(() => manager.GrantConsent("action_level"));
    }

    [Fact]
    public void RevokeConsent_Without_Initialize_Throws()
    {
        var manager = CreateManager();
        Assert.Throws<InvalidOperationException>(() => manager.RevokeConsent());
    }

    [Fact]
    public void PropertyChanged_Fires_On_State_Transition()
    {
        var manager = CreateManager();
        manager.Initialize("eng-123");

        string? changedProperty = null;
        manager.PropertyChanged += (_, e) => changedProperty = e.PropertyName;

        manager.GrantConsent("action_level");

        Assert.Equal("CurrentState", changedProperty);
    }

    [Fact]
    public void EngagementId_Is_Set_After_Initialize()
    {
        var manager = CreateManager();
        Assert.Null(manager.EngagementId);

        manager.Initialize("eng-456");
        Assert.Equal("eng-456", manager.EngagementId);
    }

    /// <summary>
    /// Simple in-memory IConsentStore for testing.
    /// </summary>
    private sealed class MockConsentStore : IConsentStore
    {
        private readonly Dictionary<string, ConsentRecord> _records = new();

        public ConsentRecord Save(string engagementId, ConsentState state, string captureScope)
        {
            var record = new ConsentRecord
            {
                EngagementId = engagementId,
                State = state,
                ConsentedAt = DateTime.UtcNow,
                Version = "1.0",
                CaptureScope = captureScope,
            };
            _records[engagementId] = record;
            return record;
        }

        public ConsentRecord Load(string engagementId)
        {
            if (_records.TryGetValue(engagementId, out var record))
                return record;

            return new ConsentRecord
            {
                EngagementId = engagementId,
                State = ConsentState.NeverConsented,
                ConsentedAt = DateTime.MinValue,
                Version = "1.0",
                CaptureScope = "none",
            };
        }

        public void Revoke(string engagementId)
        {
            Save(engagementId, ConsentState.Revoked, "none");
        }
    }
}
