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
