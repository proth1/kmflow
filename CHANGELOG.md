# Changelog

All notable changes to KMFlow are documented here.
Format: [CalVer](https://calver.org/) — `YYYY.MM.DDD` (year.month.day-of-year)

## [2026.02.071] - 2026-02-26
### Security
- Harden AgentLogger to use `privacy: .private` for all os_log interpolations (#255)
- Add `kSecAttrAccessibleAfterFirstUnlock` and `kSecAttrSynchronizable: false` to Keychain writes (#255)
- Clamp MDM integer config values to safe bounds in AgentConfig (screenshotInterval, batchSize, batchInterval, idleTimeout) (#255)
- Enforce HTTPS-only scheme validation for KMFLOW_BACKEND_URL in PythonProcessManager (#255)
- Remove unused `files.user-selected.read-write` entitlement (no effect outside sandbox) (#255)

## [2026.02.070] - 2026-02-26
### Fixed
- Add B-tree indexes on 13 unindexed ForeignKey columns for join/query performance (#252)

## [2026.02.069] - 2026-02-26
### Security
- Add --options runtime (Hardened Runtime) to all codesign invocations across build pipeline (#250)
- Refuse ad-hoc signing in release.sh (defense-in-depth) (#250)
- Pin all Python dependencies with exact versions and SHA-256 hashes for supply chain integrity (#250)
- Add SHA-256 verification for python-build-standalone tarball downloads (#250)

## [2026.02.068] - 2026-02-26
### Security
- Add WebSocket engagement membership verification for monitoring and alerts endpoints (#239)
- Wire engagement membership checks into all TOM CRUD routes (#239)
- Add pagination bounds (ge/le) to 22 limit/offset params across 10 route files (#239)

### Changed
- Replace duplicate _log_audit in engagements.py with centralized log_audit from core (#239)

### Added
- 2 new WebSocket auth tests for engagement membership (2308 total backend)

## [2026.02.067] - 2026-02-26
### Security
- Remove unused Apple Events entitlement from macOS agent (least privilege) (#244)
- Remove mouse x/y coordinates from InputEvent enum (GDPR data minimization) (#244)
- Block apps with nil bundleId by default (least privilege) (#244)
- Refuse ad-hoc signing for release builds (#244)
- Verify notarization result is "Accepted" before stapling; fail when credentials missing in release mode (#244)
- Add --require-hashes support for pip supply chain integrity (#244)
- Remove eval command injection in postinstall script (#244)
- Rewrite plist log paths from /Users/Shared to user home via PlistBuddy (#244)

### Changed
- Replace Thread.sleep with Task.sleep in SocketClient.reconnect() (#244)
- Convert 5 @unchecked Sendable classes to Swift actors for compiler-verified thread safety (#244)

## [2026.02.066] - 2026-02-26
### Security
- Harden RateLimitMiddleware: periodic pruning of expired entries to prevent memory exhaustion (#243)
- Stop trusting X-Forwarded-For header for client IP to prevent rate limit bypass (#243)

### Added
- 3 new tests for rate limiter pruning and X-Forwarded-For rejection (#243)

## [2026.02.065] - 2026-02-25
### Security
- Wire require_engagement_access into 11 route handlers for multi-tenancy enforcement (#242)
- Remove dead verify_api_key sync stub from MCP auth module (#242)
- Fix PIA R8 false encryption claim (#242)

## [2026.02.064] - 2026-02-25
### Security
- Audit Phase 0: Fix false security claims in whitepaper, DPA, PIA templates (#241)
- Correct encryption claims from "AES-256-GCM" to "planned — not yet implemented"
- Correct PII layer claims from "four-layer" to "two-layer on-device" (L3/L4 planned)
- Remove ScreenCapture from default TCC profile (principle of least privilege)
- Rename L1Filter to CaptureContextFilter for architectural clarity
- Fix incorrect socket and uninstall paths in whitepaper
- Fix false "All data is encrypted" UI string in WelcomeView

## [2026.02.063] - 2026-02-25
### Added
- CISO-ready macOS Task Mining Agent installer: app bundle with embedded Python.framework, code signing, notarization, privacy manifest
- Security hardening: buffer key and JWT token moved to macOS Keychain, mTLS client cert support, SHA-256 Python integrity manifest
- KeychainConsentStore replacing InMemoryConsentStore for persistent consent across restarts
- 5-step SwiftUI onboarding wizard (welcome, consent, permissions, connection, summary)
- Transparency log UI for real-time capture event visibility from menu bar
- DMG installer (create-dmg) and signed PKG installer with LaunchAgent for enterprise deployment
- MDM configuration profiles (managed preferences + TCC/PPPC) for Jamf/Intune/Mosyle
- Complete uninstall script removing all artifacts including Keychain items
- GitHub Actions release pipeline triggered by agent/v* tags
- CISO security whitepaper, DPA template, and PIA template for deployment approval

## [2026.02.062] - 2026-02-25
### Added
- ML task segmentation pipeline: feature extraction, gradient boosting classifier, hybrid classification, sequence mining (#231)
- Feature extraction: 30-dim vectors from AggregatedSession with interaction counts/ratios, temporal, app category one-hot (#232)
- Training data infrastructure: dataset builder, stratified splits, JSON export/import, versioned schemas (#233)
- Gradient boosting classifier: scikit-learn with calibrated probabilities, joblib model persistence (#234)
- Hybrid classifier: ML-first with configurable threshold fallback to rule-based classification (#235)
- Sequence pattern mining: n-gram extraction from classified action sequences (#235)
- Shared app category module: deduplicated detect_app_category() for graph ingestion and ML features
- 63 new tests across 4 test files (2306 total backend)

## [2026.02.061] - 2026-02-25
### Added
- Knowledge graph integration for task mining: graph ingestion, semantic bridge, LCD weight, variant detection (#225)
- Graph ingestion service: creates Application/UserAction nodes with PERFORMED_IN and PRECEDED_BY relationships (#226)
- Semantic bridge: links UserAction→Activity (SUPPORTS) and Application→System (MAPS_TO) via embedding cosine similarity (#227)
- LCD evidence weight: `task_mining: 0.90` in EVIDENCE_TYPE_WEIGHTS, above BPM models and documents (#228)
- Process variant detection: detects extra/missing/reordered steps, creates DEVIATES_FROM relationships (#229)
- Ontology extensions: SUPPORTS, MAPS_TO relationship types; DEVIATES_FROM extended for UserAction
- 71 new tests across 4 test files (2243 total backend)

### Fixed
- Chain traversal bug in variant detection: correctly identifies temporal chain starts (nodes with no predecessor)
- App category heuristic: "Calculator" no longer falsely categorized as spreadsheet

## [2026.02.060] - 2026-02-25
### Added
- Task mining admin dashboard: 4 frontend pages for agent management, capture policy, activity monitoring, quarantine review (#215)
- Agent management page: approve/revoke with confirmation, status badges, 30s auto-refresh (#216)
- Capture policy editor: app allowlist/blocklist with bundle ID validation, keystroke mode toggle with DPA confirmation (#217)
- Real-time activity dashboard: stats cards, WebSocket with exponential backoff, app usage bar chart, agent health (#218)
- PII quarantine review: TTL countdown, delete/release with reason, urgency filter (#219)
- Task mining API client module (taskmining.ts) with typed functions for all endpoints
- 38 Jest tests for API client and page utilities
- 400ms debounced engagement ID filter on all admin pages

### Fixed
- AppShell test: disambiguate multiple Dashboard link matches after adding TM Dashboard nav item

## [2026.02.059] - 2026-02-25
### Added
- Privacy and compliance suite: PII detection tests, quarantine cleanup, consent management, audit logging (#210)
- PII detection test suite: 217+ parametrized tests covering all 7 PII types with ≥99% recall validation
- Quarantine auto-cleanup job: atomic DELETE of expired PIIQuarantine records with summary reporting
- Consent management: ConsentRecord model, ConsentManager service, HMAC-SHA256 IP hashing, re-grant state machine
- Task mining audit logger: 11 new AuditAction enum values, insert-only TaskMiningAuditLogger with 9 convenience methods
- Alembic migration 028 for consent_records table

### Fixed
- PII pattern gaps: international phone (word boundary before +), US address (Broadway/Parkway suffixes), financial account (number/routing keywords)
- Quarantine cleanup TOCTOU: replaced count-then-delete with single atomic DELETE using rowcount
- Consent re-grant: REVOKED agents can now re-consent (REVOKED → APPROVED transition)
- IP address hashing: upgraded from bare SHA-256 to HMAC-SHA256 keyed by server secret

## [2026.02.058] - 2026-02-25
### Added
- Action aggregation engine: session grouping, rule-based classification, evidence materialization (#206)
- SessionAggregator: groups raw desktop events into bounded app sessions by app switches and idle periods
- ActionClassifier: first-match-wins rule engine with 6 default rules (communication, file_operation, review, data_entry, navigation_url, navigation_scroll)
- EvidenceMaterializer: converts classified sessions to EvidenceItem records (KM4WORK, reliability=0.90)
- YAML-configurable classification rules with documented ordering constraints
- 44 unit tests across 3 test files (session, classifier, materializer)

### Fixed
- YAML rule ordering aligned with hardcoded defaults (communication first, review before navigation_scroll)
- Unknown YAML conditions logged at ERROR level instead of WARNING
- PII upstream filtering contract documented for window_title_sample in materializer

## [2026.02.057] - 2026-02-25
### Added
- macOS desktop agent: Swift capture layer (21 source files) + Python intelligence layer (17 source files) (#195)
- Swift: CGEventTap input monitoring, NSWorkspace app switch, L1+L2 PII filtering, consent state machine, menu bar UI
- Python: Unix socket server, encrypted SQLite buffer, batch uploader, config manager, health reporter
- JWT auth module for agent-to-backend HTTP requests
- AmEx and JCB credit card PII patterns in both Swift and Python L2 filters

### Security
- Socket moved from /tmp to user-private ~/Library/Application Support/ with 0600 permissions
- Auto-generated random encryption key replaces hardcoded fallback
- Shared authenticated httpx.AsyncClient with JWT bearer tokens
- Socket reconnection with exponential backoff

### Fixed
- Async SQLite: all DB ops run via asyncio.to_thread() to avoid event loop blocking
- AnyCodable now handles arrays and nested dictionaries
- Menu bar items wired to action handlers via MenuActionDelegate
- Non-blocking cpu_percent() reads in health reporter

## [2026.02.056] - 2026-02-25
### Added
- Task Mining backend infrastructure: models, PII engine, API routes, processor, worker (#184)
- 37 GitHub Issues for Task Mining initiative (Epics 1-6, 37 stories) (#183)
- Full SDLC workflow infrastructure: commands, hooks, memory bank, coding standards

### Infrastructure
- SDLC hooks: session start, PR creation, post-merge, session end, decision log
- Memory bank: platformState, activeContext, decisionLog
- CalVer versioning initialized

## [2026.02.055] - 2026-02-24
### Fixed
- Fix 2 pre-existing frontend API client test failures

## [2026.02.054] - 2026-02-23
### Added
- 10 KMFlow logo concepts for brand identity review (#181)

## [2026.02.053] - 2026-02-22
### Added
- Frontend component tests for BPMNViewer, GraphExplorer, EvidenceUploader

## [2026.02.052] - 2026-02-21
### Fixed
- Audit remediation batch 2: remaining backlog (waves A/B/C) (#180)

## [2026.02.051] - 2026-02-20
### Changed
- Extract schemas and service layer from simulations.py (1334 to 1037 lines) (#179)

## [2026.02.050] - 2026-02-19
### Changed
- Refactor models.py into domain-specific package (77 classes, 11 modules) (#178)

## [2026.02.049] - 2026-02-18
### Added
- Implement HttpOnly JWT cookies (#156) and GDPR data subject rights (#165) (#177)

### Security
- Remove arbitrary Cypher query endpoint (security hardening) (#176)

## [2026.02.048] - 2026-02-17
### Fixed
- Audit remediation batch 1: resolve CRITICAL/HIGH findings (#175)

## [2026.02.047] - 2026-02-16
### Added
- Phase 3.2 + Phase 4: Complete Operating Model Scenario Engine (#127)
