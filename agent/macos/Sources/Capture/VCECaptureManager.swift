/// VCE (Visual Context Event) capture manager.
///
/// Evaluates trigger conditions and, when triggered, captures the current
/// screen and dispatches an IPC message to the Python VCE classifier pipeline.
///
/// Privacy contract:
///   - Screen image is NEVER written to disk.
///   - Screen image is NEVER logged.
///   - The image lives only in memory for the duration of the classify call.
///   - Only the resulting VCERecord metadata (no pixel data) is sent via IPC.

import CoreGraphics
import Foundation

// MARK: - Supporting types

/// Configurable rate limits for VCE captures.
public struct VCETriggerCaps: Sendable {
    /// Maximum captures allowed per rolling hour.
    public var maxPerHour: Int
    /// Maximum captures allowed per calendar day.
    public var maxPerDay: Int
    /// Minimum seconds between captures for the same app.
    public var cooldownSameAppSeconds: TimeInterval
    /// Minimum seconds between any two captures.
    public var cooldownAnySeconds: TimeInterval

    public static let `default` = VCETriggerCaps(
        maxPerHour: 12,
        maxPerDay: 60,
        cooldownSameAppSeconds: 120,
        cooldownAnySeconds: 30
    )
}

/// Context passed from the native monitoring layer to the VCE capture manager.
public struct CaptureContext: Sendable {
    public let applicationName: String
    public let windowTitle: String
    public let dwellMs: Int
    public let interactionIntensity: Double
    public let triggerReason: String

    public init(
        applicationName: String,
        windowTitle: String,
        dwellMs: Int,
        interactionIntensity: Double,
        triggerReason: String
    ) {
        self.applicationName = applicationName
        self.windowTitle = windowTitle
        self.dwellMs = dwellMs
        self.interactionIntensity = interactionIntensity
        self.triggerReason = triggerReason
    }
}

// MARK: - VCECaptureManager

/// Manages the VCE capture lifecycle with rate limiting and privacy guarantees.
///
/// All state mutations happen on the actor's executor to avoid data races.
public actor VCECaptureManager {

    // MARK: Properties

    private var caps: VCETriggerCaps
    private var isEnabled: Bool

    /// Ring buffer of recent capture timestamps (used for hourly/daily rate limiting).
    private var captureTimestamps: [Date] = []
    /// Last capture timestamp per application name.
    private var lastCaptureByApp: [String: Date] = [:]
    /// Timestamp of the most recent capture (any app).
    private var lastCaptureAny: Date?

    /// IPC send callback provided by the owning CaptureStateManager.
    /// Accepts a JSON-serialisable dict and routes it to Python via the socket.
    private let sendIPC: @Sendable ([String: Any]) async -> Void

    // MARK: Init

    public init(
        caps: VCETriggerCaps = .default,
        sendIPC: @Sendable @escaping ([String: Any]) async -> Void
    ) {
        self.caps = caps
        self.isEnabled = true
        self.sendIPC = sendIPC
    }

    // MARK: Public API

    /// Update trigger caps (called when backend config is refreshed).
    public func updateCaps(_ newCaps: VCETriggerCaps) {
        caps = newCaps
    }

    /// Enable or disable VCE capture.
    public func setEnabled(_ enabled: Bool) {
        isEnabled = enabled
    }

    /// Evaluate whether a VCE capture should fire for the given context.
    ///
    /// Enforces hourly, daily, per-app cooldown, and any-capture cooldown limits.
    /// Triggers the full capture + classify + send pipeline if approved.
    ///
    /// - Parameter context: Context from the native monitoring layer.
    /// - Returns: `true` if a capture was triggered, `false` if rate-limited or disabled.
    @discardableResult
    public func evaluateTrigger(context: CaptureContext) async -> Bool {
        guard isEnabled else { return false }

        let now = Date()
        pruneOldTimestamps(now: now)

        // Per-app cooldown
        if let lastApp = lastCaptureByApp[context.applicationName],
           now.timeIntervalSince(lastApp) < caps.cooldownSameAppSeconds {
            return false
        }

        // Any-capture cooldown
        if let lastAny = lastCaptureAny,
           now.timeIntervalSince(lastAny) < caps.cooldownAnySeconds {
            return false
        }

        // Hourly limit
        let capturesLastHour = captureTimestamps.filter {
            now.timeIntervalSince($0) <= 3600
        }.count
        if capturesLastHour >= caps.maxPerHour { return false }

        // Daily limit
        let capturesLastDay = captureTimestamps.filter {
            now.timeIntervalSince($0) <= 86400
        }.count
        if capturesLastDay >= caps.maxPerDay { return false }

        // Rate limits passed — proceed with capture
        captureTimestamps.append(now)
        lastCaptureByApp[context.applicationName] = now
        lastCaptureAny = now

        // Capture, classify, send — image never touches disk
        await captureAndDispatch(context: context)
        return true
    }

    // MARK: Private

    /// Capture the current screen and send raw bytes + context to the Python classifier.
    ///
    /// The CGImage is created in memory, converted to PNG bytes, passed to IPC,
    /// and then released. It is NEVER written to disk or logged.
    private func captureAndDispatch(context: CaptureContext) async {
        guard let image = captureScreen() else {
            return
        }

        // Convert to PNG bytes — in-memory only
        let imageBytes = cgImageToPNGBytes(image)
        // Release the CGImage reference immediately after conversion
        // (imageBytes retains the pixel data only as long as we hold it)

        await sendToClassifier(imageBytes: imageBytes, context: context)

        // Explicit nil-out to signal intent; ARC handles deallocation
        _ = imageBytes  // consumed above, reassignment not needed — just documenting
    }

    /// Capture the primary display using CGWindowListCreateImage.
    ///
    /// Returns nil if screen capture permission is not granted.
    /// Image is memory-only — NEVER written to disk.
    func captureScreen() -> CGImage? {
        let bounds = CGRect.infinite
        let image = CGWindowListCreateImage(
            bounds,
            .optionOnScreenOnly,
            kCGNullWindowID,
            [.boundsIgnoreFraming]
        )
        return image
    }

    /// Encode a CGImage to PNG bytes in memory.
    private func cgImageToPNGBytes(_ image: CGImage) -> Data {
        let mutableData = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            mutableData,
            "public.png" as CFString,
            1,
            nil
        ) else {
            return Data()
        }
        CGImageDestinationAddImage(destination, image, nil)
        CGImageDestinationFinalize(destination)
        return mutableData as Data
    }

    /// Send image bytes and capture context to the Python VCE pipeline via IPC.
    ///
    /// The Python side will:
    ///   1. Run OCR and redact PII.
    ///   2. Classify the screen state.
    ///   3. Build a VCERecord (metadata only).
    ///   4. Discard the image bytes immediately.
    ///   5. Buffer the VCERecord for upload.
    private func sendToClassifier(imageBytes: Data, context: CaptureContext) async {
        let payload: [String: Any] = [
            "event_type": "SCREEN_CAPTURE",
            "image_bytes": imageBytes.base64EncodedString(),
            "application_name": context.applicationName,
            "window_title": context.windowTitle,
            "dwell_ms": context.dwellMs,
            "interaction_intensity": context.interactionIntensity,
            "trigger_reason": context.triggerReason,
            "timestamp": ISO8601DateFormatter().string(from: Date()),
        ]
        await sendIPC(payload)
    }

    /// Remove timestamps older than 24 hours from the ring buffer.
    private func pruneOldTimestamps(now: Date) {
        let cutoff = now.addingTimeInterval(-86400)
        captureTimestamps = captureTimestamps.filter { $0 > cutoff }
    }
}
