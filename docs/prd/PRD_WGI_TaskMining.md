# WorkGraphIQ Task Mining Agent - Product Requirements Document

**Version**: 1.0.0
**Status**: Draft
**Last Updated**: 2026-02-25
**Author**: Paul Roth
**Classification**: Internal - Confidential

---

## 1. Executive Summary

WorkGraphIQ currently discovers business processes through imported evidence: documents, interviews, SaaS exports, and third-party connectors. This is the right approach for consulting engagements where evidence arrives in bulk at the start of an engagement. However, it creates a structural blind spot: WorkGraphIQ cannot observe what users actually do at the desktop level.

**The Problem with Third-Party Task Mining**:

Existing task mining integrations (Soroco Scout, Celonis) solve the observation gap but introduce a different set of problems:
- No control over capture scope, PII filtering quality, or data governance
- Evidence quality is determined entirely by the third-party vendor
- Confidence scoring requires trusting a black box
- PII handling is vendor-configured, not engagement-configurable
- Cost per engagement is $25,000+ (Soroco), consuming a significant share of engagement economics
- Data residency and processing location cannot be guaranteed

**What This PRD Defines**:

A first-party native desktop agent for macOS (Windows in Phase 3) that captures observed desktop behavior as high-quality, PII-filtered evidence directly into WorkGraphIQ. The agent is purpose-built for consulting engagements: it captures what users do, filters PII at four layers before any data leaves the device, and materializes observed behavior as KM4Work evidence items with a 0.9 source weight — the highest confidence tier in the platform.

**Strategic Position**: Observed desktop behavior is the ground truth of what processes actually exist. Documents describe what should happen. Desktop capture records what does happen. The Task Mining Agent closes the gap between declared and actual process execution.

**Market Context**: The task mining market was valued at approximately $2B in 2025 and is projected to reach $10B by 2033 at a 25% CAGR. WorkGraphIQ enters this market not as a standalone task mining product, but as the only task mining solution purpose-built for the consulting delivery workflow, with native knowledge graph integration and mandatory four-layer PII architecture.

---

## 2. Problem Statement

### 2.1 The Evidence Gap

WorkGraphIQ's evidence-first philosophy is sound. But evidence submitted by clients — documents, process models, system exports — describes intended or documented behavior. It does not reliably capture:

- Workarounds that have become standard practice
- Undocumented decision logic performed by experienced staff
- Applications used that IT does not know about
- Actual task sequences that differ from documented procedures
- Idle time and handoff delays that are invisible in system logs

These are the exact process insights consultants are paid to find. They are invisible to all current evidence categories.

### 2.2 Why Third-Party Tools Do Not Solve This

The Soroco connector (`src/integrations/soroco.py`) demonstrates the integration pattern but exposes the structural problem: WorkGraphIQ receives whatever Soroco decides to send, filtered however Soroco decides to filter it, from a system the client already owns or must purchase separately. This limits:

- **Evidence control**: PII filtering cannot be tuned per engagement
- **Confidence traceability**: The source weight assigned to Soroco data assumes vendor quality that cannot be independently verified
- **Deployment flexibility**: Soroco requires client infrastructure and IT involvement
- **Engagement economics**: Third-party licensing directly reduces engagement margin

### 2.3 Privacy as a First-Class Requirement

Desktop capture creates a uniquely sensitive data category. Unlike document evidence or system logs, desktop capture can inadvertently record passwords, financial account numbers, medical information, and personal communications. An agent that cannot guarantee PII protection at the capture layer — before any data leaves the device — is not deployable in regulated industries.

This PRD mandates four layers of PII protection. It is not a configuration option. It is an architectural invariant.

---

## 3. Product Vision

The WorkGraphIQ Task Mining Agent transforms observed desktop behavior into evidence-grade process knowledge. It captures what users actually do, filters everything that should not leave the device, and feeds the result into the same evidence pipeline that processes documents, interviews, and system exports — with the highest confidence weight in the system.

**Vision Statement**: A lightweight, privacy-first desktop agent that observes actual work patterns, applies mandatory four-layer PII filtering before any data leaves the device, and materializes observed behavior as high-confidence KM4Work evidence integrated directly into the WorkGraphIQ knowledge graph.

**Guiding Principles**:
- Privacy-first: four-layer PII filtering is architectural, not configurable off
- Lightweight: agent CPU < 3%, memory < 150MB, invisible to users during normal work
- Evidence-grade: captured data meets the same quality standards as all other WorkGraphIQ evidence
- Consulting-native: supports both bounded engagement deployment and enterprise MDM deployment
- Transparent consent: users know the agent is running, what it captures, and how to opt out of content-level capture

---

## 4. Market Context

### 4.1 Market Size and Growth

| Metric | Value |
|--------|-------|
| Task mining market size (2025) | ~$2B |
| Projected market size (2033) | ~$10B |
| CAGR | 25% |
| Primary driver | RPA adoption, process intelligence for AI transformation programs |

### 4.2 Competitive Landscape

| Vendor | Approach | Price Signal | Gap vs. WorkGraphIQ Agent |
|--------|----------|-------------|----------------------|
| **Soroco Scout** | Proprietary agent, Work Graph output | $25,000+/engagement | No knowledge graph integration; no consulting workflow; black-box PII |
| **Celonis Task Mining** | Sensor-based desktop capture, EMS integration | Enterprise license | Requires Celonis EMS; no consulting evidence pipeline; no Consensus confidence scoring |
| **UiPath Task Mining** | Desktop recorder, process discovery | Enterprise license | RPA-centric; not designed for process discovery consulting; no triangulation |
| **Microsoft Viva Insights** | Microsoft 365 behavioral data only | M365 E5 add-on | Limited to Microsoft applications; no desktop-wide capture; no process model output |
| **SAP Signavio Process Intelligence** | Log-based; task mining add-on | Enterprise license | Event log dependency; task mining is secondary capability |

### 4.3 WorkGraphIQ's Differentiated Position

No existing task mining tool integrates with a knowledge graph, applies evidence triangulation against other evidence types, or is purpose-built for the consulting engagement delivery model. WorkGraphIQ's Task Mining Agent is differentiated on:

1. **Knowledge graph integration**: Observed actions become `UserAction` nodes in Neo4j, linked to `Process`, `Application`, and `Role` nodes with typed relationships
2. **Evidence triangulation**: Task mining evidence (0.9 weight) triangulates with documents, interviews, and system data through the existing confidence scoring model
3. **Mandatory four-layer PII architecture**: Not vendor-configurable — every captured event passes through four PII filters before leaving the device
4. **Consulting deployment model**: Engagement mode (auto-disabling) and enterprise MDM mode, not just always-on enterprise licenses
5. **Process deviation detection**: Graph-based comparison of observed task sequences against POV-generated process models

---

## 5. Architecture

### 5.1 System Overview

The agent is a hybrid Swift + Python application. Swift handles OS-level event capture (the part that requires macOS security entitlements and native APIs). Python handles intelligence processing (PII filtering, action aggregation, pattern detection, and backend communication).

```mermaid
graph TD
    subgraph macOS Agent
        SW[Swift Layer\nCGEventTap / AXUIElement\nNSWorkspace / ScreenCaptureKit]
        UDS[Unix Domain Socket\nJSON Protocol]
        PY[Python Layer\nPII Filter Engine\nAction Aggregator\nSQLite Buffer\nBatch Uploader]
        SW -->|raw events| UDS
        UDS -->|deserialized events| PY
    end

    subgraph WorkGraphIQ Backend
        FASTAPI[FastAPI\nEvent Ingestion\nConfig Push\nHeartbeat]
        REDIS[Redis Stream\nTASK_MINING_STREAM]
        WORKER[Worker\nAction Assembly\nPII L3 Filter\nEvidence Materialization]
        PG[PostgreSQL\ntask_mining_events\ntask_mining_actions\ntask_mining_agents\ntask_mining_sessions\npii_quarantine]
        NEO4J[Neo4j\nApplication nodes\nUserAction nodes\nPERFORMED_IN\nPRECEDED_BY]
    end

    PY -->|HTTPS mTLS batch| FASTAPI
    FASTAPI -->|publish| REDIS
    REDIS -->|consume| WORKER
    WORKER -->|persist| PG
    WORKER -->|graph write| NEO4J
```

### 5.2 Swift Layer

The Swift layer is responsible for all OS-level event capture. It requires macOS security entitlements and cannot be replaced with Python bindings without losing access to low-level APIs.

| Swift API | Purpose | Events Produced |
|-----------|---------|----------------|
| `CGEventTap` | Keyboard and mouse events at the system level | `KEYBOARD_ACTION`, `KEYBOARD_SHORTCUT`, `MOUSE_CLICK`, `MOUSE_DOUBLE_CLICK`, `MOUSE_DRAG`, `COPY_PASTE`, `SCROLL` |
| `AXUIElement` | Accessibility API for UI element inspection | `UI_ELEMENT_INTERACTION`, `WINDOW_FOCUS` |
| `NSWorkspace` | Application lifecycle and workspace events | `APP_SWITCH`, `FILE_OPEN`, `FILE_SAVE` |
| `ScreenCaptureKit` | Screen capture with window-level granularity | `SCREEN_CAPTURE` |
| `WKWebView` / `Safari` integration | Browser URL monitoring | `URL_NAVIGATION`, `TAB_SWITCH` |

**L1 PII filtering (Swift layer)**: The Swift layer enforces capture prevention before events are even generated. Password fields are detected via AXUIElement role attributes. Blocked applications never produce events. Private browsing windows suppress URL capture. This filtering happens before any event is passed to Python.

### 5.3 Python Layer

The Python layer receives raw events from Swift via local Unix domain socket and applies intelligence before buffering for upload.

| Component | Responsibility |
|-----------|---------------|
| **Socket Server** | Receives JSON events from Swift over `unix:///tmp/kmflow-agent.sock` |
| **L2 PII Filter Engine** | Regex scrubbing (SSN, CC, email, phone, DOB), OCR-based screenshot redaction |
| **Action Aggregator** | Groups low-level events into semantic task segments (e.g., 47 keystrokes in Excel row 3 = one `KEYBOARD_ACTION` event) |
| **Idle Detector** | Monitors event cadence; emits `IDLE_START` / `IDLE_END` with duration |
| **SQLite Buffer** | Local persistence for offline resilience; WAL mode for write throughput |
| **Batch Uploader** | Polls buffer; uploads to backend via HTTPS/mTLS in configurable batch sizes; retries with exponential backoff |
| **Config Consumer** | Receives engagement config from backend (capture policy, app allowlist, retention, keystroke mode) |

### 5.4 Backend Data Flow

```mermaid
sequenceDiagram
    participant Agent as macOS Agent
    participant API as FastAPI /taskmining
    participant Redis as Redis Stream
    participant Worker as Worker Process
    participant PG as PostgreSQL
    participant Neo4j as Neo4j

    Agent->>API: POST /api/v1/taskmining/events (batch, mTLS)
    API->>Redis: XADD TASK_MINING_STREAM
    API-->>Agent: 202 Accepted
    Redis->>Worker: XREADGROUP consumer-group
    Worker->>Worker: L3 NLP PII scan
    Worker->>Worker: Action assembly (task segmentation)
    Worker->>PG: INSERT task_mining_events, task_mining_actions
    Worker->>Neo4j: MERGE Application, UserAction nodes
    Worker->>Neo4j: CREATE PERFORMED_IN, PRECEDED_BY relationships
```

### 5.5 Packaging

**macOS**: `.app` bundle with embedded Python runtime (py2app). The bundle includes all Python dependencies, the PII model weights, and the Swift binary. A single notarized `.dmg` is distributed for manual installation in engagement mode. An MDM-compatible `.pkg` with configuration profile support is distributed for enterprise mode.

**Configuration**: Engagement-specific configuration is delivered via signed JWT from the backend at registration time. The agent does not ship with hardcoded engagement parameters.

### 5.6 Communication Protocol

The Swift-to-Python Unix domain socket uses a newline-delimited JSON protocol:

```json
{
  "event_type": "KEYBOARD_ACTION",
  "timestamp_ns": 1740480000000000000,
  "app_bundle_id": "com.microsoft.Excel",
  "window_title": "[REDACTED_PII]",
  "element_role": "AXTextField",
  "element_description": "Row 3 input",
  "action_metadata": {
    "char_count": 47,
    "duration_ms": 12300,
    "content_level": false
  }
}
```

The backend batch upload uses JSON arrays over HTTPS with mTLS client certificate authentication. Each batch includes the agent ID, session ID, sequence numbers for deduplication, and a batch checksum.

---

## 6. Deployment Modes

### 6.1 Engagement Mode (Temporary)

Used for consulting engagements where the agent is installed on client machines for the duration of the discovery phase.

| Characteristic | Value |
|---------------|-------|
| Deployment method | Manual .dmg install; IT-assisted or self-service |
| Configuration | Backend-provided JWT with engagement ID and end date |
| Auto-disable | Agent ceases capture at engagement end date; requires re-authorization to resume |
| Data scope | Bounded to engagement session window |
| Uninstall | Self-service via agent preferences; MDM removal on enterprise machines |
| Consent flow | User-visible notification at install with capture summary; user acceptance required before capture begins |

Engagement mode is appropriate when the client's IT department is willing to install the agent for the duration of discovery, with a defined end date and explicit consent flow.

### 6.2 Enterprise Mode (Persistent)

Used for clients who want ongoing process intelligence as a persistent capability.

| Characteristic | Value |
|---------------|-------|
| Deployment method | MDM push via Jamf Pro or Microsoft Intune |
| Configuration | MDM configuration profile with backend URL, certificate, and engagement settings |
| Persistence | Runs continuously; configuration updates pushed via MDM |
| Session management | Sessions aligned to business hours or user login/logout |
| Data scope | Ongoing; retention policy enforced server-side |
| Consent flow | Enterprise IT deploys with corporate policy disclosure; individual opt-out for content-level capture |

Enterprise mode is appropriate for clients embedding WorkGraphIQ process intelligence into their ongoing operational model. The agent becomes part of the client's managed software estate.

### 6.3 Mode Switching

An agent registered in engagement mode cannot switch to enterprise mode without re-registration. This is enforced server-side and is not configurable by the agent. Mode transitions generate audit log entries.

---

## 7. PII Filtering Architecture

PII filtering is a four-layer mandatory architecture. No layer can be disabled independently. The layers form a defense-in-depth stack where each layer catches what prior layers missed.

### 7.1 Architecture Overview

```mermaid
graph LR
    RAW[Raw Desktop\nActivity]
    L1[L1: Capture Prevention\nSwift / On-Device\nNever captured]
    L2[L2: At-Source Filtering\nPython / On-Device\nScrubbed before buffer]
    L3[L3: Server-Side\nFastAPI + NLP\nQuarantined if flagged]
    L4[L4: Data Management\nRetention + Erasure\nAudit trail]
    EVIDENCE[WorkGraphIQ\nEvidence Store]

    RAW --> L1
    L1 --> L2
    L2 --> L3
    L3 --> L4
    L4 --> EVIDENCE
```

### 7.2 Layer 1: Capture Prevention (Swift, On-Device)

Events that match L1 criteria are never generated. They do not enter the event stream at all.

| Rule | Detection Method | Action |
|------|-----------------|--------|
| Password field | `AXUIElement` role = `AXSecureTextField` | No event generated |
| Blocked application | `NSWorkspace` bundle ID vs. engagement allowlist | No events for this app |
| Private browsing | Browser window state detection | No URL events; keyboard metadata only |
| Screen lock / screensaver | `NSWorkspace` notifications | Capture suspended |
| System preferences / keychain | Bundle ID blocklist (hardcoded) | No events generated |

The allowlist is defined per engagement in the backend configuration. If no allowlist is configured, a default blocklist of known sensitive applications (password managers, banking apps, personal health apps) applies.

### 7.3 Layer 2: At-Source Filtering (Python, On-Device)

Applied to every event before it enters the SQLite buffer. Events that contain PII are scrubbed in place; the scrubbed version is buffered. Original values never touch disk or network.

**Text scrubbing patterns**:

| PII Type | Detection Pattern | Replacement |
|----------|------------------|-------------|
| US Social Security Number | `\b\d{3}-\d{2}-\d{4}\b` | `[SSN_REDACTED]` |
| Credit/debit card | Luhn-valid 13-19 digit sequences | `[CARD_REDACTED]` |
| Email address | RFC 5322 pattern | `[EMAIL_REDACTED]` |
| US phone number | `\b(\+1[-.\s]?)?(\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b` | `[PHONE_REDACTED]` |
| Date of birth | Contextual date + age-suggestive proximity | `[DOB_REDACTED]` |
| IP address | IPv4 and IPv6 patterns | `[IP_REDACTED]` |
| Passport / driver license | Pattern library by jurisdiction | `[ID_REDACTED]` |

**Screenshot redaction (Phase 2)**:
When `SCREEN_CAPTURE` events are enabled, the Python layer runs a local OCR model (Tesseract or Apple Vision framework output) over each screenshot and applies bounding-box redaction over detected PII regions before the image is encoded for upload. The redaction replaces the pixel region with a solid fill, not a blur. Screenshots that fail OCR processing are dropped, not uploaded.

### 7.4 Layer 3: Server-Side Processing (FastAPI + Worker)

Applied after events arrive at the backend, before they are written to PostgreSQL.

| Stage | Method | Outcome |
|-------|--------|---------|
| NLP PII scan | spaCy NER (PERSON, ORG, GPE, DATE entities in context) | Flag and quarantine |
| LLM ambiguous PII | Claude API with few-shot PII classification prompt | Quarantine if high-confidence PII |
| Quarantine | `pii_quarantine` table with 24-hour TTL | Auto-delete after TTL; no persistence to evidence store |
| Audit log | Every quarantine event logged with agent ID, session, event type, detection method | Immutable audit trail |

Quarantined events do not flow to `task_mining_events` or the knowledge graph. If a batch contains quarantined events, the non-quarantined events in the same batch are processed normally. Quarantine does not block the batch.

### 7.5 Layer 4: Data Management

| Control | Configuration | Default |
|---------|--------------|---------|
| Raw event retention | Engagement-configurable | 90 days |
| Aggregated action retention | Engagement-configurable | 365 days |
| GDPR erasure | `DELETE FROM task_mining_*` where `agent_id` in erasure request | Within 30 days of request |
| Right to access | Export all events for a given agent/user | Available via API |
| Audit log retention | Not deletable | 7 years (compliance hold) |
| Data residency | Events processed and stored in configured region | EU or US |
| Encryption at rest | AES-256 | Required |
| Encryption in transit | TLS 1.3 + mTLS client cert | Required |

---

## 8. Desktop Evidence Capture Policy

This section defines the capture policy for all desktop evidence types: keystroke behavior, context switching sequences, and Visual Context Events (VCEs). All capture is governed by the PII filtering architecture defined in Section 7 and the engagement policy bundle.

### 8.1 Keystroke Capture Policy

Keystroke capture has two modes. The default is action-level. Content-level is opt-in and requires explicit configuration at the engagement level.

#### 8.1.1 Action-Level (Default)

The agent records metadata about keyboard activity but not the actual characters typed.

```json
{
  "event_type": "KEYBOARD_ACTION",
  "app_bundle_id": "com.microsoft.Excel",
  "element_role": "AXTextField",
  "action_metadata": {
    "char_count": 47,
    "duration_ms": 12300,
    "backspace_count": 3,
    "special_key_count": 2,
    "content_level": false
  }
}
```

This captures the behavioral pattern (typing speed, correction rate, field usage) without any content that could contain PII.

#### 8.1.2 Content-Level (Opt-In)

When enabled, the agent records the actual characters typed. This mode requires:
1. Explicit `keystroke_mode: content` in the engagement configuration
2. L1 password field detection remains active (password fields never record content regardless of mode)
3. L2 regex scrubbing applied to all content before buffering
4. L3 NLP scan applied server-side before persistence

Content-level capture produces significantly richer evidence for detecting process patterns (specific values entered, form field sequences, copy-paste content) but increases PII risk. It is appropriate only when the engagement scope justifies it and the client has signed appropriate data processing agreements.

#### 8.1.3 Keyboard Shortcut Capture

Keyboard shortcuts (`Ctrl+C`, `Cmd+Z`, `Alt+F4`, etc.) are always captured in both modes without restriction. Shortcuts are process signals (copy-paste frequency, undo patterns) and contain no PII.

---

### 8.2 Switching Sequences

#### 8.2.1 Intent

Context switching sequences capture the ordered transitions between applications during a work session. Switching data is critical for detecting friction patterns (work bouncing across systems), identifying cross-system dependency chains, informing swimlane attribution in the Work Reality Graph, and surfacing automation candidates where repetitive system-switching implies manual handoff work.

Switching sequences are derived from application focus sessions and do not require additional sensitive capture.

#### 8.2.2 SwitchingTrace Data Model

Each individual application-to-application transition is recorded as a `SwitchingTrace`:

```python
class SwitchingTrace:
    id: UUID                        # Unique trace ID
    session_id: UUID                # Parent task mining session
    agent_id: UUID                  # Originating agent
    engagement_id: UUID             # Engagement scope
    role_ref: str                   # Role identifier (never personal identity by default)
    from_app: str                   # Normalized app identifier
    from_module: str | None         # Module/window within app (if observable)
    to_app: str                     # Normalized app identifier
    to_module: str | None           # Module/window within app (if observable)
    switched_at: datetime           # UTC timestamp of focus change
    dwell_ms: int                   # Time spent in from_app before switching
    interaction_intensity: float    # Interaction count in from_app during dwell window (0.0–1.0 normalized)
    vce_ref: UUID | None            # Optional: VCE captured at this transition
    created_at: datetime
```

#### 8.2.3 TransitionMatrix

The `TransitionMatrix` is a pre-aggregated representation of switching patterns for a role over a time window. It is computed by the backend worker and used by analytics and heat map services.

```python
class TransitionMatrix:
    id: UUID
    engagement_id: UUID
    role_ref: str
    window_start: datetime
    window_end: datetime
    matrix: dict[str, dict[str, int]]  # {from_app: {to_app: count}}
    total_transitions: int
    dominant_path: list[str]           # Most frequent sequence of apps
    friction_score: float              # Composite friction index (0.0–1.0)
    ping_pong_pairs: list[dict]        # Detected A↔B oscillations with counts
    computed_at: datetime
```

#### 8.2.4 Role-Level Aggregation

Switching analytics are computed at role level by default. Individual user identity is never surfaced in switching views unless the engagement policy explicitly enables identity-level drilldown (gated by ABAC policy). Analytics roll up via `role_ref`, which is derived from directory group membership or enrollment configuration.

Minimum cohort size is enforced before any role-level view is surfaced. If a role has fewer than the configured minimum (default: 3 users), the view is suppressed to prevent re-identification.

#### 8.2.5 Friction Detection

The friction score for a transition matrix is computed as a weighted sum of:
- **Raw transition volume**: high switch frequency indicates system dependency
- **Dwell time variance**: high variance indicates unpredictable wait states
- **Return rate**: how often the user returns to the previous app within N seconds (ping-pong indicator)
- **Interaction intensity drop**: switches preceded by low interaction may indicate blocking/waiting states

```
friction_score = (
    normalized_transition_rate   * 0.30 +
    dwell_variance_coefficient   * 0.25 +
    return_rate                  * 0.25 +
    pre_switch_idle_ratio        * 0.20
)
```

#### 8.2.6 Ping-Pong Detection

Ping-pong (A→B→A→B oscillation) is detected when the same pair of applications appears in alternating sequence at least 3 times within a 10-minute window. Ping-pong is a strong signal of:
- Copy-paste workflows that should be automated
- Dual-screen lookup patterns (ERP + spreadsheet cross-referencing)
- Error-correction loops (enter in system A, verify in system B)

Detected ping-pong pairs are surfaced in the `TransitionMatrix.ping_pong_pairs` field and flagged in the Work Reality Graph as `FRICTION_SIGNAL` relationship attributes.

---

### 8.3 Visual Context Events (VCEs)

#### 8.3.1 Intent

A Visual Context Event (VCE) is a structured metadata record derived from a targeted, on-device screenshot. VCEs resolve ambiguity that application focus data alone cannot resolve: specifically, they classify what type of work the user is performing when time accumulates on a given screen.

VCEs are not screen recordings. The screenshot is processed locally, produces structured metadata, and is then discarded by default. The VCE record contains the classification output, not the image.

#### 8.3.2 VCE Record Schema

All 13 fields are required in the VCE record:

```python
class VisualContextEvent:
    timestamp: datetime              # UTC timestamp when screenshot was captured
    screen_state_class: str          # Classification: one of 8 screen state classes (see 8.3.3)
    system_guess: str | None         # Best-guess system/application if inferable from UI signals
    module_guess: str | None         # Best-guess module/section within system if inferable
    confidence: float                # Classification confidence (0.0–1.0)
    trigger_reason: str              # Which trigger class fired (see 8.4.2)
    sensitivity_flags: list[str]     # PII risk category tags detected (e.g., ["PII_NAME", "FINANCIAL"])
    application_name: str            # Normalized application name from agent context
    window_title_redacted: str       # Window title with PII tokens replaced by L2 scrubber
    dwell_ms: int                    # Time user spent on this screen before VCE triggered
    interaction_intensity: float     # Interaction activity level during dwell window (0.0–1.0)
    snapshot_ref: UUID | None        # Reference to redacted snapshot in R2 (only if retention enabled)
    ocr_text_redacted: str | None    # OCR-extracted text with PII redacted (only if OCR enabled)
```

#### 8.3.3 Screen State Classes

Eight mutually exclusive screen state classes are supported. The classifier assigns one class per VCE:

| Class | Description | Process Signal |
|-------|-------------|----------------|
| `queue` | User is viewing a work queue, inbox, or task list | Queue depth, arrival rate, workload distribution |
| `search` | User is executing a search query or browsing results | Search frequency, result navigation time |
| `data_entry` | User is typing structured data into form fields | Data entry duration, field traversal, error rate |
| `review` | User is reading, scanning, or reviewing content without entering data | Review time, document type |
| `error` | An error message, validation failure, or exception screen is visible | Error frequency, error type clustering |
| `waiting_latency` | Screen shows a loading state, spinner, or progress indicator | System latency, wait time accumulation |
| `navigation` | User is navigating menus, switching tabs, or changing views within an app | Navigation complexity, menu depth |
| `other` | Screen state does not fit the above classes or confidence is below threshold | Unclassified time accumulation |

#### 8.3.4 Classification Pipeline

VCE classification runs on-device via a local lightweight model. The pipeline is:

1. **Screenshot capture** — taken into memory only; never written to disk in default mode
2. **Sensitivity pre-scan** — heuristic detection of PII-likely regions (form fields, personal data patterns); regions are blurred before classification input
3. **Local classification** — screen state model produces `screen_state_class` + `confidence`
4. **System/module inference** — app context + UI element signals used to populate `system_guess` / `module_guess`
5. **OCR** (optional, policy-gated) — local OCR extracts text; L2 PII scrubber applied to output
6. **Record assembly** — VCE record assembled from all outputs
7. **Screenshot discard** — image memory freed immediately after step 6 (default mode)
8. **Redacted snapshot retention** (optional) — if `vce_snapshot_retention: enabled` in policy, a redacted JPEG is encrypted with AES-256-GCM and uploaded to R2 with a content-expiry header

---

### 8.4 VCE Trigger Policy

#### 8.4.1 Intent

VCE triggers are the mechanism that controls *when* screenshots occur. Triggers exist to limit screenshot frequency and to ensure captures are purposeful. This is a trust requirement: workers and enterprise IT must be able to predict when screenshots can be taken and confirm that the system does not capture continuously.

All trigger parameters are policy-controlled via the engagement configuration bundle and subject to hard frequency caps.

#### 8.4.2 Trigger Classes

Five trigger classes are defined. All are enabled by default but can be individually disabled in policy:

**Trigger 1: High Dwell Time**
Fires when focus duration on an allowlisted app exceeds the dwell threshold AND interaction intensity during that dwell period is below the activity threshold. This classifies accumulated time as waiting, review, or queue processing rather than active work.

**Trigger 2: Low Classification Confidence**
Fires when the agent cannot classify the current work state from non-image signals (application context, focus session metadata, interaction counts). A VCE is taken to reduce ambiguity and improve the Work Reality Graph segment quality.

**Trigger 3: Recurring Error Signature**
Fires when a VCE previously classified as `error` is detected in a repeating pattern: same application, similar session context, within the error recurrence window. This quantifies rework loops and error frequency.

**Trigger 4: Novel/Unclassified Cluster**
Fires when a new pattern of focus session and interaction features appears frequently but cannot be classified using existing session signals. This identifies missing subprocess coverage in the Work Reality Graph.

**Trigger 5: Taxonomy Boundary**
Fires at engagement-defined transition boundaries — points in the process model where the engagement team needs confirmation of which subprocess is executing. Only fires when the agent context matches the configured boundary condition.

#### 8.4.3 Frequency Caps

The following caps are enforced as hard limits. The agent will not trigger a VCE that would violate any active cap, regardless of trigger condition:

| Cap | Default | Configurable Range |
|-----|---------|-------------------|
| Max VCEs per hour per device | 12 | 1–30 |
| Max VCEs per workday per device | 60 | 10–200 |
| Min cooldown between VCEs (same app) | 120 seconds | 30–600 seconds |
| Min cooldown between VCEs (any app) | 30 seconds | 10–120 seconds |

If the engagement policy sets `vce_enabled: false` or the user pauses capture via the widget, all VCE triggers are immediately disabled until the policy is updated or capture is resumed.

---

### 8.5 On-Device Processing and Retention

#### 8.5.1 Intent

The endpoint must not become a sensitive data replication tool. Image processing runs locally by default, and retention is minimized. This section defines the default memory-only pipeline and the gated optional retention mode.

#### 8.5.2 Default: Memory-Only Pipeline

In default mode, the VCE pipeline is fully in-memory:

1. Screenshot captured into a temporary memory buffer (never written to disk)
2. Sensitivity pre-scan applied to blur PII-likely regions in memory
3. Local classifier runs against the in-memory buffer
4. VCE metadata record assembled
5. Screenshot memory buffer freed immediately
6. VCE metadata record buffered in SQLite for upload
7. Classified image is never transmitted — only the VCE metadata record leaves the device

#### 8.5.3 Optional Redacted Retention Mode

When `vce_snapshot_retention: enabled` is set in the engagement policy:

- A redacted JPEG (PII-likely regions replaced with solid fill, not blur) is produced from the in-memory buffer after classification
- The redacted image is encrypted with AES-256-GCM using a per-engagement key
- The encrypted blob is uploaded to Cloudflare R2 with a content-expiry header matching the engagement retention policy
- The `snapshot_ref` field in the VCE record is populated with the R2 object key
- Access to R2 snapshots is controlled via ABAC policy: only engagement leads with `vce_snapshot:read` permission can retrieve them
- Snapshot retention is bounded to the engagement window plus 30 days; automatic deletion is enforced via R2 lifecycle rules

This mode is off by default and must be explicitly enabled with client approval. Enabling it requires a signed data processing addendum acknowledging the snapshot retention scope.

---

## 9. Event Taxonomy

All events share a common envelope:

```json
{
  "agent_id": "uuid",
  "session_id": "uuid",
  "sequence_number": 1042,
  "event_type": "APP_SWITCH",
  "timestamp_ns": 1740480000000000000,
  "app_bundle_id": "com.microsoft.Excel",
  "window_title": "Q4 Budget Review.xlsx",
  "payload": { ... }
}
```

### 9.1 Event Type Reference

| Event Type | Trigger | Key Payload Fields |
|------------|---------|-------------------|
| `APP_SWITCH` | User moves focus to a different application | `from_app`, `to_app`, `dwell_ms` |
| `WINDOW_FOCUS` | Window within an application gains focus | `window_title`, `window_role` |
| `MOUSE_CLICK` | Single mouse button press | `button`, `element_role`, `element_description`, `x`, `y` |
| `MOUSE_DOUBLE_CLICK` | Double click on element | `button`, `element_role`, `element_description` |
| `MOUSE_DRAG` | Drag from source to target | `source_role`, `target_role`, `delta_px` |
| `KEYBOARD_ACTION` | Keyboard typing in a field | `char_count`, `duration_ms`, `backspace_count`, `content` (content-level only) |
| `KEYBOARD_SHORTCUT` | System or application shortcut | `shortcut_keys`, `app_action` |
| `COPY_PASTE` | Clipboard copy or paste operation | `operation` (copy/paste/cut), `content_type` (text/image/file), `char_count` |
| `SCROLL` | Scroll event in application | `direction`, `delta_units`, `element_role` |
| `TAB_SWITCH` | Browser tab change | `from_url_domain`, `to_url_domain` |
| `FILE_OPEN` | File opened in application | `file_extension`, `file_size_kb`, `app_bundle_id` |
| `FILE_SAVE` | File saved | `file_extension`, `file_size_kb`, `save_type` (save/save-as/auto-save) |
| `URL_NAVIGATION` | Browser navigates to URL | `url_domain`, `url_path_hash` (never full URL with PII params) |
| `SCREEN_CAPTURE` | Periodic or triggered screenshot | `capture_trigger`, `image_data_redacted` (base64, PII-redacted) |
| `UI_ELEMENT_INTERACTION` | AXUIElement interaction not covered above | `element_role`, `element_description`, `interaction_type` |
| `IDLE_START` | No events for idle threshold (default: 5 minutes) | `idle_threshold_s` |
| `IDLE_END` | Activity resumes after idle | `idle_duration_s`, `resuming_app` |
| `VISUAL_CONTEXT_EVENT` | VCE trigger condition met (see Section 8.3–8.4) | `screen_state_class`, `system_guess`, `module_guess`, `confidence`, `trigger_reason`, `sensitivity_flags`, `dwell_ms`, `interaction_intensity`, `window_title_redacted`, `snapshot_ref` |

**Privacy notes on URL capture**: Full URLs are never stored. Only the domain and a hash of the path are captured. Query parameters are always dropped. URL capture requires the browser to be on the engagement allowlist.

**Privacy notes on VISUAL_CONTEXT_EVENT**: The VCE record contains structured metadata only. The originating screenshot is processed locally and discarded in default mode. The `window_title_redacted` field has PII tokens replaced by the L2 scrubber before the record is buffered. The `snapshot_ref` field is `null` unless optional redacted retention is enabled (see Section 8.5.3).

---

## 10. Evidence Integration

### 10.1 Evidence Materialization

Captured task mining data materializes as `EvidenceItem` records in WorkGraphIQ's evidence store with category `KM4Work` (category 7 in the platform taxonomy). This follows the same pattern as the Soroco connector but with first-party data and guaranteed quality provenance.

```python
EvidenceItem(
    engagement_id=session.engagement_id,
    category=EvidenceCategory.KM4WORK,
    format=EvidenceFormat.TASK_MINING_AGENT,
    source="kmflow_task_mining_agent",
    agent_id=agent.id,
    session_id=session.id,
    quality_score=compute_quality(session),
    reliability_score=0.90,  # First-party observed behavior: highest tier
    freshness_score=compute_freshness(session.end_time),
    completeness_score=compute_completeness(session),
    validation_status=ValidationStatus.AUTO_VALIDATED,
    content_hash=sha256(session_payload),
    metadata={
        "event_count": session.event_count,
        "action_count": session.action_count,
        "app_coverage": session.applications_observed,
        "pii_events_quarantined": session.pii_quarantine_count,
        "capture_mode": session.keystroke_mode,
        "agent_version": agent.version,
    }
)
```

### 10.2 Confidence Score Weight

Task mining evidence carries a source weight of **0.9** in the confidence scoring model. This is the highest tier in the platform — equal to system-generated data — because observed behavior represents ground truth process execution:

```
confidence = (
    evidence_coverage  * 0.30 +    # Task mining provides direct observation
    evidence_agreement * 0.25 +    # Cross-validates with documents/interviews
    evidence_quality   * 0.20 +    # 0.9 reliability (first-party, PII-filtered)
    source_reliability * 0.15 +    # 0.9 source weight (observed, not declared)
    evidence_recency   * 0.10      # Freshness based on session recency
)
```

### 10.3 Redis Streams Integration

Task mining events are published to a dedicated Redis Stream to isolate throughput from other monitoring streams:

```
Stream: TASK_MINING_STREAM
Consumer group: task-mining-workers
Message fields: agent_id, session_id, batch_id, event_count, payload_compressed
```

The worker consumes from `TASK_MINING_STREAM` using the standard consumer group pattern established by the monitoring subsystem. Failed batches are retried with exponential backoff up to 5 attempts, then moved to a dead-letter queue for manual inspection.

### 10.4 Knowledge Graph Integration

Task mining data extends the Neo4j schema with two new node types and two new relationship types:

**New node types**:

```cypher
// Application observed in task mining sessions
(:Application {
    bundle_id: string,          // com.microsoft.Excel
    display_name: string,       // Microsoft Excel
    category: string,           // productivity | browser | erp | crm | ...
    first_observed: datetime,
    engagement_id: string
})

// Aggregated user action (not raw event — semantic task unit)
(:UserAction {
    id: string,
    session_id: string,
    action_type: string,        // APP_SWITCH | FILE_OPEN | KEYBOARD_ACTION | ...
    app_bundle_id: string,
    element_role: string,
    duration_ms: int,
    timestamp: datetime,
    engagement_id: string
})
```

**New relationship types**:

```cypher
// Links a UserAction to the Application it occurred in
(:UserAction)-[:PERFORMED_IN {duration_ms: int}]->(:Application)

// Links sequential UserActions within a session (task sequence chain)
(:UserAction)-[:PRECEDED_BY {gap_ms: int, same_app: bool}]->(:UserAction)

// Links UserAction to a WorkGraphIQ Process element (populated by Phase 3 assembly) (populated by Phase 3 assembly)
(:UserAction)-[:MAPS_TO {confidence: float, assembly_version: string}]->(:Activity)
```

### 10.5 MonitoringSourceType Integration

Task mining sessions register as monitoring sources using the existing `MonitoringSourceType.TASK_MINING` enum value (`src/core/models/monitoring.py`). This connects task mining sessions to the monitoring dashboard and enables unified process deviation detection across all monitoring source types.

---

## 11. Database Schema

### 11.1 New Tables

**`task_mining_agents`** — Registered desktop agents

```sql
CREATE TABLE task_mining_agents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id   UUID NOT NULL REFERENCES engagements(id),
    hostname        VARCHAR(255) NOT NULL,
    machine_id      VARCHAR(255) NOT NULL,  -- macOS hardware UUID, hashed
    os_version      VARCHAR(100) NOT NULL,
    agent_version   VARCHAR(50) NOT NULL,
    deployment_mode VARCHAR(20) NOT NULL CHECK (deployment_mode IN ('engagement', 'enterprise')),
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'paused', 'expired', 'revoked')),
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,            -- NULL for enterprise mode
    last_heartbeat  TIMESTAMPTZ,
    config_jwt      TEXT NOT NULL,          -- Signed config delivered to agent
    cert_thumbprint VARCHAR(128),           -- mTLS client cert fingerprint
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_mining_agents_engagement ON task_mining_agents(engagement_id);
CREATE INDEX idx_task_mining_agents_status ON task_mining_agents(status);
CREATE UNIQUE INDEX idx_task_mining_agents_machine ON task_mining_agents(engagement_id, machine_id);
```

**`task_mining_sessions`** — Capture sessions per agent

```sql
CREATE TABLE task_mining_sessions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id                UUID NOT NULL REFERENCES task_mining_agents(id),
    engagement_id           UUID NOT NULL REFERENCES engagements(id),
    started_at              TIMESTAMPTZ NOT NULL,
    ended_at                TIMESTAMPTZ,
    status                  VARCHAR(20) NOT NULL DEFAULT 'active'
                                CHECK (status IN ('active', 'completed', 'interrupted')),
    keystroke_mode          VARCHAR(20) NOT NULL DEFAULT 'action'
                                CHECK (keystroke_mode IN ('action', 'content')),
    event_count             INTEGER NOT NULL DEFAULT 0,
    action_count            INTEGER NOT NULL DEFAULT 0,
    pii_quarantine_count    INTEGER NOT NULL DEFAULT 0,
    applications_observed   TEXT[],
    idle_duration_total_s   INTEGER NOT NULL DEFAULT 0,
    evidence_item_id        UUID REFERENCES evidence_items(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_mining_sessions_agent ON task_mining_sessions(agent_id);
CREATE INDEX idx_task_mining_sessions_engagement ON task_mining_sessions(engagement_id);
CREATE INDEX idx_task_mining_sessions_started ON task_mining_sessions(started_at);
```

**`task_mining_events`** — Raw event stream (high-volume, partitioned by month)

```sql
CREATE TABLE task_mining_events (
    id              UUID NOT NULL DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES task_mining_sessions(id),
    agent_id        UUID NOT NULL REFERENCES task_mining_agents(id),
    engagement_id   UUID NOT NULL REFERENCES engagements(id),
    sequence_number BIGINT NOT NULL,
    event_type      VARCHAR(50) NOT NULL,
    timestamp_ns    BIGINT NOT NULL,        -- Nanosecond epoch from agent
    app_bundle_id   VARCHAR(255),
    window_title    TEXT,                   -- L2-filtered; may contain [PII_REDACTED] tokens
    element_role    VARCHAR(100),
    payload         JSONB NOT NULL,
    batch_id        UUID NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE INDEX idx_task_mining_events_session ON task_mining_events(session_id, created_at);
CREATE INDEX idx_task_mining_events_type ON task_mining_events(event_type, created_at);
CREATE INDEX idx_task_mining_events_app ON task_mining_events(app_bundle_id, created_at);
```

**`task_mining_actions`** — Aggregated semantic actions (lower volume, queryable)

```sql
CREATE TABLE task_mining_actions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES task_mining_sessions(id),
    engagement_id   UUID NOT NULL REFERENCES engagements(id),
    action_type     VARCHAR(50) NOT NULL,
    app_bundle_id   VARCHAR(255),
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ NOT NULL,
    duration_ms     INTEGER NOT NULL,
    event_ids       UUID[],                 -- Source events aggregated into this action
    properties      JSONB NOT NULL,
    graph_node_id   VARCHAR(255),           -- Neo4j UserAction node ID
    process_element_id UUID,               -- Linked process element (Phase 3)
    confidence      FLOAT,                  -- Assembly confidence (Phase 3)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_mining_actions_session ON task_mining_actions(session_id);
CREATE INDEX idx_task_mining_actions_engagement ON task_mining_actions(engagement_id);
CREATE INDEX idx_task_mining_actions_type ON task_mining_actions(action_type, started_at);
CREATE INDEX idx_task_mining_actions_app ON task_mining_actions(app_bundle_id);
```

**`pii_quarantine`** — PII-flagged events pending review and auto-deletion

```sql
CREATE TABLE pii_quarantine (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id            UUID NOT NULL REFERENCES task_mining_agents(id),
    session_id          UUID NOT NULL REFERENCES task_mining_sessions(id),
    batch_id            UUID NOT NULL,
    sequence_number     BIGINT NOT NULL,
    event_type          VARCHAR(50) NOT NULL,
    detection_layer     VARCHAR(10) NOT NULL CHECK (detection_layer IN ('L3', 'L4')),
    detection_method    VARCHAR(100) NOT NULL,   -- 'spacy_ner', 'llm_classification', etc.
    confidence          FLOAT NOT NULL,
    payload_hash        VARCHAR(64) NOT NULL,    -- SHA-256, not the payload itself
    quarantined_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '24 hours',
    deleted_at          TIMESTAMPTZ,
    audit_note          TEXT
);

CREATE INDEX idx_pii_quarantine_expires ON pii_quarantine(expires_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_pii_quarantine_agent ON pii_quarantine(agent_id);
```

**`switching_traces`** — Individual application-to-application transitions

```sql
CREATE TABLE switching_traces (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id              UUID NOT NULL REFERENCES task_mining_sessions(id),
    agent_id                UUID NOT NULL REFERENCES task_mining_agents(id),
    engagement_id           UUID NOT NULL REFERENCES engagements(id),
    role_ref                VARCHAR(255) NOT NULL,          -- Role identifier (never personal identity by default)
    from_app                VARCHAR(255) NOT NULL,          -- Normalized app identifier
    from_module             VARCHAR(255),                   -- Module/window within app (if observable)
    to_app                  VARCHAR(255) NOT NULL,          -- Normalized app identifier
    to_module               VARCHAR(255),                   -- Module/window within app (if observable)
    switched_at             TIMESTAMPTZ NOT NULL,           -- UTC timestamp of focus change
    dwell_ms                INTEGER NOT NULL,               -- Time spent in from_app before switching
    interaction_intensity   FLOAT NOT NULL DEFAULT 0.0,    -- 0.0–1.0 normalized activity level
    vce_ref                 UUID,                           -- Optional: VCE captured at this transition
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_switching_traces_session ON switching_traces(session_id);
CREATE INDEX idx_switching_traces_engagement ON switching_traces(engagement_id, switched_at);
CREATE INDEX idx_switching_traces_role ON switching_traces(engagement_id, role_ref, switched_at);
CREATE INDEX idx_switching_traces_apps ON switching_traces(from_app, to_app, engagement_id);
```

**`transition_matrices`** — Pre-aggregated switching pattern summaries per role per time window

```sql
CREATE TABLE transition_matrices (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id       UUID NOT NULL REFERENCES engagements(id),
    role_ref            VARCHAR(255) NOT NULL,
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,
    matrix              JSONB NOT NULL,             -- {from_app: {to_app: count}}
    total_transitions   INTEGER NOT NULL DEFAULT 0,
    dominant_path       TEXT[],                    -- Most frequent app sequence
    friction_score      FLOAT,                     -- Composite friction index (0.0–1.0)
    ping_pong_pairs     JSONB,                     -- Detected A↔B oscillations with counts
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_transition_matrices_engagement ON transition_matrices(engagement_id, window_start);
CREATE INDEX idx_transition_matrices_role ON transition_matrices(engagement_id, role_ref, window_start);
CREATE UNIQUE INDEX idx_transition_matrices_role_window ON transition_matrices(engagement_id, role_ref, window_start, window_end);
```

**`visual_context_events`** — VCE metadata records (all 13 fields)

```sql
CREATE TABLE visual_context_events (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id              UUID NOT NULL REFERENCES task_mining_sessions(id),
    agent_id                UUID NOT NULL REFERENCES task_mining_agents(id),
    engagement_id           UUID NOT NULL REFERENCES engagements(id),
    timestamp               TIMESTAMPTZ NOT NULL,                   -- When screenshot was captured
    screen_state_class      VARCHAR(50) NOT NULL
                                CHECK (screen_state_class IN (
                                    'queue', 'search', 'data_entry', 'review',
                                    'error', 'waiting_latency', 'navigation', 'other'
                                )),
    system_guess            VARCHAR(255),                           -- Best-guess system if inferable
    module_guess            VARCHAR(255),                           -- Best-guess module if inferable
    confidence              FLOAT NOT NULL
                                CHECK (confidence >= 0.0 AND confidence <= 1.0),
    trigger_reason          VARCHAR(50) NOT NULL
                                CHECK (trigger_reason IN (
                                    'high_dwell', 'low_confidence', 'recurring_error',
                                    'novel_state', 'taxonomy_boundary'
                                )),
    sensitivity_flags       TEXT[] NOT NULL DEFAULT '{}',           -- PII risk category tags
    application_name        VARCHAR(255) NOT NULL,                  -- Normalized app name from agent
    window_title_redacted   TEXT NOT NULL,                          -- L2-scrubbed window title
    dwell_ms                INTEGER NOT NULL,                       -- Dwell time before VCE triggered
    interaction_intensity   FLOAT NOT NULL DEFAULT 0.0
                                CHECK (interaction_intensity >= 0.0 AND interaction_intensity <= 1.0),
    snapshot_ref            VARCHAR(512),                           -- R2 object key (null by default)
    ocr_text_redacted       TEXT,                                   -- L2-scrubbed OCR output (null by default)
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_vce_session ON visual_context_events(session_id, timestamp);
CREATE INDEX idx_vce_engagement ON visual_context_events(engagement_id, timestamp);
CREATE INDEX idx_vce_class ON visual_context_events(engagement_id, screen_state_class, timestamp);
CREATE INDEX idx_vce_trigger ON visual_context_events(trigger_reason, engagement_id);
CREATE INDEX idx_vce_app ON visual_context_events(application_name, engagement_id, timestamp);
```

### 11.2 GDPR Erasure Extension

The existing GDPR erasure procedure is extended to include task mining tables and the new WGI evidence tables. When a user erasure request is processed, the procedure deletes all rows from `task_mining_events`, `task_mining_actions`, `task_mining_sessions`, `switching_traces`, `transition_matrices`, and `visual_context_events` associated with the agent(s) registered for that user. The `pii_quarantine` table is included. `task_mining_agents` records are anonymized (hostname and machine_id nulled) but not deleted, to preserve audit log integrity.

For `visual_context_events` rows with a non-null `snapshot_ref`, the corresponding R2 object is deleted via the R2 API before the database row is removed. Snapshot deletion is logged in the audit trail.

---

## 12. API Specification

### 12.1 Agent Lifecycle

**`POST /api/v1/taskmining/agents/register`**

Registers a new agent installation. Returns a signed configuration JWT and mTLS client certificate.

```json
Request:
{
  "engagement_id": "uuid",
  "hostname": "mbp-john-doe.local",
  "machine_id_hash": "sha256-of-hardware-uuid",
  "os_version": "macOS 15.3",
  "agent_version": "1.0.0",
  "deployment_mode": "engagement"
}

Response 201:
{
  "agent_id": "uuid",
  "config_jwt": "eyJ...",
  "client_cert_pem": "-----BEGIN CERTIFICATE-----...",
  "client_key_pem": "-----BEGIN PRIVATE KEY-----...",
  "config": {
    "keystroke_mode": "action",
    "app_allowlist": ["com.microsoft.Excel", "com.sap.gui"],
    "idle_threshold_s": 300,
    "batch_size": 500,
    "batch_interval_s": 30,
    "engagement_end_date": "2026-05-31"
  }
}
```

**`POST /api/v1/taskmining/heartbeat`**

Periodic liveness signal from agent. Returns updated configuration if changed since last heartbeat.

```json
Request:
{
  "agent_id": "uuid",
  "session_id": "uuid",
  "buffer_depth": 142,
  "last_event_timestamp_ns": 1740480000000000000,
  "agent_version": "1.0.0"
}

Response 200:
{
  "status": "active",
  "config_updated": false,
  "config": null
}
```

### 12.2 Event Ingestion

**`POST /api/v1/taskmining/events`**

Batch event upload from agent. Requires mTLS client certificate authentication.

```json
Request:
{
  "agent_id": "uuid",
  "session_id": "uuid",
  "batch_id": "uuid",
  "sequence_range": [1000, 1499],
  "event_count": 500,
  "checksum": "sha256-of-payload",
  "events": [ ... ]
}

Response 202:
{
  "accepted": 500,
  "quarantined": 2,
  "batch_id": "uuid",
  "stream_offset": "1-1740480000042"
}
```

### 12.3 Configuration

**`GET /api/v1/taskmining/config`**

Fetches current engagement configuration for a registered agent. Requires valid agent JWT.

```json
Response 200:
{
  "agent_id": "uuid",
  "engagement_id": "uuid",
  "keystroke_mode": "action",
  "app_allowlist": ["com.microsoft.Excel"],
  "app_blocklist_additions": [],
  "idle_threshold_s": 300,
  "batch_size": 500,
  "batch_interval_s": 30,
  "screen_capture_enabled": false,
  "ui_inspection_enabled": false,
  "engagement_end_date": "2026-05-31",
  "config_version": 3,
  "config_updated_at": "2026-02-20T10:00:00Z"
}
```

### 12.4 Query APIs

**`GET /api/v1/taskmining/sessions`**

Lists capture sessions for an engagement.

```
Query params: engagement_id, agent_id, status, started_after, started_before, limit, offset
```

**`GET /api/v1/taskmining/sessions/{session_id}/actions`**

Returns aggregated actions for a session with optional filtering by action type and application.

**`GET /api/v1/taskmining/actions`**

Returns aggregated actions across all sessions for an engagement.

```
Query params: engagement_id, action_type, app_bundle_id, started_after, started_before, limit, offset
```

### 12.5 Dashboard

**`GET /api/v1/taskmining/dashboard/stats`**

Returns engagement-level statistics for the task mining dashboard.

```json
Response 200:
{
  "engagement_id": "uuid",
  "active_agents": 8,
  "total_sessions": 42,
  "total_events": 1847293,
  "total_actions": 28471,
  "pii_quarantine_total": 143,
  "application_coverage": [
    {"bundle_id": "com.microsoft.Excel", "action_count": 8420, "session_count": 38},
    {"bundle_id": "com.sap.gui", "action_count": 6211, "session_count": 35}
  ],
  "top_action_types": [
    {"action_type": "KEYBOARD_ACTION", "count": 12040},
    {"action_type": "APP_SWITCH", "count": 8831}
  ],
  "idle_percentage": 18.4,
  "evidence_items_generated": 12,
  "capture_period": {
    "earliest_session": "2026-02-18T08:02:11Z",
    "latest_event": "2026-02-25T17:44:02Z"
  }
}
```

---

## 13. User Flows

### Flow 1: Agent Deployment (Engagement Mode)

```mermaid
sequenceDiagram
    participant EL as Engagement Lead
    participant Admin as WorkGraphIQ Admin
    participant IT as Client IT
    participant User as Client User
    participant Agent as macOS Agent

    EL->>Admin: Configure engagement for task mining
    Admin->>Admin: Define app allowlist, keystroke mode, end date
    Admin->>IT: Generate .dmg installer with engagement config
    IT->>User: Push .dmg via self-service or email
    User->>Agent: Install .dmg
    Agent->>User: Show consent dialog (what is captured)
    User->>Agent: Accept consent
    Agent->>Admin: POST /taskmining/agents/register
    Admin-->>Agent: agent_id + config JWT + mTLS cert
    Agent->>Agent: Begin capture (L1 active immediately)
    Agent->>Admin: POST /taskmining/heartbeat (every 30s)
    Agent->>Admin: POST /taskmining/events (every 30s batch)
```

### Flow 2: PII Event Handling

```mermaid
flowchart TD
    A[User types in text field] --> B{L1: Password field?}
    B -- Yes --> C[No event generated]
    B -- No --> D[Swift generates event]
    D --> E{L2: Regex PII match?}
    E -- Match --> F[Scrub in place: replace with token]
    E -- No match --> G[Event as-is]
    F --> G
    G --> H[Buffer to SQLite]
    H --> I[Batch upload to backend]
    I --> J{L3: NLP / LLM PII scan}
    J -- PII detected --> K[Quarantine: pii_quarantine table]
    J -- Clean --> L[Write to task_mining_events]
    K --> M[24h TTL auto-delete]
    L --> N[Publish to TASK_MINING_STREAM]
    N --> O[Worker: action assembly + graph write]
```

### Flow 3: Evidence Materialization and POV Impact

1. Engagement Lead configures task mining scope (apps, duration, keystroke mode)
2. Agents deployed to a sample of users performing target business process
3. Sessions run for agreed capture window (e.g., 5 business days)
4. Worker assembles raw events into semantic action sequences per session
5. Session evidence items created with `category=KM4WORK`, `reliability_score=0.9`
6. Process analyst reviews application coverage and action distribution in dashboard
7. POV generator re-runs with task mining evidence included
8. Confidence scores increase for process elements now observed in desktop data
9. Process variants detected (users following different task sequences) are flagged
10. Gap analysis updated: task-mined process elements without TOM alignment are new gap findings

---

## 14. Agent Performance Requirements

| Metric | Target | Measurement Method |
|--------|--------|--------------------|
| Event capture latency | < 5ms per event (p95) | Timestamp delta from OS event to Swift handler completion |
| Event loss rate | < 0.1% | Sequence number gap analysis on received batches |
| Agent CPU usage | < 3% average; < 10% burst (< 30s) | macOS Activity Monitor sampling during load test |
| Agent memory (resident) | < 150MB RSS | macOS `vmmap` during 8-hour session |
| Batch upload success rate | > 99.5% within 60s of batch ready | Server-side batch receipt acknowledgment |
| PII detection recall (L2) | > 99% on benchmark PII test set | Labeled test corpus with known PII patterns |
| PII detection precision (L2) | > 95% (minimize false positive redactions) | Labeled test corpus |
| Agent startup time | < 3s from launch to first event capture | End-to-end timing in test harness |
| SQLite buffer capacity | > 100,000 events offline before loss | Offline simulation with buffer fill rate |
| Backend event ingestion throughput | > 10,000 events/second per node | Load test with simulated agent fleet |

---

## 15. Security and Privacy

### 15.1 Transport Security

All agent-to-backend communication uses mutual TLS (mTLS). The backend issues a client certificate at registration time. This certificate is stored in the macOS keychain, accessible only to the agent application. The certificate is rotated every 90 days or on re-registration.

Agent communication never traverses HTTP. Port 443 is the only network requirement. No inbound ports are opened on the client machine.

### 15.2 Code Signing and Notarization

The macOS `.app` bundle is signed with an Apple Developer ID certificate and notarized with Apple's notary service. Unsigned builds fail macOS Gatekeeper checks and cannot be installed on modern macOS. The CI/CD pipeline includes automated notarization as a release gate.

### 15.3 Consent and Transparency

- Agent displays a visible menu bar icon while running; it cannot be hidden
- Consent dialog presented at first launch summarizes capture scope
- Content-level keystroke capture requires a separate explicit consent step
- Users can pause capture from the menu bar at any time
- Agent cannot be re-enabled by the user alone after a user-initiated pause; re-authorization requires backend config push

### 15.4 Data Minimization

The agent captures only what is necessary for process discovery:

- Application identifiers, not binary paths
- Window titles (PII-filtered), not window content
- Action metadata (char count, duration), not content (action-level mode)
- URL domains and hashed paths, not full URLs
- File extensions, not file names or paths

### 15.5 Audit Trail

Every agent registration, configuration change, consent event, capture pause/resume, PII quarantine event, and GDPR erasure action generates an immutable audit log entry. The audit log is append-only at the application layer and protected by database-level write constraints.

---

## 16. Phased Delivery

### Phase 1 - MVP (Q2 2026)

**Goal**: Core desktop observation capability deployable in a consulting engagement. Provides immediate value without requiring ML models or complex backend processing.

| Capability | Description |
|-----------|-------------|
| Swift event capture | `APP_SWITCH`, `WINDOW_FOCUS`, `MOUSE_CLICK`, `KEYBOARD_ACTION` (action-level), `KEYBOARD_SHORTCUT`, `IDLE_START`, `IDLE_END` |
| L1 PII prevention | Password field detection, app allowlist enforcement |
| L2 PII filtering | Regex scrubbing (SSN, CC, email, phone) |
| Local SQLite buffer | Offline persistence with 100,000 event capacity |
| Batch upload | HTTPS/mTLS to backend, 30s interval, 500 event batch |
| Agent registration API | `POST /api/v1/taskmining/agents/register` |
| Event ingestion API | `POST /api/v1/taskmining/events` |
| Heartbeat API | `POST /api/v1/taskmining/heartbeat` |
| Config API | `GET /api/v1/taskmining/config` |
| Redis Stream integration | `TASK_MINING_STREAM` with consumer group |
| Basic worker | Persist to `task_mining_events`; session management |
| Evidence materialization | `EvidenceItem(category=KM4WORK)` per session |
| Admin dashboard | Active agents, session count, event volume, app coverage |
| Engagement mode | Auto-disable at engagement end date |

**Phase 1 Success Gate**: At least one full engagement capture cycle (agent install through evidence materialization and POV re-run) completed with a real or simulated engagement, with zero PII leakage observed and < 0.1% event loss.

### Phase 2 - Intelligence (Q3 2026)

| Capability | Description |
|-----------|-------------|
| Full event taxonomy | Add `COPY_PASTE`, `SCROLL`, `TAB_SWITCH`, `FILE_OPEN`, `FILE_SAVE`, `URL_NAVIGATION`, `UI_ELEMENT_INTERACTION` |
| AXUIElement inspection | UI element role and description capture |
| Screenshot capture | `SCREEN_CAPTURE` events with local OCR + bounding-box PII redaction |
| L3 PII processing | spaCy NER + Claude LLM scan; quarantine table |
| ML task segmentation | Supervised model segmenting event streams into semantic task units |
| Action aggregation | Worker-side assembly of raw events into `task_mining_actions` |
| Knowledge graph writes | `Application` and `UserAction` nodes; `PERFORMED_IN`, `PRECEDED_BY` relationships |
| Content-level keystroke | Opt-in mode with L1+L2 mandatory enforcement |
| GDPR erasure extension | Extend existing erasure procedures to task mining tables |
| .pkg for MDM | Enterprise mode installer with Jamf/Intune configuration profile support |

### Phase 3 - Scale and Process Assembly (Q4 2026)

| Capability | Description |
|-----------|-------------|
| Process assembly | Link `UserAction` nodes to `Activity` nodes in WorkGraphIQ process models |
| Process variant detection | Graph-based identification of users following different task sequences |
| Knowledge graph queries | Task mining data available via `GET /api/v1/graph/query` |
| Windows agent | Port Swift layer to Windows (Win32 accessibility APIs, WH_KEYBOARD_LL hook) |
| Deviation detection | Compare observed task sequences against POV-generated process models in real time |
| Cross-agent session analysis | Aggregate task sequences across multiple agents for the same business process |
| Integration with Scenario Engine | Task mining observations feed directly into Scenario Comparison Workbench |

### Phase 4 - Autonomous Intelligence (2027)

| Capability | Description |
|-----------|-------------|
| Audio capture | Meeting and screen-share audio with ASR transcription; consent and PII architecture extended |
| AI agent monitoring | Capture AI agent actions (API calls, tool invocations) as first-class process events |
| Automated SOP generation | LLM-assisted generation of procedure documents from observed task sequences |
| Predictive assistance | Identify process deviations in progress; alert before exception occurs |
| Pattern library contribution | Cross-engagement process pattern extraction with strict engagement-level data isolation |

---

## 17. Competitive Differentiation

### 17.1 Feature Comparison

| Capability | WorkGraphIQ Agent | Soroco Scout | Celonis Task Mining | UiPath Task Mining |
|-----------|:-----------:|:------------:|:------------------:|:-----------------:|
| Knowledge graph integration | Yes | No | No | No |
| Evidence triangulation with docs/interviews | Yes | No | No | No |
| Consensus confidence scoring | Yes | No | No | No |
| Mandatory 4-layer PII architecture | Yes | Config-based | Config-based | Config-based |
| Engagement mode (auto-disable) | Yes | No | No | No |
| MDM deployment (Jamf/Intune) | Yes (Phase 2) | Yes | Yes | Yes |
| Process variant detection (graph-based) | Yes (Phase 3) | Limited | Yes | Limited |
| Consulting-native delivery workflow | Yes | No | No | No |
| On-device PII filtering (before upload) | Yes | Partial | Partial | Partial |
| First-party data (no vendor lock-in) | Yes | No | No | No |

### 17.2 Economic Comparison

| Factor | WorkGraphIQ Agent | Soroco Scout | Celonis Task Mining |
|--------|:-----------:|:------------:|:------------------:|
| Per-engagement cost | Platform subscription | $25,000+/engagement | Enterprise license |
| Data portability | Full (your data) | Limited (vendor platform) | Limited |
| PII architecture control | Full | Vendor-controlled | Vendor-controlled |
| Integration with evidence pipeline | Native | Via connector | Via connector |

---

## 18. Success Metrics

| Metric | Target | Phase | Measurement |
|--------|--------|-------|-------------|
| Capture latency (p95) | < 5ms/event | 1 | Swift timestamp delta |
| Event loss rate | < 0.1% | 1 | Sequence number gap analysis |
| Agent CPU (average) | < 3% | 1 | Activity Monitor sampling |
| Agent memory (RSS) | < 150MB | 1 | vmmap during 8h session |
| Batch upload success | > 99.5% within 60s | 1 | Server batch acknowledgment rate |
| PII detection recall (L2) | > 99% | 1 | Labeled PII test corpus |
| PII detection precision (L2) | > 95% | 1 | Labeled PII test corpus |
| Agent install success rate | > 98% | 1 | Registration success / install attempts |
| Confidence score uplift | > +0.10 on task-mining-enriched elements | 2 | Before/after POV comparison |
| Process variant detection recall | > 85% | 3 | Against manually labeled variant set |
| Soroco connector displacement | > 50% of engagements use first-party agent | 3 | Usage analytics |
| Engagement Lead satisfaction | > 4.5/5.0 | Ongoing | Post-engagement survey |

---

## 19. Risk Analysis

### 19.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| macOS API changes break capture (e.g., AXUIElement permissions tightened) | Medium | High | Monitor Apple developer announcements; pin macOS target version; test on beta releases |
| mTLS certificate rotation during active session causes upload failure | Medium | Medium | Grace period overlap during rotation; session-level retry with exponential backoff |
| SQLite buffer fill on disconnected machines causes event loss | Low | Medium | Buffer capacity monitoring via heartbeat; configurable max-buffer-size with graceful event dropping and audit logging |
| OCR-based screenshot PII redaction misses novel PII patterns | Medium | High | Defense-in-depth with L3 server-side scan; conservative false-positive threshold (redact on low confidence) |
| Windows accessibility API coverage gap vs. macOS | High | Medium | Phase 3 scope includes Windows-specific API research before commitment |

### 19.2 Privacy and Compliance Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| L2 regex fails to catch novel PII format (e.g., new national ID pattern) | Medium | High | L3 NLP scan as backstop; pattern library update process with quarterly review |
| User records clipboard content containing patient data despite L2 scrubbing | Low | Critical | Clipboard capture limited to content-type metadata in action-level mode; content-level requires additional consent |
| GDPR erasure request while active session buffering | Low | Medium | Erasure marks agent as suspended immediately; in-flight batches quarantined, not persisted |
| Enterprise mode deployed without user disclosure | Low | Critical | Deployment documentation requires corporate data processing notice; compliance checklist in MDM configuration profile |
| PII quarantine TTL expiry delayed by database load | Low | Medium | Quarantine deletion is a background job with SLA monitoring; TTL enforcement not query-dependent |

### 19.3 Business Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Client IT refuses agent installation in engagement mode | High | Medium | Provide detailed security whitepaper; offer air-gapped mode (local processing only, no upload); enterprise mode with MDM as alternative |
| User resistance to desktop monitoring | Medium | High | Transparent consent flow; visible menu bar icon; user pause capability; clear data minimization policy |
| macOS notarization delays block release | Low | Medium | Maintain active Apple Developer Program membership; automated notarization in CI/CD pipeline |
| Competing platform ships first-party task mining before Phase 1 complete | Medium | Medium | Phase 1 scope is deliberately narrow and fast to ship; knowledge graph integration is hard to replicate quickly |

---

## 20. Integration with Existing Platform

### 20.1 Module Placement

The Task Mining Agent backend components extend the existing `src/taskmining/` module:

```
src/
  taskmining/
    __init__.py          # Existing
    pii/
      __init__.py        # Existing
      filters.py         # NEW: L2 regex filter implementations
      quarantine.py      # NEW: L3 quarantine logic and TTL management
    agent.py             # NEW: Agent registration and lifecycle
    session.py           # NEW: Session management
    events.py            # NEW: Event ingestion and stream publishing
    worker.py            # NEW: Consumer group worker (event processing)
    actions.py           # NEW: Action aggregation (Phase 2)
    graph.py             # NEW: Neo4j write handlers (Phase 2)
    evidence.py          # NEW: EvidenceItem materialization
    dashboard.py         # NEW: Stats aggregation for dashboard API
```

### 20.2 API Router Integration

The task mining API endpoints register under the existing FastAPI application:

```python
# src/api/main.py
from src.api.routers import taskmining

app.include_router(
    taskmining.router,
    prefix="/api/v1/taskmining",
    tags=["task-mining"]
)
```

### 20.3 Evidence Pipeline Compatibility

Task mining sessions materialize as `EvidenceItem` records compatible with the existing evidence pipeline. The `category=KM4Work` assignment means:
- Evidence is included in POV generation when KM4Work is in scope
- Quality scoring uses the same four-dimension model (completeness, reliability, freshness, consistency)
- Evidence lifecycle (`PENDING` -> `VALIDATED` -> `ACTIVE`) applies without modification
- Content hashing and audit trail apply without modification

The only new behavior is `validation_status=AUTO_VALIDATED` at materialization time, bypassing the manual review queue for agent-sourced evidence (analogous to system connector behavior in the existing Soroco connector pattern).

---

## 21. Document Control

| Field | Value |
|-------|-------|
| Document ID | PRD-KMF-003 |
| Version | 1.0.0 |
| Status | Draft |
| Classification | Internal - Confidential |
| Owner | Paul Roth |
| Created | 2026-02-25 |
| Last Updated | 2026-02-25 |
| Next Review | 2026-03-25 |
| Related Documents | `docs/prd/PRD_KMFlow_Platform.md` (Platform PRD) |

---

*End of Document*
