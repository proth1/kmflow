# C2: Frontend Code Quality Audit Findings

**Auditor**: C2 (Frontend Quality Auditor)
**Scope**: `frontend/src/` — React component patterns, error boundaries, accessibility, token storage security, state management
**Date**: 2026-02-26
**Prior Audit**: 2026-02-20 (findings superseded by this report)

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1     |
| HIGH     | 3     |
| MEDIUM   | 5     |
| LOW      | 4     |
| **Total** | **13** |

---

## Improvements Since Prior Audit (2026-02-20)

The following findings from the prior audit have been resolved:

- **ErrorBoundary now exists and is applied**: `ErrorBoundary` wraps `AppShell` in the root layout.
- **`api.ts` god file split**: The monolithic 1,694-line `api.ts` has been split into domain modules under `frontend/src/lib/api/`. The old path now re-exports via a barrel.
- **`AnnotationPanel` auth fixed**: Now uses `apiGet`, `apiPost`, `apiDelete` from the shared API client consistently.
- **Simulations page refactored**: Extracted into 8 child tab components under `app/simulations/components/`. The page coordinator is now 517 lines.
- **`EvidenceUploader` stale closure fixed**: Index tracking now uses a functional `setUploads` updater that reads `prev.length` from the actual current state.

---

## Critical Issues

### [CRITICAL] SECURITY: JWT Token Read from `localStorage` in `EvidenceUploader`

**File**: `frontend/src/components/EvidenceUploader.tsx:107`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// Mirror the auth strategy from api.ts: cookie via credentials + optional
// legacy localStorage token for backward compatibility.
const token = typeof window !== "undefined" ? localStorage.getItem("kmflow_token") : null;
const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
```
**Description**: This is the last surviving reference to `localStorage` for token retrieval. The comment describes it as a "legacy" backward-compat path, but backward compatibility with an insecure pattern means the insecure path remains active for any client that has a token stored there. The shared API client (`lib/api/client.ts`) correctly uses only `credentials: "include"` (HttpOnly cookies) with no localStorage read. `EvidenceUploader` diverges from this by reading localStorage, perpetuating the XSS-accessible token surface. The test file at `frontend/src/__tests__/api.test.ts:40` also still sets `kmflow_token` in localStorage, confirming the legacy path is still exercised.
**Risk**: If any XSS vector exists (third-party dependency compromise, injected content), an attacker can read `kmflow_token` from localStorage and impersonate the user. HttpOnly cookies cannot be read by JavaScript; localStorage cannot provide this protection.
**Recommendation**: Remove the localStorage read entirely. The component already sends `credentials: "include"` on line 124, which transmits the HttpOnly cookie automatically. The `Authorization` header branch is dead code for browser sessions. Update `api.test.ts:40` to remove the `localStorage.setItem("kmflow_token", ...)` setup.

---

## High Severity Issues

### [HIGH] ARCHITECTURE: Single `ErrorBoundary` at Root — No Per-Route or Per-Feature Boundaries

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
**Description**: A single `ErrorBoundary` wraps the entire application. While this prevents a total white screen, any render error in any page tears down the entire application UI — including the navigation sidebar — leaving users stranded with no way to navigate to another page. High-risk components that consume external data or use third-party renderers (`BPMNViewer`, `GraphExplorer`) have no dedicated boundaries. A crash in `BPMNViewer` while viewing a process model replaces the entire page (not just the diagram) with the error fallback.
**Risk**: Any render-time exception in any leaf component causes a full application teardown with no graceful degradation. Users cannot recover without a hard reload.
**Recommendation**: Add `ErrorBoundary` wrappers around high-risk leaf components: `BPMNViewer`, `GraphExplorer`, and `AnnotationPanel`. Additionally, use Next.js App Router `error.tsx` files at the route segment level (e.g., `app/simulations/error.tsx`) to scope recovery to individual pages rather than the whole app.

---

### [HIGH] TYPE SAFETY: Pervasive `any` Types in Third-Party Integration Components

**File**: `frontend/src/components/BPMNViewer.tsx:48,76,81,82,84,144,145`
**File**: `frontend/src/components/GraphExplorer.tsx:44,91,120,125,153`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// BPMNViewer.tsx:48
const viewerRef = useRef<any>(null);
// BPMNViewer.tsx:76,81-84
const canvas = viewer.get("canvas") as any;
const overlays = viewer.get("overlays") as any;
const elementRegistry = viewer.get("elementRegistry") as any;
elementRegistry.forEach((element: any) => {
// GraphExplorer.tsx:44,91,120,125,153
const cyRef = useRef<any>(null);
"background-color": (ele: any) => NODE_COLORS[ele.data("type")] ?? "#9ca3af",
cy.on("tap", "node", (event: any) => {
cy.nodes().filter((n: any) => {
```
**Description**: Both `BPMNViewer` and `GraphExplorer` use `any` types for all library-provided objects and event parameters. The `cytoscape` library ships its own TypeScript declarations (`Core`, `NodeSingular`, `EventObject`, etc.). The `bpmn-js` community typings (`@types/bpmn-js`) are available on npm. Using `any` disables all compiler checking on these interactions.
**Risk**: Runtime errors from incorrect property access or method calls on library objects are not caught at compile time. Refactoring these components is risky because TypeScript cannot validate changes. The `useRef<any>` in particular can mask null-dereference bugs since `any` suppresses the `null` check that `useRef<BpmnViewer | null>` would enforce.
**Recommendation**: Install or declare minimal interface types for the specific bpmn-js and cytoscape APIs in use. At minimum, define local interfaces for the subset of the API this code uses:
```typescript
interface BpmnCanvas { zoom(value: string): void; }
interface BpmnOverlays { add(elementId: string, type: string, overlay: object): void; }
```
For cytoscape, replace `any` with the library's exported `Core`, `NodeSingular`, and `EventObject` types.

---

### [HIGH] MISSING CLEANUP: `useMonitoringData` Hooks Have No AbortController

**File**: `frontend/src/hooks/useMonitoringData.ts:51-67,76-92,101-119`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
export function useMonitoringStats(engagementId: string) {
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
**Description**: All three hooks in `useMonitoringData.ts` (`useMonitoringStats`, `useMonitoringJobs`, `useMonitoringAlerts`) fire async API calls via `useEffect` without any mechanism to cancel in-flight requests on unmount. When a component using these hooks unmounts while a fetch is in flight (e.g., fast navigation away), the `setStats`/`setJobs`/`setAlerts` calls will still execute and attempt to update state on an unmounted component. The rest of the codebase uses `AbortController` consistently for this purpose (`useDataLoader`, `useEngagementData`, direct `useEffect` calls in most pages).
**Risk**: State updates on unmounted components produce React warnings in development and can cause memory leaks or subtle state corruption in production if the component remounts before the old fetch settles. In monitoring contexts where these hooks may be polled, the leak accumulates.
**Recommendation**: Apply the same `AbortController` pattern used throughout the rest of the codebase:
```typescript
useEffect(() => {
  const controller = new AbortController();
  refresh(controller.signal);
  return () => controller.abort();
}, [engagementId]);
```
Pass `signal` through to `apiGet` calls.

---

## Medium Severity Issues

### [MEDIUM] ACCESSIBILITY: Form Inputs Without Labels in `FinancialTab`

**File**: `frontend/src/app/simulations/components/FinancialTab.tsx:116-162`
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
<select
  value={newAssumption.assumption_type}
  onChange={(e) => onNewAssumptionChange({ ... })}
  className="border rounded px-3 py-1.5 text-sm"
>
```
**Description**: The financial assumption creation form in `FinancialTab` has five inputs (Name, Assumption Type, Value, Unit, and Confidence range) with no `<label>` elements or `aria-label` attributes. Placeholders are used as the only label mechanism. Once the user begins typing in a field, the placeholder disappears and the input has no programmatic label. The `Confidence` label at line 164 is a bare `<label>` with no `htmlFor`, making it unassociated.
**Risk**: Screen reader users cannot identify what each field expects. The unassociated label means assistive technology announces the range input without context.
**Recommendation**: Add `aria-label` to each input in the assumption form, or restructure as `<label htmlFor="...">`/`<input id="...">` pairs. The `<label className="text-sm">Confidence:</label>` at line 164 must gain an `htmlFor` referencing the range input's `id`.

---

### [MEDIUM] ACCESSIBILITY: Icon-Only Delete Button in `FinancialTab` Has No Label

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
**Description**: The delete button for financial assumptions renders only an icon with no text content, `aria-label`, or `title`. Screen readers will announce this as "button" with no indication of what it deletes. This is in a table row that contains the assumption name, but the button is not associated with that context for assistive technology.
**Risk**: Screen reader users cannot distinguish which assumption a delete button targets, making the assumptions table unusable with assistive technology.
**Recommendation**: Add `aria-label={`Delete assumption ${a.name}`}` to the Button component.

---

### [MEDIUM] CONFORMANCE PAGE: Raw `fetch` Bypasses Shared Auth Client

**File**: `frontend/src/app/conformance/page.tsx:62-70,82-89,114`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
const loadReferenceModels = async () => {
  try {
    const response = await fetch(
      `${API_BASE}/api/v1/conformance/reference-models`
    );
    if (!response.ok) throw new Error("Failed to load reference models");
    const data = await response.json();
    setReferenceModels(data);
  } catch (err) {
```
**Description**: `conformance/page.tsx` uses raw `fetch` calls for all three API interactions (list reference models, upload reference model, run conformance check). None of these calls include `credentials: "include"`, meaning the HttpOnly auth cookie is not sent. The page also defines its own `API_BASE` constant (`process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"`) instead of importing `API_BASE_URL` from `lib/api/client.ts`. This means auth, error handling format, and base URL resolution diverge from every other page in the application.
**Risk**: All three conformance API endpoints are called without authentication — any API request will fail with 401 on a secured backend. The divergence also makes the page invisible to future auth migrations.
**Recommendation**: Replace raw `fetch` calls with `apiGet` and `apiPost` from `@/lib/api`. Remove the local `API_BASE` constant.

---

### [MEDIUM] PORTAL UPLOAD PAGE: Inline Styles Instead of Tailwind

**File**: `frontend/src/app/portal/[engagementId]/upload/page.tsx:17-36`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
return (
  <main
    style={{
      maxWidth: "800px",
      margin: "0 auto",
      padding: "32px 24px",
    }}
  >
    <div style={{ marginBottom: "32px" }}>
      <h1
        style={{
          fontSize: "24px",
          fontWeight: 700,
          margin: "0 0 4px 0",
          color: "#111827",
        }}
      >
```
**Description**: The portal upload page uses inline `style={{}}` objects with hardcoded pixel values and color hex codes for all layout and typography. The rest of the application uses Tailwind utility classes consistently. This page stands out as inconsistent — it hardcodes `#111827` directly while other pages use `text-[hsl(var(--foreground))]` or standard Tailwind text classes that respond to dark mode.
**Risk**: This page will not respond to the application's dark mode theme because hardcoded hex colors are not CSS variable-aware. It also bypasses any future design-token changes.
**Recommendation**: Replace all inline style objects with equivalent Tailwind classes. E.g., `style={{ maxWidth: "800px", margin: "0 auto", padding: "32px 24px" }}` becomes `className="max-w-3xl mx-auto px-6 py-8"`.

---

### [MEDIUM] SILENT ERROR HANDLING: `useMonitoringData` Swallows All Errors Without Logging

**File**: `frontend/src/hooks/useMonitoringData.ts:57-60,83-85,108-111`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
const refresh = useCallback(async () => {
  setLoading(true);
  try {
    const data = await apiGet<MonitoringStats>(`/api/v1/monitoring/stats/${engagementId}`);
    setStats(data);
  } catch {
    setStats(null);   // Error silently swallowed
  } finally {
    setLoading(false);
  }
}, [engagementId]);
```
**Description**: All three monitoring hooks catch every exception and respond by setting state to `null` or `[]` without any error surface to the UI or logging. The `catch` block receives no parameter at all (bare `catch {}`). Consumers of these hooks receive `loading: false` and `stats: null` but have no way to distinguish "no data yet" from "API failure." Monitoring pages will silently show empty dashboards on backend errors.
**Risk**: Operational errors (network partition, backend crash, auth expiry) on the monitoring pages are invisible to users. They see empty charts and tables with no indication that data failed to load. Debugging is also impaired because errors are not logged.
**Recommendation**: At minimum, return an `error` field from each hook (matching the pattern in `useDataLoader` and `useEngagementData`) and log the error:
```typescript
} catch (err) {
  console.error("Failed to load monitoring stats:", err);
  setStats(null);
  setError(err instanceof Error ? err.message : "Failed to load monitoring stats");
}
```

---

## Low Severity Issues

### [LOW] REACTIVITY: `conformance/page.tsx` Has Missing `useEffect` Dependency

**File**: `frontend/src/app/conformance/page.tsx:58-60`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
useEffect(() => {
  loadReferenceModels();
}, []);
```
**Description**: `loadReferenceModels` is declared as a regular `async` function (not wrapped in `useCallback`) but is not included in the `useEffect` dependency array. While this runs correctly on mount, if `loadReferenceModels` were ever refactored to close over a prop or state, the stale closure would silently use stale values. ESLint's `react-hooks/exhaustive-deps` rule would flag this.
**Risk**: Low immediate risk given the function currently has no external dependencies, but establishes a pattern that could cause bugs if the function is extended.
**Recommendation**: Either wrap `loadReferenceModels` in `useCallback` with a proper dependency array, or inline the fetch call directly in the `useEffect` body.

---

### [LOW] HARDCODED ENGAGEMENT IDs IN NAVIGATION

**File**: `frontend/src/components/shell/AppShell.tsx:64,71,73,80`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
{ label: "Knowledge Graph", href: "/graph/1db9aa11-c73b-5867-82a3-864dd695cf23", icon: Network },
{ label: "TOM Alignment", href: "/tom/1db9aa11-c73b-5867-82a3-864dd695cf23", icon: Target },
{ label: "Visualize", href: "/visualize/1db9aa11-c73b-5867-82a3-864dd695cf23", icon: Eye },
{ label: "Roadmap", href: "/roadmap/1db9aa11-c73b-5867-82a3-864dd695cf23", icon: Map },
```
**Description**: Four navigation items in `AppShell` have the engagement UUID `1db9aa11-c73b-5867-82a3-864dd695cf23` hardcoded directly in the href. This appears to be a development fixture/demo engagement ID embedded in the production navigation. The sidebar will route all users who click these links to the same engagement regardless of which engagement they are working on.
**Risk**: Multi-engagement or multi-tenant usage is broken for these four features via the sidebar. Users cannot navigate to their actual engagement from the global navigation. This also reveals an internal engagement UUID in the client-rendered HTML.
**Recommendation**: The sidebar should navigate to an engagement selector or use a dynamic current engagement ID from application state (e.g., via a context or URL-aware routing). Remove the hardcoded UUIDs.

---

### [LOW] INLINE STYLES FOR DYNAMIC VALUES — Pattern Is Acceptable But Inconsistent

**File**: `frontend/src/components/BPMNViewer.tsx:98-107`
**File**: `frontend/src/app/graph/[engagementId]/page.tsx:82`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// BPMNViewer.tsx — unavoidable (bpmn-js HTML string injection):
html: `<div style="background: ${color}; color: white; padding: 1px 6px; ...">`,

// graph page — avoidable:
<div style={{ height: "calc(100vh - 250px)" }}>
```
**Description**: There are two distinct patterns here. The inline styles in `BPMNViewer` for overlay HTML strings are unavoidable — bpmn-js accepts raw HTML strings and there is no way to use Tailwind classes in that context. However, the `style={{ height: "calc(100vh - 250px)" }}` on the graph page wrapping div is a straightforward case that could use a CSS variable or a `min-h-[calc(100vh-250px)]` Tailwind arbitrary value.
**Risk**: Low. The BPMN overlay case is intentional. The graph page case is a minor consistency issue.
**Recommendation**: For the graph page, use `className="h-[calc(100vh-250px)]"` to stay consistent with Tailwind. Add a code comment in `BPMNViewer` marking the inline style strings as intentional (unavoidable due to bpmn-js API constraint).

---

### [LOW] MISSING `aria-label` ON ICON-ONLY SIDEBAR COLLAPSE TOGGLE

**File**: `frontend/src/components/shell/AppShell.tsx:255-265`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
<button
  onClick={() => setSidebarCollapsed((v) => !v)}
  className="rounded-md p-1.5 hover:bg-white/10 transition-colors"
  aria-label="Toggle sidebar"
>
  {sidebarCollapsed ? (
    <ChevronRight className="h-4 w-4" />
  ) : (
    <ChevronLeft className="h-4 w-4" />
  )}
</button>
```
**Description**: The sidebar collapse toggle has `aria-label="Toggle sidebar"` but does not communicate its current state (`aria-expanded` or `aria-pressed`). Screen readers cannot determine whether the sidebar is currently expanded or collapsed from this button alone. The label "Toggle sidebar" also does not indicate what will happen on activation (expand or collapse).
**Risk**: Screen reader users cannot determine the current sidebar state from the toggle button, making it harder to use keyboard navigation effectively.
**Recommendation**: Add `aria-expanded={!sidebarCollapsed}` and update the `aria-label` to reflect the action: `aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}`.

---

## Positive Highlights

1. **`ErrorBoundary` implemented correctly**: Uses `getDerivedStateFromError` and `componentDidCatch`, provides a functional "Try again" button with proper `aria-label`, and supports a custom `fallback` prop.

2. **API domain split completed**: The prior god-file `api.ts` is now a re-export barrel. Domain modules (`monitoring.ts`, `taskmining.ts`, `simulations.ts`, etc.) are under `lib/api/` with clear separation. Backward compatibility is maintained via the barrel.

3. **`AbortController` used correctly across most hooks**: `useDataLoader`, `useEngagementData`, and the majority of direct `useEffect` data fetches use `AbortController` with cleanup, preventing state updates on unmounted components.

4. **WebSocket lifecycle well-managed**: `useWebSocket` and the inline WebSocket in `TaskMiningDashboard` both clear reconnect timers and close sockets on unmount. Exponential backoff is implemented correctly.

5. **No `dangerouslySetInnerHTML`**: Zero XSS-via-React-props vectors found across all 40+ source files.

6. **No `console.log` in production code**: All source files are clean of debug logging.

7. **Keyboard accessibility in `GapTable`**: Sortable column headers use `role="button"`, `tabIndex={0}`, `aria-label` with sort direction, and `onKeyDown` handlers for Enter/Space — a correctly implemented accessible sort pattern.

8. **Strong accessibility in `EvidenceUploader`**: Drop zone uses `role="button"`, `aria-label`, `tabIndex`, Enter/Space key handling, and the progress bar correctly uses `role="progressbar"` with `aria-valuenow/min/max`.

9. **Proper TypeScript in API layer**: All API functions use generic type parameters (`apiGet<T>`, `apiPost<T>`) and define explicit interfaces for all request/response shapes. No `any` in the shared API utilities.

10. **Defensive deletion in `AnnotationPanel`**: The delete handler uses optimistic UI update (`setAnnotations` filter) and catches errors without crashing the component.

---

## Checkbox Verification Results

| Criterion | Status | Details |
|-----------|--------|---------|
| NO TODO COMMENTS | PASS | No TODO comments found in current source files |
| NO PLACEHOLDERS | PARTIAL | `upload/page.tsx:43` has an empty `onUploadComplete` callback with comment "Could trigger a toast notification" — stub behavior |
| NO HARDCODED SECRETS | PARTIAL | No credentials; hardcoded engagement UUID in AppShell navigation is a data exposure concern |
| PROPER ERROR HANDLING | FAIL | `useMonitoringData.ts` silently swallows all errors in three hooks; `conformance/page.tsx` is missing `credentials: "include"` making auth fail silently |
| NO `any` TYPES | FAIL | 13 `any` usages across `BPMNViewer.tsx` (8) and `GraphExplorer.tsx` (5) |
| ERROR BOUNDARIES | PARTIAL | One root boundary exists; no per-route or per-component boundaries around high-risk renderers |
