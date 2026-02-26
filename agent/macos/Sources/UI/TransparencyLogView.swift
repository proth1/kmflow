/// Read-only SwiftUI view that shows recent captured events from the
/// local SQLite buffer, with event-type filtering and PII redaction badges.
///
/// This view is the primary transparency surface for the end user.
/// It deliberately offers no editing or deletion controls — the capture
/// buffer is managed solely by the Python layer.

import SwiftUI

// MARK: - TransparencyLogView

/// Window-level view for the KMFlow Transparency Log.
///
/// Present this view in a dedicated `Window` scene so it appears as a
/// separate, resizable macOS window independent of the menu bar popover.
///
/// ```swift
/// Window("KMFlow Transparency Log", id: "transparency-log") {
///     TransparencyLogView()
/// }
/// ```
public struct TransparencyLogView: View {

    @StateObject private var controller = TransparencyLogController()

    /// The event type selected in the filter picker, or `nil` for "All".
    @State private var selectedEventType: String? = nil

    // MARK: - Body

    public var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()
            eventList
            Divider()
            footer
        }
        .frame(minWidth: 680, minHeight: 400)
        .navigationTitle("KMFlow Transparency Log")
        .onAppear { controller.startRefreshing() }
        .onDisappear { controller.stopRefreshing() }
    }

    // MARK: - Sub-views

    private var toolbar: some View {
        HStack(spacing: 12) {
            Text("Filter by type:")
                .font(.subheadline)
                .foregroundStyle(.secondary)

            Picker("Event Type", selection: $selectedEventType) {
                Text("All").tag(String?.none)
                ForEach(uniqueEventTypes, id: \.self) { type in
                    Text(displayName(for: type)).tag(String?.some(type))
                }
            }
            .pickerStyle(.menu)
            .frame(width: 200)

            Spacer()

            Text(eventCountLabel)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private var eventList: some View {
        Group {
            if filteredEvents.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "list.bullet.clipboard")
                        .font(.largeTitle)
                        .foregroundStyle(.tertiary)
                    Text(controller.statusMessage.isEmpty
                         ? "No events match the current filter."
                         : controller.statusMessage)
                        .font(.body)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(filteredEvents) { event in
                    EventRow(event: event)
                }
                .listStyle(.plain)
            }
        }
    }

    private var footer: some View {
        HStack {
            Image(systemName: "lock.shield")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text("All data shown is local to this device. PII patterns have been redacted.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
        .background(.bar)
    }

    // MARK: - Derived data

    private var filteredEvents: [TransparencyEvent] {
        guard let filter = selectedEventType else {
            return Array(controller.events.prefix(200))
        }
        return controller.events.filter { $0.eventType == filter }.prefix(200).map { $0 }
    }

    private var uniqueEventTypes: [String] {
        var seen = Set<String>()
        return controller.events.compactMap { event in
            seen.insert(event.eventType).inserted ? event.eventType : nil
        }.sorted()
    }

    private var eventCountLabel: String {
        let shown = filteredEvents.count
        let total = controller.events.count
        if selectedEventType == nil {
            return "\(total) event\(total == 1 ? "" : "s")"
        }
        return "\(shown) of \(total) event\(total == 1 ? "" : "s")"
    }

    // MARK: - Helpers

    /// Convert a raw `event_type` snake_case string into a human-friendly label.
    private func displayName(for rawType: String) -> String {
        rawType
            .replacingOccurrences(of: "_", with: " ")
            .capitalized
    }
}

// MARK: - EventRow

/// One row in the transparency log list.
private struct EventRow: View {
    let event: TransparencyEvent

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .none
        f.timeStyle = .medium
        return f
    }()

    private static let dateTimeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .short
        f.timeStyle = .medium
        return f
    }()

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            // Event type icon
            Image(systemName: iconName(for: event.eventType))
                .frame(width: 20)
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(displayName(for: event.eventType))
                        .font(.subheadline)
                        .fontWeight(.medium)

                    if event.piiRedacted {
                        PIIBadge()
                    }
                }

                HStack(spacing: 8) {
                    if let app = event.appName, !app.isEmpty {
                        Label(app, systemImage: "app.badge")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    if let title = event.windowTitle, !title.isEmpty {
                        Text(title)
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                    }
                }
            }

            Spacer()

            // Timestamp
            VStack(alignment: .trailing, spacing: 1) {
                Text(EventRow.timeFormatter.string(from: event.timestamp))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                Text(EventRow.dateTimeFormatter.string(from: event.timestamp).components(separatedBy: ",").first ?? "")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel)
    }

    // MARK: - Helpers

    private func displayName(for rawType: String) -> String {
        rawType.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private func iconName(for eventType: String) -> String {
        switch eventType {
        case "app_switch":             return "arrow.left.arrow.right.square"
        case "window_focus":           return "macwindow"
        case "mouse_click",
             "mouse_double_click":     return "cursorarrow.click"
        case "mouse_drag":             return "cursorarrow.motionlines"
        case "keyboard_action":        return "keyboard"
        case "keyboard_shortcut":      return "command.square"
        case "copy_paste":             return "doc.on.clipboard"
        case "scroll":                 return "scroll"
        case "tab_switch":             return "menubar.arrow.up.rectangle"
        case "file_open":              return "doc"
        case "file_save":              return "doc.badge.ellipsis"
        case "url_navigation":         return "safari"
        case "screen_capture":         return "camera.viewfinder"
        case "ui_element_interaction": return "hand.point.up.left"
        case "idle_start":             return "moon"
        case "idle_end":               return "sun.max"
        default:                       return "circle.dotted"
        }
    }

    private var accessibilityLabel: String {
        var parts: [String] = []
        parts.append(displayName(for: event.eventType))
        if let app = event.appName { parts.append(app) }
        if event.piiRedacted { parts.append("PII redacted") }
        parts.append(EventRow.dateTimeFormatter.string(from: event.timestamp))
        return parts.joined(separator: ", ")
    }
}

// MARK: - PIIBadge

/// Small inline badge indicating that PII was redacted from this event.
private struct PIIBadge: View {
    var body: some View {
        Label("PII redacted", systemImage: "eye.slash")
            .font(.caption2.weight(.semibold))
            .foregroundStyle(.orange)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(
                RoundedRectangle(cornerRadius: 4)
                    .fill(.orange.opacity(0.12))
            )
            .accessibilityLabel("PII patterns have been redacted")
    }
}

// MARK: - Preview

#if DEBUG
struct TransparencyLogView_Previews: PreviewProvider {
    static var previews: some View {
        TransparencyLogView()
            .frame(width: 780, height: 520)
    }
}
#endif
