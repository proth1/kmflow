# C2: Frontend Code Quality Audit Findings

**Auditor**: C2 (Frontend Quality Auditor)
**Scope**: `frontend/src/` — React component patterns, error boundaries, accessibility, token storage security, state management
**Date**: 2026-02-20

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 4 |
| MEDIUM   | 4 |
| LOW      | 3 |
| **Total** | **12** |

---

## Critical Issues

### [CRITICAL] SECURITY: JWT Token Stored in localStorage (XSS-Accessible)

**File**: `frontend/src/lib/api.ts:22`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("kmflow_token");
}
```
**Description**: The JWT auth token is stored in `localStorage` which is readable by any JavaScript executing in the browser context. This is a textbook XSS attack vector. Any successful XSS injection — from a third-party dependency, from BPMN XML rendering, or from annotation content — would allow an attacker to exfiltrate the token and impersonate the user.
**Risk**: Token theft via XSS leads to full account takeover. Given this platform handles confidential consulting engagement data, the blast radius is significant.
**Recommendation**: Migrate to `HttpOnly` cookies set by the server. The browser cannot read `HttpOnly` cookies via JavaScript, eliminating the theft surface. Alternatively use a short-lived in-memory token with a silent refresh flow backed by a secure cookie.

---

## High Severity Issues

### [HIGH] ARCHITECTURE: No React Error Boundaries Anywhere in the Application

**File**: `frontend/src/app/layout.tsx:14`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem disableTransitionOnChange>
          <AppShell>{children}</AppShell>
```
**Description**: No `ErrorBoundary` component exists anywhere under `frontend/src/`. A render-time exception in any component (e.g., a null deref when API data has an unexpected shape, or an error in the `bpmn-js` or `cytoscape` dynamic import path) will tear down the entire React tree and show a blank white page with no user-friendly message. The `AppShell` wraps all content but provides no error boundary protection.
**Risk**: Any unhandled render exception causes a complete application crash with no recovery path. Users lose all in-progress work.
**Recommendation**: Add at minimum one `ErrorBoundary` at the root layout level wrapping `AppShell`, and ideally per-page boundaries around the main page content. Next.js App Router also supports `error.tsx` files per route segment as a simpler alternative.

---

### [HIGH] CODE QUALITY: God File — `api.ts` is 1,694 Lines and Growing

**File**: `frontend/src/lib/api.ts:1-1694`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
/**
 * TODO: Split into domain modules when this file exceeds 1500 lines.
 * Suggested modules: api/evidence.ts, api/governance.ts, api/monitoring.ts,
 * api/reports.ts, api/admin.ts
 */
```
**Description**: `api.ts` is already 194 lines past its own self-declared splitting threshold (1,500 lines). It contains types and API functions across 12+ domains: dashboard, evidence, TOM, roadmap, monitoring, patterns, simulation, portal, graph, auth, governance, integrations, shelf-requests, metrics, annotations, and lineage. This is a textbook god file.
**Risk**: Merge conflicts are likely as multiple features touch this file simultaneously. Finding specific types or functions requires scanning the entire file. Bundle splitting cannot be applied — all API code is shipped in a single chunk even if only a subset is used.
**Recommendation**: Split along the domain boundaries already identified in the TODO comment. Each domain module (`api/evidence.ts`, `api/governance.ts`, etc.) should export its own types and functions.

---

### [HIGH] SECURITY: `AnnotationPanel` Makes Unauthenticated API Calls

**File**: `frontend/src/components/AnnotationPanel.tsx:48-57`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
const res = await fetch(
  `${API_BASE}/api/v1/annotations/?${params.toString()}`,
);
if (res.ok) {
  const data = await res.json();
  setAnnotations(data.items || []);
}
```
**Description**: `AnnotationPanel` uses raw `fetch` without any `Authorization` header, while the rest of the application uses `authHeaders()` via `apiGet`/`apiPost`. This means annotation reads and writes go unauthenticated. The DELETE call on line 101 also omits auth headers. This is inconsistent with the application's auth model and leaves annotation endpoints as potential IDOR targets.
**Risk**: Annotations may be readable/deletable by unauthenticated users, or across tenants if the backend relies on the token for scoping.
**Recommendation**: Replace the raw `fetch` calls in `AnnotationPanel` with `apiGet`, `apiPost`, and `apiDelete` from `lib/api.ts` which apply `authHeaders()` consistently.

---

### [HIGH] TYPE SAFETY: Pervasive `any` Types in Third-Party Integration Components

**File**: `frontend/src/components/BPMNViewer.tsx:48,76,77,81,84,144,145`
**File**: `frontend/src/components/GraphExplorer.tsx:44,91,120,125,153`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// BPMNViewer.tsx
const viewerRef = useRef<any>(null);
const canvas = viewer.get("canvas") as any;
const overlays = viewer.get("overlays") as any;
const elementRegistry = viewer.get("elementRegistry") as any;
elementRegistry.forEach((element: any) => {
  eventBus.on("element.click", (event: any) => {

// GraphExplorer.tsx
const cyRef = useRef<any>(null);
"background-color": (ele: any) => NODE_COLORS[ele.data("type")] ?? "#9ca3af",
cy.on("tap", "node", (event: any) => {
cy.nodes().filter((n: any) => {
```
**Description**: Both the BPMN viewer and graph explorer use `any` types for library-provided objects. While `bpmn-js` and `cytoscape` have community TypeScript definitions available (`@types/bpmn-js`, `cytoscape` ships its own types), the code bypasses type safety entirely. This also affects the `useRef<any>` instances that could mask null deref issues.
**Risk**: Type errors in element access or event handling are caught only at runtime. Refactoring is dangerous because the compiler offers no guidance.
**Recommendation**: Install `@types/bpmn-js` if available, or define minimal local interface types for the specific APIs used (`canvas`, `overlays`, `eventBus`, `elementRegistry`). For `cytoscape`, use its built-in types (`Core`, `NodeCollection`, `EventObject`).

---

## Medium Severity Issues

### [MEDIUM] ACCESSIBILITY: Interactive Buttons Missing `aria-label` in Several Components

**File**: `frontend/src/components/GraphExplorer.tsx:224-229`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
<button
  onClick={() => setSelectedNode(null)}
  className="text-gray-400 hover:text-gray-600"
>
  x
</button>
```
**Description**: The node detail panel close button in `GraphExplorer` uses the text "x" with no `aria-label`. Screen readers will announce this as "x button" which is not descriptive. Similarly, the `SidebarContent` section toggle buttons in `AppShell.tsx` have no `aria-label` or `aria-expanded` attribute to communicate their state to assistive technology.
**Risk**: Screen reader users cannot effectively operate the graph explorer or understand sidebar section state.
**Recommendation**: Add `aria-label="Close node details"` to the close button. Add `aria-expanded={!isSectionCollapsed}` and a descriptive `aria-label` to the sidebar section toggle buttons.

---

### [MEDIUM] ACCESSIBILITY: Simulation Page Form Inputs Missing Labels

**File**: `frontend/src/app/simulations/page.tsx:499-503`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
<input
  type="text"
  placeholder="Scenario name"
  value={newName}
  onChange={(e) => setNewName(e.target.value)}
  className="border rounded px-3 py-1.5 text-sm w-full"
/>
```
**Description**: The scenario creation form inputs (name, description) and the financial assumption form inputs (name, value, unit) in `simulations/page.tsx` use placeholder text as the only label. Placeholders disappear when the user types, leaving the input unlabeled mid-form. The assumption form inputs on lines 1080-1103 also lack associated `<label>` elements or `aria-label` attributes.
**Risk**: Screen reader users and users relying on visible persistent labels cannot identify form fields once input begins.
**Recommendation**: Add `<label htmlFor="...">` elements for each form input, or use `aria-label` attributes. Several other selects in the same component already use `<label htmlFor="...">` correctly (e.g., `baseline-select`, `coverage-select`) — the pattern just needs to be applied consistently.

---

### [MEDIUM] PATTERN: Simulations Page Violates Single Responsibility — 1,247-Line God Component

**File**: `frontend/src/app/simulations/page.tsx:1-1247`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
// State slice count (partial):
const [scenarios, setScenarios] = useState<ScenarioData[]>([]);
const [comparisonData, setComparisonData] = useState<ScenarioComparisonData | null>(null);
const [coverageData, setCoverageData] = useState<ScenarioCoverageData | null>(null);
const [epistemicPlan, setEpistemicPlan] = useState<EpistemicPlanData | null>(null);
const [suggestions, setSuggestions] = useState<AlternativeSuggestionData[]>([]);
const [assumptions, setAssumptions] = useState<FinancialAssumptionData[]>([]);
const [rankingData, setRankingData] = useState<ScenarioRankingData | null>(null);
// ... 20+ more state variables
```
**Description**: `SimulationsPage` manages 8 separate feature domains (scenarios, results, comparison, coverage, epistemic planning, suggestions, financial modeling, ranking) in a single 1,247-line component with 20+ independent state variables and 10+ async handler functions. Each tab section is a separate feature that could be its own component with its own data fetching.
**Risk**: Extremely difficult to test, debug, or modify any single feature without risk of inadvertently breaking another. State interactions between independent features create subtle bugs. Bundle cannot be code-split.
**Recommendation**: Extract each tab into its own component (e.g., `ScenarioList`, `ScenarioComparison`, `EvidenceCoverageTab`, `EpistemicPlanTab`, `SuggestionsTab`, `FinancialTab`, `RankingTab`) with co-located state and data fetching.

---

### [MEDIUM] PATTERN: `EvidenceUploader` Has Stale Closure Bug in `uploadFile` Index Tracking

**File**: `frontend/src/components/EvidenceUploader.tsx:81-83`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
newUploads.forEach((upload, idx) => {
  const uploadIdx = uploads.length + idx;
  uploadFile(upload.file, uploadIdx);
});
```
**Description**: `uploadFile` uses a positional index (`uploadIdx`) computed at call time from `uploads.length`. However `uploads` is captured from the outer scope via closure, and `setUploads` is asynchronous — by the time `uploadFile` runs its `setUploads` calls, additional state updates may have shifted the array. If multiple files are added rapidly or re-rendered between add and upload, `uploadIdx` may reference the wrong upload entry.
**Risk**: Progress updates and status changes may be applied to the wrong file in the uploads list, showing incorrect state.
**Recommendation**: Use a stable identity (e.g., a UUID or `crypto.randomUUID()`) for each upload entry rather than a positional index, and key all state updates on that ID.

---

## Low Severity Issues

### [LOW] CODE STYLE: TODO Comment in Production Code

**File**: `frontend/src/lib/api.ts:7-9`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
 * TODO: Split into domain modules when this file exceeds 1500 lines.
 * Suggested modules: api/evidence.ts, api/governance.ts, api/monitoring.ts,
 * api/reports.ts, api/admin.ts
```
**Description**: A TODO comment describing a known architectural improvement is committed to production code and the threshold has already been passed (file is 1,694 lines). TODO comments in shipped code represent deferred work with no enforcement mechanism.
**Risk**: The comment will continue to be silently ignored. The file will grow further.
**Recommendation**: Convert this to a tracked GitHub issue and remove the TODO comment. The split is now overdue.

---

### [LOW] CODE STYLE: Inline Styles Mixed With Tailwind — `BPMNViewer` and `GraphExplorer`

**File**: `frontend/src/components/BPMNViewer.tsx:98-107,120-133,182-225`
**File**: `frontend/src/components/GraphExplorer.tsx:204`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
html: `<div style="
  background: ${color};
  color: white;
  padding: 1px 6px;
  border-radius: 8px;
  ...
">${pct}%</div>`,
```
**Description**: `BPMNViewer` injects inline style strings into BPMN overlay HTML, and the error/loading states use the `style={{}}` prop directly rather than Tailwind classes. `GraphExplorer` also mixes `style={{}}` inline for type-filter button active colors. While the overlay case is unavoidable (bpmn-js renders HTML strings), the component-level uses are inconsistent with the rest of the codebase.
**Risk**: Inconsistent styling approach makes the codebase harder to theme or audit for style compliance.
**Recommendation**: For component-level styling use Tailwind classes consistently. For the BPMN overlay HTML strings (which are injected into the bpmn-js canvas), inline styles are acceptable and should be documented as intentional.

---

### [LOW] ACCESSIBILITY: `useDataLoader` Initial Load Silences Errors Unexpectedly

**File**: `frontend/src/hooks/useDataLoader.ts:61-64`
**Agent**: C2 (Frontend Quality Auditor)
**Evidence**:
```typescript
useEffect(() => {
  const silent = isInitialLoad.current;
  isInitialLoad.current = false;
  loadData(silent);
```
**Description**: On the initial load of any component using `useDataLoader`, errors are silently swallowed (`silent = true`). If the initial API call fails (e.g., network error, 500, auth failure), the component renders with `loading: false`, `data: null`, `error: null` — showing no content and no error message. Users see a blank panel with no indication of what happened.
**Risk**: Silent failures on initial load are invisible to users. They cannot distinguish "no data" from "failed to load" which may cause them to take incorrect follow-up actions.
**Recommendation**: Remove the silent-on-initial-load behavior, or at minimum surface a non-disruptive error state (e.g., an inline warning) even on the first load failure.

---

## Positive Highlights

1. **Proper AbortController usage**: Both `useDataLoader` and `useEngagementData` correctly use `AbortController` with cleanup in `useEffect` return functions, preventing state updates on unmounted components.

2. **WebSocket lifecycle management**: `useWebSocket` correctly cleans up the WebSocket, clears reconnect timers, and sets retry count to max on unmount to prevent reconnection after unmount.

3. **Input validation in `EvidenceUploader`**: Client-side file type and size validation is implemented before upload, with clear user-facing error messages.

4. **Consistent error handling in API utilities**: `apiGet`, `apiPost`, `apiPut`, `apiPatch`, and `apiDelete` all follow the same error handling pattern with proper fallback parsing.

5. **Accessibility in `EvidenceUploader`**: The drop zone correctly uses `role="button"`, `aria-label`, keyboard event handling (`Enter`/`Space`), `tabIndex`, and the progress bar uses `role="progressbar"` with `aria-valuenow/min/max`.

6. **Type safety in API layer**: The API layer uses TypeScript generics (`apiGet<T>`, `apiPost<T>`) and specific interface types throughout, avoiding `any` in the shared API utilities.

7. **No `dangerouslySetInnerHTML` usage**: No XSS-via-React-props vectors found in any component.

8. **No `console.log` in production code**: Debug logging is absent from all source files, keeping production output clean.

---

## Checkbox Verification Results

| Criterion | Status | Details |
|-----------|--------|---------|
| NO TODO COMMENTS | FAIL | 1 TODO found in `api.ts:7` |
| NO PLACEHOLDERS | PASS | No stub implementations found |
| NO HARDCODED SECRETS | PASS | No credentials found; only env-var references |
| PROPER ERROR HANDLING | PARTIAL | `useDataLoader` silences initial load errors; `AnnotationPanel` silences fetch errors entirely |
| NO `any` TYPES | FAIL | 8 `any` usages in `BPMNViewer.tsx` and `GraphExplorer.tsx` |
| ERROR BOUNDARIES | FAIL | Zero `ErrorBoundary` components in entire frontend |
