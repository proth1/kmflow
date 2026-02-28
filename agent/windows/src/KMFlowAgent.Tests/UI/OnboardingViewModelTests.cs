// Unit tests for OnboardingViewModel wizard logic.

using KMFlowAgent.Consent;
using KMFlowAgent.UI;
using Xunit;

namespace KMFlowAgent.Tests.UI;

public class OnboardingViewModelTests
{
    private readonly MockConsentManager _consentManager = new();

    [Fact]
    public void InitialStep_IsWelcome()
    {
        var vm = new OnboardingViewModel(_consentManager);

        Assert.Equal(OnboardingStep.Welcome, vm.CurrentStep);
    }

    [Fact]
    public void GoNext_AdvancesStep()
    {
        var vm = new OnboardingViewModel(_consentManager);

        vm.GoNext();
        Assert.Equal(OnboardingStep.CaptureDetails, vm.CurrentStep);

        vm.GoNext();
        Assert.Equal(OnboardingStep.ConsentGrant, vm.CurrentStep);
    }

    [Fact]
    public void GoBack_ReturnsToWelcome()
    {
        var vm = new OnboardingViewModel(_consentManager);

        vm.GoNext(); // CaptureDetails
        vm.GoBack(); // Welcome

        Assert.Equal(OnboardingStep.Welcome, vm.CurrentStep);
    }

    [Fact]
    public void GoBack_AtWelcome_StaysAtWelcome()
    {
        var vm = new OnboardingViewModel(_consentManager);

        vm.GoBack();

        Assert.Equal(OnboardingStep.Welcome, vm.CurrentStep);
    }

    [Fact]
    public void CanGoBack_FalseOnWelcome()
    {
        var vm = new OnboardingViewModel(_consentManager);

        Assert.False(vm.CanGoBack);
    }

    [Fact]
    public void CanGoBack_TrueAfterFirstStep()
    {
        var vm = new OnboardingViewModel(_consentManager);
        vm.GoNext();

        Assert.True(vm.CanGoBack);
    }

    [Fact]
    public void NextButtonLabel_Changes_OnConsentStep()
    {
        var vm = new OnboardingViewModel(_consentManager);

        Assert.Equal("Next", vm.NextButtonLabel);

        vm.GoNext(); // CaptureDetails
        Assert.Equal("Next", vm.NextButtonLabel);

        vm.GoNext(); // ConsentGrant
        Assert.Equal("I Consent", vm.NextButtonLabel);

        vm.GoNext(); // Confirmation
        Assert.Equal("Start Capture", vm.NextButtonLabel);
    }

    [Fact]
    public void FinalStep_GrantsConsent()
    {
        _consentManager.InitializeCalled = false;
        _consentManager.Initialize("test-engagement");
        var vm = new OnboardingViewModel(_consentManager);

        // Walk through all steps
        vm.GoNext(); // CaptureDetails
        vm.GoNext(); // ConsentGrant
        vm.GoNext(); // Confirmation
        vm.GoNext(); // Complete (grants consent)

        Assert.True(vm.IsComplete);
        Assert.True(_consentManager.ConsentGranted);
    }

    [Fact]
    public void OnboardingCompleted_EventFires()
    {
        _consentManager.Initialize("test-engagement");
        var vm = new OnboardingViewModel(_consentManager);
        bool completedFired = false;
        vm.OnboardingCompleted += (_, _) => completedFired = true;

        vm.GoNext(); // CaptureDetails
        vm.GoNext(); // ConsentGrant
        vm.GoNext(); // Confirmation
        vm.GoNext(); // Complete

        Assert.True(completedFired);
    }

    [Fact]
    public void GoNext_AfterComplete_DoesNothing()
    {
        _consentManager.Initialize("test-engagement");
        var vm = new OnboardingViewModel(_consentManager);

        // Complete the wizard
        vm.GoNext();
        vm.GoNext();
        vm.GoNext();
        vm.GoNext();

        Assert.True(vm.IsComplete);

        // Further GoNext calls should be no-ops
        vm.GoNext();
        Assert.True(vm.IsComplete);
    }

    [Fact]
    public void SelectedScope_DefaultsToActionLevel()
    {
        var vm = new OnboardingViewModel(_consentManager);

        Assert.Equal("action_level", vm.SelectedScope);
    }

    [Fact]
    public void SelectedScope_CanBeChanged()
    {
        var vm = new OnboardingViewModel(_consentManager);

        vm.SelectedScope = "content_level";

        Assert.Equal("content_level", vm.SelectedScope);
    }

    [Fact]
    public void StepTitle_ReturnsCorrectTitle()
    {
        var vm = new OnboardingViewModel(_consentManager);

        Assert.Equal("Welcome to KMFlow", vm.StepTitle);

        vm.GoNext();
        Assert.Equal("What We Capture", vm.StepTitle);
    }

    [Fact]
    public void PropertyChanged_Fires_OnStepChange()
    {
        var vm = new OnboardingViewModel(_consentManager);
        var changedProps = new List<string>();
        vm.PropertyChanged += (_, e) => changedProps.Add(e.PropertyName!);

        vm.GoNext();

        Assert.Contains("CurrentStep", changedProps);
        Assert.Contains("StepTitle", changedProps);
        Assert.Contains("StepDescription", changedProps);
    }

    /// <summary>
    /// Simple mock for testing — tracks calls without DPAPI/registry.
    /// </summary>
    private sealed class MockConsentManager : IConsentManager
    {
        public ConsentState CurrentState { get; private set; } = ConsentState.NeverConsented;
        public string? EngagementId { get; private set; }
        public bool ConsentGranted { get; private set; }
        public bool InitializeCalled { get; set; }

        public event System.ComponentModel.PropertyChangedEventHandler? PropertyChanged;

        public void Initialize(string engagementId)
        {
            EngagementId = engagementId;
            InitializeCalled = true;
        }

        public void GrantConsent(string captureScope)
        {
            CurrentState = ConsentState.Consented;
            ConsentGranted = true;
        }

        public void RevokeConsent()
        {
            CurrentState = ConsentState.Revoked;
        }
    }
}
