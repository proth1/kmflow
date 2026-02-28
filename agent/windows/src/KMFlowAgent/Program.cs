// KMFlow Task Mining Agent for Windows — Entry Point
//
// Initializes capture subsystems, connects to the Python intelligence layer
// via named pipe, and runs until shutdown is requested.

using KMFlowAgent.Capture;
using KMFlowAgent.IPC;
using KMFlowAgent.PII;
using KMFlowAgent.Utilities;

namespace KMFlowAgent;

public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        AgentLogger.Info("KMFlow Agent starting");

        var dataDir = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var agentDir = Path.Combine(dataDir, "KMFlowAgent");
        Directory.CreateDirectory(agentDir);

        AgentLogger.EnableFileLogging(Path.Combine(agentDir, "agent.log"));

        using var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) =>
        {
            e.Cancel = true;
            cts.Cancel();
        };

        try
        {
            // Initialize components
            var pipeClient = new NamedPipeClient();
            var processIdentifier = new ProcessIdentifier();
            var contextFilter = new CaptureContextFilter();

            // Connect to Python layer
            AgentLogger.Info("Connecting to Python intelligence layer...");
            await pipeClient.ConnectAsync(cts.Token);
            AgentLogger.Info("Connected to Python layer");

            // Start capture
            using var captureManager = new CaptureStateManager(
                pipeClient, contextFilter, processIdentifier);

            captureManager.Start();
            AgentLogger.Info("Capture started");

            // Run until cancellation
            try
            {
                await Task.Delay(Timeout.Infinite, cts.Token);
            }
            catch (OperationCanceledException)
            {
                // Expected on shutdown
            }

            captureManager.Stop();
            AgentLogger.Info($"Agent stopped. Total events captured: {captureManager.EventCount}");

            await pipeClient.DisposeAsync();
            return 0;
        }
        catch (Exception ex)
        {
            AgentLogger.Error("Fatal error", ex);
            return 1;
        }
        finally
        {
            AgentLogger.Shutdown();
        }
    }
}
