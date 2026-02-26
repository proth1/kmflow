/// State machine for the KMFlow Agent first-run onboarding wizard.
///
/// `OnboardingState` is the single source of truth for wizard navigation,
/// field values, and completion status. All views observe this object and
/// must not mutate wizard state directly.

import Foundation
import Combine

/// Observable state machine that drives the 5-step onboarding wizard.
@MainActor
public final class OnboardingState: ObservableObject {

    // MARK: - Step Definition

    /// Ordered steps in the onboarding wizard.
    public enum Step: Int, CaseIterable {
        case welcome     = 0
        case consent     = 1
        case permissions = 2
        case connection  = 3
        case summary     = 4

        /// Human-readable title shown in the progress header.
        var title: String {
            switch self {
            case .welcome:     return "Welcome"
            case .consent:     return "Consent & Details"
            case .permissions: return "Permissions"
            case .connection:  return "Backend Connection"
            case .summary:     return "Summary"
            }
        }

        /// The step that immediately follows this one, or `nil` if this is the last step.
        var next: Step? {
            Step(rawValue: rawValue + 1)
        }

        /// The step that immediately precedes this one, or `nil` if this is the first step.
        var previous: Step? {
            Step(rawValue: rawValue - 1)
        }
    }

    // MARK: - Published State

    /// The step currently displayed in the wizard.
    @Published public var currentStep: Step = .welcome

    // Consent step fields
    /// The engagement identifier entered by the user (required).
    @Published public var engagementId: String = ""

    /// The name of the person who authorized this deployment (required).
    @Published public var authorizedBy: String = ""

    /// The selected capture scope: "action_level" or "content_level".
    @Published public var captureScope: String = "action_level"

    /// Whether the user has ticked all three explicit consent checkboxes.
    @Published public var consentGranted: Bool = false

    // Consent checkboxes tracked individually so the UI can reflect each one
    @Published public var consentAcknowledgedObservation: Bool = false
    @Published public var consentAcknowledgedInformed: Bool = false
    @Published public var consentAcknowledgedMonitoring: Bool = false

    // Permissions step
    /// Whether Accessibility permission has been granted (polled from AXIsProcessTrusted).
    @Published public var accessibilityGranted: Bool = false

    // Connection step
    /// The backend base URL entered by the user.
    @Published public var backendURL: String = ""

    /// Whether the last HTTP health-check against `backendURL` succeeded.
    @Published public var connectionTestPassed: Bool = false

    // Completion
    /// Set to `true` when the user confirms the summary step.
    @Published public private(set) var isComplete: Bool = false

    // MARK: - Computed Properties

    /// Fraction of the wizard that has been completed, from 0.0 to 1.0.
    ///
    /// Progress advances as the user moves forward through steps. It reaches
    /// 1.0 only once `isComplete` is set to `true`.
    public var progress: Double {
        guard !isComplete else { return 1.0 }
        let total = Double(Step.allCases.count)
        return Double(currentStep.rawValue) / total
    }

    /// Whether all three consent acknowledgement checkboxes are checked.
    public var allConsentChecked: Bool {
        consentAcknowledgedObservation && consentAcknowledgedInformed && consentAcknowledgedMonitoring
    }

    // MARK: - Validation

    /// Returns `true` when the user may advance past the given step.
    ///
    /// - Parameter step: The step to validate.
    /// - Returns: `true` if all required fields for `step` are satisfied.
    public func canAdvance(from step: Step) -> Bool {
        switch step {
        case .welcome:
            // No input required on the welcome screen.
            return true

        case .consent:
            // All form fields must be filled and all checkboxes checked.
            return !engagementId.trimmingCharacters(in: .whitespaces).isEmpty
                && !authorizedBy.trimmingCharacters(in: .whitespaces).isEmpty
                && allConsentChecked

        case .permissions:
            // Accessibility is mandatory; we do not block here — the user
            // may choose to grant it and the view polls every 2 seconds.
            // We allow advancement even without it so users aren't stuck,
            // but the view surfaces a warning.
            return true

        case .connection:
            // A URL must be entered and the connection test must have passed.
            return !backendURL.trimmingCharacters(in: .whitespaces).isEmpty
                && connectionTestPassed

        case .summary:
            // The summary is informational; the "Start Monitoring" button
            // triggers completion rather than advance.
            return true
        }
    }

    // MARK: - Navigation

    /// Advances to the next step if `canAdvance(from:currentStep)` returns `true`.
    ///
    /// Has no effect when called from the final step.
    public func advance() {
        guard canAdvance(from: currentStep), let next = currentStep.next else { return }
        currentStep = next
    }

    /// Moves back to the previous step.
    ///
    /// Has no effect when called from the welcome step.
    public func goBack() {
        guard let previous = currentStep.previous else { return }
        currentStep = previous
    }

    /// Marks onboarding as complete. Called from the summary step's "Start Monitoring" button.
    ///
    /// Sets `isComplete` to `true` and updates `consentGranted` to reflect the final state.
    public func complete() {
        consentGranted = allConsentChecked
        isComplete = true
    }
}
