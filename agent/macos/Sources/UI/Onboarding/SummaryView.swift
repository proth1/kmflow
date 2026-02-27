/// Step 5 — Summary of what will and will not be captured.
///
/// Presents a two-column breakdown of data that will be collected versus data
/// that is explicitly excluded, followed by a recap of the engagement details
/// the user entered in step 2. The "Start Monitoring" button is rendered by
/// `OnboardingContentView` — this view is purely informational.

import SwiftUI

/// The final summary step of the onboarding wizard.
///
/// No user input is required here. The user reviews the capture scope and then
/// taps "Start Monitoring" (in the outer navigation bar) to complete setup.
public struct SummaryView: View {

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
            captureScope
            Divider()
            engagementSummary
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Sub-views

    /// Side-by-side "Will be captured" / "Will NOT be captured" columns.
    private var captureScope: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Data Collection Summary")
                .font(.headline)

            HStack(alignment: .top, spacing: 16) {
                // Left column — what IS captured
                VStack(alignment: .leading, spacing: 10) {
                    Text("What will be captured")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundColor(.green)

                    CaptureRow(symbol: "checkmark.circle.fill", color: .green,
                               text: "Application switches and dwell time")
                    CaptureRow(symbol: "checkmark.circle.fill", color: .green,
                               text: "Window titles (with PII redaction)")
                    CaptureRow(symbol: "checkmark.circle.fill", color: .green,
                               text: "Keyboard and mouse activity counts")
                    CaptureRow(symbol: "checkmark.circle.fill", color: .green,
                               text: "Idle periods")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(14)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.green.opacity(0.06))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.green.opacity(0.25), lineWidth: 1)
                )

                // Right column — what is NOT captured
                VStack(alignment: .leading, spacing: 10) {
                    Text("What will NOT be captured")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundColor(.red)

                    CaptureRow(symbol: "xmark.circle.fill", color: .red,
                               text: "Keystroke content or passwords")
                    CaptureRow(symbol: "xmark.circle.fill", color: .red,
                               text: "Private or incognito browsing")
                    CaptureRow(symbol: "xmark.circle.fill", color: .red,
                               text: "File contents or clipboard data")
                    CaptureRow(symbol: "xmark.circle.fill", color: .red,
                               text: "Blocked apps (password managers, etc.)")
                    CaptureRow(symbol: "xmark.circle.fill", color: .red,
                               text: "Screen recordings (unless explicitly enabled)")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(14)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color.red.opacity(0.06))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.red.opacity(0.25), lineWidth: 1)
                )
            }
        }
    }

    /// Recap of the engagement ID, authorizer, and chosen scope.
    private var engagementSummary: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Engagement Configuration")
                .font(.headline)

            VStack(spacing: 0) {
                SummaryRow(
                    label: "Engagement ID",
                    value: state.engagementId.isEmpty ? "—" : state.engagementId
                )
                Divider().padding(.leading, 120)
                SummaryRow(
                    label: "Authorized By",
                    value: state.authorizedBy.isEmpty ? "—" : state.authorizedBy
                )
                Divider().padding(.leading, 120)
                SummaryRow(
                    label: "Capture Scope",
                    value: state.captureScope == "action_level"
                        ? "Activity Level (counts only)"
                        : "Content Level (with PII filtering)"
                )
                Divider().padding(.leading, 120)
                SummaryRow(
                    label: "Backend URL",
                    value: state.backendURL.isEmpty ? "—" : state.backendURL
                )
                Divider().padding(.leading, 120)
                SummaryRow(
                    label: "Connection",
                    value: state.connectionTestPassed ? "Verified" : "Not verified"
                )
                .foregroundColor(state.connectionTestPassed ? .green : .orange)

                // Show MDM source indicator when values are centrally managed
                if state.isMDMConfigured {
                    Divider().padding(.leading, 120)
                    SummaryRow(
                        label: "Configuration",
                        value: "Managed by your organization (MDM)"
                    )
                    .foregroundColor(.secondary)
                }
            }
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color(NSColor.controlBackgroundColor))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.secondary.opacity(0.2), lineWidth: 1)
            )
        }
    }
}

// MARK: - Helper: CaptureRow

/// A single bullet row inside the capture-scope summary columns.
private struct CaptureRow: View {
    let symbol: String
    let color: Color
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: symbol)
                .foregroundColor(color)
                .frame(width: 16, height: 16)
                .padding(.top, 1)
            Text(text)
                .font(.caption)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - Helper: SummaryRow

/// A label–value pair row inside the engagement configuration table.
private struct SummaryRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .top) {
            Text(label)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .frame(width: 120, alignment: .leading)
                .padding(.vertical, 10)
                .padding(.leading, 14)

            Text(value)
                .font(.subheadline)
                .fontWeight(.medium)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 10)
                .padding(.trailing, 14)
        }
    }
}

// MARK: - Preview

#if DEBUG
struct SummaryView_Previews: PreviewProvider {
    static var previews: some View {
        let state = OnboardingState()
        state.engagementId = "ENG-2026-001"
        state.authorizedBy = "Jane Smith"
        state.captureScope = "action_level"
        state.backendURL = "https://api.kmflow.example.com"
        state.connectionTestPassed = true
        return SummaryView(state: state)
            .padding(24)
            .frame(width: 552)
    }
}
#endif
