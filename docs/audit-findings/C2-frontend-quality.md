# C2: Frontend Code Quality Audit Findings

**Auditor**: C2 (Frontend Quality Auditor)
**Scope**: `frontend/src/` — React component patterns, error boundaries, accessibility, token storage security, state management
**Date**: 2026-03-19
**Prior Audit**: 2026-02-26 (findings superseded by this report)

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 3     |
| MEDIUM   | 4     |
| LOW      | 4     |
| **Total** | **11** |

---

## Resolved Since Prior Audit (2026-02-26)

The following findings from the prior audit have been closed in the current codebase:

- **CRITICAL resolved — JWT localStorage read removed from `EvidenceUploader`**: The `localStorage.getItem("kmflow_token")` call no longer exists in `EvidenceUploader.tsx`. Auth is now exclusively via `credentials: "include"` (HttpOnly cookie), matching the shared API client.
- **Conformance page migrated to shared API client**: Raw `fetch` calls replaced with `apiGet` / `apiPost` from `@/lib/api`. The local `API_BASE` constant is gone. `AbortController` is now used correctly.
- **Portal upload page inline styles removed**: The page now uses Tailwind classes (`className="mx-auto max-w-3xl px-6 py-8"`).
- **`useEffect` dependency lint suppression noted**: The `// eslint-disable-line react-hooks/exhaustive-deps` comment remains at `conformance/page.tsx:64`, but the underlying pattern (calling a non-`useCallback` function) is now mitigated by an `AbortController` cleanup in the return.

---

## High Severity Issues

### [HIGH] TYPE SAFETY: Pervasive `any` Types in Third-Party Integration Components

**File**: `frontend/src/components/BPMNViewer.tsx:48,76,91,92,94,154,155`
**File**: `frontend/src/components/GraphExplorer.tsx:44,90,95,97,105,135,161,191,202,207,214,221,228,232,259`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// BPMNViewer.tsx:48,76,91-94
const viewerRef = useRef<any>(null);
const canvas = viewer.get("canvas") as any;
const overlays = viewer.get("overlays") as any;
const elementRegistry = viewer.get("elementRegistry") as any;
elementRegistry.forEach((element: any) => {
// GraphExplorer.tsx:44,95,202
const cyRef = useRef<any>(null);
"background-color": (ele: any) => NODE_COLORS[ele.data("type")] ?? "#9ca3af",
cy.on("tap", "node", (event: any) => {
```
**Description**: Both `BPMNViewer` and `GraphExplorer` use `any` types throughout — for library-provided references, service objects (`canvas`, `overlays`, `elementRegistry`), and all event parameters. The `cytoscape` library ships TypeScript declarations (`Core`, `NodeSingular`, `EventObject`). The `bpmn-js` community typings are available via `@types/bpmn-js`. All 22 `any` usages across these two files bypass compiler checking on third-party API interactions.
**Risk**: Runtime errors from incorrect property access on library objects are not caught at compile time. `useRef<any>` specifically suppresses the null-check that `useRef<BpmnViewer | null>` would enforce, masking potential null-dereference bugs during viewer lifecycle transitions.
**Recommendation**: For cytoscape, replace `any` with the library's exported `Core`, `NodeSingular`, and `EdgeSingular` types. For bpmn-js, define local minimal interfaces for the service objects in use:
```typescript
interface BpmnCanvas { zoom(value: string): void; viewbox(): { x: number; y: number; width: number; height: number }; viewbox(box: object): void; }
interface BpmnOverlays { add(elementId: string, type: string, overlay: object): void; }
```

---

### [HIGH] MISSING CLEANUP: `useMonitoringData` Hooks Have No AbortController

**File**: `frontend/src/hooks/useMonitoringData.ts:51-67,76-92,101-119`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
const refresh = useCallback(async () => {
  setLoading(true);
  try {
    const data = await apiGet<MonitoringStats>(`/api/v1/monitoring/stats/${engagementId}`);
    setStats(data);
  } catch {
    setStats(null);
  } finally {
    setLoading(false);
  }
}, [engagementId]);

useEffect(() => {
  refresh();
}, [refresh]);
// No cleanup — no AbortController, no cancelled flag
```
**Description**: All three hooks in `useMonitoringData.ts` (`useMonitoringStats`, `useMonitoringJobs`, `useMonitoringAlerts`) fire async `apiGet` calls from `useEffect` with no mechanism to cancel in-flight requests on unmount. When a component using these hooks unmounts while a fetch is in flight (e.g., navigation away from a monitoring page), the `setStats`/`setJobs`/`setAlerts` calls will still execute and attempt to update state on an unmounted component. The rest of the codebase uses `AbortController` consistently for this pattern (`useDataLoader`, `useEngagementData`, `conformance/page.tsx`, `monitoring/[jobId]/page.tsx`).
**Risk**: State updates on unmounted components produce React warnings in development and can cause subtle state corruption or memory retention in production, particularly in monitoring contexts where these hooks may be polled on interval.
**Recommendation**: Apply the same `AbortController` pattern used across the rest of the codebase. Pass the `signal` to `apiGet` and clean up in the `useEffect` return:
```typescript
useEffect(() => {
  const controller = new AbortController();
  (async () => {
    setLoading(true);
    try {
      const data = await apiGet<MonitoringStats>(
        `/api/v1/monitoring/stats/${engagementId}`,
        controller.signal,
      );
      if (!controller.signal.aborted) setStats(data);
    } catch {
      if (!controller.signal.aborted) setStats(null);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  })();
  return () => controller.abort();
}, [engagementId]);
```

---

### [HIGH] SILENT ERROR HANDLING: `useMonitoringData` Swallows All Errors Without Logging or Exposure

**File**: `frontend/src/hooks/useMonitoringData.ts:58-60,83-85,108-110`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
  } catch {
    setStats(null);   // Bare catch — error swallowed, no log, no error state
  } finally {
    setLoading(false);
  }
```
**Description**: All three monitoring hooks use bare `catch {}` blocks with no parameter, no logging, and no error state surface. Consumers receive `loading: false, stats: null` but cannot distinguish "data unavailable" from "API failure." The monitoring page (`app/monitoring/page.tsx`) will silently render empty dashboards on backend errors, network failures, or auth expiry with no indication to the user. This diverges from every other data-fetching hook in the codebase, all of which expose an `error` return value.
**Risk**: Silent failures on monitoring pages mean operational problems (backend crash, auth expiry, network partition) are invisible to users who see empty tables with no error message and no recovery path.
**Recommendation**: Add an `error` state and surface it alongside `loading`:
```typescript
const [error, setError] = useState<string | null>(null);
// In catch:
} catch (err) {
  if (!controller.signal.aborted) {
    setStats(null);
    setError(err instanceof Error ? err.message : "Failed to load monitoring stats");
  }
}
// Return: { stats, loading, error, refresh }
```

---

## Medium Severity Issues

### [MEDIUM] ACCESSIBILITY: Form Inputs Without Labels in `FinancialTab` Assumption Form

**File**: `frontend/src/app/simulations/components/FinancialTab.tsx:116-178`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
<input
  type="text"
  placeholder="Name"
  value={newAssumption.name}
  onChange={(e) => onNewAssumptionChange({ ...newAssumption, name: e.target.value })}
  className="border rounded px-3 py-1.5 text-sm"
/>
<label className="text-sm">Confidence:</label>
<input type="range" min="0" max="1" step="0.05" value={newAssumption.confidence} ... />
```
**Description**: The financial assumption creation form has five inputs (Name, Assumption Type, Value, Unit, and Confidence range) with no `<label>` elements or `aria-label` attributes. Placeholders are the only label mechanism; they disappear on input. The `<label className="text-sm">Confidence:</label>` at line 164 has no `htmlFor`, making it unassociated with the range input it visually labels.
**Risk**: Screen reader users cannot identify what each field expects. The unassociated Confidence label means assistive technology announces the range input without context.
**Recommendation**: Add `aria-label` to each unlabeled input, or restructure as `<label htmlFor="...">`/`<input id="...">` pairs. The `<label>Confidence:</label>` must gain `htmlFor="assumption-confidence"` and the range input must gain `id="assumption-confidence"`.

---

### [MEDIUM] ACCESSIBILITY: Icon-Only Delete Button in `FinancialTab` Has No Accessible Name

**File**: `frontend/src/app/simulations/components/FinancialTab.tsx:228-233`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
<Button
  size="sm"
  variant="ghost"
  onClick={() => onDeleteAssumption(a.id)}
>
  <Trash2 className="h-3 w-3 text-muted-foreground" />
</Button>
```
**Description**: The delete button for financial assumptions renders only a `Trash2` icon with no text content, `aria-label`, or `title`. Screen readers announce this as "button" with no indication of what it deletes. The button sits in a table row alongside assumption data but has no programmatic association with the row label.
**Risk**: Screen reader users cannot distinguish which assumption a delete button targets, making the assumptions table non-functional with assistive technology.
**Recommendation**: Add `aria-label={`Delete assumption ${a.name}`}` to the Button component.

---

### [MEDIUM] HARDCODED ENGAGEMENT IDs IN PRODUCTION NAVIGATION

**File**: `frontend/src/components/shell/AppShell.tsx:64,71,73,80`
**File**: `frontend/src/app/page.tsx:24,30`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
{ label: "Knowledge Graph", href: "/graph/1db9aa11-c73b-5867-82a3-864dd695cf23", icon: Network },
{ label: "TOM Alignment", href: "/tom/1db9aa11-c73b-5867-82a3-864dd695cf23", icon: Target },
{ label: "Visualize", href: "/visualize/1db9aa11-c73b-5867-82a3-864dd695cf23", icon: Eye },
{ label: "Roadmap", href: "/roadmap/1db9aa11-c73b-5867-82a3-864dd695cf23", icon: Map },
```
**Description**: Four sidebar navigation items and two homepage quick-action cards hard-code the engagement UUID `1db9aa11-c73b-5867-82a3-864dd695cf23` directly in the href. This appears to be a development fixture/demo engagement. Every user who clicks these navigation links is routed to the same single engagement regardless of which engagement they are working on. The UUID is embedded in the client-rendered HTML shipped to all users.
**Risk**: Multi-engagement usage is broken for these four features via the sidebar. This also reveals an internal engagement UUID in all client sessions.
**Recommendation**: The sidebar links for engagement-scoped features should navigate to an engagement selector, or read a "current engagement" from application state (context, URL params, or user profile). Remove the hardcoded UUIDs and replace with either dynamic routing or a redirect to an engagement picker.

---

### [MEDIUM] `useEffect` ESLint Suppression Without Justification Comment

**File**: `frontend/src/app/conformance/page.tsx:64`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
useEffect(() => {
  loadReferenceModels();
  return () => {
    abortRef.current?.abort();
  };
}, []); // eslint-disable-line react-hooks/exhaustive-deps
```
**Description**: The `eslint-disable-line react-hooks/exhaustive-deps` comment suppresses a legitimate lint warning without an explanatory comment. `loadReferenceModels` is declared as a `const` (not `useCallback`) and not included in the dependency array. The intent is to run once on mount — which is correct — but the suppression comment gives no indication of this intent to future maintainers, who may add state dependencies to `loadReferenceModels` and encounter a stale closure.
**Risk**: Low immediate risk since `loadReferenceModels` currently closes over no mutable state. If a prop or state variable is added to the function body in the future, the stale closure bug will be silent.
**Recommendation**: Add an explanatory comment: `// eslint-disable-line react-hooks/exhaustive-deps -- intentional mount-only; loadReferenceModels uses only the abortRef which is stable`. Alternatively, wrap `loadReferenceModels` in `useCallback([])` to satisfy the rule without suppression.

---

## Low Severity Issues

### [LOW] ERROR BOUNDARY COVERAGE GAP: No Per-Route `error.tsx` Files

**File**: `frontend/src/app/layout.tsx:24`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
<ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
  <ErrorBoundary>
    <AppShell>{children}</AppShell>
  </ErrorBoundary>
</ThemeProvider>
```
**Description**: The root `ErrorBoundary` wraps the full app. `ComponentErrorBoundary` is correctly applied around `BPMNViewer`, `GraphExplorer`, and the monitoring dashboard — these are the highest-risk crash points and their coverage is good. However, there are no Next.js App Router `error.tsx` files at the route segment level. A render error in a page component (e.g., `simulations/page.tsx` with its 11 state slices) tears down the full `AppShell` including the navigation sidebar, leaving users unable to navigate without a hard reload.
**Risk**: Any uncaught render error in a page-level component replaces the entire UI (including navigation) with the root fallback. Recovery requires a full page reload.
**Recommendation**: Add `app/error.tsx` at the segment level for data-heavy pages (`simulations`, `conformance`, `analytics`). Next.js `error.tsx` automatically scopes the error boundary to the route segment and preserves the surrounding layout.

---

### [LOW] INLINE STYLE FOR DYNAMIC HEIGHT ON GRAPH PAGE

**File**: `frontend/src/app/graph/[engagementId]/page.tsx:82`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
<div style={{ height: "calc(100vh - 250px)" }}>
```
**Description**: A single inline style uses `calc(100vh - 250px)` for the graph container height. The rest of the application uses Tailwind exclusively. This is a minor consistency deviation; the value is straightforward to express as a Tailwind arbitrary value.
**Risk**: No functional risk. Minor theme and dark-mode consistency concern if height-related variables are introduced later.
**Recommendation**: Replace with `className="h-[calc(100vh-250px)]"`.

---

### [LOW] `OntologyGraph` USES SYNCHRONOUS `import` FOR CYTOSCAPE (SSR CONCERN)

**File**: `frontend/src/app/ontology/OntologyGraph.tsx:4`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
import cytoscape from "cytoscape";
```
**Description**: `OntologyGraph.tsx` has a `"use client"` directive and imports cytoscape synchronously at the top level. `GraphExplorer.tsx` correctly uses a dynamic `await import("cytoscape")` inside a `useEffect` to avoid SSR issues. While the `"use client"` directive prevents SSR execution of this component's render function, the static import is still processed by the module bundler synchronously and included in the initial chunk rather than being deferred to a lazy chunk.
**Risk**: `OntologyGraph` is not wrapped in `next/dynamic` with `ssr: false`, unlike the graph and BPMN pages. If Next.js ever attempts to render this component on the server (e.g., if the `"use client"` boundary is accidentally removed), the cytoscape DOM dependency would throw. Additionally, the synchronous import adds cytoscape to the initial JS bundle for the ontology page rather than loading it lazily.
**Recommendation**: Wrap the import with `next/dynamic` with `ssr: false` (matching the pattern used in `app/graph/[engagementId]/page.tsx`) or convert the cytoscape import to a dynamic `import()` inside `useEffect`, matching the pattern in `GraphExplorer`.

---

### [LOW] SIDEBAR COLLAPSE TOGGLE MISSING `aria-expanded`

**File**: `frontend/src/components/shell/AppShell.tsx:255-265`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
<button
  onClick={() => setSidebarCollapsed((v) => !v)}
  className="rounded-md p-1.5 hover:bg-white/10 transition-colors"
  aria-label="Toggle sidebar"
>
  {sidebarCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
</button>
```
**Description**: The sidebar collapse toggle has `aria-label="Toggle sidebar"` but does not expose the current expanded/collapsed state via `aria-expanded`. The static label "Toggle sidebar" also does not indicate the resulting action (expand or collapse), only that a toggle occurs.
**Risk**: Screen reader users cannot determine whether the sidebar is currently open or closed from this button alone. WCAG 4.1.2 (Name, Role, Value) requires interactive controls to expose their current state.
**Recommendation**: Add `aria-expanded={!sidebarCollapsed}` and use a dynamic label: `aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}`.

---

## Positive Highlights

1. **JWT token vulnerability resolved**: Prior CRITICAL finding (localStorage JWT read in `EvidenceUploader`) is confirmed resolved. Auth is now exclusively via HttpOnly cookie (`credentials: "include"`) across all API calls including the uploader.

2. **No `dangerouslySetInnerHTML` anywhere**: Zero XSS-via-React-props vectors found across all 123 source files.

3. **No `console.log` in source code**: All four `console.error` calls found are appropriate — inside error boundary `componentDidCatch` (intentional) and two legitimate data-load error logs in `analytics/page.tsx` and `governance/page.tsx`.

4. **No TODO comments**: No TODO, FIXME, HACK, or placeholder comments in source files. The `upload/page.tsx` stub callback comment (`// Could trigger a toast notification`) is informational, not a deferred implementation.

5. **Error boundaries well-applied to high-risk renderers**: `ComponentErrorBoundary` wraps `BPMNViewer` in both the visualize and heatmap pages, `GraphExplorer` in the graph page, and the monitoring dashboard. The root `ErrorBoundary` in `layout.tsx` provides the final safety net.

6. **WebSocket lifecycle correctly managed**: `useWebSocket` and the inline WebSocket in `TaskMiningDashboard` both clear reconnect timers and close connections on unmount. Exponential backoff is correctly implemented in the dashboard.

7. **`AbortController` used consistently across 24 files**: All data-loading hooks and the majority of direct `useEffect` data fetches use `AbortController` with cleanup to prevent state updates on unmounted components. `useMonitoringData.ts` is the sole exception (see HIGH findings above).

8. **API client is strongly typed**: All API functions use generic type parameters (`apiGet<T>`, `apiPost<T>`) with explicit interfaces. No `any` in `lib/api/` — the 22 `any` usages are confined to the third-party library integration components.

9. **Accessibility is thorough in interactive components**: `EvidenceUploader` uses `role="button"`, `aria-label`, `tabIndex`, Enter/Space key handling, and `role="progressbar"` with value attributes. `GraphExplorer` uses `aria-label` and `aria-pressed` on the node type filter buttons. `GapTable` implements accessible sortable column headers with `role="button"`, `tabIndex`, and `onKeyDown`.

10. **No hardcoded secrets or credentials**: No API keys, passwords, or secrets found in source files.

---

## Checkbox Verification Results

| Criterion | Status | Details |
|-----------|--------|---------|
| NO TODO COMMENTS | PASS | No TODO/FIXME/HACK comments found in 123 source files |
| NO PLACEHOLDERS | PASS | No stub implementations; stub callback comment in `upload/page.tsx` is informational only |
| NO HARDCODED SECRETS | PASS | No credentials or API keys; hardcoded engagement UUID in navigation is a functional defect (MEDIUM finding), not a secret |
| PROPER ERROR HANDLING | FAIL | `useMonitoringData.ts` silently swallows all errors in 3 hooks with bare `catch {}` (HIGH finding) |
| NO `any` TYPES | FAIL | 22 `any` usages in `BPMNViewer.tsx` (7) and `GraphExplorer.tsx` (15); all confined to third-party library integration |
| ERROR BOUNDARIES | PARTIAL | Root boundary + `ComponentErrorBoundary` on 4 heavy components is good; no per-route `error.tsx` files (LOW finding) |
