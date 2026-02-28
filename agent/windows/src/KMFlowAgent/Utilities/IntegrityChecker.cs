// Self-integrity verification for the agent binary.
//
// Verifies Authenticode signatures and detects tampering at startup.
// On failure, the agent refuses to start and logs the error.
//
// Mirrors the pattern in agent/macos/Sources/Utilities/IntegrityChecker.swift
// (which checks code signing via SecStaticCode).

using System.Runtime.InteropServices;
using KMFlowAgent.Utilities;

namespace KMFlowAgent.Utilities;

/// <summary>
/// Verifies that the agent binary has a valid Authenticode signature.
/// Called at startup to detect tampering. In development builds without
/// signatures, this check can be bypassed via configuration.
/// </summary>
public static class IntegrityChecker
{
    /// <summary>
    /// Verify the Authenticode signature of the running executable.
    /// Returns true if valid or if running unsigned in development mode.
    /// </summary>
    public static bool VerifyBinarySignature(bool requireSignature = false)
    {
        var exePath = Environment.ProcessPath;
        if (string.IsNullOrEmpty(exePath))
        {
            AgentLogger.Warn("IntegrityChecker: Cannot determine process path");
            return !requireSignature;
        }

        return VerifyFileSignature(exePath, requireSignature);
    }

    /// <summary>
    /// Verify the Authenticode signature of a specific file.
    /// Uses WinVerifyTrust to check the cryptographic signature chain.
    /// </summary>
    public static bool VerifyFileSignature(string filePath, bool requireSignature = false)
    {
        if (!File.Exists(filePath))
        {
            AgentLogger.Error($"IntegrityChecker: File not found: {filePath}");
            return false;
        }

        try
        {
            var result = WinVerifyTrust(filePath);

            switch (result)
            {
                case WinVerifyTrustResult.Success:
                    AgentLogger.Debug($"IntegrityChecker: Valid signature on {Path.GetFileName(filePath)}");
                    return true;

                case WinVerifyTrustResult.SubjectNotTrusted:
                case WinVerifyTrustResult.ProviderUnknown:
                case WinVerifyTrustResult.ActionUnknown:
                case WinVerifyTrustResult.SubjectFormUnknown:
                    // File is not signed
                    if (requireSignature)
                    {
                        AgentLogger.Error($"IntegrityChecker: No valid signature on {Path.GetFileName(filePath)} (result: {result})");
                        return false;
                    }
                    AgentLogger.Info($"IntegrityChecker: Unsigned binary (development mode)");
                    return true;

                case WinVerifyTrustResult.FileNotSigned:
                    if (requireSignature)
                    {
                        AgentLogger.Error($"IntegrityChecker: File not signed: {Path.GetFileName(filePath)}");
                        return false;
                    }
                    AgentLogger.Info("IntegrityChecker: Unsigned binary (development mode)");
                    return true;

                default:
                    AgentLogger.Error($"IntegrityChecker: Verification failed (0x{(uint)result:X8}) for {Path.GetFileName(filePath)}");
                    return false;
            }
        }
        catch (Exception ex)
        {
            AgentLogger.Error($"IntegrityChecker: Exception during verification: {ex.Message}");
            return !requireSignature;
        }
    }

    /// <summary>
    /// Verify the SHA-256 hash of a file against an expected value.
    /// Used for verifying companion files (e.g., HookDll).
    /// </summary>
    public static bool VerifyFileHash(string filePath, string expectedSha256Hex)
    {
        if (!File.Exists(filePath))
        {
            AgentLogger.Error($"IntegrityChecker: File not found for hash check: {filePath}");
            return false;
        }

        try
        {
            using var sha256 = System.Security.Cryptography.SHA256.Create();
            using var stream = File.OpenRead(filePath);
            var hash = sha256.ComputeHash(stream);
            var actualHex = Convert.ToHexString(hash);

            if (string.Equals(actualHex, expectedSha256Hex, StringComparison.OrdinalIgnoreCase))
            {
                AgentLogger.Debug($"IntegrityChecker: Hash verified for {Path.GetFileName(filePath)}");
                return true;
            }

            AgentLogger.Error($"IntegrityChecker: Hash mismatch for {Path.GetFileName(filePath)}");
            return false;
        }
        catch (Exception ex)
        {
            AgentLogger.Error($"IntegrityChecker: Hash check failed: {ex.Message}");
            return false;
        }
    }

    // WinVerifyTrust via P/Invoke
    private static WinVerifyTrustResult WinVerifyTrust(string filePath)
    {
        var fileInfo = new WINTRUST_FILE_INFO
        {
            cbStruct = (uint)Marshal.SizeOf<WINTRUST_FILE_INFO>(),
            pcwszFilePath = filePath,
        };

        var trustData = new WINTRUST_DATA
        {
            cbStruct = (uint)Marshal.SizeOf<WINTRUST_DATA>(),
            dwUIChoice = 2, // WTD_UI_NONE
            fdwRevocationChecks = 0, // WTD_REVOKE_NONE
            dwUnionChoice = 1, // WTD_CHOICE_FILE
            dwStateAction = 0, // WTD_STATEACTION_IGNORE
            dwProvFlags = 0x00000010, // WTD_CACHE_ONLY_URL_RETRIEVAL
        };

        var fileInfoPtr = Marshal.AllocHGlobal(Marshal.SizeOf<WINTRUST_FILE_INFO>());
        try
        {
            Marshal.StructureToPtr(fileInfo, fileInfoPtr, false);
            trustData.pUnionData = fileInfoPtr;

            var actionId = new Guid("00AAC56B-CD44-11d0-8CC2-00C04FC295EE"); // WINTRUST_ACTION_GENERIC_VERIFY_V2
            var result = WinVerifyTrustNative(IntPtr.Zero, ref actionId, ref trustData);
            return (WinVerifyTrustResult)result;
        }
        finally
        {
            Marshal.FreeHGlobal(fileInfoPtr);
        }
    }

    [DllImport("wintrust.dll", EntryPoint = "WinVerifyTrust", CharSet = CharSet.Unicode)]
    private static extern int WinVerifyTrustNative(IntPtr hwnd, ref Guid pgActionID, ref WINTRUST_DATA pWVTData);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WINTRUST_FILE_INFO
    {
        public uint cbStruct;
        [MarshalAs(UnmanagedType.LPWStr)]
        public string pcwszFilePath;
        public IntPtr hFile;
        public IntPtr pgKnownSubject;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct WINTRUST_DATA
    {
        public uint cbStruct;
        public IntPtr pPolicyCallbackData;
        public IntPtr pSIPClientData;
        public uint dwUIChoice;
        public uint fdwRevocationChecks;
        public uint dwUnionChoice;
        public IntPtr pUnionData;
        public uint dwStateAction;
        public IntPtr hWVTStateData;
        public IntPtr pwszURLReference;
        public uint dwProvFlags;
        public uint dwUIContext;
        public IntPtr pSignatureSettings;
    }

    private enum WinVerifyTrustResult : uint
    {
        Success = 0,
        ProviderUnknown = 0x800B0001,
        ActionUnknown = 0x800B0002,
        SubjectFormUnknown = 0x800B0003,
        SubjectNotTrusted = 0x800B0004,
        FileNotSigned = 0x800B0100,
        SubjectExplicitlyDistrusted = 0x800B0111,
        SignatureOrFileCorrupt = 0x80096010,
        SubjectCertExpired = 0x800B0101,
        SubjectCertRevoked = 0x800B010C,
    }
}
