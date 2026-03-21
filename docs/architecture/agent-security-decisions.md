# macOS Agent Security Decisions

## App Sandbox: Disabled

The KMFlow Desktop Agent intentionally does **not** enable the macOS App Sandbox entitlement. This is a deliberate architectural decision, not an oversight.

### Why App Sandbox is incompatible

The agent's core functionality requires:

1. **Accessibility API access** — Observing application switches, window titles, and input activity across all apps. App Sandbox restricts cross-application observation.

2. **Screen capture** — The VCE (Visual Context Event) pipeline captures screen content for OCR and classification. Sandboxed apps cannot use `CGWindowListCreateImage` without explicit user-granted exceptions that defeat the purpose.

3. **Unix domain sockets** — The Swift → Python IPC channel uses a Unix domain socket in `~/Library/Application Support/KMFlowAgent/`. Sandbox file access restrictions would require a container-specific path, breaking the IPC contract.

4. **Keychain access** — The agent stores JWT tokens and encryption keys in the macOS Keychain via the `security` CLI. Sandbox keychain access groups add complexity without security benefit for a non-App Store distributed app.

5. **Process spawning** — The Swift app embeds and launches a Python 3.12 runtime as a child process. App Sandbox restricts subprocess execution.

### Compensating controls

The absence of App Sandbox is compensated by:

| Control | Description |
|---------|-------------|
| **Hardened Runtime** | Enabled via `--options runtime` in codesigning. Prevents code injection, restricts debugging, enforces library validation. |
| **Notarization** | Apple's notarization service scans for malware before distribution. Required for Gatekeeper approval. |
| **Code signing** | All binaries, frameworks, and dylibs are signed with a Developer ID Application certificate. Ad-hoc signing is rejected for release builds. |
| **User consent model** | Captures only start after explicit user consent. Consent is stored in Keychain with HMAC tamper detection. Granular consent per capture type (v2). |
| **Encrypted buffer** | All event data is AES-256-GCM encrypted at rest in the SQLite buffer. Key derived via HKDF. |
| **Socket permissions** | IPC socket is created with 0600 permissions. Peer UID verified via `getsockopt(LOCAL_PEERCRED)`. |
| **HTTPS enforcement** | Non-localhost HTTP connections are rejected. mTLS client certificates supported. |
| **PII filtering** | L2 filter redacts PII before buffering. VCE pipeline redacts OCR text before persistence. Image bytes are never written to disk. |
| **Transparency log** | All captured event metadata is visible to the user via the Transparency Log UI. |
| **GDPR data purge** | Right to Be Forgotten: full local + remote data purge on consent revocation. |

### Distribution model

The agent is distributed outside the Mac App Store via:
- Direct download (DMG or PKG installer)
- MDM deployment (Intune, JAMF, Mosyle)

App Sandbox is an App Store requirement, not a technical requirement for non-App Store distribution. Apple's documentation confirms that Hardened Runtime + Notarization is the correct security posture for Developer ID-distributed apps.
