# KMFlow macOS Task Mining Agent — Comprehensive Security Audit Report

**Date**: 2026-02-25
**Classification**: Confidential — Security Audit Finding
**Auditor**: Claude Opus 4.6 (8 specialized agents, 3 squads)
**Scope**: All Swift source (37 files, 4,610 lines), build/installer scripts (13 files, 1,538 lines), configuration profiles, security documentation
**Codebase**: `/Users/proth/repos/kmflow/agent/macos/`

---

## Executive Summary

The KMFlow macOS Task Mining Agent is a workplace activity monitoring tool that captures application usage, window titles, and input activity metrics on employee machines. It uses macOS Accessibility APIs, stores data in a local SQLite buffer, and transmits events via Unix socket IPC to an embedded Python backend.

This audit examined the agent through **8 specialized lenses** across **3 squads**: Security & Entitlements (E1-E3), Installer & Supply Chain (F1-F3), and Code Quality & Privacy (G1-G2).

### Headline Verdict

**The agent is NOT ready for production deployment at a regulated enterprise.** While the architecture demonstrates strong security thinking (consent-first design, protocol-based abstractions, multi-layer PII filtering, integrity verification), there are **critical gaps between what the security documentation promises and what the code implements**. Three headline security controls claimed in the CISO-facing whitepaper do not exist:

1. **AES-256-GCM encryption** of the local buffer — the database is plaintext
2. **L3 ML-based NER** PII protection — not implemented
3. **L4 Human quarantine review** — not implemented

Additionally, the TCC profile **silently pre-authorizes ScreenCapture** despite the whitepaper claiming "no screen capture" — creating a trust violation between CISO documentation and shipped artifacts.

### Finding Totals

| Severity | Squad E (Security) | Squad F (Installer) | Squad G (Quality/Privacy) | **Total** |
|----------|:-:|:-:|:-:|:-:|
| CRITICAL | 4 | 8 | 5 | **17** |
| HIGH | 11 | 14 | 15 | **40** |
| MEDIUM | 16 | 16 | 16 | **48** |
| LOW | 9 | 11 | 10 | **30** |
| **Total** | **40** | **49** | **46** | **135** |

> Note: Some findings appear in multiple agents due to overlapping scope (e.g., sandbox disabled, logger privacy). After deduplication, the unique finding count is approximately **95 distinct issues**.

### Security Scores by Agent

| Agent | Score | Focus |
|-------|:-----:|-------|
| E1 Entitlements & TCC | 6.5/10 | Entitlements, TCC profiles, Hardened Runtime |
| E2 Capture Layer | 6.5/10 | CGEventTap, data minimization, PII filtering |
| E3 Keychain & Encryption | 3.5/10 | Encryption, Keychain config, IPC security |
| F1 Code Signing | 4.0/10 | Signing pipeline, notarization, supply chain |
| F2 Installer & LaunchAgent | 5.5/10 | PKG scripts, launchd, uninstall |
| F3 MDM Profiles | — | TCC profile, MDM config, whitepaper verification |
| G1 Swift Quality | 7.0/10 | Concurrency, error handling, test coverage |
| G2 Privacy & Data Min | — | PII protection, consent, GDPR alignment |

---

## Top 15 Critical & High Findings

These are the findings that **must be resolved before any production deployment**.

### CRITICAL — Deployment Blockers

| # | Finding | Agent | File | Issue |
|---|---------|-------|------|-------|
| 1 | **Plaintext SQLite buffer** | E3, G2 | `TransparencyLogController.swift:109` | Whitepaper claims AES-256-GCM; code comments say "a no-op for plaintext rows today." WelcomeView tells employees "All data is encrypted" — this is false. |
| 2 | **Unauthenticated IPC socket** | E3 | `SocketClient.swift:10-63` | Unix socket has no auth, no encryption, no pre-existence check. Any same-user process can inject/sniff events. |
| 3 | **L3/L4 PII layers don't exist** | G2 | `security-whitepaper.md:214-221` | "Four-layer PII protection" is a headline claim. L3 (ML NER) is "planned for Phase 3." L4 (human review) has no code. Actual PII defense = 1 regex layer. |
| 4 | **ScreenCapture TCC pre-authorized** | F3, E1 | `tcc.mobileconfig:130-151` | Whitepaper says "no screen capture." TCC profile silently grants ScreenCapture. CISO trust violation. |
| 5 | **Mouse coordinates in InputEvent** | E2 | `InputMonitor.swift:19-21` | X/Y coords on mouseDown/mouseUp/mouseDrag — undisclosed, enables behavioral reconstruction beyond consent. |
| 6 | **Ad-hoc signing default** | F1 | `sign-all.sh:12` | All scripts default to `"-"` (ad-hoc). Gatekeeper rejects on every enterprise machine. |
| 7 | **Silent notarization skip** | F1 | `notarize.sh:19-22` | Exits 0 when credentials missing. Pipeline produces un-notarized artifacts that look successful. |
| 8 | **Supply chain: no pip hash verification** | F1 | `vendor-python-deps.sh:151` | `pip install` without `--require-hashes`. PyPI compromise → malicious code in signed bundle with Accessibility access. |
| 9 | **World-writable log paths** | F2 | `com.kmflow.agent.plist:47-58` | Plist ships with `/Users/Shared/` paths. Comment says postinstall rewrites them — **it doesn't**. |
| 10 | **`eval` in root postinstall** | F2 | `postinstall:23` | `eval echo "~$CONSOLE_USER"` in a root-context script. Command injection vector. |

### HIGH — Must Fix Before Beta

| # | Finding | Agent | File | Issue |
|---|---------|-------|------|-------|
| 11 | **Apple Events entitlement unused** | E1 | `KMFlowAgent.entitlements:14` | `automation.apple-events` = true but zero Apple Events API usage. Grants ability to control any app. |
| 12 | **Hardened Runtime missing in build script** | E1 | `build-app-bundle.sh:336` | `--options runtime` not included. Entitlements declarations are inert without it. |
| 13 | **TCC CodeRequirement placeholder** | E1, F3 | `tcc.mobileconfig:107` | `REPLACE_TEAM_ID` literal. Deployed as-is = silent TCC grant failure. |
| 14 | **Consent tokens unsigned** | E3 | `KeychainConsentStore.swift:85-96` | Plain JSON in Keychain, no HMAC. Any local process can forge consent records. |
| 15 | **No data cleanup on consent revocation** | E3 | `ConsentManager.swift:39-43` | `revokeConsent()` only sets a flag. Buffer, Keychain keys, socket, Python process — all untouched. |

---

## CRITICAL Findings (All)

### From E1 — Entitlements & TCC

#### [CRITICAL] Apple Events Entitlement Granted Without Code Usage
**File**: `Resources/KMFlowAgent.entitlements:14-15`
**Evidence**: `com.apple.security.automation.apple-events` = `true` with zero API usage across all 29 Swift files. The comment misleadingly says "Accessibility API access."
**Risk**: A compromised agent process can programmatically control any application — read email, open files, send keystrokes — without additional prompts.
**Recommendation**: Remove the entitlement entirely. Accessibility APIs (AXUIElement, CGEventTap) do not require it.

### From E2 — Capture Layer

#### [CRITICAL] Mouse Coordinate Capture Exceeds Stated Purpose
**File**: `Sources/Capture/InputMonitor.swift:19-21`
**Evidence**: `InputEvent` enum carries `x: Double, y: Double` for mouseDown/mouseUp/mouseDrag. The consent UI says "application usage patterns" — not click positions.
**Risk**: Mouse coordinates reveal what the user clicked on within a UI. Combined with window titles and timestamps, this enables detailed behavioral reconstruction.
**Recommendation**: Remove x/y parameters from the enum. If needed in future, require separate consent toggle with quantization.

### From E3 — Keychain & Encryption

#### [CRITICAL] SQLite Capture Buffer Stored in Plaintext
**File**: `Sources/UI/TransparencyLogController.swift:109-113`
**Evidence**: Code comment: "decryption is a no-op for plaintext rows today." `WelcomeView.swift:72`: "All data is encrypted and PII is automatically redacted."
**Risk**: Any same-user process can read the SQLite database. The false claim creates legal liability under GDPR/CCPA.
**Recommendation**: Implement AES-256-GCM encryption or correct all documentation to reflect reality.

#### [CRITICAL] Unix Domain Socket Has No Authentication or Encryption
**File**: `Sources/IPC/SocketClient.swift:10-63`
**Evidence**: Direct `connect()` with no handshake, plaintext ndjson, no pre-existence check for symlink attacks.
**Risk**: Event injection, passive sniffing, or symlink-based data redirection by any local process.
**Recommendation**: Add peer credential verification, shared-secret handshake, and symlink check.

### From F1 — Code Signing

#### [CRITICAL] Ad-Hoc Signing Default
**File**: `scripts/sign-all.sh:12` (and 4 other scripts)
**Evidence**: `IDENTITY="${KMFLOW_CODESIGN_IDENTITY:--}"` — defaults to ad-hoc across all scripts.
**Risk**: Enterprise MDM deployment with ad-hoc signing = Gatekeeper rejection on every machine.
**Recommendation**: Validate identity exists in Keychain. Refuse release with ad-hoc unless `--allow-adhoc`.

#### [CRITICAL] Notarization Silently Skipped
**File**: `scripts/notarize.sh:19-22`
**Evidence**: `if [[ -z "${APPLE_ID:-}" ]]; then exit 0; fi` — success exit when credentials missing.
**Risk**: Un-notarized artifacts pass through the pipeline. Gatekeeper blocks on macOS 10.15+.
**Recommendation**: Non-zero exit. Gate release on `spctl --assess`.

#### [CRITICAL] Notarization Result Not Verified
**File**: `scripts/notarize.sh:68-79`
**Evidence**: `notarytool submit --wait` followed immediately by `stapler staple` with no status check.
**Risk**: Rejected submissions proceed to stapling and packaging.
**Recommendation**: Capture submission ID, verify "Accepted" status, fetch log on failure.

#### [CRITICAL] Python Dependencies Without Hash Verification
**File**: `scripts/vendor-python-deps.sh:151-160`
**Evidence**: `pip install` with `>=` version specifiers, no `--require-hashes`, no lock file.
**Risk**: PyPI supply chain attack → malicious code signed into agent with Accessibility access.
**Recommendation**: Pin versions, use `--require-hashes`, generate SBOM.

### From F2 — Installer

#### [CRITICAL] Command Injection via `eval` in Root Postinstall
**File**: `installer/pkg/scripts/postinstall:23`
**Evidence**: `eval echo "~$CONSOLE_USER"` in a root-context script.
**Risk**: Arbitrary command execution as root if username is influenced.
**Recommendation**: Replace with `dscl` or `/Users/$CONSOLE_USER` fallback.

#### [CRITICAL] World-Writable Log Paths in LaunchAgent Plist
**File**: `installer/launchagent/com.kmflow.agent.plist:47-58`
**Evidence**: `StandardOutPath` and `HOME` point to `/Users/Shared/`. Comments claim postinstall rewrites them — **it does not**.
**Risk**: Symlink attacks, log injection, IPC socket accessible to all users.
**Recommendation**: Implement the plist rewriting (using PlistBuddy) that was designed but never built.

### From F3 — MDM Profiles

#### [CRITICAL] ScreenCapture Pre-Authorized Despite "No Screenshot" Claim
**File**: `installer/profiles/com.kmflow.agent.tcc.mobileconfig:130-151`
**Evidence**: `ScreenCapture` → `Allowed` = `true`. Whitepaper: "It does not record the content of screenshots."
**Risk**: CISO approves based on whitepaper. TCC profile enables the permission silently. Server-side toggle could activate without user prompt.
**Recommendation**: Remove ScreenCapture from default profile. Create a separate, explicitly-deployed profile for Phase 2.

### From G2 — Privacy

#### [CRITICAL] L1 Filter Contains No PII Regex
**File**: `Sources/PII/L1Filter.swift:28-49`
**Evidence**: L1Filter only checks password fields and blocked apps — zero PII pattern matching.
**Risk**: "Four-layer PII protection" is misleading. Only L2 regex scrubs PII content.
**Recommendation**: Rename to "CaptureContextFilter." Update whitepaper to distinguish context blocking from content scrubbing.

#### [CRITICAL] Encryption Not Implemented Despite Claims
**File**: `Sources/UI/TransparencyLogController.swift:109-113`
**(Cross-reference with E3 DATA-AT-REST-001)**

#### [CRITICAL] L3 and L4 PII Layers Do Not Exist in Code
**File**: `docs/security/task-mining-agent-security-whitepaper.md:214-221`
**Evidence**: L3: "planned for Phase 3." L4: no backend code. DPA and PIA present them as implemented.
**Risk**: CISOs and DPOs making deployment decisions based on inaccurate documentation.
**Recommendation**: Add prominent "not yet implemented" disclaimers. Do not present future features as active controls.

---

## HIGH Findings Summary

| # | Finding | Agent | Key Issue |
|---|---------|-------|-----------|
| 1 | Unused Apple Events entitlement | E1 | Privilege escalation surface |
| 2 | Hardened Runtime missing in build | E1 | Entitlements inert, DYLD injection possible |
| 3 | TCC CodeRequirement placeholder | E1, F3 | Silent permission grant failure |
| 4 | File access entitlement without sandbox | E1 | Misleading security posture |
| 5 | `content_level` mode scaffolds keystroke capture | E2 | UI allows selection of unimplemented keylogger mode |
| 6 | Nil bundleIdentifier bypasses blocklist | E2, F3 | Unknown apps captured by default |
| 7 | All logger messages `privacy: .public` | E1, E2, E3, G1 | PII in system-wide logs |
| 8 | KeychainHelper missing kSecAttrAccessible | E1, E3 | Inconsistent Keychain protection |
| 9 | Consent tokens unsigned/forgeable | E3 | Any local process can forge consent |
| 10 | No data cleanup on consent revocation | E3 | GDPR right-to-erasure violation |
| 11 | App Sandbox disabled without ADR | E3, F2 | Full user-privilege blast radius |
| 12 | Backend URL not validated from MDM | F3 | Data exfiltration via rogue MDM |
| 13 | No MDM config bounds validation | F3, G1 | BatchSize=0 → crash, interval=0 → CPU loop |
| 14 | Python framework signed without Hardened Runtime | F1 | Nested components lack protection |
| 15 | Codesign failures silently suppressed | F1 | `2>/dev/null \|\| true` masks all signing errors |
| 16 | `--deep` flag used (Apple discourages) | F1 | Over-grants entitlements to nested code |
| 17 | PKG uses wrong cert type for productsign | F1 | MDM rejects improperly signed packages |
| 18 | Python tarball not hash-verified | F1, F2 | Downloaded from GitHub with no SHA-256 check |
| 19 | Notarization password on command line | F1 | Credential exposure in process listing |
| 20 | PYTHONPATH inherits from environment | F2 | Breaks embedded Python isolation |
| 21 | TOCTOU race in plist ownership | F2 | LaunchAgents dir may be left root-owned |
| 22 | Incomplete uninstall | F2 | /Users/Shared residue, UserDefaults not cleaned |
| 23 | Thread.sleep blocks actor executor | G1 | 62-second freeze on reconnect |
| 24 | @unchecked Sendable with NSLock | G1 | 5 classes bypass compiler safety |
| 25 | Consent save silently fails | G1 | `try?` swallows encoding errors |
| 26 | Force-unwrap of Application Support URL | G1 | `.first!` → fleet-wide crash if nil |
| 27 | SIGPIPE crash on socket write | G1 | FileHandle.write raises ObjC exception |
| 28 | Capture scope picker has no effect | G2 | User's selection is discarded |
| 29 | No consent withdrawal mechanism | G2 | UI promises it, code doesn't implement it |
| 30 | Window titles capture full content | G2 | Document names, email subjects, URLs up to 512 chars |

---

## MEDIUM Findings Summary

48 MEDIUM findings across all agents. Key themes:

- **Pause/resume not wired** — CaptureStateManager.pauseCapture() doesn't stop monitors (E2)
- **Private browsing detection fragile** — English-only strings, missing browsers (E2)
- **L2 PII patterns incomplete** — No SSN without dashes, no IBAN, no file-path usernames (E2, G2)
- **Integrity check startup-only** — Post-launch tampering undetected (E3)
- **Integrity manifest unsigned** — Attacker can replace both files and manifest (E3)
- **Consent checked only at startup** — No runtime enforcement (E3)
- **kSecAttrSynchronizable not explicitly disabled** — Risk of iCloud sync (E3)
- **Verification script incomplete** — No Hardened Runtime, Team ID, or staple check (F1)
- **DMG missing --timestamp** — Notarization will reject (F1)
- **Crash loop protection weak** — 10s ThrottleInterval, no max retry (F2)
- **Shell heredoc interpolation** — Build paths in unquoted heredoc (F2)
- **Profile signing uses -noverify** — No chain validation, non-failing exit (F3)
- **PayloadOrganization hardcoded** — "KMFlow" instead of deploying org (F3)
- **System vs User scope mismatch** — TCC grants apply to all users on machine (F3)
- **Test coverage gaps** — 5 of 14+ modules tested (G1)
- **AnyCodable stores Any** — Not truly Sendable (G1)

---

## LOW Findings Summary

30 LOW findings. Notable items:
- Capture state not persisted across restarts (E2)
- Blocked-app dwell time leaked (E2)
- No key rotation mechanism (E3)
- CI allows unsigned release artifacts (F1)
- Checksums not GPG-signed (F1)
- Missing LowPriorityIO in plist (F2)
- LSUIElement in wrong plist (F2)
- Sequential placeholder PayloadUUIDs (F3)
- ISO8601DateFormatter created per-row (G1)
- Mock objects in production source (G1)

---

## Whitepaper Claims vs. Reality

| Claim | Whitepaper Says | Code Reality | Verdict |
|-------|----------------|--------------|:-------:|
| AES-256-GCM encryption | "All captured events in an encrypted SQLite database" | Plaintext. Comment: "a no-op for plaintext rows today." | **FALSE** |
| Four-layer PII protection | "L1 through L4 operate in concert" | L1 = context filter (not PII). L2 = regex (1 layer). L3 = "planned Phase 3." L4 = no code. | **MISLEADING** |
| No screen capture | "Does not record the content of screenshots" | TCC profile pre-authorizes ScreenCapture. Config has `screenshotEnabled`. Event type `screenCapture` exists. | **CONTRADICTED BY PROFILE** |
| Only Accessibility permission | "Requests only Accessibility" | TCC profile also includes ScreenCapture block | **FALSE** |
| No keystroke logging | "Does not record the content of keystrokes" | No keystroke content API calls found. `content_level` mode docs reference it. | **TRUE (current code)** |
| User-controlled pause | "Pause at any time from the menu bar" | Pause sets a state flag. Monitors are not stopped. Events continue flowing. | **PARTIALLY FALSE** |
| Consent revocation | "Revoke consent at any time" | `revokeConsent()` sets a flag. No data deletion, no process termination. | **INCOMPLETE** |
| On-device data stays encrypted | WelcomeView: "All data is encrypted" | SQLite is plaintext | **FALSE** |

---

## Positive Security Observations

Despite the critical gaps, the agent has a strong architectural foundation:

1. **Zero external Swift dependencies** — eliminates supply-chain risk in the native layer
2. **Protocol-based testability** — 7 key interfaces abstracted for mocking
3. **Consent-first architecture** — no capture without explicit 3-checkbox consent
4. **L1 context blocking** — password fields, private browsing, hardcoded password manager blocklist
5. **L2 regex PII scrubbing** — SSN, email, phone, credit card patterns scrubbed before IPC
6. **SHA-256 integrity verification** of Python bundle at startup
7. **Circuit breaker** on Python subprocess restarts (5 in 60s)
8. **Hardened Runtime dangerous capabilities disabled** — JIT, unsigned memory, library validation all false
9. **Clean 7-module architecture** with minimal coupling
10. **StaticCode=false in TCC profile** — re-validates binary signature on each access
11. **Proper Swift actor usage** for PythonProcessManager
12. **Idempotency keys** on CaptureEvents for exactly-once processing
13. **Window title truncation** to 512 characters

---

## Remediation Roadmap

### Phase 0 — Documentation Corrections (Immediate, Before Any External Sharing)

| # | Action | Effort | Agents |
|---|--------|--------|--------|
| 1 | Update whitepaper: encryption is "planned," not implemented | 1 hour | E3, G2 |
| 2 | Update whitepaper: L3/L4 are "future phases," not active | 1 hour | G2 |
| 3 | Remove ScreenCapture from default TCC profile | 15 min | F3, E1 |
| 4 | Fix WelcomeView "All data is encrypted" claim | 15 min | E3, G2 |
| 5 | Rename L1Filter to CaptureContextFilter | 30 min | G2 |

### Phase 1 — Critical Security Fixes (Before Any Deployment)

| # | Action | Effort | Agents |
|---|--------|--------|--------|
| 6 | Remove `automation.apple-events` entitlement | 5 min | E1 |
| 7 | Remove mouse X/Y from InputEvent enum | 15 min | E2 |
| 8 | Add `--options runtime` to build-app-bundle.sh | 5 min | E1, F1 |
| 9 | Implement plist path rewriting in postinstall | 1 hour | F2 |
| 10 | Replace `eval` with safe alternative in postinstall | 15 min | F2 |
| 11 | Add signing identity validation (refuse ad-hoc for release) | 1 hour | F1 |
| 12 | Fix notarization: verify result, fail on skip | 1 hour | F1 |
| 13 | Pin Python deps, add `--require-hashes` | 2 hours | F1 |
| 14 | Add Python tarball SHA-256 verification | 30 min | F1, F2 |

### Phase 2 — High-Priority Fixes (Before Beta)

| # | Action | Effort | Agents |
|---|--------|--------|--------|
| 15 | Implement AES-256-GCM buffer encryption | 2-3 days | E3 |
| 16 | Add IPC socket authentication + symlink check | 1 day | E3 |
| 17 | Sign consent records with HMAC | 1 day | E3 |
| 18 | Implement data cleanup on consent revocation | 1 day | E3 |
| 19 | Wire pause/resume to actual monitor lifecycle | 4 hours | E2 |
| 20 | Disable `content_level` UI option | 15 min | E2 |
| 21 | Fix nil bundleId → deny by default | 15 min | E2, F3 |
| 22 | Change logger to `privacy: .private` default | 1 hour | E1, G1 |
| 23 | Replace Thread.sleep with Task.sleep in SocketClient | 1 hour | G1 |
| 24 | Add MDM config bounds validation | 2 hours | F3, G1 |
| 25 | Add backend URL validation (https + host check) | 2 hours | F3 |
| 26 | Remove `--deep`, sign components individually | 2 hours | F1 |
| 27 | Remove `2>/dev/null \|\| true` from codesign commands | 30 min | F1 |
| 28 | Clean PYTHONPATH inheritance in launcher | 15 min | F2 |

### Phase 3 — Medium-Term Improvements (Before GA)

| # | Action | Effort |
|---|--------|--------|
| 29 | Convert @unchecked Sendable classes to actors | 1 day |
| 30 | Add periodic integrity checking | 4 hours |
| 31 | Sign integrity manifest with embedded hash | 4 hours |
| 32 | Add runtime consent enforcement per-event | 4 hours |
| 33 | Expand L2 PII patterns (IBAN, file paths, international) | 1 day |
| 34 | Improve private browsing detection (AXPrivate, more browsers) | 4 hours |
| 35 | Add tests for SocketClient, IntegrityChecker, PythonProcessManager | 2 days |
| 36 | Replace `try!` with `do/catch` in regex compilation | 1 hour |
| 37 | Document sandbox-disabled rationale in ADR | 2 hours |
| 38 | Add complete /Users/Shared cleanup to uninstall | 30 min |
| 39 | Prepare profile customization script (Team ID, UUIDs, org name) | 4 hours |
| 40 | Mandatory re-audit when CGEventTap is implemented | — |

---

## Squad Reports

### Squad E: Security & Entitlements

| Agent | Findings | Score | Report |
|-------|:--------:|:-----:|--------|
| E1 — Entitlements & TCC | 12 | 6.5/10 | `docs/audit-findings/E1-entitlements-tcc.md` |
| E2 — Capture Layer | 13 | 6.5/10 | `docs/audit-findings/E2-capture-layer.md` |
| E3 — Keychain & Encryption | 15 | 3.5/10 | `docs/audit-findings/E3-keychain-encryption.md` |

### Squad F: Installer & Supply Chain

| Agent | Findings | Score | Report |
|-------|:--------:|:-----:|--------|
| F1 — Code Signing & Notarization | 18 | 4.0/10 | `docs/audit-findings/F1-signing-notarization.md` |
| F2 — Installer & LaunchAgent | 17 | 5.5/10 | `docs/audit-findings/F2-installer-launchagent.md` |
| F3 — MDM & Config Profiles | 13 | — | `docs/audit-findings/F3-mdm-config-profiles.md` |

### Squad G: Code Quality & Privacy

| Agent | Findings | Score | Report |
|-------|:--------:|:-----:|--------|
| G1 — Swift Code Quality | 23 | 7.0/10 | `docs/audit-findings/G1-swift-quality.md` |
| G2 — Privacy & Data Minimization | 23 | — | `docs/audit-findings/G2-privacy-data-minimization.md` |

---

## Methodology

Each agent was given explicit scope, target files, and specific checks to perform. All agents operated in read-only mode — no source files were modified. Findings include actual code evidence (3-5 lines from the file), risk assessment, and specific remediation recommendations.

The audit covered:
- **37 Swift source files** (4,196 lines) — every line read by at least one agent
- **5 test files** (414 lines)
- **13 build/installer scripts** (1,538 lines)
- **2 MDM configuration profiles** (283 lines)
- **1 LaunchAgent plist** (80 lines)
- **3 security/compliance documents** (whitepaper, PIA, DPA)
- **Build configuration** (Package.swift, Makefile, entitlements, Info.plist)

---

*Report compiled from 8 parallel audit agents. Full findings with code evidence available in individual squad reports under `docs/audit-findings/`.*
