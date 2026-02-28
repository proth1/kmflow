// Named pipe client for sending capture events to the Python intelligence layer.
//
// Connects to \\.\pipe\KMFlowAgent and writes newline-delimited JSON events.
// Includes reconnection with exponential backoff.
//
// This is the Windows equivalent of agent/macos/Sources/IPC/SocketClient.swift,
// using named pipes instead of Unix domain sockets.

using System.IO.Pipes;
using System.Text;
using System.Text.Json;

namespace KMFlowAgent.IPC;

/// <summary>
/// Sends CaptureEvents over a named pipe to the Python intelligence layer.
/// Thread-safe: serialization and pipe write are synchronized via SemaphoreSlim.
/// </summary>
public sealed class NamedPipeClient : IAsyncDisposable
{
    private const string DefaultPipeName = "KMFlowAgent";
    private const int MaxReconnectDelayMs = 30_000;
    private const int InitialReconnectDelayMs = 100;

    private readonly string _pipeName;
    private readonly SemaphoreSlim _writeLock = new(1, 1);
    private readonly CancellationTokenSource _disposeCts = new();

    private NamedPipeClientStream? _pipe;
    private StreamWriter? _writer;
    private long _eventsSent;
    private bool _disposed;

    public NamedPipeClient(string pipeName = DefaultPipeName)
    {
        _pipeName = pipeName;
    }

    /// <summary>Number of events successfully sent over the pipe.</summary>
    public long EventsSent => Interlocked.Read(ref _eventsSent);

    /// <summary>Whether the pipe is currently connected.</summary>
    public bool IsConnected => _pipe?.IsConnected == true;

    /// <summary>
    /// Connect to the named pipe server. Retries with exponential backoff
    /// until connected or cancellation is requested.
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

                _pipe = new NamedPipeClientStream(
                    serverName: ".",
                    pipeName: _pipeName,
                    direction: PipeDirection.Out,
                    options: PipeOptions.Asynchronous);

                await _pipe.ConnectAsync(5000, linked.Token).ConfigureAwait(false);

                _writer = new StreamWriter(_pipe, Encoding.UTF8, leaveOpen: true)
                {
                    AutoFlush = true,
                };

                delay = InitialReconnectDelayMs;
                return;
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

    /// <summary>
    /// Send a CaptureEvent as a single ndjson line over the named pipe.
    /// If the pipe is disconnected, attempts reconnection before sending.
    /// </summary>
    public async Task SendEventAsync(CaptureEvent captureEvent, CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        await _writeLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (_writer is null || _pipe?.IsConnected != true)
            {
                await ConnectAsync(cancellationToken).ConfigureAwait(false);
            }

            var json = JsonSerializer.Serialize(captureEvent, EventProtocolJsonContext.Default.CaptureEvent);
            await _writer!.WriteLineAsync(json.AsMemory(), cancellationToken).ConfigureAwait(false);

            Interlocked.Increment(ref _eventsSent);
        }
        catch (IOException)
        {
            // Pipe broken — next call will reconnect
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

        if (_pipe is not null)
        {
            await _pipe.DisposeAsync().ConfigureAwait(false);
            _pipe = null;
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_disposed) return;
        _disposed = true;

        _disposeCts.Cancel();
        _disposeCts.Dispose();

        await _writeLock.WaitAsync().ConfigureAwait(false);
        try
        {
            await DisconnectInternalAsync().ConfigureAwait(false);
        }
        finally
        {
            _writeLock.Release();
            _writeLock.Dispose();
        }
    }
}
