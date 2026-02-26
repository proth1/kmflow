/// Manages the Python intelligence subprocess lifecycle.
///
/// The Python layer runs as a child process of the Swift agent, connected
/// via Unix domain socket (managed by SocketClient in the IPC module).
/// PythonProcessManager handles launch, graceful shutdown, and crash recovery
/// with an exponential-backoff circuit breaker to cap restart attempts.

import Foundation
import os.log

/// Actor that owns and supervises the Python subprocess.
///
/// All state mutations run on the actor's executor, making them safe to call
/// from any Swift concurrency context without additional synchronisation.
public actor PythonProcessManager {

    // MARK: - Types

    /// Outcome returned by `stop()`.
    public enum StopOutcome: Sendable {
        case terminatedGracefully
        case killed
    }

    // MARK: - State

    private var process: Process?

    /// `true` while the manager considers itself in the running state.
    /// Set to `false` before sending SIGTERM so the termination handler
    /// does not trigger an automatic restart.
    private var isRunning: Bool = false

    // Circuit-breaker counters
    private var restartTimestamps: [Date] = []
    private let maxRestarts: Int = 5
    private let restartWindow: TimeInterval = 60

    // MARK: - Logger

    private let log = os.Logger(subsystem: "com.kmflow.agent", category: "PythonProcessManager")

    // MARK: - Lifecycle

    public init() {}

    /// Launch the `kmflow-python` shim bundled alongside this executable.
    ///
    /// The shim is expected to reside in the same directory as the agent
    /// binary (i.e. `Bundle.main.executableURL?.deletingLastPathComponent()`).
    /// Environment variables `KMFLOW_AGENT_ID` and `KMFLOW_BACKEND_URL` are
    /// forwarded from `UserDefaults` so the shim can connect to the backend.
    public func start() {
        guard !isRunning else {
            log.warning("start() called while already running — ignoring")
            return
        }

        // Locate the shim next to the agent binary.
        guard let executableDir = Bundle.main.executableURL?.deletingLastPathComponent() else {
            log.error("Cannot determine executable directory; Python subprocess will not start")
            return
        }
        let shimURL = executableDir.appendingPathComponent("kmflow-python")

        guard FileManager.default.isExecutableFile(atPath: shimURL.path) else {
            log.error("kmflow-python shim not found at \(shimURL.path, privacy: .public)")
            return
        }

        // Resources directory for the Python layer (working directory).
        let resourcesURL: URL
        if let bundleResources = Bundle.main.resourceURL {
            resourcesURL = bundleResources
        } else {
            resourcesURL = executableDir
        }

        // Build environment.
        var environment = ProcessInfo.processInfo.environment
        let defaults = UserDefaults.standard
        if let agentId = defaults.string(forKey: "KMFLOW_AGENT_ID"), !agentId.isEmpty {
            environment["KMFLOW_AGENT_ID"] = agentId
        }
        if let backendURL = defaults.string(forKey: "KMFLOW_BACKEND_URL"), !backendURL.isEmpty {
            // Validate URL scheme to prevent data exfiltration via rogue MDM config
            if let url = URL(string: backendURL),
               let scheme = url.scheme?.lowercased(),
               scheme == "https" || scheme == "http",
               url.host != nil {
                environment["KMFLOW_BACKEND_URL"] = backendURL
            } else {
                log.error("Invalid KMFLOW_BACKEND_URL — must be a valid http(s) URL with a host")
            }
        }

        let proc = Process()
        proc.executableURL = shimURL
        proc.environment = environment
        proc.currentDirectoryURL = resourcesURL
        proc.standardOutput = FileHandle.standardOutput
        proc.standardError = FileHandle.standardError

        // Capture self weakly; the Task below holds a strong reference to the
        // actor for the duration of the termination handler.
        proc.terminationHandler = { [weak self] finishedProcess in
            guard let self else { return }
            let code = finishedProcess.terminationStatus
            Task {
                await self.handleUnexpectedTermination(exitCode: code)
            }
        }

        do {
            try proc.run()
        } catch {
            log.error("Failed to launch Python subprocess: \(error.localizedDescription, privacy: .public)")
            return
        }

        self.process = proc
        self.isRunning = true
        log.info("Python subprocess started with PID \(proc.processIdentifier, privacy: .public)")
    }

    /// Gracefully stop the Python subprocess.
    ///
    /// Sends SIGTERM and waits up to 5 seconds; escalates to SIGKILL if the
    /// process has not exited by then.
    ///
    /// - Returns: Whether the process exited gracefully or was force-killed.
    @discardableResult
    public func stop() async -> StopOutcome {
        guard let proc = process, isRunning else {
            log.debug("stop() called but no process is running")
            return .terminatedGracefully
        }

        // Mark as intentionally stopped before sending signal so the
        // termination handler does not schedule a restart.
        isRunning = false

        log.info("Sending SIGTERM to Python subprocess (PID \(proc.processIdentifier, privacy: .public))")
        proc.terminate()

        // Poll for up to 5 seconds in 100 ms increments.
        let deadline = Date(timeIntervalSinceNow: 5)
        while proc.isRunning, Date() < deadline {
            try? await Task.sleep(nanoseconds: 100_000_000) // 100 ms
        }

        if proc.isRunning {
            log.warning("Python subprocess did not exit within 5 s — sending SIGKILL")
            kill(proc.processIdentifier, SIGKILL)
            process = nil
            return .killed
        }

        log.info("Python subprocess exited cleanly (code \(proc.terminationStatus, privacy: .public))")
        process = nil
        return .terminatedGracefully
    }

    /// Restart the Python subprocess after a brief delay.
    ///
    /// Called automatically by the termination handler on unexpected exits.
    /// A circuit breaker prevents more than `maxRestarts` attempts within
    /// `restartWindow` seconds; once tripped, the manager logs an error and
    /// stops retrying.
    public func restart() async {
        log.warning("Scheduling Python subprocess restart in 2 s…")
        try? await Task.sleep(nanoseconds: 2_000_000_000) // 2 s

        // Prune timestamps outside the sliding window.
        let windowStart = Date(timeIntervalSinceNow: -restartWindow)
        restartTimestamps = restartTimestamps.filter { $0 > windowStart }

        if restartTimestamps.count >= maxRestarts {
            log.error(
                "Circuit breaker tripped: \(self.maxRestarts, privacy: .public) restarts in \(Int(self.restartWindow), privacy: .public) s — giving up"
            )
            return
        }

        restartTimestamps.append(Date())
        log.warning(
            "Restarting Python subprocess (attempt \(self.restartTimestamps.count, privacy: .public) of \(self.maxRestarts, privacy: .public))"
        )
        start()
    }

    // MARK: - Private

    private func handleUnexpectedTermination(exitCode: Int32) async {
        guard isRunning else {
            // Intentional stop — do not restart.
            return
        }
        log.warning("Python subprocess exited unexpectedly with code \(exitCode, privacy: .public)")
        process = nil
        isRunning = false
        await restart()
    }
}
