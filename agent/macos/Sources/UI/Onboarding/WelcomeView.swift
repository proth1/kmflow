/// Step 1 — Welcome screen for the KMFlow Agent onboarding wizard.
///
/// Explains what KMFlow does, why it has been installed, and what privacy
/// guarantees are in place. No user input is required; the user simply reads
/// and advances.

import SwiftUI

/// The welcome step of the onboarding wizard.
///
/// Presents the KMFlow identity, a short description of the agent's purpose,
/// three capability bullets, and a footer consent notice.
public struct WelcomeView: View {

    // MARK: - Body

    public init() {}

    public var body: some View {
        VStack(alignment: .center, spacing: 28) {
            appIcon
            titleBlock
            featureBullets
            footerNotice
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Sub-views

    /// Large waveform icon representing the agent.
    private var appIcon: some View {
        Image(systemName: "waveform.circle.fill")
            .resizable()
            .scaledToFit()
            .frame(width: 72, height: 72)
            .foregroundStyle(.tint)
            .symbolRenderingMode(.hierarchical)
    }

    /// App name and explanatory paragraph.
    private var titleBlock: some View {
        VStack(spacing: 10) {
            Text("Welcome to KMFlow Agent")
                .font(.title2)
                .fontWeight(.semibold)
                .multilineTextAlignment(.center)

            Text(
                "KMFlow is a process mining agent that observes your work patterns to help optimize business processes. It was deployed as part of a consulting engagement."
            )
            .font(.body)
            .foregroundColor(.secondary)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Three capability bullets — what the agent captures.
    private var featureBullets: some View {
        VStack(alignment: .leading, spacing: 14) {
            FeatureBullet(
                symbol: "arrow.triangle.swap",
                text: "Observes application switches and window focus changes"
            )
            FeatureBullet(
                symbol: "keyboard",
                text: "Counts keyboard and mouse interactions (not content)"
            )
            FeatureBullet(
                symbol: "lock.shield.fill",
                text: "All data is encrypted and PII is automatically redacted"
            )
        }
        .padding(.horizontal, 8)
    }

    /// Consent prerequisite notice shown at the bottom of the welcome screen.
    private var footerNotice: some View {
        Text("Your explicit consent is required before any data collection begins.")
            .font(.footnote)
            .foregroundColor(.secondary)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.accentColor.opacity(0.08))
            )
    }
}

// MARK: - Helper: FeatureBullet

/// A single icon + text row used to describe an agent capability.
private struct FeatureBullet: View {
    let symbol: String
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol)
                .frame(width: 20, height: 20)
                .foregroundStyle(.tint)
                .symbolRenderingMode(.hierarchical)

            Text(text)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

// MARK: - Preview

#if DEBUG
struct WelcomeView_Previews: PreviewProvider {
    static var previews: some View {
        WelcomeView()
            .padding(24)
            .frame(width: 552)
    }
}
#endif
