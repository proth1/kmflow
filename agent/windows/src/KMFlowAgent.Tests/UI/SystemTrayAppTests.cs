// Unit tests for SystemTrayApp view model logic.

using KMFlowAgent.Capture;
using KMFlowAgent.Consent;
using KMFlowAgent.IPC;
using KMFlowAgent.PII;
using KMFlowAgent.UI;
using KMFlowAgent.Utilities;
using Xunit;

namespace KMFlowAgent.Tests.UI;

public class SystemTrayAppTests
{
    [Fact]
    public void BuildTooltip_Active_ShowsActiveState()
    {
        var tooltip = SystemTrayApp.BuildTooltip(isPaused: false, eventCount: 1234);

        Assert.Equal("KMFlow Agent - Active (1,234 events captured)", tooltip);
    }

    [Fact]
    public void BuildTooltip_Paused_ShowsPausedState()
    {
        var tooltip = SystemTrayApp.BuildTooltip(isPaused: true, eventCount: 0);

        Assert.Equal("KMFlow Agent - Paused (0 events captured)", tooltip);
    }

    [Fact]
    public void BuildTooltip_LargeCount_FormatsWithCommas()
    {
        var tooltip = SystemTrayApp.BuildTooltip(isPaused: false, eventCount: 1_000_000);

        Assert.Contains("1,000,000", tooltip);
    }

    [Fact]
    public void GetPauseResumeLabel_NotPaused_ShowsPause()
    {
        Assert.Equal("Pause Capture", SystemTrayApp.GetPauseResumeLabel(isPaused: false));
    }

    [Fact]
    public void GetPauseResumeLabel_Paused_ShowsResume()
    {
        Assert.Equal("Resume Capture", SystemTrayApp.GetPauseResumeLabel(isPaused: true));
    }

    [Fact]
    public void OnPauseResumeClicked_WhenActive_PausesCapture()
    {
        var (tray, captureManager, _) = CreateTrayApp();

        Assert.False(captureManager.IsPaused);
        tray.OnPauseResumeClicked();
        Assert.True(captureManager.IsPaused);
    }

    [Fact]
    public void OnPauseResumeClicked_WhenPaused_ResumesCapture()
    {
        var (tray, captureManager, _) = CreateTrayApp();
        captureManager.Pause();

        tray.OnPauseResumeClicked();
        Assert.False(captureManager.IsPaused);
    }

    [Fact]
    public void OnQuitClicked_InvokesShutdownCallback()
    {
        bool shutdownCalled = false;
        var (tray, _, _) = CreateTrayApp(onShutdown: () => shutdownCalled = true);

        tray.OnQuitClicked();
        Assert.True(shutdownCalled);
    }

    [Fact]
    public void OnTransparencyLogClicked_InvokesCallback()
    {
        bool logOpened = false;
        var (tray, _, _) = CreateTrayApp(onTransparencyLog: () => logOpened = true);

        tray.OnTransparencyLogClicked();
        Assert.True(logOpened);
    }

    [Fact]
    public void OnOnboardingClicked_InvokesCallback()
    {
        bool onboardingOpened = false;
        var (tray, _, _) = CreateTrayApp(onOnboarding: () => onboardingOpened = true);

        tray.OnOnboardingClicked();
        Assert.True(onboardingOpened);
    }

    [Fact]
    public void Dispose_DoesNotThrow()
    {
        var (tray, _, _) = CreateTrayApp();
        tray.Dispose();
        // Double dispose should also be safe
        tray.Dispose();
    }

    private static (SystemTrayApp tray, CaptureStateManager capture, MockConsentManager consent) CreateTrayApp(
        Action? onShutdown = null,
        Action? onTransparencyLog = null,
        Action? onOnboarding = null)
    {
        var consent = new MockConsentManager();
        var pipeClient = new NamedPipeClient();
        var contextFilter = new CaptureContextFilter();
        var processId = new ProcessIdentifier();
        var capture = new CaptureStateManager(pipeClient, contextFilter, processId);

        var tray = new SystemTrayApp(
            consent,
            capture,
            onShutdown ?? (() => { }),
            onTransparencyLog,
            onOnboarding);

        return (tray, capture, consent);
    }

    private sealed class MockConsentManager : IConsentManager
    {
        public ConsentState CurrentState { get; private set; } = ConsentState.Consented;
        public string? EngagementId => "test-engagement";
        public event System.ComponentModel.PropertyChangedEventHandler? PropertyChanged;
        public void Initialize(string engagementId) { }
        public void GrantConsent(string captureScope) { CurrentState = ConsentState.Consented; }
        public void RevokeConsent() { CurrentState = ConsentState.Revoked; }
    }
}
