# C2: Frontend Code Quality Audit Findings

**Auditor**: C2 (Frontend Quality Auditor)
**Scope**: `frontend/src/` — React component patterns, error boundaries, accessibility, token storage security, state management
**Date**: 2026-03-20
**Audit Cycle**: 7
**Prior Audit**: Cycle 6 (2026-03-19)

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 0     |
| MEDIUM   | 3     |
| LOW      | 3     |
| **Total** | **6** |

**Trend**: Improved from cycle 6. The prior HIGH finding (BPMNViewer double cast) is now resolved — `BPMNViewer.tsx` uses a single justified `as BpmnViewer` cast with a comment. The prior LOW finding for `ontology/page.tsx` silent error discard is also resolved — both `validateError` and `exportError` state variables are now present and rendered. Three MEDIUM findings persist unchanged: missing cancellation guards in two page effects, silent secondary data failures in governance and analytics pages, and missing ARIA live regions for loading states. Three LOW findings remain: index keys in six locations, per-route `error.tsx` gap, and a new `useMonitoringData` null cast.

---

## Resolved Since Prior Audit (Cycle 6)

### BPMNViewer double cast — RESOLVED

**File**: `frontend/src/components/BPMNViewer.tsx:91`

The six repeated `as unknown as BpmnViewer` casts have been replaced with a single direct cast at construction time:

```typescript
const viewer = new BpmnJS({ container: containerRef.current }) as BpmnViewer;
// Safe: BpmnJS satisfies the BpmnViewer interface at runtime
```

Subsequent uses of `viewer.get(...)` and `viewer.importXML(...)` now call through the typed reference without additional casts. The justifying comment is present. This closes the HIGH finding from cycles 5–6.

### ontology/page.tsx silent error discard — RESOLVED

**File**: `frontend/src/app/ontology/page.tsx`

`validateError` and `exportError` state variables are now present. Both `handleValidate` and `handleExport` set the respective error state on failure, and the errors are rendered in the UI. The bare `catch {}` blocks are gone. This closes the LOW finding from cycles 5–6.

---

## Medium Severity Issues

### [MEDIUM] ASYNC SAFETY: Missing Cancellation Guard in Two Page-Level Effects

**File**: `frontend/src/app/portal/[engagementId]/page.tsx:15`
**File**: `frontend/src/app/dashboard/[engagementId]/page.tsx:53`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// portal/[engagementId]/page.tsx — no cancelled ref, no cleanup return
useEffect(() => {
  if (!engagementId) return;
  fetchPortalOverview(engagementId)
    .then((data) => {
      setOverview(data);      // executes after potential unmount
      setLoading(false);
    })
    .catch((err: Error) => {
      setError(err.message || "Failed to load overview");
      setLoading(false);
    });
}, [engagementId]);

// dashboard/[engagementId]/page.tsx — async inner function, no cleanup
useEffect(() => {
  async function loadData() { ... }
  loadData();
}, [engagementId]);
```
**Description**: `portal/[engagementId]/page.tsx` has no `cancelled` ref guard and no cleanup return. If the user navigates away before the fetch resolves, `setOverview` and `setLoading(false)` execute on an unmounted component. `dashboard/[engagementId]/page.tsx` wraps all fetches in `Promise.allSettled` which is appropriate for handling partial failures, but the `loadData` async function has no cancellation guard and no cleanup return from `useEffect`. The rest of the codebase uses either `cancelled` refs or `AbortController` consistently (confirmed in 22 of 24 files with async effects).
**Risk**: React logs state-update-on-unmounted-component warnings. In React 18 strict mode, effects run twice on mount, which can produce duplicate in-flight requests that both resolve and attempt state updates.
**Recommendation**: Apply the `cancelled` ref pattern already established in `monitoring/[jobId]/page.tsx:21`:
```typescript
useEffect(() => {
  let cancelled = false;
  fetchPortalOverview(engagementId).then((data) => {
    if (!cancelled) { setOverview(data); setLoading(false); }
  }).catch((err: Error) => {
    if (!cancelled) { setError(err.message || "Failed to load overview"); setLoading(false); }
  });
  return () => { cancelled = true; };
}, [engagementId]);
```

---

### [MEDIUM] SILENT ERROR DISCARD: Secondary Data Load Failures Not Surfaced in UI

**File**: `frontend/src/app/governance/page.tsx:62-74`
**File**: `frontend/src/app/analytics/page.tsx:51-63`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// governance/page.tsx
useEffect(() => {
  let mounted = true;
  fetchPolicies()
    .then((data) => { if (mounted) setPolicies(data); })
    .catch((err) => {
      if (mounted) console.error("Failed to load policies:", err); // only console
    });
  return () => { mounted = false; };
}, []);

// analytics/page.tsx — identical pattern
.catch((err) => {
  if (mounted) console.error("Failed to load metric definitions:", err);
});
```
**Description**: Both pages load secondary data (policies and metric definitions) in standalone effects that log failures only to `console.error`. If these fetches fail, users see a page that appears fully loaded but is missing policy or metric data with no visual indication. The primary data loads use `useEngagementData` which surfaces errors via `PageLayout`. Only the secondary loads are silent.
**Risk**: Users operate under incomplete data without knowing it. This is particularly relevant for `governance/page.tsx` — a missing policy list on a governance page is a meaningful accuracy gap that users may act on incorrectly.
**Recommendation**: Add a `secondaryError` state for each affected page and render it as a dismissible warning banner below the `PageLayout` header content.

---

### [MEDIUM] ACCESSIBILITY: No ARIA Live Regions for Loading States on Async Pages

**File**: `frontend/src/app/dashboard/[engagementId]/page.tsx:89-96`
**File**: `frontend/src/app/tom/[engagementId]/page.tsx:59-67`
**File**: `frontend/src/app/patterns/page.tsx:63-72`
**File**: `frontend/src/app/monitoring/[jobId]/page.tsx:44-52`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// dashboard — loading container has no role or aria-live
if (loading) {
  return (
    <div className="max-w-6xl mx-auto p-8">
      <div className="text-center text-[hsl(var(--muted-foreground))] py-12">
        Loading dashboard...
      </div>
    </div>
  );
}
```
**Description**: Loading states across async data-fetching pages render visible text without `role="status"` or `aria-live="polite"`. Screen readers do not announce these changes because text injected via React virtual DOM replacement is not treated as a live region. `EvidenceUploader` and `shelf-requests/page.tsx` use `role="progressbar"` correctly — the inconsistency suggests the pattern is known but not uniformly applied. Eight or more pages are affected.
**Risk**: Screen reader users receive no auditory feedback during data loading or on completion, making async pages indistinguishable from a hung page during the loading period.
**Recommendation**: Add `role="status"` to loading indicator containers. This is equivalent to `aria-live="polite"` for status messages and requires a one-line change per loading state:
```typescript
<div role="status" className="text-center text-[hsl(var(--muted-foreground))] py-12">
  Loading dashboard...
</div>
```

---

## Low Severity Issues

### [LOW] LIST INDEX KEYS: Six Locations Using Array Index as React Key

**File**: `frontend/src/components/Sidebar.tsx:103`
**File**: `frontend/src/app/monitoring/[jobId]/page.tsx:111`
**File**: `frontend/src/app/simulations/components/ScenarioFinancialColumn.tsx:59`
**File**: `frontend/src/app/lineage/page.tsx:155`
**File**: `frontend/src/app/conformance/page.tsx:503`
**File**: `frontend/src/components/RoadmapTimeline.tsx:136`
**File**: `frontend/src/app/copilot/page.tsx:160`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// Sidebar.tsx:103 — plain string contradictions
{element.contradictions.map((c, i) => (
  <li key={i}>{c}</li>

// monitoring/[jobId]/page.tsx:111 — drift chart (date+magnitude objects)
{driftData.map((d, i) => (
  <div key={i} className="flex items-center gap-3">

// ScenarioFinancialColumn.tsx:59 — sensitivities (have assumption_name)
{topSensitivities.map((s, i) => (
  <div key={i} className="flex items-center justify-between text-sm">

// RoadmapTimeline.tsx:136 — initiatives (have dimension field)
{phase.initiatives.map((init, idx) => (
  <InitiativeRow key={idx} initiative={init} />

// copilot/page.tsx:160 — citations (have source_id)
<div key={citIndex} className="rounded bg-gray-200 px-2 py-1 text-xs"
```
**Description**: Seven list renders use array index as React key. All lists are currently read-only and never reordered. Two locations have stable fields available: `ScenarioFinancialColumn.tsx` sensitivities have `s.assumption_name`; `copilot/page.tsx` citations have `citation.source_id`. `RoadmapTimeline.tsx` initiatives have a `dimension` field. `conformance/page.tsx` deviations lack a stable ID in the `Deviation` interface. `monitoring/[jobId]/page.tsx` `driftData` is derived from deviations (which have `id`) but the mapping strips the id. `Sidebar.tsx` contradictions are plain strings.
**Risk**: Low immediate risk given read-only nature. Risk increases if any list gains sort, filter, or reorder functionality.
**Recommendation**: Use stable keys where available: `s.assumption_name` for sensitivities, `citation.source_id` for copilot citations, `init.dimension` for roadmap initiatives. For remaining locations (plain strings, stripped-id derived data), index is acceptable but document with a comment.

---

### [LOW] ERROR BOUNDARY COVERAGE GAP: No Per-Route `error.tsx` Files

**File**: `frontend/src/app/layout.tsx:24`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
<ErrorBoundary>
  <AppShell>{children}</AppShell>
</ErrorBoundary>
```
**Description**: The root `ErrorBoundary` in `layout.tsx` wraps the full application. `ComponentErrorBoundary` is correctly applied around the four highest-risk rendering components (`BPMNViewer` in two pages, `GraphExplorer`, monitoring dashboard). Only `simulations/` has a Next.js App Router `error.tsx`. A render error in any other complex page component tears down the full `AppShell` including the navigation sidebar, requiring a hard reload to recover.
**Risk**: Any uncaught render error in a page-level component replaces the entire UI (including navigation) with the root fallback, losing all navigation state.
**Recommendation**: Add `app/error.tsx` as a default App Router error boundary for the page layer. Next.js scopes it to the route segment automatically and preserves the parent layout. Priority candidates: `conformance/`, `analytics/`, `governance/`.

---

### [LOW] TYPE ESCAPE: `null as unknown as MonitoringStats` in Hook Initializer

**File**: `frontend/src/hooks/useMonitoringData.ts:98`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
null as unknown as MonitoringStats,
```
**Description**: `useMonitoringStats` passes `null` as the initial value for `MonitoringStats` via a double cast. This is necessary because the generic `useMonitoringFetch<T>` hook types its `initialValue` parameter as the extracted type `T`, which is `MonitoringStats` (a non-nullable object type). Passing `null` would be a type error without the cast. The double cast is constrained to this single initialization point, not spread across multiple use sites as the prior BPMNViewer issue was. Callers of `useMonitoringStats` receive `stats: MonitoringStats` and must null-check before use — the return type annotation does not surface the nullable reality.
**Risk**: Low. The hook is used in one location (`monitoring/page.tsx`) and the caller correctly null-checks `stats` before rendering. However, the type contract is misleading: `stats` is typed `MonitoringStats` but is actually `null` until the first fetch resolves.
**Recommendation**: Change the generic constraint or the return type to `MonitoringStats | null` to make the nullable reality explicit:
```typescript
export function useMonitoringStats(engagementId: string) {
  const { data: stats, loading, error, refresh } = useMonitoringFetch<MonitoringStats | null>(
    ...
    null,  // no cast needed
  );
  return { stats, loading, error, refresh };
}
```

---

## Positive Highlights

1. **JWT token storage is secure**: Auth is exclusively via HttpOnly cookie (`credentials: "include"`) across all API calls. No token in `localStorage` or `sessionStorage` in any source file. The `localStorage` reference in `__tests__/api.test.ts` is test-only infrastructure for a legacy token path that is no longer in the production code.

2. **No `dangerouslySetInnerHTML`**: Zero XSS-via-React-props vectors across all source files.

3. **No `console.log` in source**: All `console.error` calls are in error boundary `componentDidCatch` handlers (intentional diagnostic logging) or the secondary-data error paths (MEDIUM finding above).

4. **No TODO/FIXME comments**: No deferred work markers found across all source files. All `placeholder` occurrences are HTML input `placeholder` attributes, not code debt markers.

5. **No hardcoded secrets or credentials**: No API keys, tokens, passwords, or internal identifiers embedded in source.

6. **BPMNViewer type cast resolved**: Single justified `as BpmnViewer` cast replaces six prior `as unknown as` double casts. Comment explains the runtime safety rationale.

7. **`useMonitoringData` fully clean**: All three hooks use `AbortController` with proper cleanup via `controllerRef.current?.abort()` in the effect cleanup function. All three expose `error: string | null`. The `null as unknown as MonitoringStats` initializer is a LOW finding, not HIGH.

8. **`AbortController` used in 22 of 24 async effect files**: The two exceptions (`portal/[engagementId]/page.tsx`, `dashboard/[engagementId]/page.tsx`) are the MEDIUM finding above.

9. **WebSocket lifecycle correctly managed**: `admin/task-mining/dashboard/page.tsx` clears reconnect timers and closes connections on unmount. Bare `catch {}` blocks for malformed message JSON and WS construction failure are documented with comments — these are acceptable intentional silent failures.

10. **Error boundaries well-layered**: Root `ErrorBoundary` in `layout.tsx`, `ComponentErrorBoundary` with `role="alert"` on four heavy visualization components, and `simulations/error.tsx` for the most complex page.

11. **TypeScript coverage is high**: No `@ts-ignore`, `@ts-nocheck`, or `@ts-expect-error` anywhere. Five `as any` casts confined to Cytoscape style overrides in `GraphExplorer.tsx` — library type gap, not application logic.

12. **Dynamic imports with SSR disabled**: `graph/`, `visualize/`, `ontology/`, and `assessment-matrix/` pages all use `next/dynamic` with `{ ssr: false }` for cytoscape, bpmn-js, and recharts.

13. **Accessibility thorough on interactive components**: `EvidenceUploader`, `GraphExplorer`, `AppShell` sidebar, `RoadmapTimeline` phase toggles (correct `aria-label` and `aria-expanded`), and all form components in admin pages use correct aria patterns.

---

## Checkbox Verification Results

| Criterion | Status | Details |
|-----------|--------|---------|
| NO TODO COMMENTS | PASS | No TODO/FIXME/HACK/PLACEHOLDER code debt markers in source files |
| NO PLACEHOLDERS | PASS | No stub implementations or incomplete functions |
| NO HARDCODED SECRETS | PASS | No credentials, API keys, or secrets |
| PROPER ERROR HANDLING | PARTIAL | MEDIUM: 2 pages missing cancellation guards; 2 pages silently discard secondary data errors |
| NO `any` TYPES | PARTIAL | LOW: `null as unknown as MonitoringStats` in `useMonitoringData.ts:98`; 5 `as any` in `GraphExplorer.tsx` style overrides (library type gap) |
| ERROR BOUNDARIES | PARTIAL | Root boundary + ComponentErrorBoundary on 4 heavy components; only `simulations/` has per-route `error.tsx` |
| ACCESSIBILITY | PARTIAL | MEDIUM: No `role="status"` on loading states across 8+ async pages |

---

## Code Quality Score

**8.0 / 10**

Improved from 7.5 in cycle 6. The BPMNViewer HIGH finding is resolved; the ontology silent error LOW finding is resolved. The remaining issues are: two page effects missing the established cancellation pattern (MEDIUM), two pages with silent secondary data failure (MEDIUM), loading states lacking ARIA live regions (MEDIUM), index keys in six read-only list renders (LOW), absent per-route `error.tsx` files (LOW), and a misleading nullable type in one hook initializer (LOW). No security regressions are present. The codebase is consistent in its patterns with a small number of isolated deviations.
