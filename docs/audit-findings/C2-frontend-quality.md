# C2: Frontend Code Quality Audit Findings

**Auditor**: C2 (Frontend Quality Auditor)
**Scope**: `frontend/src/` — React component patterns, error boundaries, accessibility, token storage security, state management
**Date**: 2026-03-20
**Prior Audit**: 2026-03-19 (findings updated in this report)

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 1     |
| MEDIUM   | 3     |
| LOW      | 4     |
| **Total** | **8** |

**Trend**: Stable since prior audit. The one HIGH finding (BPMNViewer double cast) persists. Three MEDIUM findings identified in this cycle: missing cancellation in two page-level effects, secondary data failure silently swallowed in two pages, and missing ARIA live regions for async loading states. Four LOW findings: index keys in four locations, per-route error boundary gaps, ontology silent error discard, and inline graph height (confirmed resolved from prior audit).

---

## Resolved Since Prior Audit (2026-02-26)

The following findings from the earlier audit cycle are confirmed closed in the current codebase:

- **CRITICAL resolved — JWT localStorage read removed**: The `localStorage.getItem("kmflow_token")` call confirmed absent from all source files. Auth is exclusively via `credentials: "include"` (HttpOnly cookie).
- **HIGH resolved — `useMonitoringData` AbortController**: `useMonitoringData.ts` now uses a shared `useMonitoringFetch` generic that passes `AbortController` correctly and exposes an `error` state on all three hooks.
- **HIGH resolved — `useMonitoringData` silent error swallowing**: All three hooks now expose `error: string | null` and set it on failure; bare `catch {}` blocks are gone.
- **MEDIUM resolved — Hardcoded engagement UUIDs in navigation**: `AppShell.tsx` sidebar links and `app/page.tsx` quick actions now use generic routes without any embedded engagement UUIDs.
- **MEDIUM resolved — `FinancialTab` unlabeled form inputs**: All five inputs in the assumption form now have `aria-label` attributes.
- **MEDIUM resolved — `FinancialTab` icon-only delete button**: Delete button has `aria-label={`Delete assumption ${a.name}`}`.
- **MEDIUM resolved — `conformance/page.tsx` eslint suppression**: The suppression comment is now documented with justification.
- **LOW resolved — `AppShell` sidebar toggle missing `aria-expanded`**: The collapse toggle now has `aria-expanded={!sidebarCollapsed}`.
- **LOW resolved — `OntologyGraph` synchronous cytoscape import**: Uses dynamic `import("cytoscape")` inside `useEffect`; wrapped with `next/dynamic` and `ssr: false`.
- **LOW resolved — inline graph height**: `graph/[engagementId]/page.tsx` now uses `className="h-[calc(100vh-250px)]"` (Tailwind arbitrary value), not inline style.

---

## High Severity Issues

### [HIGH] TYPE SAFETY: `as unknown as` Cast Bypasses Type System in BPMNViewer

**File**: `frontend/src/components/BPMNViewer.tsx:95`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
viewerRef.current = viewer as unknown as BpmnViewer;
await (viewer as unknown as BpmnViewer).importXML(bpmnXml);
const canvas = (viewer as unknown as BpmnViewer).get("canvas");
const overlays = (viewer as unknown as BpmnViewer).get("overlays");
const elementRegistry = (viewer as unknown as BpmnViewer).get("elementRegistry");
const eventBus = (viewer as unknown as BpmnViewer).get("eventBus");
```
**Description**: The `BPMNViewer` component defines local interface stubs (`BpmnCanvas`, `BpmnOverlays`, `BpmnElementRegistry`, `BpmnEventBus`, `BpmnViewer`) and then casts the dynamically-imported `bpmn-js` instance through `as unknown as BpmnViewer` six times. This double cast is TypeScript's escape hatch for unsafe coercions — it unconditionally succeeds at compile time regardless of whether the runtime type matches the declared interface. Additionally, `GraphExplorer.tsx` has five `as any` casts in Cytoscape style properties (`"font-weight": "bold" as any`, `"text-background-padding": "2px" as any`, `nodeRepulsion: 8000 as any`) to work around Cytoscape's style type definitions being narrower than its actual accepted values.
**Risk**: Double casts on the bpmn-js viewer instance mean that any property access mismatch between the local stub interfaces and the actual library object is silently ignored by the compiler. If the `bpmn-js` library version changes its service API shape, TypeScript will not catch the mismatch.
**Recommendation**: Type the initial import result directly as `BpmnViewer` in a single cast rather than double-casting each use site. For `GraphExplorer`, the `as any` casts on Cytoscape style properties are an acceptable library-type-gap workaround; add a comment on each explaining the rationale.

---

## Medium Severity Issues

### [MEDIUM] ASYNC SAFETY: Missing Cancellation Guard in `portal/[engagementId]/page.tsx` and `dashboard/[engagementId]/page.tsx` useEffect

**File**: `frontend/src/app/portal/[engagementId]/page.tsx:15`
**File**: `frontend/src/app/dashboard/[engagementId]/page.tsx:53`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// portal/[engagementId]/page.tsx — no cancelled ref
useEffect(() => {
  if (!engagementId) return;
  fetchPortalOverview(engagementId)
    .then((data) => {
      setOverview(data);      // state update after potential unmount
      setLoading(false);
    })
    .catch((err: Error) => {
      setError(err.message || "Failed to load overview");
      setLoading(false);
    });
}, [engagementId]);

// dashboard/[engagementId]/page.tsx — no cleanup return
useEffect(() => {
  async function loadData() { ... }
  loadData();
}, [engagementId]);
```
**Description**: The `portal/[engagementId]/page.tsx` effect uses `.then()/.catch()` chains without a `cancelled` ref guard or cleanup return. If the component unmounts before the fetch resolves (e.g., the user navigates away), both `setOverview` and `setLoading(false)` will execute on an unmounted component, producing the React "Can't perform a state update on an unmounted component" warning. The `dashboard/[engagementId]/page.tsx` `loadData` function also has no cancellation guard — no `cancelled` ref, no `AbortController`, and no cleanup return from the `useEffect`. The rest of the codebase consistently uses either `cancelled` refs or `AbortController` for async effects (confirmed in 22 of 24 files with async effects).
**Risk**: React will log an error for state updates on unmounted components. In React 18 concurrent mode, this can produce duplicate state updates on strict mode remounts if the async request completes twice. The inconsistency with the established codebase pattern increases maintainability burden.
**Recommendation**: Apply the same `cancelled` ref pattern already established in `monitoring/[jobId]/page.tsx:21` and `portal/[engagementId]/evidence/page.tsx:21`:
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
**Description**: Both `governance/page.tsx` and `analytics/page.tsx` load secondary data (policies and metric definitions) in separate effects that only log to `console.error` on failure — nothing is surfaced in the UI. If `fetchPolicies()` or `fetchMetricDefinitions()` fails (network error, 500, auth expiry), the user sees a page that appears to have loaded successfully but is missing data, with no indication that policies or metric definitions are unavailable. The primary data loads in both pages use the `useEngagementData` hook which does surface errors via `PageLayout`. Only the secondary data loads are silent.
**Risk**: Users operate under incomplete data (missing policies/metrics) without knowing it. Particularly relevant for `governance/page.tsx` — a page about data governance showing incorrect policy state is a meaningful accuracy gap.
**Recommendation**: Introduce a dedicated `secondaryError` state variable for each affected page and render it as a non-blocking warning (e.g., dismissible banner below the main content) rather than replacing the full page view. Alternatively, include both data loads in the `useEngagementData` hook call for a unified error surface.

---

### [MEDIUM] ACCESSIBILITY: No ARIA Live Regions for Loading States on Async Pages

**File**: `frontend/src/app/dashboard/[engagementId]/page.tsx:89-96`
**File**: `frontend/src/app/tom/[engagementId]/page.tsx:59-67`
**File**: `frontend/src/app/patterns/page.tsx:63-72`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// dashboard page — loading state has no aria-live announcement
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
**Description**: Loading states across async data-fetching pages render text like "Loading dashboard...", "Loading TOM dashboard...", "Loading patterns..." without `aria-live="polite"` or `role="status"`. Screen readers do not announce these loading state changes because the text is injected via React's virtual DOM replacement, not via a live region. When the loaded content replaces the loading indicator, there is also no announcement that data has finished loading or that an error has occurred. The `EvidenceUploader` and `shelf-requests/page.tsx` progress bars do use `role="progressbar"` with `aria-valuenow/min/max` correctly — this inconsistency suggests the pattern is known but not uniformly applied.
**Risk**: Screen reader users have no auditory feedback during data loading and no confirmation that loading has completed. On pages with engagement-specific data (dashboard, TOM, graph), this creates a silent blank period that is indistinguishable from a hung page.
**Recommendation**: Add `role="status"` to loading indicator containers (this is equivalent to `aria-live="polite"` for status messages):
```typescript
<div role="status" className="text-center text-[hsl(var(--muted-foreground))] py-12">
  Loading dashboard...
</div>
```
This is a one-line change per loading state and applies to all 8+ pages with conditional loading renders.

---

## Low Severity Issues

### [LOW] ERROR BOUNDARY COVERAGE GAP: No Per-Route `error.tsx` Files

**File**: `frontend/src/app/layout.tsx:24`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
<ErrorBoundary>
  <AppShell>{children}</AppShell>
</ErrorBoundary>
```
**Description**: The root `ErrorBoundary` in `layout.tsx` wraps the full application. `ComponentErrorBoundary` is correctly applied around the four highest-risk rendering components (`BPMNViewer` in two pages, `GraphExplorer`, monitoring dashboard). Only `simulations/` has a Next.js App Router `error.tsx`. A render error in any other complex page component tears down the full `AppShell` including the navigation sidebar. Users cannot navigate away without a hard reload.
**Risk**: Any uncaught render error in a page-level component replaces the entire UI (including navigation) with the root fallback, losing all navigation state. Recovery requires a full page reload.
**Recommendation**: Add `app/error.tsx` as the default App Router error boundary for the page layer. Next.js scopes `error.tsx` to the route segment automatically and preserves the parent layout (including `AppShell`). Target initially: `conformance/`, `analytics/`, and `governance/` — pages with the most state slices.

---

### [LOW] SILENT ERROR DISCARD: `ontology/page.tsx` Validate and Export Handlers

**File**: `frontend/src/app/ontology/page.tsx:85-88, 101-103`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
} catch {
  // Validation errors handled in UI
}
// ...
} catch {
  // Export errors handled silently
}
```
**Description**: The `handleValidate` and `handleExport` functions have bare `catch {}` blocks that discard errors entirely. If the validation API fails (e.g., network error, 500 response), the user sees no feedback — the Validate button simply stops spinning. The export catch comment `// Export errors handled silently` acknowledges the silent failure. Both are user-initiated operations.
**Risk**: Users may retry the same failed operation repeatedly or incorrectly assume the operation succeeded.
**Recommendation**: Expose error state for both operations alongside the existing `deriveError` state and render a dismissible error message below the respective buttons.

---

### [LOW] LIST INDEX KEYS: Four Locations Using Array Index as React Key

**File**: `frontend/src/components/Sidebar.tsx:103`
**File**: `frontend/src/app/monitoring/[jobId]/page.tsx:111`
**File**: `frontend/src/app/simulations/components/ScenarioFinancialColumn.tsx:59`
**File**: `frontend/src/app/lineage/page.tsx:155`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// Sidebar.tsx:103 — contradictions list
{element.contradictions.map((c, i) => (
  <li key={i}>{c}</li>

// monitoring/[jobId]/page.tsx:111 — drift chart bars
{driftData.map((d, i) => (
  <div key={i} className="flex items-center gap-3">

// ScenarioFinancialColumn.tsx:59 — sensitivities list
{topSensitivities.map((s, i) => (
  <div key={i} className="flex items-center justify-between text-sm">

// lineage/page.tsx:155 — transformation chain steps
{record.transformation_chain.map((step, i) => (
  <div key={i} className="text-xs bg-muted rounded px-2 py-1">
```
**Description**: Four components use array index as the React `key`. All four lists are effectively read-only and never reordered, so reconciliation correctness is not affected in the current implementation. Deviation objects in `monitoring/[jobId]` have stable `id` fields usable as keys; sensitivity entries in `ScenarioFinancialColumn` have `assumption_name`; lineage transformation steps are untyped `unknown[]` (no guaranteed stable ID). The `Sidebar.tsx` contradictions are plain strings with no stable ID.
**Risk**: Low immediate risk given read-only nature. Risk increases if any list gains sort/filter/delete functionality without updating the key strategy.
**Recommendation**: Use stable keys where available (`deviation.id`, `s.assumption_name`). For plain string lists (`Sidebar.tsx` contradictions) and untyped transformation chains (`lineage/page.tsx`), index is acceptable but should be documented with a comment.

---

### [LOW] COPILOT CITATION LIST USES INDEX KEY

**File**: `frontend/src/app/copilot/page.tsx:158-160`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
{message.citations.map((citation, citIndex) => (
  <div
    key={citIndex}
    className="rounded bg-gray-200 px-2 py-1 text-xs"
```
**Description**: The citation list in the copilot chat uses `citIndex` (array index) as the key. Citations are per-message and the list is append-only. `source_id` is available on each citation object and is a stable identifier. The `messages.map` at line 133 uses a composite `key={`${message.role}-${index}`}` which is better but still index-based.
**Risk**: Low — citation lists are read-only per message and never reordered. However, using `source_id` is straightforward.
**Recommendation**: Use `citation.source_id` as key: `key={citation.source_id}`. For the message list, consider a `useRef` counter to assign monotonic IDs to messages at creation time.

---

## Positive Highlights

1. **JWT token storage is secure**: Auth is exclusively via HttpOnly cookie (`credentials: "include"`) across all 150+ API calls. No token in `localStorage` or `sessionStorage` in any source file.

2. **No `dangerouslySetInnerHTML`**: Zero XSS-via-React-props vectors across all source files.

3. **No `console.log` in source**: All `console.error` calls are in error boundary `componentDidCatch` handlers (intentional diagnostic logging) or secondary data-load error paths (MEDIUM finding above).

4. **No TODO/FIXME comments**: No deferred work markers found across all source files.

5. **No hardcoded secrets or credentials**: No API keys, tokens, passwords, or internal identifiers embedded in source.

6. **`useMonitoringData` fully remediated**: All three monitoring hooks use `AbortController` with cleanup and expose `error` state consistently.

7. **Error boundaries well-layered**: Root `ErrorBoundary` in `layout.tsx`, `ComponentErrorBoundary` on four heavy visualization components, and `simulations/error.tsx` for the most complex page.

8. **WebSocket lifecycle correctly managed**: `useWebSocket` clears reconnect timers and closes connections on unmount. Reconnect logic uses a retry cap.

9. **`AbortController` used consistently in 22 of 24 async effect files**: The two exceptions (`portal/[engagementId]/page.tsx`, `dashboard/[engagementId]/page.tsx`) are the MEDIUM finding above.

10. **Accessibility thorough on interactive components**: `EvidenceUploader`, `GraphExplorer`, `AppShell` sidebar, and all form components in admin pages use correct `aria-label`, `aria-expanded`, `role`, and keyboard handler patterns.

11. **TypeScript type coverage is high**: No `any` in `lib/api/` or any hook. Five `as any` casts confined to Cytoscape style overrides; six `as unknown as BpmnViewer` in `BPMNViewer.tsx` (HIGH finding above). No `@ts-ignore`, `@ts-nocheck`, or `@ts-expect-error` anywhere.

12. **Dynamic imports with SSR disabled for heavy visualization libs**: `graph/`, `visualize/`, `ontology/`, and `assessment-matrix/` pages all use `next/dynamic` with `{ ssr: false }` for cytoscape, bpmn-js, and recharts.

---

## Checkbox Verification Results

| Criterion | Status | Details |
|-----------|--------|---------|
| NO TODO COMMENTS | PASS | No TODO/FIXME/HACK/PLACEHOLDER comments found in source files |
| NO PLACEHOLDERS | PASS | No stub implementations or incomplete functions |
| NO HARDCODED SECRETS | PASS | No credentials, API keys, or secrets |
| PROPER ERROR HANDLING | PARTIAL | MEDIUM: 2 pages missing cancellation guards; 2 pages silently discard secondary data errors. LOW: `ontology/page.tsx` discards validate/export errors |
| NO `any` TYPES | PARTIAL | HIGH: 6 `as unknown as BpmnViewer` casts in `BPMNViewer.tsx`; 5 `as any` in `GraphExplorer.tsx` Cytoscape style overrides |
| ERROR BOUNDARIES | PARTIAL | Root boundary + ComponentErrorBoundary on 4 heavy components appropriate; only `simulations/` has per-route `error.tsx` |
| ACCESSIBILITY | PARTIAL | MEDIUM: No `role="status"` on loading states across 8+ async pages |

---

## Code Quality Score

**7.5 / 10**

The codebase demonstrates strong fundamentals: no security vulnerabilities, no TODO debt, consistent AbortController cleanup on nearly all async effects, proper HttpOnly cookie auth, zero dangerouslySetInnerHTML, and thorough accessibility on interactive components. The score is limited by the type-system escape hatch in `BPMNViewer`, two page-level effects missing the established cancellation pattern, silent secondary data failures in governance and analytics pages, and absent ARIA live regions for loading states. No regressions from the prior audit cycle are present.
