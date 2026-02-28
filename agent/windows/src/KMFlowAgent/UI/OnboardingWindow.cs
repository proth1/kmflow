// Multi-step onboarding wizard for first-run consent and configuration.
//
// Step 1: Welcome — explains what the agent captures and why.
// Step 2: Capture Details — lists event types and PII protections.
// Step 3: Consent — explicit opt-in with scope selection.
// Step 4: Confirmation — summary and start capture.
//
// This is a model class that drives the onboarding UI (WPF or console).
// The actual WPF window would bind to these properties and commands.
// Keeping the logic separate from the view enables unit testing and
// NativeAOT compatibility.

using System.ComponentModel;
using System.Runtime.CompilerServices;
using KMFlowAgent.Consent;
using KMFlowAgent.Utilities;

namespace KMFlowAgent.UI;

/// <summary>
/// Onboarding wizard step identifiers.
/// </summary>
public enum OnboardingStep
{
    Welcome = 0,
    CaptureDetails = 1,
    ConsentGrant = 2,
    Confirmation = 3,
}

/// <summary>
/// View model for the multi-step onboarding wizard.
/// Drives UI state without direct WPF dependencies.
/// </summary>
public sealed class OnboardingViewModel : INotifyPropertyChanged
{
    private readonly IConsentManager _consentManager;
    private OnboardingStep _currentStep = OnboardingStep.Welcome;
    private string _selectedScope = "action_level";
    private bool _isComplete;

    public event PropertyChangedEventHandler? PropertyChanged;
    public event EventHandler? OnboardingCompleted;

    public OnboardingViewModel(IConsentManager consentManager)
    {
        _consentManager = consentManager;
    }

    /// <summary>Current wizard step.</summary>
    public OnboardingStep CurrentStep
    {
        get => _currentStep;
        private set
        {
            if (_currentStep != value)
            {
                _currentStep = value;
                OnPropertyChanged();
                OnPropertyChanged(nameof(CanGoBack));
                OnPropertyChanged(nameof(CanGoNext));
                OnPropertyChanged(nameof(NextButtonLabel));
                OnPropertyChanged(nameof(StepTitle));
                OnPropertyChanged(nameof(StepDescription));
            }
        }
    }

    /// <summary>Selected capture scope for consent.</summary>
    public string SelectedScope
    {
        get => _selectedScope;
        set
        {
            if (_selectedScope != value)
            {
                _selectedScope = value;
                OnPropertyChanged();
            }
        }
    }

    /// <summary>Whether onboarding has been completed.</summary>
    public bool IsComplete => _isComplete;

    /// <summary>Total number of steps.</summary>
    public static int TotalSteps => 4;

    /// <summary>Whether the Back button should be enabled.</summary>
    public bool CanGoBack => CurrentStep > OnboardingStep.Welcome;

    /// <summary>Whether the Next button should be enabled.</summary>
    public bool CanGoNext => !_isComplete;

    /// <summary>Label for the Next button (changes on last step).</summary>
    public string NextButtonLabel => CurrentStep switch
    {
        OnboardingStep.ConsentGrant => "I Consent",
        OnboardingStep.Confirmation => "Start Capture",
        _ => "Next",
    };

    /// <summary>Title for the current step.</summary>
    public string StepTitle => CurrentStep switch
    {
        OnboardingStep.Welcome => "Welcome to KMFlow",
        OnboardingStep.CaptureDetails => "What We Capture",
        OnboardingStep.ConsentGrant => "Your Consent",
        OnboardingStep.Confirmation => "Ready to Start",
        _ => "",
    };

    /// <summary>Description text for the current step.</summary>
    public string StepDescription => CurrentStep switch
    {
        OnboardingStep.Welcome =>
            "KMFlow helps your organization understand how work gets done by observing " +
            "application usage patterns. This wizard will explain what is captured and " +
            "ask for your explicit consent before any monitoring begins.",
        OnboardingStep.CaptureDetails =>
            "KMFlow captures: application switches, window titles (with PII redacted), " +
            "keyboard action counts (not keystrokes), mouse click counts, and idle periods. " +
            "All data is filtered through 4 layers of PII protection. " +
            "Password fields, password managers, and private browsing are never captured.",
        OnboardingStep.ConsentGrant =>
            "By consenting, you agree to the capture described above for the duration of " +
            "this engagement. You can pause or revoke consent at any time via the system tray icon. " +
            "Your consent decision is stored locally and protected by DPAPI encryption.",
        OnboardingStep.Confirmation =>
            "Capture will begin immediately. You will see a KMFlow icon in your system tray. " +
            "Right-click it at any time to pause capture, view the transparency log, or revoke consent.",
        _ => "",
    };

    /// <summary>Navigate to the next step.</summary>
    public void GoNext()
    {
        if (_isComplete) return;

        if (CurrentStep == OnboardingStep.Confirmation)
        {
            // Final step: grant consent and complete onboarding
            _consentManager.GrantConsent(_selectedScope);
            _isComplete = true;
            OnPropertyChanged(nameof(IsComplete));
            OnPropertyChanged(nameof(CanGoNext));

            AgentLogger.Info($"Onboarding completed, consent granted (scope: {_selectedScope})");
            OnboardingCompleted?.Invoke(this, EventArgs.Empty);
            return;
        }

        CurrentStep = (OnboardingStep)((int)CurrentStep + 1);
    }

    /// <summary>Navigate to the previous step.</summary>
    public void GoBack()
    {
        if (CurrentStep > OnboardingStep.Welcome)
        {
            CurrentStep = (OnboardingStep)((int)CurrentStep - 1);
        }
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}
