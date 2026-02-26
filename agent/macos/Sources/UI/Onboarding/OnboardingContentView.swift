/// Root SwiftUI view for the onboarding wizard.
///
/// `OnboardingContentView` owns the chrome: the top progress bar, step title,
/// scrollable content area, and the bottom navigation bar (Back / Next /
/// Complete Setup buttons). Individual step views are swapped in/out based on
/// `OnboardingState.currentStep`.

import SwiftUI

/// The root container view rendered by the onboarding NSWindow.
public struct OnboardingContentView: View {

    // MARK: - Dependencies

    @ObservedObject private var state: OnboardingState

    // MARK: - Initialiser

    /// Creates the content view bound to the provided state object.
    ///
    /// - Parameter state: The shared `OnboardingState` driving the wizard.
    public init(state: OnboardingState) {
        self.state = state
    }

    // MARK: - Body

    public var body: some View {
        VStack(spacing: 0) {
            progressHeader
            Divider()
            stepContent
            Divider()
            navigationBar
        }
        .frame(width: 600, height: 500)
        .background(Color(NSColor.windowBackgroundColor))
    }

    // MARK: - Sub-views

    /// Horizontal progress bar and step title shown at the top of every screen.
    private var progressHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(state.currentStep.title)
                    .font(.headline)
                    .foregroundColor(.primary)
                Spacer()
                Text("Step \(state.currentStep.rawValue + 1) of \(OnboardingState.Step.allCases.count)")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            ProgressView(value: state.progress)
                .progressViewStyle(.linear)
                .tint(.accentColor)
                .animation(.easeInOut(duration: 0.25), value: state.progress)
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 16)
    }

    /// The scrollable content area. Swaps view based on `currentStep`.
    private var stepContent: some View {
        ScrollView(.vertical, showsIndicators: true) {
            Group {
                switch state.currentStep {
                case .welcome:
                    WelcomeView()
                case .consent:
                    ConsentView(state: state)
                case .permissions:
                    PermissionsView(state: state)
                case .connection:
                    ConnectionView(state: state)
                case .summary:
                    SummaryView(state: state)
                }
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 20)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// Bottom navigation bar containing Back, Next, and Complete Setup buttons.
    private var navigationBar: some View {
        HStack {
            // Back button — hidden on welcome step.
            if state.currentStep != .welcome {
                Button("Back") {
                    state.goBack()
                }
                .keyboardShortcut(.leftArrow, modifiers: [])
            }

            Spacer()

            // Next / Complete Setup — swapped on final step.
            if state.currentStep == .summary {
                Button("Start Monitoring") {
                    state.complete()
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.return, modifiers: [])
            } else {
                Button("Next") {
                    state.advance()
                }
                .buttonStyle(.borderedProminent)
                .disabled(!state.canAdvance(from: state.currentStep))
                .keyboardShortcut(.return, modifiers: [])
            }
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 16)
    }
}

// MARK: - Preview

#if DEBUG
struct OnboardingContentView_Previews: PreviewProvider {
    static var previews: some View {
        OnboardingContentView(state: OnboardingState())
    }
}
#endif
