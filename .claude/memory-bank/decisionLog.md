# Decision Log

Architectural and design decisions for KMFlow platform.

## Format
Each entry follows:
- **Date**: When the decision was made
- **Decision**: What was decided
- **Context**: Why this decision was necessary
- **Alternatives**: What else was considered
- **Consequences**: Impact of the decision

---

## 2026-02-25: CalVer Versioning

**Decision**: Adopt Calendar Versioning (CalVer) format `YYYY.MM.MICRO`.

**Context**: KMFlow is a continuously deployed platform with no fixed release cycles. Semantic versioning (semver) implies API contract stability which doesn't apply to an internal platform.

**Alternatives**: SemVer, date-only (YYYY-MM-DD), build numbers.

**Consequences**: Version numbers are immediately meaningful (when was this deployed?). No debates about major/minor/patch bumps. MICRO is a monotonically incrementing build number that does NOT reset across months — ensures strict ordering (e.g., `2026.02.192` < `2026.03.193`).

---

## 2026-02-25: 4-Layer PII Architecture for Task Mining

**Decision**: Implement mandatory 4-layer PII filtering for all task mining data.

**Context**: Task mining captures desktop activity that may contain sensitive data (SSNs, credit cards, emails). Competitors use config-based PII filtering which can be disabled. Our architecture makes PII filtering mandatory and layered.

**Alternatives**: Single-layer server-side filtering, optional client-side filtering.

**Consequences**: Stronger privacy guarantees than competitors. L1+L2 filter on-device before transmission. L3 server-side catches what L1/L2 miss. L4 provides data lifecycle management. Trade-off: more complexity, slightly higher latency.

---

## 2026-02-25: Redis Streams for Task Mining Event Processing

**Decision**: Use Redis Streams (not Pub/Sub) for task mining event processing.

**Context**: Task mining events arrive in batches and must be processed reliably. Redis Streams provide consumer groups, acknowledgment, and replay capabilities.

**Alternatives**: Redis Pub/Sub (no durability), RabbitMQ (additional infrastructure), direct database writes (no backpressure).

**Consequences**: Consistent with existing monitoring worker pattern. Consumer groups allow horizontal scaling. Stream max length prevents unbounded memory growth. Events are durable until acknowledged.

---

## 2026-02-25: GitHub Issues for Project Management

**Decision**: Use GitHub Issues (not Jira) for KMFlow project management.

**Context**: KMFlow is developed in a GitHub-centric workflow. Label-based hierarchy (epic/story/task) provides sufficient structure without the overhead of Jira.

**Alternatives**: Jira (used by rival project), Linear, Shortcut.

**Consequences**: Tighter integration with PRs (`Closes #N`). No external service dependency. Label-based workflow requires discipline. Issue body text for hierarchy links (`Part of epic #N`).

---

## 2026-02-25: Evidence-First Architecture

**Decision**: Build process intelligence from diverse evidence (documents, interviews, system exports) rather than requiring structured event logs.

**Context**: Competitors (Celonis, Soroco) require clean event logs which most consulting clients don't have. David Johnson's founding requirement was to work with whatever evidence clients can provide.

**Alternatives**: Event-log-first (like Celonis), structured-input-only, manual process mapping.

**Consequences**: 15+ parsers needed (PDF, Excel, BPMN, audio, video, SaaS exports, etc.). Quality scoring engine needed to weight heterogeneous evidence. Consensus algorithm synthesizes agreement from potentially contradictory sources. Three-dimensional confidence model (score + brightness + grade) communicates certainty to users.

---

## 2026-02-27: Row-Level Security for Multi-Engagement Isolation

**Decision**: Use PostgreSQL RLS policies on all 32 engagement-scoped tables.

**Context**: Platform serves multiple consulting engagements. Data isolation must be enforced at the database level, not just application logic, to prevent IDOR vulnerabilities.

**Alternatives**: Application-level filtering only, separate databases per engagement, schema-per-tenant.

**Consequences**: Every query automatically filtered by `app.current_engagement_id`. WITH CHECK prevents engagement_id mutation. Admin bypass via `SET LOCAL row_security = off`. Alembic migrations must set RLS bypass parameter.

---

## 2026-02-27: Nine Universal Knowledge Forms

**Decision**: Structure all process knowledge into 9 universal forms for gap detection.

**Context**: Need a systematic way to identify what's known vs unknown about any process. The 9 forms provide exhaustive coverage of process knowledge dimensions.

**Alternatives**: Ad-hoc gap detection, checklist-based, free-form annotation.

**Consequences**: Coverage computation drives the "dark room" visualization (BRIGHT/DIM/DARK). Gap-targeted probe generation uses missing forms to guide survey questions. Illumination planner maps evidence acquisition actions to specific knowledge forms.

---

## 2026-02-28: Inaugural Release as v2026.02.191

**Decision**: Ship MVP as a single GitHub Release with full changelog.

**Context**: All 106 stories from PRD v2.1 were complete. Platform had passed 8-phase security audit. 5,797 tests passing with >80% coverage.

**Alternatives**: Phased releases per epic, private beta, feature-flagged rollout.

**Consequences**: Clean milestone marker for the project. Single version tag for reference. Presentation deployed to Cloudflare for stakeholder access. Clean backlog (0 open issues) going forward.
