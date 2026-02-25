# Changelog

All notable changes to KMFlow are documented here.
Format: [CalVer](https://calver.org/) — `YYYY.MM.DDD` (year.month.day-of-year)

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
