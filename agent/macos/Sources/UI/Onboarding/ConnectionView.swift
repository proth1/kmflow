/// Step 4 — Backend URL entry and health-check verification.
///
/// The user enters the KMFlow backend base URL and taps "Test Connection".
/// The view performs an HTTP GET to `{url}/api/v1/health` and displays the
/// result inline. The wizard cannot advance until a test passes.

import SwiftUI

/// Connection status for the health-check request.
private enum ConnectionStatus: Equatable {
    case untested
    case testing
    case success
    case failed(String)
}

/// The backend connection step of the onboarding wizard.
///
/// Uses `URLSession.shared` for the health check. The connection test result
/// is surfaced inline and is mirrored into `OnboardingState.connectionTestPassed`.
public struct ConnectionView: View {

    // MARK: - Dependencies

    @ObservedObject private var state: OnboardingState

    // MARK: - Private State

    @State private var connectionStatus: ConnectionStatus = .untested
    @State private var testTask: Task<Void, Never>? = nil

    // MARK: - Initialiser

    /// - Parameter state: The shared wizard state.
    public init(state: OnboardingState) {
        self.state = state
    }

    // MARK: - Body

    public var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            headerSection
            urlInputSection
            connectionStatusSection
            Divider()
            mtlsSection
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Sub-views

    /// Explanatory header.
    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Backend Connection")
                .font(.headline)

            Text(
                "Enter the base URL of the KMFlow backend that will receive activity data from this agent. The URL must be reachable from this machine."
            )
            .font(.body)
            .foregroundColor(.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// URL text field and Test Connection button.
    private var urlInputSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Backend URL")
                .font(.subheadline)
                .fontWeight(.medium)

            HStack(spacing: 10) {
                TextField("https://api.kmflow.example.com", text: $state.backendURL)
                    .textFieldStyle(.roundedBorder)
                    .disableAutocorrection(true)
                    .onChange(of: state.backendURL) { _ in
                        // Reset test result when the URL is edited.
                        resetConnectionStatus()
                    }

                Button(action: runConnectionTest) {
                    Label("Test Connection", systemImage: "network")
                }
                .buttonStyle(.bordered)
                .disabled(
                    state.backendURL.trimmingCharacters(in: .whitespaces).isEmpty
                    || connectionStatus == .testing
                )
            }
        }
    }

    /// Inline status display below the URL row.
    private var connectionStatusSection: some View {
        Group {
            switch connectionStatus {
            case .untested:
                HStack(spacing: 6) {
                    Image(systemName: "circle.dashed")
                        .foregroundColor(.secondary)
                    Text("Not tested yet")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                }

            case .testing:
                HStack(spacing: 8) {
                    ProgressView()
                        .scaleEffect(0.75)
                    Text("Testing connection…")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                }

            case .success:
                HStack(spacing: 6) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(.green)
                    Text("Connection successful")
                        .font(.footnote)
                        .foregroundColor(.green)
                }
                .transition(.opacity)

            case .failed(let message):
                HStack(alignment: .top, spacing: 6) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.red)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Connection failed")
                            .font(.footnote)
                            .fontWeight(.medium)
                            .foregroundColor(.red)
                        Text(message)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: connectionStatus)
    }

    /// Placeholder mTLS section — disabled for this release.
    private var mtlsSection: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "certificate.fill")
                .foregroundColor(.secondary)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 4) {
                Text("Client Certificate (mTLS)")
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .foregroundColor(.secondary)

                Text("mTLS enrollment is available in a future release.")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Button("Enroll Client Certificate…") {}
                    .buttonStyle(.bordered)
                    .disabled(true)
                    .padding(.top, 4)
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color(NSColor.controlBackgroundColor).opacity(0.5))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.secondary.opacity(0.2), lineWidth: 1)
        )
    }

    // MARK: - Actions

    /// Resets the connection status and clears the `connectionTestPassed` flag.
    private func resetConnectionStatus() {
        testTask?.cancel()
        testTask = nil
        connectionStatus = .untested
        state.connectionTestPassed = false
    }

    /// Performs `GET {backendURL}/api/v1/health` and updates state accordingly.
    private func runConnectionTest() {
        testTask?.cancel()
        connectionStatus = .testing
        state.connectionTestPassed = false

        let rawURL = state.backendURL.trimmingCharacters(in: .whitespaces)
        testTask = Task {
            do {
                let result = try await performHealthCheck(baseURL: rawURL)
                guard !Task.isCancelled else { return }
                connectionStatus = .success
                state.connectionTestPassed = result
            } catch {
                guard !Task.isCancelled else { return }
                connectionStatus = .failed(error.localizedDescription)
                state.connectionTestPassed = false
            }
        }
    }

    /// Sends a GET request to `{baseURL}/api/v1/health` and returns `true` on 2xx.
    ///
    /// - Parameter baseURL: The raw string entered by the user.
    /// - Throws: `URLError` if the request fails or the URL is malformed.
    private func performHealthCheck(baseURL: String) async throws -> Bool {
        var urlString = baseURL
        // Remove trailing slash to avoid double-slash in path.
        if urlString.hasSuffix("/") {
            urlString.removeLast()
        }
        urlString += "/api/v1/health"

        guard let url = URL(string: urlString) else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url, timeoutInterval: 10)
        request.httpMethod = "GET"

        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        return (200...299).contains(http.statusCode)
    }
}

// MARK: - Preview

#if DEBUG
struct ConnectionView_Previews: PreviewProvider {
    static var previews: some View {
        ConnectionView(state: OnboardingState())
            .padding(24)
            .frame(width: 552)
    }
}
#endif
