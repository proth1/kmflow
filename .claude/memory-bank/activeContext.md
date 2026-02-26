# Active Context

**Last Updated**: 2026-02-26

## Current Focus

**Audit Remediation** — Phases 0-3 COMPLETE. Re-audit COMPLETE.
- Phase 0 (docs): All 5 items done (PRs #245, #251)
- Phase 1 (critical security): All 9 items done (PRs #246, #247, #248, #251)
- Phase 2 (HIGH findings): All 4 PRs done (#249, #252, #255, #256)
- Phase 3 (MEDIUM improvements): All 12 items done (#258)
- Re-audit: All 20 agents re-run, comprehensive report compiled
- **Result**: Agent CRITICALs 16→0, Agent HIGHs 46→16, Platform CRITICALs 19→11
- Remaining: 11 platform CRITICAL (quality/test gaps, not active vulns), 54 HIGH total

## Recently Completed

- **PR #258 merged** — Audit Phase 3: macOS Agent MEDIUM-Priority Improvements (v2026.02.073)
  - Periodic integrity re-verification (5-min timer) with violation callback
  - HMAC-SHA256 signed integrity manifest with per-build key; build script fixes format mismatch
  - Per-event consent guard (CaptureStateManager.isCapturePermitted)
  - Expanded L2 PII: +IBAN, file paths, UK NINO (8 patterns, was 5); try! → lazy try?
  - 20 new tests: 8 IntegrityChecker + 12 L2PIIFilter
  - ADR 001: sandbox-disabled rationale; profile customization script
  - Uninstall: /Users/Shared cleanup; step numbering fix
  - PR review: 1 HIGH (HMAC threat model doc) + 4 MEDIUM (tests, assertions, format mismatch) all fixed
- **PR #256 merged** — Audit Phase 2 PR 4: macOS Agent HIGH Security Hardening (v2026.02.072)
  - AES-256-GCM buffer encryption: Keychain key provisioning + decryption in TransparencyLogController
  - IPC socket: symlink detection + JSONSerialization-based auth handshake (fixed JSON injection in review)
  - HMAC-SHA256 consent record signing with per-install Keychain key; tampered records rejected
  - ConsentManager.onRevocation() handler pattern for cleanup wiring
  - CaptureStateManager.onStateChange() callback for monitor lifecycle
  - Content-level UI option disabled until L2+ PII filtering validated
  - kSecAttrSynchronizable on all Keychain stores (no iCloud sync)
  - Removed --deep from codesign, exposed codesign errors, isolated PYTHONPATH
  - PR review: 1 HIGH fixed (JSON injection), 2 LOW fixed (iCloud sync, var→let)
- **PR #255 merged** — Audit Phase 2 PR 3: Agent HIGH Security Hardening (v2026.02.071)
  - Hardened AgentLogger: all os_log interpolations now use `privacy: .private`
  - Added `kSecAttrAccessibleAfterFirstUnlock` + `kSecAttrSynchronizable: false` to Keychain writes
  - MDM config bounds clamping: screenshotInterval (5-3600), batchSize (1-10000), batchInterval (5-3600), idleTimeout (30-3600)
  - HTTPS-only scheme validation for KMFLOW_BACKEND_URL in PythonProcessManager
  - Removed unused `files.user-selected.read-write` entitlement
  - PR review: 1 blocking (HTTP allowed → fixed to HTTPS-only), 2 advisory (publicError variant, direct os.Logger usage)
- **PR #252 merged** — Audit Phase 2 PR 2: Missing FK Indexes (v2026.02.070)
  - Migration 029: 13 B-tree indexes on unindexed FK columns across 6 model modules
  - PR review: 1 MEDIUM fixed (removed non-FK lineage_id), 1 LOW fixed (naming suffix)
- **PR #251 merged** — Audit Phase 1: macOS Agent Build Pipeline Hardening (v2026.02.069)
  - Added --options runtime to all codesign invocations across embed-python.sh, build-app-bundle.sh, sign-all.sh
  - Refused ad-hoc signing in release.sh (defense-in-depth)
  - Pinned all 11 Python packages (4 direct + 7 transitive) with == and SHA-256 hashes
  - Added SHA-256 verification for python-build-standalone tarball downloads
  - PR review: 1 CRITICAL + 1 HIGH fixed (missing --options runtime in embed-python.sh and sign-all.sh)
- **PR #249 merged** — Audit Phase 2 PR 1: Platform Auth & API Hardening (v2026.02.068)
  - Pagination bounds on 22 limit/offset params across 10 route files (ge/le validators)
  - WebSocket engagement membership verification for monitoring + alerts endpoints
  - TOM CRUD membership checks for all 6 routes (create/list/get/update models, create/list gaps)
  - Replaced duplicate _log_audit in engagements.py with centralized log_audit
  - 2 new WebSocket auth tests, 2308 total backend tests
  - PR review: APPROVE with 2 MEDIUM (auth duplication — follow-up, get/update TOM — fixed), 3 LOW
- **PR #248 merged** — Audit Phase 1 PR 3: Agent Security (v2026.02.067)
  - Removed Apple Events entitlement, mouse x/y coordinates, nil bundleId bypass
  - Fixed signing (refuse ad-hoc for release), notarization (verify Accepted status), pip hashes
  - Removed eval injection in postinstall, rewrote plist log paths via PlistBuddy
  - Replaced Thread.sleep with Task.sleep, converted 5 @unchecked Sendable to actors
  - AES-256-GCM encryption and IPC auth documented as planned (E3-CRITICAL follow-up)
- **PR #247 merged** — Audit Phase 1 PR 2: Platform Quality (v2026.02.066)
  - Hardened RateLimitMiddleware: periodic pruning of expired entries
  - Stopped trusting X-Forwarded-For header for client IP
  - 3 new tests for pruning and X-Forwarded-For rejection
  - Note: 11 of 13 Story #243 tasks were already fixed in prior releases; CRITICAL slowapi finding was false positive
- **PR #246 merged** — Audit Phase 1 PR 1: Platform Security (v2026.02.065)
  - Wired require_engagement_access into 11 routes across 5 files
  - Removed dead verify_api_key sync stub from MCP auth
  - Fixed PIA R8 false encryption claim
  - Updated test mocks for engagement access dependency
  - Note: Routes with body-only engagement_id need follow-up
- **PR #245 merged** — Audit Phase 0: Documentation Corrections (v2026.02.064)
  - Fixed false encryption, PII layer, socket path, uninstall path claims in whitepaper
  - Corrected DPA template, PIA template with "planned" disclaimers
  - Removed ScreenCapture from TCC profile (least privilege)
  - Renamed L1Filter → CaptureContextFilter for clarity
  - Fixed "All data is encrypted" UI string in WelcomeView
  - PR review: 1 MEDIUM (PIA R8 row — will fix in Phase 1)
- **Committed to main** — CISO-ready macOS Agent Installer (v2026.02.063)
  - App bundle with embedded Python.framework, code signing, notarization pipeline
  - Security hardening: Keychain for secrets, mTLS, SHA-256 integrity manifest
  - SwiftUI onboarding wizard, transparency log, MDM profiles
  - DMG + PKG installers, LaunchAgent, uninstall script
  - GitHub Actions release pipeline (agent/v* tags)
  - Security whitepaper, DPA template, PIA template for CISO review
- **PR #236 merged** — ML Task Segmentation (Epic 8) (v2026.02.062)
  - Feature extraction (30-dim vectors), gradient boosting classifier, hybrid ML+rules, sequence mining
  - Shared app_categories module extracted to deduplicate graph_ingest + ML features
  - 63 new tests, 2306 total backend tests passing
  - PR review: 0 CRITICAL, 0 HIGH, 3 MEDIUM fixed (dead imports, code duplication, missing test)
  - Stories covered: #232-#235
- **PR #230 merged** — Knowledge Graph Integration (Epic 7) (v2026.02.061)
  - Graph ingestion, semantic bridge, LCD weight, variant detection
  - Ontology: SUPPORTS, MAPS_TO, extended DEVIATES_FROM
  - 71 new tests, 2243 total backend tests passing
  - Stories covered: #226-#229
- **PR #224 merged** — Admin Dashboard (Epic 6) (v2026.02.060)
- **PR #223 merged** — Privacy and Compliance (Epic 5) (v2026.02.059)
- **PR #222 merged** — Action Aggregation Engine (Epic 4) (v2026.02.058)
- **PR #221 merged** — macOS Desktop Agent (Epic 3) (v2026.02.057)
- **PR #220 merged** — Task Mining backend + SDLC infrastructure (v2026.02.056)

## Pending Work

- **Worker.py wiring**: Connect aggregation engine to Redis stream consumer (TODO in worker.py)
- **API endpoints**: Expose graph ingestion, semantic bridge, variant detection, ML classification via REST
- Follow-up items from PR #224: client-side role guard layout, WebSocket auth verification

## Session Notes

- 2308 backend tests + 206 frontend tests passing
- All 8 task mining epics (1-8) complete
- Phase 1 MVP + Phase 2 ML + Phase 3 graph integration implemented

