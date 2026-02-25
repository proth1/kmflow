/// Unix domain socket client for sending events to the Python intelligence layer.
///
/// Events are serialized as newline-delimited JSON (ndjson) over
/// `unix:///tmp/kmflow-agent.sock`.

import Foundation

public actor SocketClient {
    private let socketPath: String
    private var fileHandle: FileHandle?
    private let encoder: JSONEncoder
    private var isConnected = false

    public init(socketPath: String = "/tmp/kmflow-agent.sock") {
        self.socketPath = socketPath
        self.encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
    }

    /// Connect to the Python socket server.
    public func connect() throws {
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
                _ = pathBytes.withUnsafeBufferPointer { src in
                    memcpy(dest, src.baseAddress!, src.count)
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
        isConnected = true
    }

    /// Send a capture event over the socket as ndjson.
    public func send(_ event: CaptureEvent) throws {
        guard isConnected, let fh = fileHandle else {
            throw SocketError.notConnected
        }
        var data = try encoder.encode(event)
        data.append(0x0A) // newline
        fh.write(data)
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
