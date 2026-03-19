# ADR: Dependency Version Pinning Strategy

**Status**: Accepted
**Date**: 2026-03-18
**Decision makers**: Paul Roth
**Context**: PR #619 (Next.js 15.5.10 → 15.5.13 patch), closed Dependabot PR for Next.js 16.x

## Decision

KMFlow will remain on its current major dependency versions and apply only **patch-level security fixes**. Major version upgrades are deferred until a defined trigger condition is met.

### Current Pinned Versions

| Dependency | Current Version | Latest Major | Upgrade Deferred? |
|------------|----------------|--------------|-------------------|
| **Next.js** | 15.5.13 | 16.x | Yes |
| **React** | 18.3.0 | 19.x | Yes |
| **FastAPI** | 0.115.x | 1.x (not yet released) | N/A |
| **SQLAlchemy** | 2.0.x | 2.0.x | At latest major |
| **Neo4j driver** | 5.27.x | 5.x | At latest major |
| **Tailwind CSS** | 4.1.x | 4.x | At latest major |
| **bpmn-js** | 18.12.x | 18.x | At latest major |
| **Python** | 3.12+ | 3.13 | Yes (runtime) |

### What We Will Do

1. **Apply patch/minor security fixes immediately** — e.g., Next.js 15.5.10 → 15.5.13 for CVE-2026-29057
2. **Pin exact versions** in `package.json` (no ranges) to prevent drift
3. **Use semver ranges** in `pyproject.toml` with major version caps (e.g., `>=0.115.0,<1.0`)
4. **Monitor advisories** via `npm audit`, `pip-audit`, and Dependabot

### What We Will Not Do

- Upgrade to Next.js 16.x, React 19.x, or Python 3.13 at this time
- Accept Dependabot PRs that propose major version bumps
- Add `@next/codemod` or migration tooling to the build

## Context

### Why Not Upgrade Next.js to 16.x?

Next.js 16 introduced breaking changes that affect KMFlow:

1. **React 19 required** — Next.js 16 drops React 18 support. React 19 changes the hooks API (`use()` replacing `useEffect` for data fetching), removes `ReactDOMTestUtils.act` (our 242 tests import it via `@testing-library/react`), and changes Suspense behavior. This is a cascading upgrade — touching Next.js means touching React, which means touching every test file and many components.

2. **Middleware and rewrites changes** — Next.js 16 changes the middleware API and rewrite handling. KMFlow uses both for API proxying and tenant routing. These require testing against our Cloudflare Worker + Docker topology.

3. **`next/image` changes** — The image component API changed in 16.x. While KMFlow uses it lightly, the migration is non-trivial combined with the other changes.

4. **Test infrastructure** — `jest-environment-jsdom` compatibility with React 19 requires upgrading to a version that may not yet be stable. Our 242 tests would need migration.

5. **ROI is negative today** — KMFlow is feature-complete at MVP. Engineering effort is better spent on backend capabilities (Redis wiring, REST endpoints, multi-tenant) than framework churn that delivers no user-visible value.

### Why Not Upgrade React to 19.x Independently?

React 19 cannot be adopted without Next.js 16 in a Next.js project — the two are coupled. Next.js 15 bundles React 18 internally even if you install React 19 in `package.json`, creating version conflicts.

### Remaining Advisories (Accepted Risk)

| Advisory | Severity | Package | Fix | Decision |
|----------|----------|---------|-----|----------|
| GHSA-3x4c-7xq6-9pq8 | Moderate | `next` 10.0.0–16.1.6 | Next.js 16.2+ | **Accept**: `next/image` disk cache growth requires attacker-controlled image URLs in `next.config.js` `remotePatterns`. KMFlow has no remote image sources configured. Unexploitable in our deployment. |
| GHSA-vpq2-c234-7xj6 | Low | `@tootallnate/once` | `jest-environment-jsdom` 27.x (breaking) | **Accept**: Dev dependency only. Not present in production builds. Incorrect control flow scoping in a test-time HTTP proxy agent. No production exposure. |

### Python Dependencies

`pip-audit` reports **zero known vulnerabilities** as of 2026-03-18. All Python dependencies use semver ranges capped at the next major version, which allows automatic patch/minor updates while preventing breaking changes.

## Trigger Conditions to Revisit

This decision **must be revisited** when any of the following occur:

### Immediate Triggers (revisit within 1 sprint)

| # | Trigger | Rationale |
|---|---------|-----------|
| T1 | **Critical/High CVE in Next.js 15.x with no backport** | If Vercel stops backporting security fixes to 15.x, we lose our patch-only strategy |
| T2 | **Critical/High CVE in React 18.x with no backport** | Same — React 18 entering EOL forces the cascade |
| T3 | **Next.js 15 reaches official EOL** | Vercel typically supports N-1 for ~12 months after N releases. Monitor the [Next.js support policy](https://nextjs.org/docs/getting-started/installation) |
| T4 | **A required new feature only exists in Next.js 16+** | e.g., if React Server Components improvements we need are 16-only |

### Scheduled Triggers (revisit at milestone)

| # | Trigger | Rationale |
|---|---------|-----------|
| T5 | **Q3 2026 planning** | Re-evaluate as part of quarterly tech debt review. By then Next.js 16 will have had 3+ months of community stabilization |
| T6 | **Multi-tenant launch** | The multi-tenant milestone will require significant frontend work anyway — bundle a framework upgrade if the effort overlaps |
| T7 | **Test infrastructure modernization** | If we migrate from Jest to Vitest (planned), the React 19 test migration cost drops significantly since we'd rewrite test setup regardless |

### Automatic Monitoring

- **Dependabot** alerts on new CVEs — triage within 48 hours
- **`npm audit`** runs in every pipeline execution
- **`pip-audit`** runs in every pipeline execution
- **Monthly manual review** of Next.js and React release notes for EOL signals

## Consequences

### Positive

- **Stability** — No risk of framework-induced regressions during feature development
- **Velocity** — Engineering time goes to user-visible features, not migration busywork
- **Predictability** — Exact version pins mean builds are reproducible across environments
- **Security** — Patch-level fixes still flow in promptly (CVE-2026-29057 fixed same day)

### Negative

- **Accumulating migration debt** — The longer we wait, the larger the eventual upgrade. Mitigated by T5 (quarterly review)
- **Missing upstream improvements** — Next.js 16 has performance optimizations (Turbopack stable, improved tree-shaking). These are nice-to-have, not blockers
- **Developer experience** — Contributors familiar with React 19 patterns (`use()`, `useFormStatus`) cannot use them. Mitigated by the fact that the team is small and aligned

### Neutral

- The two accepted advisories (GHSA-3x4c-7xq6-9pq8, GHSA-vpq2-c234-7xj6) are documented with exploitation analysis. Neither is exploitable in KMFlow's deployment topology.

## Related

- PR #619: Next.js 15.5.10 → 15.5.13 (CVE-2026-29057 patch)
- `.claude/rules/frontend-docker-build.md`: Production build requirements
- `docs/architecture/databricks-upgrade-runbook.md`: Prior upgrade decision pattern
