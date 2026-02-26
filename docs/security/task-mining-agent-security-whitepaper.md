# KMFlow Task Mining Agent — Security Whitepaper

**Document ID**: KMF-SEC-001
**Version**: 1.0
**Effective Date**: 2026-02-25
**Classification**: Confidential — For CISO Review
**Owner**: KMFlow Platform Security Team

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Data Flow](#3-data-flow)
4. [PII Protection Architecture](#4-pii-protection-architecture)
5. [Encryption](#5-encryption)
6. [Permission Model](#6-permission-model)
7. [Agent Lifecycle](#7-agent-lifecycle)
8. [Code Signing and Supply Chain](#8-code-signing-and-supply-chain)
9. [Data Retention and Deletion](#9-data-retention-and-deletion)
10. [Incident Response](#10-incident-response)
11. [Compliance Mapping](#11-compliance-mapping)

---

## 1. Executive Summary

The KMFlow Task Mining Agent is a macOS desktop agent deployed on consultant workstations to capture objective process-execution signals for business process mining engagements. It records the applications used, time spent per application, window context (titles), and aggregate keyboard and mouse interaction counts. It does **not** record the content of keystrokes, the content of screenshots, clipboard data, files accessed, or communications content.

The agent is designed with a defense-in-depth security model and was purpose-built for enterprise deployment under CISO review.

### What the Agent Captures

| Signal | Purpose | Retention on Device |
|--------|---------|---------------------|
| Application name + bundle ID | Activity segmentation | Until uploaded (FIFO, max 100 MB) |
| Window title (PII-scrubbed) | Task context | Until uploaded |
| App switch timestamps | Handoff and transition timing | Until uploaded |
| Keyboard/mouse event counts | Effort estimation (not content) | Until uploaded |
| Active/idle time intervals | Focus vs. context-switch analysis | Until uploaded |

### Key Security Controls

- **PII protection**: Two-layer on-device architecture prevents raw PII from leaving the endpoint. L1 (capture prevention) and L2 (regex scrubbing) operate on-device before data is written to local storage. Additional layers (L3 ML-based NER and L4 human quarantine review) are planned for a future phase and are not yet implemented.
- **Encryption at rest** *(planned)*: Local buffer database encryption with AES-256-GCM is planned; the current implementation stores data in plaintext SQLite. The encryption key infrastructure (macOS Keychain storage) is in place but not yet wired to the buffer.
- **Encryption in transit**: All backend communication uses TLS 1.3; mutual TLS (mTLS) is planned for the next phase.
- **Least privilege**: Agent requests only the macOS permissions required for its function (Accessibility). Full Disk Access, admin rights, and kernel extensions are not required and not requested.
- **Server-side control**: The agent polls a configuration endpoint at every heartbeat (default 5-minute interval). Revocation, configuration changes, and forced pause take effect within one heartbeat cycle.
- **Transparent to the employee**: The agent runs as a visible menu bar item and is disclosed to employees via an explicit consent flow at first launch.

### Compliance Posture

The agent architecture was designed to satisfy the technical controls required by SOC 2 Type II (Security and Availability TSCs), ISO/IEC 27001:2022, and GDPR Articles 25, 28, 32, and 35. Detailed mapping is provided in Section 11.

---

## 2. Architecture Overview

The agent uses a two-layer design to separate OS-level capture (which requires elevated macOS entitlements) from intelligence and transmission logic (which does not).

```
┌─────────────────────────────────────────────────────────────────────┐
│  TRUST BOUNDARY: macOS Endpoint (Consultant Laptop)                  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Layer 1: Swift Capture Process (com.kmflow.taskmining.cap) │    │
│  │                                                              │    │
│  │  • Menu bar app (LSUIElement, no Dock icon)                 │    │
│  │  • CGEventTap      → keyboard/mouse counts (NOT content)    │    │
│  │  • NSWorkspace     → application switch notifications       │    │
│  │  • AXUIElement     → frontmost window title (PII-filtered)  │    │
│  │  • L1 PII filter   → blocks password fields, private tabs   │    │
│  │                                                              │    │
│  │  Entitlements: Accessibility, Network (localhost only)      │    │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                              │ Unix domain socket (ndjson)            │
│                              │ ~/Library/Application Support/        │
│                              │   KMFlowAgent/agent.sock              │
│  ┌──────────────────────────▼───────────────────────────────────┐   │
│  │  Layer 2: Python Intelligence Process (com.kmflow.taskmining) │   │
│  │                                                               │   │
│  │  • IPC consumer (socket listener)                            │   │
│  │  • L2 PII regex scrubbing                                    │   │
│  │  • SQLite buffer (buffer.db) — encryption planned             │   │
│  │  • Batch assembler + gzip compressor                         │   │
│  │  • Upload manager (TLS 1.3, exponential backoff retry)       │   │
│  │  • Heartbeat poller (config pull + revocation check)         │   │
│  │                                                              │    │
│  │  Entitlements: Network (outbound only)                      │    │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                              │                                        │
└──────────────────────────────┼────────────────────────────────────── ┘
                               │ TLS 1.3 (mTLS Phase 2)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  TRUST BOUNDARY: KMFlow Backend (Cloud)                               │
│                                                                        │
│  POST /api/v1/taskmining/events    → Quarantine queue                 │
│  POST /api/v1/taskmining/heartbeat → Config + revocation signals      │
│  GET  /api/v1/taskmining/config/{agent_id} → Agent configuration      │
│                                                                        │
│  L3: ML-based NER residual PII scan (planned — not yet implemented)   │
│  L4: Human quarantine review (planned — not yet implemented)          │
└──────────────────────────────────────────────────────────────────────┘
```

### Separation of Concerns

The Swift capture process holds the macOS Accessibility entitlement (required for CGEventTap and AXUIElement). It has no network access to the internet — its only outbound channel is the local Unix domain socket. The Python intelligence process holds outbound network access but has no Accessibility entitlement and receives only pre-filtered, PII-scrubbed event records. This separation ensures that even if the Python process were compromised, the attacker would not gain access to raw keystroke-level data, password fields, or secure input contexts — because those signals are blocked at the Swift layer before they reach the socket.

---

## 3. Data Flow

The following describes the complete lifecycle of a single captured event.

### States and Transitions

```
[User Activity]
      │
      ▼
[L1 Filter — Swift]  ←─── blocks: password managers, private browsing,
      │                           password fields (isSecureText),
      │                           system-defined secure input contexts
      ▼
[CGEventTap / NSWorkspace / AXUIElement]
      │  (event type: app_switch | window_title | activity_counts)
      │  (format: ndjson line, unencrypted, localhost-only socket)
      ▼
[Unix Domain Socket: ~/Library/Application Support/KMFlowAgent/agent.sock]
      │
      ▼
[L2 Filter — Python]  ←─── regex scrubbing: SSN, email, phone, credit card
      │                     replaces matches with [PII_REDACTED]
      │
      ▼
[buffer.db — SQLite]  (DATA AT REST — encryption planned, currently plaintext)
      │  (100 MB FIFO cap; oldest batches pruned when cap reached)
      │
      ▼
[Batch Assembler]
      │  batches: up to 500 events or 60 seconds, whichever comes first
      │  compression: gzip
      │
      ▼
[TLS 1.3 Upload]  →  POST /api/v1/taskmining/events  (DATA IN TRANSIT — ENCRYPTED)
      │
      ▼
[Backend Quarantine Queue]
      │  events held, not visible to analytics
      │
      ▼
[L3: ML-based NER scan]  (future phase)
      │
      ▼
[L4: Human Quarantine Review]  ←── analyst reviews flagged records
      │
      ▼
[Analytics Layer]
```

### Data States Summary

| State | Location | Protection |
|-------|----------|------------|
| Capture buffer (pre-filter) | Swift process memory | Process isolation; never written to disk |
| IPC channel | Unix domain socket (localhost) | OS-enforced; no external network access |
| Local storage | `~/Library/Application Support/KMFlowAgent/buffer.db` | Plaintext SQLite (AES-256-GCM encryption planned) |
| In transit | HTTPS (TLS 1.3) to backend | TLS 1.3; mTLS Phase 2 |
| Quarantine (backend) | Backend database | Access-controlled; not visible to analytics |
| Analytics | Backend data warehouse | Role-based access, engagement-scoped |

---

## 4. PII Protection Architecture

The agent implements a two-layer on-device PII protection model (L1 and L2). Two additional backend layers (L3 and L4) are planned for a future phase and are **not yet implemented**.

### Layer 1 — Capture Prevention (Swift)

L1 prevents PII-sensitive contexts from generating events at all. No data is captured from these contexts — they are silently skipped.

| Mechanism | Implementation | What It Prevents |
|-----------|---------------|-----------------|
| Password field detection | `AXUIElement` attribute `AXIsPasswordField == true` | Password entry, PIN entry |
| Secure input context | `CGEventTapCreate` returns `nil` when secure input is active; agent detects and skips | System-enforced secure input (banking sites, 1Password entry mode) |
| Password manager detection | Bundle ID blocklist checked on every app-switch event | 1Password, LastPass, Bitwarden, Dashlane, Keychain dialogs |
| Private browsing detection | Browser bundle ID + window title prefix heuristics | Safari Private, Chrome Incognito, Firefox Private Window |

L1 is implemented in the Swift process, which is the only process with the Accessibility entitlement. L1 failures cannot be exploited by the Python process.

### Layer 2 — Regex Scrubbing (Swift + Python)

L2 applies regex patterns at two points: in the Swift process before writing to the socket, and again in the Python process after reading from the socket. The double application provides defense in depth.

The following patterns are applied. Each match is replaced with the token `[PII_REDACTED]`.

| PII Type | Regex Pattern |
|----------|--------------|
| US Social Security Number | `\b\d{3}-\d{2}-\d{4}\b` |
| Email address | `\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b` |
| US phone number | `\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b` |
| Credit card number (Luhn-valid) | `\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b` |
| UK National Insurance Number | `\b[A-Z]{2}\d{6}[A-D]\b` |
| IP address (RFC 1918) | `\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b` |
| Date of birth (common formats) | `\b(0?[1-9]|1[012])[\/\-](0?[1-9]|[12]\d|3[01])[\/\-](19|20)\d{2}\b` |

These patterns are applied to all string fields in every captured event (window titles, application names). Numeric event counts (keyboard/mouse counts) are not subject to regex scrubbing as they are aggregate integers, not strings.

### Layer 3 — ML-Based NER Scan (Backend) — *NOT YET IMPLEMENTED*

> **Status**: Planned for Phase 3. No code exists for this layer today.

After upload, an NLP named-entity recognition model will scan event records for residual PII that evaded regex (e.g., names embedded in window titles, non-standard formats). Flagged records will be routed to a quarantine queue and not admitted to analytics. This layer is planned for a future phase of the platform and is not yet implemented.

### Layer 4 — Human Quarantine Review — *NOT YET IMPLEMENTED*

> **Status**: Planned for a future phase. No backend code or review interface exists today.

In the planned design, all uploaded records will enter a quarantine queue before becoming visible to analytics. A trained data steward will review flagged records (from L3) and a statistical sample of non-flagged records. Records will be approved, redacted, or deleted. Only approved records will advance to the analytics layer.

---

## 5. Encryption

### Data at Rest — AES-256-GCM *(Planned — Not Yet Implemented)*

> **Status**: The local buffer database (`buffer.db`) currently stores captured events in **plaintext SQLite**. AES-256-GCM encryption is the planned target architecture. The Keychain infrastructure described below is in place for consent records but is not yet wired to the buffer encryption.

The planned encryption parameters are:

| Parameter | Planned Value | Current Status |
|-----------|-------|----------------|
| Algorithm | AES-256-GCM | **Not implemented** — buffer is plaintext |
| Key length | 256 bits (32 bytes) | Key generation code exists but is not used for buffer encryption |
| Nonce | 12 bytes, randomly generated per write operation | Not implemented |
| Authentication tag | 128 bits (16 bytes) | Not implemented |
| Key storage | macOS Keychain (kSecClassGenericPassword, `com.kmflow.taskmining`, access group `com.kmflow`) | Keychain helper exists and is used for consent records |
| Key derivation | 256-bit random key generated at first agent registration; never derived from password | Not implemented |
| Key rotation | Supported via server-side configuration push; triggers local re-encryption of buffer | Not implemented |

Once implemented, the Keychain item will be protected with `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, meaning:

- The key will be available after the first unlock following a reboot.
- The key will **not** be available when the device is locked (screen lock).
- The key will **not** be exportable from the device — it cannot be copied to another machine.
- Physical access to the disk without the device's Keychain unlock credentials will not expose the key.

### Data in Transit — TLS 1.3

All communication between the agent and the KMFlow backend uses HTTPS with TLS 1.3.

| Parameter | Value |
|-----------|-------|
| Protocol | TLS 1.3 (minimum; TLS 1.2 rejected) |
| Cipher suites | TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256 |
| Certificate validation | Standard X.509 chain validation + hostname verification; no certificate pinning (Phase 1) |
| Mutual TLS (mTLS) | Planned Phase 2: client certificate issued per agent registration, 90-day rotation, revocation via OCSP |

### Consent Records

The employee's explicit consent record (timestamp, agent ID, consent version, scope) is stored in the macOS Keychain alongside the encryption key. Consent records are also uploaded to the backend and retained as an audit artifact for the engagement.

---

## 6. Permission Model

The agent requests the minimum macOS permissions required for its stated function.

### Permissions Requested

| Permission | Required? | Justification |
|-----------|-----------|--------------|
| Accessibility | Yes — required | CGEventTap (keyboard/mouse counts) requires Accessibility. AXUIElement (window titles) requires Accessibility. No alternative API exists for these signals. |
| Screen Recording | Optional (Phase 2) | Required only if screenshot capture is enabled. Disabled by default. Enabled only with explicit per-engagement configuration and additional employee consent. |
| Network | Yes — required | Required for TLS upload to backend and heartbeat polling. Scoped to the Python process only; Swift process has no internet access. |
| Full Disk Access | Not requested | The agent reads no files on the user's file system. Requesting FDA would exceed least privilege. |
| Contacts, Calendar, Camera, Microphone | Not requested | Not used. Not requested. |
| Admin / root | Not requested | The agent runs as the logged-in user. Installation requires a one-time admin prompt to install the LaunchAgent plist and set socket permissions. The running agent has no elevated privileges. |
| Kernel Extensions (kext / DriverKit) | Not requested | CGEventTap is a user-space API. Kernel extensions would introduce unnecessary kernel attack surface and are not required. |

### App Sandbox

The Swift capture process runs **without** App Sandbox. Justification:

- CGEventTap requires `com.apple.security.temporary-exception.mach-lookup.global-name` or must run unsandboxed; Apple does not permit this entitlement in sandboxed apps distributed outside the Mac App Store for system monitoring use cases.
- AXUIElement requires sandbox exceptions that are not granted to sandboxed apps in an MDM-managed enterprise context.
- The agent is distributed via signed PKG/DMG for enterprise deployment, not through the Mac App Store.

The absence of sandbox is mitigated by: hardened runtime enforcement, no network access in the Swift process, separation from the Python process, and MDM-managed TCC profiles that explicitly enumerate the permissions granted.

### MDM Configuration

The agent ships with configuration profiles for Jamf Pro, Microsoft Intune, and Mosyle MDM. These profiles:

- Grant Accessibility TCC silently without prompting the employee.
- Optionally grant Screen Recording TCC (disabled by default, requires explicit MDM profile activation).
- Configure the LaunchAgent to start at login.
- Set organization-specific backend URL and engagement ID.

---

## 7. Agent Lifecycle

The agent follows a defined state machine controlled by the backend. No state transition occurs without server acknowledgment.

```
UNREGISTERED
     │
     │ (installer runs, employee provides consent)
     ▼
REGISTERED ──── awaiting backend approval ────▶ REJECTED (installer removes agent)
     │
     │ (engagement manager approves in KMFlow console)
     ▼
ACTIVE ◄──────────────────────────────────────────────────────┐
     │                                                          │
     │ heartbeat response: {"state": "paused"}                  │
     ▼                                                          │
PAUSED ──── heartbeat response: {"state": "active"} ──────────┘
     │
     │ heartbeat response: {"state": "revoked"}
     ▼
REVOKED ──── agent stops capture, deletes buffer, schedules uninstall
     │
     ▼
UNINSTALLED (launchctl unload, files removed, Keychain items deleted)
```

### Heartbeat Mechanism

The agent sends a heartbeat to `POST /api/v1/taskmining/heartbeat` at a configurable interval (default: every 5 minutes). The heartbeat response carries:

- Current desired agent state (active / paused / revoked)
- Configuration version (triggers config pull if changed)
- Server timestamp (for clock drift detection)

**Revocation latency**: Maximum 5 minutes (one heartbeat interval). On receiving `"state": "revoked"`, the agent immediately stops capture, deletes the local buffer, removes the Keychain items, and schedules a LaunchAgent unload.

### Employee Visibility

The agent always runs as a visible macOS menu bar icon. The employee can:

- View current capture status (active/paused).
- Pause capture manually (subject to engagement policy configuration).
- View a transparency log of what has been captured and uploaded.
- Initiate a withdrawal of consent, which triggers the REVOKED state.

---

## 8. Code Signing and Supply Chain

### macOS Code Signing

| Artifact | Signing | Entitlements |
|----------|---------|-------------|
| Swift .app bundle | Developer ID Application (hardened runtime) | Accessibility, Entitlements plist |
| Python .framework | Developer ID Application | None |
| All bundled .dylib | Developer ID Application | None |
| All bundled .so | Developer ID Application | None |
| PKG installer | Developer ID Installer | N/A |
| DMG | Not signed (ad-hoc distribution) | N/A |

Hardened runtime is enabled on all binaries. Exceptions granted:

- `com.apple.security.cs.allow-jit` — not granted (not required)
- `com.apple.security.cs.disable-library-validation` — not granted; all bundled libraries are individually signed

### Apple Notarization

The DMG and PKG are submitted to Apple's notarization service before distribution. Notarization verifies that no known malware signatures are present and that hardened runtime is active. The notarization ticket is stapled to both artifacts.

### Python Integrity Manifest

At launch, the Python process verifies an integrity manifest (`integrity.json`) that contains SHA-256 hashes of all Python source files and compiled bytecode. The manifest itself is signed with the same Developer ID certificate. If any file fails hash verification, the agent refuses to start and logs a tamper-detection event to the backend.

### Vendored Dependencies

All Python and Swift dependencies are vendored into the application bundle. The agent performs **no runtime downloads** of dependencies or updates. This eliminates supply chain risk from dependency repositories. Updates are delivered only via signed installer packages.

---

## 9. Data Retention and Deletion

### On-Device Retention

| Data | Retention | Deletion Trigger |
|------|-----------|-----------------|
| Encrypted buffer (buffer.db) | Until uploaded (max 100 MB, FIFO) | Successful upload acknowledgment from backend; buffer entry deleted immediately |
| Upload retry queue | Up to 7 days (exponential backoff) | Successful upload or 7-day TTL expiry |
| Consent record (Keychain) | Duration of engagement | Agent revocation or explicit uninstall |
| Encryption key (Keychain) | Duration of engagement | Agent revocation or explicit uninstall |
| LaunchAgent plist | Duration of installation | Uninstall |

The 100 MB FIFO cap ensures the device never accumulates more than approximately 1–3 days of event data (at typical consultant activity rates). When the cap is reached, the oldest batch is deleted without uploading.

### Backend Retention

Backend retention is configurable per engagement in the KMFlow console. Default is 90 days from the engagement close date. Events can be deleted on demand by the engagement manager. The engagement data is stored in an engagement-scoped partition; data from one engagement is not accessible to another.

### Complete Uninstall

The PKG uninstaller and the agent's self-uninstall path remove:

- The application bundle (`/Applications/KMFlow Agent.app`)
- The LaunchAgent plist (`~/Library/LaunchAgents/com.kmflow.agent.plist`)
- The Application Support directory (`~/Library/Application Support/KMFlowAgent/`)
- The buffer database
- All Keychain items (`com.kmflow.agent.*`)
- The Unix domain socket file (`~/Library/Application Support/KMFlowAgent/agent.sock`)
- All log files (`~/Library/Logs/KMFlowAgent/`)

After uninstall, no KMFlow artifacts remain on the device. The macOS TCC database entry for Accessibility remains (managed by MDM); the MDM profile removal removes the TCC grant.

---

## 10. Incident Response

### Compromise Scenarios

#### Scenario 1: Agent Binary Compromised (Tampering)

- **Detection**: Python integrity manifest verification fails at launch; tamper event logged to backend.
- **Immediate mitigation**: Agent refuses to start. No events captured.
- **Backend action**: Engagement manager notified. Agent state set to REVOKED.
- **Recovery**: Reinstall from notarized PKG. Investigate via MDM logs.

#### Scenario 2: Device Lost or Stolen

- **Data exposure risk**: Encrypted buffer on disk (AES-256-GCM). Key in Keychain protected by device unlock credentials. Data inaccessible without the device's Keychain unlock.
- **Immediate mitigation**: Remotely revoke agent via KMFlow console (takes effect on next heartbeat or at most 5 minutes). Backend stops accepting events from the agent ID.
- **Key destruction**: Revocation command instructs agent to delete Keychain items on next wake. If device never wakes, Keychain items remain but are inaccessible without device credentials.
- **MDM action**: Issue remote wipe via MDM if device is confirmed lost.

#### Scenario 3: Backend Credentials Compromised (JWT Token Leaked)

- **Data exposure risk**: An attacker with the JWT can upload fake events and read the agent configuration, but cannot decrypt the local buffer (key is in Keychain, not transmitted).
- **Immediate mitigation**: Rotate the JWT signing key in the backend. All existing tokens are immediately invalidated. Agent re-registers on next heartbeat.
- **Investigation**: Audit backend access logs for unauthorized uploads.

#### Scenario 4: L2 Regex Filter Bypass (PII Leaks to Backend)

- **Risk**: A novel PII format not covered by L2 regex reaches the backend.
- **Current mitigation**: L2 regex scrubbing is the only active defense. L3 (ML NER) and L4 (human review) are planned but not yet implemented, so residual PII that bypasses L2 will reach the backend unfiltered.
- **Response**: Update L2 regex patterns, redeploy agent via signed update PKG, purge affected backend records. Implementing L3 and L4 is a priority for a future phase.

### No Raw PII on Device

After L2 scrubbing, the buffer contains only redacted event records with `[PII_REDACTED]` tokens in place of matched PII patterns. Note: the buffer is currently stored in plaintext SQLite (encryption is planned), so any same-user process can read it. Raw PII exists only in Swift process memory during the brief L1 filtering window and is never written to any persistent storage. PII patterns not covered by L2 regex (e.g., names, non-standard formats) will persist in the buffer until L3 ML-based filtering is implemented.

---

## 11. Compliance Mapping

### SOC 2 Type II

| Control | Reference | Implementation |
|---------|-----------|---------------|
| CC6.1 — Logical and physical access controls | Sec. 6, 7 | Agent operates under named user account only; no admin access; MDM TCC controls; server-side revocation within 5 minutes |
| CC6.6 — Encryption of data at rest and in transit | Sec. 5 | TLS 1.3 in transit; AES-256-GCM at rest planned (currently plaintext); keys in macOS Keychain |
| CC7.1 — System monitoring | Sec. 7 | Heartbeat every 5 minutes with state verification; tamper detection via integrity manifest; backend access logging |
| CC7.2 — Incident response | Sec. 10 | Documented compromise scenarios with mitigations; remote revocation capability; 5-minute maximum response latency for active agents |
| CC9.2 — Vendor risk management | Sec. 8 | Vendored dependencies (no runtime downloads); Apple notarization; Developer ID signing on all artifacts |

### ISO/IEC 27001:2022

| Control | Annex Reference | Implementation |
|---------|----------------|---------------|
| Asset management | A.8 | Data inventory (Sec. 3); retention and deletion policy (Sec. 9); engagement-scoped data partitioning |
| Cryptography | A.10 | TLS 1.3 in transit; AES-256-GCM at rest planned (Sec. 5); Keychain key storage |
| Communications security | A.13 | TLS 1.3 minimum; mTLS Phase 2; no unencrypted transmission path |
| Compliance | A.18 | GDPR DPIA (PIA template, KMF-SEC-003); DPA with data controller (DPA template, KMF-SEC-002); consent records in Keychain and backend |
| Operations security | A.12 | Immutable audit log; integrity manifest; signed artifacts; no runtime code downloads |
| Access control | A.9 | Least privilege permission model (Sec. 6); no admin rights; MDM-managed TCC |

### GDPR

| Article | Requirement | Implementation |
|---------|------------|---------------|
| Art. 25 — Data protection by design and by default | Minimize data collection; protect by default | Two-layer on-device PII architecture (L1 capture prevention, L2 regex scrubbing); L3/L4 planned; capture disabled for sensitive contexts by default; Screen Recording opt-in only |
| Art. 28 — Processor obligations | Written agreement; processor compliance | DPA template (KMF-SEC-002) addresses all Art. 28 requirements; sub-processor listed |
| Art. 30 — Records of processing activities | Maintain processing records | Data inventory (Sec. 3); DPA template includes ROPA entry template |
| Art. 32 — Security of processing | Appropriate technical measures | TLS 1.3; AES-256-GCM planned; access control; incident response plan (Sec. 10) |
| Art. 35 — Data Protection Impact Assessment | DPIA for high-risk processing | PIA template (KMF-SEC-003) provided; employee monitoring is a high-risk processing activity under Art. 35(3)(b) |

---

*This whitepaper describes the security architecture of the KMFlow Task Mining Agent as of version 1.0. It is intended for review by enterprise security teams, DPOs, and CISOs evaluating deployment approval. For questions or additional technical detail, contact the KMFlow Security Team.*

*Document ID: KMF-SEC-001 | Next Review: 2026-08-25*
