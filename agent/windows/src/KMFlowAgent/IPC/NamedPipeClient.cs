// IPC client for sending capture events to the Python intelligence layer.
//
// Tries named pipe (\\.\pipe\KMFlowAgent) first, then falls back to TCP
// loopback (127.0.0.1:{port from ipc_port file}) for compatibility with
// Python asyncio which lacks native named pipe server support on Windows.
//
// Writes newline-delimited JSON events. Includes reconnection with
// exponential backoff.
//
// This is the Windows equivalent of agent/macos/Sources/IPC/SocketClient.swift.

using System.IO.Pipes;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using KMFlowAgent.Utilities;

namespace KMFlowAgent.IPC;

/// <summary>
/// Sends CaptureEvents to the Python intelligence layer over named pipe
/// or TCP loopback. Thread-safe: writes synchronized via SemaphoreSlim.
/// </summary>
public sealed class NamedPipeClient : IAsyncDisposable
{
    private const string DefaultPipeName = "KMFlowAgent";
    private const string TcpFallbackHost = "127.0.0.1";
    private const int DefaultTcpFallbackPort = 19847;
    private const int MaxReconnectDelayMs = 30_000;
    private const int InitialReconnectDelayMs = 100;

    private readonly string _pipeName;
    private readonly SemaphoreSlim _writeLock = new(1, 1);
    private readonly CancellationTokenSource _disposeCts = new();

    private Stream? _stream;
    private StreamWriter? _writer;
    private TcpClient? _tcpClient;
    private long _eventsSent;
    private bool _disposed;
    private bool _usingTcpFallback;

    public NamedPipeClient(string pipeName = DefaultPipeName)
    {
        _pipeName = pipeName;
    }

    /// <summary>Number of events successfully sent.</summary>
    public long EventsSent => Interlocked.Read(ref _eventsSent);

    /// <summary>Whether the transport is currently connected.</summary>
    public bool IsConnected
    {
        get
        {
            if (_usingTcpFallback)
                return _tcpClient?.Connected == true;
            return _stream is NamedPipeClientStream pipe && pipe.IsConnected;
        }
    }

    /// <summary>
    /// Connect to the Python layer. Tries named pipe first, then falls back
    /// to TCP loopback. Retries with exponential backoff.
    /// </summary>
    public async Task ConnectAsync(CancellationToken cancellationToken = default)
    {
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken, _disposeCts.Token);

        var delay = InitialReconnectDelayMs;

        while (!linked.Token.IsCancellationRequested)
        {
            try
            {
                await DisconnectInternalAsync().ConfigureAwait(false);

                // Try named pipe first
                if (await TryConnectNamedPipeAsync(linked.Token).ConfigureAwait(false))
                {
                    AgentLogger.Info("Connected via named pipe");
                    delay = InitialReconnectDelayMs;
                    return;
                }

                // Fall back to TCP loopback
                if (await TryConnectTcpAsync(linked.Token).ConfigureAwait(false))
                {
                    AgentLogger.Info("Connected via TCP loopback");
                    delay = InitialReconnectDelayMs;
                    return;
                }

                // Neither succeeded — backoff and retry
                AgentLogger.Debug($"Connection failed, retrying in {delay}ms");
                await Task.Delay(delay, linked.Token).ConfigureAwait(false);
                delay = Math.Min(delay * 2, MaxReconnectDelayMs);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception)
            {
                await Task.Delay(delay, linked.Token).ConfigureAwait(false);
                delay = Math.Min(delay * 2, MaxReconnectDelayMs);
            }
        }

        linked.Token.ThrowIfCancellationRequested();
    }

    private async Task<bool> TryConnectNamedPipeAsync(CancellationToken ct)
    {
        try
        {
            var pipe = new NamedPipeClientStream(
                serverName: ".",
                pipeName: _pipeName,
                direction: PipeDirection.Out,
                options: PipeOptions.Asynchronous);

            await pipe.ConnectAsync(2000, ct).ConfigureAwait(false);

            _stream = pipe;
            _writer = new StreamWriter(pipe, Encoding.UTF8, leaveOpen: true)
            {
                AutoFlush = true,
            };
            _usingTcpFallback = false;
            return true;
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch
        {
            return false;
        }
    }

    private async Task<bool> TryConnectTcpAsync(CancellationToken ct)
    {
        try
        {
            var port = ReadTcpPortFromFile();
            var tcp = new TcpClient();
            await tcp.ConnectAsync(TcpFallbackHost, port, ct).ConfigureAwait(false);

            // Read the auth token from the ipc_port file and send as first line
            var authToken = ReadAuthTokenFromFile();
            var stream = tcp.GetStream();
            var writer = new StreamWriter(stream, Encoding.UTF8, leaveOpen: true)
            {
                AutoFlush = true,
            };

            if (authToken is not null)
            {
                await writer.WriteLineAsync(authToken.AsMemory(), ct).ConfigureAwait(false);
            }

            _tcpClient = tcp;
            _stream = stream;
            _writer = writer;
            _usingTcpFallback = true;
            return true;
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch
        {
            return false;
        }
    }

    private static int ReadTcpPortFromFile()
    {
        var dataDir = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var portFile = Path.Combine(dataDir, "KMFlowAgent", "ipc_port");
        if (File.Exists(portFile))
        {
            var content = File.ReadAllText(portFile).Trim();
            // Format: "port:token" or just "port"
            var parts = content.Split(':', 2);
            if (int.TryParse(parts[0], out var port))
                return port;
        }
        return DefaultTcpFallbackPort;
    }

    private static string? ReadAuthTokenFromFile()
    {
        var dataDir = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var portFile = Path.Combine(dataDir, "KMFlowAgent", "ipc_port");
        if (File.Exists(portFile))
        {
            var content = File.ReadAllText(portFile).Trim();
            var parts = content.Split(':', 2);
            if (parts.Length == 2)
                return parts[1];
        }
        return null;
    }

    /// <summary>
    /// Send a CaptureEvent as a single ndjson line.
    /// If disconnected, attempts reconnection before sending.
    /// </summary>
    public async Task SendEventAsync(CaptureEvent captureEvent, CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        await _writeLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (_writer is null || !IsConnected)
            {
                await ConnectAsync(cancellationToken).ConfigureAwait(false);
            }

            var json = JsonSerializer.Serialize(captureEvent, EventProtocolJsonContext.Default.CaptureEvent);
            await _writer!.WriteLineAsync(json.AsMemory(), cancellationToken).ConfigureAwait(false);

            Interlocked.Increment(ref _eventsSent);
        }
        catch (IOException)
        {
            await DisconnectInternalAsync().ConfigureAwait(false);
            throw;
        }
        finally
        {
            _writeLock.Release();
        }
    }

    /// <summary>
    /// Send multiple CaptureEvents in a batch. Each event is a separate ndjson line.
    /// </summary>
    public async Task SendEventsAsync(
        IEnumerable<CaptureEvent> events,
        CancellationToken cancellationToken = default)
    {
        foreach (var evt in events)
        {
            await SendEventAsync(evt, cancellationToken).ConfigureAwait(false);
        }
    }

    private async Task DisconnectInternalAsync()
    {
        if (_writer is not null)
        {
            await _writer.DisposeAsync().ConfigureAwait(false);
            _writer = null;
        }

        if (_stream is not null)
        {
            await _stream.DisposeAsync().ConfigureAwait(false);
            _stream = null;
        }

        if (_tcpClient is not null)
        {
            _tcpClient.Dispose();
            _tcpClient = null;
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_disposed) return;
        _disposed = true;

        _disposeCts.Cancel();
        _disposeCts.Dispose();

        var acquired = await _writeLock.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        try
        {
            await DisconnectInternalAsync().ConfigureAwait(false);
        }
        finally
        {
            if (acquired) _writeLock.Release();
            _writeLock.Dispose();
        }
    }
}
