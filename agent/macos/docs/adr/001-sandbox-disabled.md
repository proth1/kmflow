# ADR 001: App Sandbox Disabled

**Status**: Accepted
**Date**: 2026-02-26
**Context**: macOS Task Mining Agent entitlements

## Decision

The KMFlow macOS Task Mining Agent runs with `com.apple.security.app-sandbox` set to `false`.

## Context

The agent requires macOS Accessibility APIs (`AXUIElement`, `CGEventTap`) to observe application switches, window titles, and input activity metrics. These APIs are incompatible with the App Sandbox:

1. **Accessibility API access** — The agent uses `AXUIElementCopyAttributeValue` to read window titles from other applications. Sandboxed apps cannot access the AX APIs of other processes.

2. **CGEventTap** — Input monitoring (`CGEventTapCreate`) requires posting to the HID event stream, which the sandbox prohibits.

3. **Unix domain socket IPC** — The embedded Python intelligence layer communicates over a Unix socket in `~/Library/Application Support/KMFlowAgent/`. While the sandbox allows limited file access, the dynamic socket path and peer credential verification are simpler outside the sandbox.

4. **Python.framework embedding** — The agent embeds a relocatable CPython 3.12 framework that loads `.dylib`/`.so` files at runtime from `Contents/Frameworks/`. The sandbox's library validation would reject unsigned or differently-signed dynamic libraries.

## Consequences

- The agent cannot be distributed through the Mac App Store (which requires sandbox).
- Distribution is via Developer ID signing + notarization (direct download, MDM, or PKG installer).
- Defense-in-depth is provided by: Hardened Runtime (`--options runtime`), notarization, entitlement minimization (only `network.client` and `accessibility` are granted), and TCC/PPPC enforcement for Accessibility access.
- The `files.user-selected.read-write` entitlement was removed (no effect outside sandbox).

## Alternatives Considered

1. **Enable sandbox with temporary exceptions** — Apple's temporary exception entitlements (`com.apple.security.temporary-exception.*`) are deprecated and rejected during notarization for new apps.

2. **Split into sandboxed UI + unsandboxed helper** — This would add significant complexity (XPC service, separate signing, two binaries) for marginal security benefit, since the helper would still need full Accessibility access.

## References

- Apple: [App Sandbox Design Guide](https://developer.apple.com/documentation/security/app-sandbox)
- Apple: [Hardened Runtime](https://developer.apple.com/documentation/security/hardened-runtime)
- Entitlements file: `agent/macos/Resources/KMFlowAgent.entitlements`
