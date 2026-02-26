/// Unix domain socket client for sending events to the Python intelligence layer.
///
/// Events are serialized as newline-delimited JSON (ndjson) over a
/// user-private Unix domain socket (0600 permissions).
///
/// Security measures:
/// - Socket path is validated against symlink attacks before connecting
/// - A shared secret handshake authenticates the client to the server
/// - The secret is stored in the macOS Keychain and shared with the Python layer

import Foundation

public actor SocketClient {
    /// Default socket path in user-private Application Support directory.
    public static let defaultSocketPath: String = {
        let home = NSHomeDirectory()
        return "\(home)/Library/Application Support/KMFlowAgent/agent.sock"
    }()

    private let socketPath: String
    private var fileHandle: FileHandle?
    private let encoder: JSONEncoder
    private var isConnected = false
    private let maxReconnectAttempts = 5
    private let baseReconnectDelay: TimeInterval = 1.0
    /// Shared secret for authenticating the IPC handshake.
    private let authToken: String?

    public init(socketPath: String = SocketClient.defaultSocketPath, authToken: String? = nil) {
        self.socketPath = socketPath
        self.authToken = authToken
        self.encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
    }

    /// Connect to the Python socket server.
    ///
    /// Validates the socket path is not a symlink (to prevent IPC hijacking),
    /// then performs a shared-secret handshake if an auth token is configured.
    public func connect() throws {
        // Symlink check: reject if the socket path is a symbolic link.
        // An attacker could replace the socket file with a symlink pointing
        // to their own server to intercept capture events.
        var statBuf = stat()
        if lstat(socketPath, &statBuf) == 0 {
            if (statBuf.st_mode & S_IFMT) == S_IFLNK {
                throw SocketError.connectionFailed("Socket path is a symlink — possible IPC hijack attempt: \(socketPath)")
            }
        }

        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else {
            throw SocketError.connectionFailed("Failed to create socket: \(errno)")
        }

        var addr = sockaddr_un()
        addr.sun_family = sa_family_t(AF_UNIX)
        let pathBytes = socketPath.utf8CString
        guard pathBytes.count <= MemoryLayout.size(ofValue: addr.sun_path) else {
            close(fd)
            throw SocketError.connectionFailed("Socket path too long")
        }
        withUnsafeMutablePointer(to: &addr.sun_path) { ptr in
            ptr.withMemoryRebound(to: CChar.self, capacity: pathBytes.count) { dest in
                for i in 0..<pathBytes.count {
                    dest[i] = pathBytes[i]
                }
            }
        }

        let addrLen = socklen_t(MemoryLayout<sockaddr_un>.size)
        let result = withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockPtr in
                Foundation.connect(fd, sockPtr, addrLen)
            }
        }
        guard result == 0 else {
            close(fd)
            throw SocketError.connectionFailed("connect() failed: \(errno)")
        }

        fileHandle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)

        // Perform auth handshake if token is configured.
        // Use JSONSerialization to avoid JSON injection via malformed tokens.
        if let token = authToken, let fh = fileHandle {
            let authDict: [String: String] = ["auth": token]
            guard let jsonData = try? JSONSerialization.data(withJSONObject: authDict),
                  let authData = String(data: jsonData, encoding: .utf8)?.appending("\n").data(using: .utf8)
            else {
                close(fd)
                fileHandle = nil
                throw SocketError.connectionFailed("Failed to encode auth token")
            }
            fh.write(authData)
        }

        isConnected = true
    }

    /// Send a capture event, reconnecting if needed.
    public func send(_ event: CaptureEvent) async throws {
        if !isConnected {
            try await reconnect()
        }
        guard let fh = fileHandle else {
            throw SocketError.notConnected
        }
        do {
            var data = try encoder.encode(event)
            data.append(0x0A) // newline
            fh.write(data)
        } catch {
            // Write failed — mark disconnected for next attempt
            isConnected = false
            fileHandle = nil
            throw error
        }
    }

    /// Attempt reconnection with exponential backoff.
    private func reconnect() async throws {
        for attempt in 0..<maxReconnectAttempts {
            do {
                try connect()
                return
            } catch {
                let delay = min(baseReconnectDelay * pow(2.0, Double(attempt)), 30.0)
                try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            }
        }
        throw SocketError.connectionFailed("Failed after \(maxReconnectAttempts) reconnect attempts")
    }

    /// Disconnect from the socket.
    public func disconnect() {
        fileHandle?.closeFile()
        fileHandle = nil
        isConnected = false
    }

    public enum SocketError: Error, LocalizedError {
        case connectionFailed(String)
        case notConnected

        public var errorDescription: String? {
            switch self {
            case .connectionFailed(let msg): return "Socket connection failed: \(msg)"
            case .notConnected: return "Socket not connected"
            }
        }
    }
}
