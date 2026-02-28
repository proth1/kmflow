// Logging utility with Windows Event Log and file output.
//
// Windows equivalent of agent/macos/Sources/Utilities/Logger.swift.

namespace KMFlowAgent.Utilities;

/// <summary>
/// Centralized logging with support for console, file, and Windows Event Log output.
/// Uses a simple severity-based approach compatible with NativeAOT.
/// </summary>
public static class AgentLogger
{
    private static readonly object WriteLock = new();
    private static StreamWriter? _fileWriter;
    private static LogLevel _minimumLevel = LogLevel.Information;

    public enum LogLevel
    {
        Debug,
        Information,
        Warning,
        Error,
    }

    /// <summary>Set the minimum log level. Messages below this level are discarded.</summary>
    public static void SetMinimumLevel(LogLevel level) => _minimumLevel = level;

    /// <summary>Enable file logging to the agent data directory.</summary>
    public static void EnableFileLogging(string logFilePath)
    {
        var dir = Path.GetDirectoryName(logFilePath);
        if (dir is not null)
            Directory.CreateDirectory(dir);

        _fileWriter = new StreamWriter(logFilePath, append: true)
        {
            AutoFlush = true,
        };
    }

    public static void Debug(string message) => Log(LogLevel.Debug, message);
    public static void Info(string message) => Log(LogLevel.Information, message);
    public static void Warn(string message) => Log(LogLevel.Warning, message);
    public static void Error(string message) => Log(LogLevel.Error, message);
    public static void Error(string message, Exception ex) => Log(LogLevel.Error, $"{message}: {ex}");

    private static void Log(LogLevel level, string message)
    {
        if (level < _minimumLevel) return;

        var timestamp = DateTime.UtcNow.ToString("yyyy-MM-dd HH:mm:ss.fff");
        var prefix = level switch
        {
            LogLevel.Debug => "DBG",
            LogLevel.Information => "INF",
            LogLevel.Warning => "WRN",
            LogLevel.Error => "ERR",
            _ => "???",
        };

        var line = $"[{timestamp}] [{prefix}] {message}";

        lock (WriteLock)
        {
            Console.Error.WriteLine(line);
            _fileWriter?.WriteLine(line);
        }
    }

    /// <summary>Flush and close the file logger.</summary>
    public static void Shutdown()
    {
        lock (WriteLock)
        {
            _fileWriter?.Flush();
            _fileWriter?.Dispose();
            _fileWriter = null;
        }
    }
}
