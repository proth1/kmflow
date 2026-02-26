/// Step 2 — Engagement details and explicit informed-consent collection.
///
/// The user must provide an engagement ID, the name of the person who
/// authorised this deployment, and choose a capture scope. Three explicit
/// consent checkboxes must all be ticked before the wizard allows advancement.

import SwiftUI

/// The consent and engagement details step of the onboarding wizard.
///
/// All three checkboxes must be checked and both required text fields must be
/// non-empty before `OnboardingState.canAdvance(from: .consent)` returns `true`.
public struct ConsentView: View {

    // MARK: - Dependencies

    @ObservedObject private var state: OnboardingState

    // MARK: - Initialiser

    /// - Parameter state: The shared wizard state.
    public init(state: OnboardingState) {
        self.state = state
    }

    // MARK: - Body

    public var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            engagementForm
            Divider()
            consentCheckboxes
            Divider()
            legalFooter
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Sub-views

    /// Engagement ID, Authorized By, and Capture Scope form fields.
    private var engagementForm: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Engagement Details")
                .font(.headline)

            LabeledFormField(label: "Engagement ID", isRequired: true) {
                TextField("e.g. ENG-2026-001", text: $state.engagementId)
                    .textFieldStyle(.roundedBorder)
            }

            LabeledFormField(label: "Authorized By", isRequired: true) {
                TextField("Full name of approving stakeholder", text: $state.authorizedBy)
                    .textFieldStyle(.roundedBorder)
            }

            LabeledFormField(label: "Capture Scope", isRequired: false) {
                Picker("Capture Scope", selection: $state.captureScope) {
                    Text("Activity Level (counts only)")
                        .tag("action_level")
                    Text("Content Level (with PII filtering)")
                        .tag("content_level")
                }
                .pickerStyle(.segmented)
                .labelsHidden()
            }
        }
    }

    /// Three explicit acknowledgement checkboxes.
    private var consentCheckboxes: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Explicit Consent")
                .font(.headline)

            ConsentCheckbox(
                isChecked: $state.consentAcknowledgedObservation,
                label: "I understand that KMFlow will observe my application usage patterns"
            )

            ConsentCheckbox(
                isChecked: $state.consentAcknowledgedInformed,
                label: "I have been informed about data collection by my organization"
            )

            ConsentCheckbox(
                isChecked: $state.consentAcknowledgedMonitoring,
                label: "I consent to activity monitoring for the specified engagement"
            )
        }
    }

    /// Legal reminder about revocation rights.
    private var legalFooter: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "info.circle")
                .foregroundColor(.secondary)
                .frame(width: 16)
            Text("You can revoke consent at any time from the menu bar icon.")
                .font(.footnote)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - Helper: LabeledFormField

/// A vertical label + content stack for form fields.
private struct LabeledFormField<Content: View>: View {
    let label: String
    let isRequired: Bool
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 2) {
                Text(label)
                    .font(.subheadline)
                    .fontWeight(.medium)
                if isRequired {
                    Text("*")
                        .foregroundColor(.red)
                        .font(.subheadline)
                }
            }
            content()
        }
    }
}

// MARK: - Helper: ConsentCheckbox

/// A single labelled checkbox for explicit consent acknowledgement.
private struct ConsentCheckbox: View {
    @Binding var isChecked: Bool
    let label: String

    var body: some View {
        Toggle(isOn: $isChecked) {
            Text(label)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
        }
        .toggleStyle(.checkbox)
    }
}

// MARK: - Preview

#if DEBUG
struct ConsentView_Previews: PreviewProvider {
    static var previews: some View {
        ConsentView(state: OnboardingState())
            .padding(24)
            .frame(width: 552)
    }
}
#endif
