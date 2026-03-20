# KM4ProcessBot v1 — Evidence Weighting Additions

## Purpose

This document defines seven additions to KM4ProcessBot v1 that make its interview methodology **machine-actionable** for the KMFlow consensus algorithm. The KM4ProcessBot document's philosophical framework is sound — the two-pathway architecture, eight probe types, epistemic frames, and evidence grading ladder are well-designed. These additions bridge the gap between the qualitative methodology and the quantitative weight computation that the consensus algorithm requires.

Without these additions, all interview evidence receives a flat 0.40 weight in the consensus algorithm regardless of who is being interviewed, what they reveal, or how confident they are. With these additions, a process owner describing shadow work they perform daily is weighted fundamentally differently than a department head speculating about a process they don't perform.

---

## Gap Analysis Summary

| # | Gap | Current State | Required State | Impact |
|---|---|---|---|---|
| 1 | No structured respondent metadata | `source: "activity owner interview"` as flat label | Structured fields: proximity, tenure, scope, interview type | Enables respondent authority multiplier on weight |
| 2 | No fragment-level assertion classification | Entire interview = one evidence source | Each fragment tagged: corroborative, elaborative, revelatory, contradictory | Enables novelty detection + shadow work flagging |
| 3 | No numeric weight modifiers | Qualitative grading ladder (Proposed → Auditable) | Quantitative formula: `base_weight × authority × novelty` | Bridges methodology to consensus algorithm |
| 4 | No shadow work validation queue | Revelatory evidence scored as low-confidence single-source | Flagged, routed to human validation, conditionally boosted | Prevents high-value evidence from being buried |
| 5 | No structured upstream/downstream chains | Sequence Probe captures narrative | Structured triples with per-link proximity | Maps directly to graph edges with confidence |
| 6 | No certainty tier on probe responses | Uncertainty captured only in dedicated probe (Part 4) | Every probe response carries certainty signal | Feeds claim weight into graph (1.0 / 0.6 / 0.3 / -0.5) |
| 7 | No stakeholder-ready contradiction report | Flat list of contradictions with evidence IDs | Grouped by element, enriched with named respondents, swim lanes, authority, and priority scoring + consensus heatmap | Drives targeted facilitation sessions to resolve disagreements across 100+ participants |

---

## Addition 1: Structured Respondent Metadata Capture

**Insert as**: New Section 5.2 in KM4ProcessBot

### 5.2 Respondent Metadata Capture

Before probing begins, the Survey Bot MUST capture structured metadata about the respondent. This metadata flows into `EvidenceItem.metadata_json` and feeds the consensus algorithm's respondent authority multiplier.

#### Required Fields

| Field | Type | Values | Capture Method |
|---|---|---|---|
| `respondent_name` | string | Full name of the interviewee | Bot asks: "What is your name?" (or pre-populated from session scheduling) |
| `respondent_role` | string | Free text organizational title | Bot asks: "What is your role/title?" |
| `process_proximity` | enum | `owner`, `participant`, `supervisor`, `consumer`, `observer` | Bot asks: "Do you perform this activity yourself, participate in it, supervise it, receive its output, or observe it from outside?" |
| `authority_scope` | enum | `own_activities`, `team_activities`, `department_activities`, `hearsay` | Bot asks: "Are you describing work you personally do, work your team does, work in your department, or something you've been told about?" |
| `years_in_role` | integer | 0–50 | Bot asks: "How long have you been in this role?" |
| `interview_type` | enum | `structured_walkthrough`, `open_ended`, `validation_session`, `process_mapping_workshop` | Set by interview facilitator at session start |
| `swim_lane` | string | The swim lane this respondent operates in | Bot asks: "Which part of the process are you responsible for?" |

#### Definition of Process Proximity Values

- **owner**: The person who performs the activity as part of their daily responsibilities. They can describe inputs, outputs, timing, exceptions, and workarounds from direct operational experience. They ARE the human-in-the-loop for this step.

- **participant**: Someone who is involved in the activity but does not own it. They may perform it sometimes, assist the owner, or share responsibility. They have direct but partial operational experience.

- **supervisor**: Someone who oversees the activity but does not perform it. They understand the design intent, governance requirements, and performance metrics but may not know operational details, workarounds, or undocumented steps.

- **consumer**: Someone who receives the output of the activity. They can describe what they need from it and what goes wrong when it fails, but they cannot describe how the activity is internally performed.

- **observer**: Someone who knows the activity exists and can describe it at a high level, but has no direct operational involvement. Their knowledge may be secondhand or based on documentation rather than experience.

#### Capture Timing

These fields are captured ONCE per interview session, before probing begins. They apply to all fragments produced during that session. If the respondent's proximity changes mid-interview (e.g., they describe their own step as `owner` then describe an adjacent step as `consumer`), the bot MUST tag subsequent fragments with the updated proximity.

#### Example

```json
{
  "respondent_name": "Sarah Chen",
  "respondent_role": "Senior Loan Processor",
  "process_proximity": "owner",
  "authority_scope": "own_activities",
  "years_in_role": 12,
  "interview_type": "structured_walkthrough",
  "swim_lane": "Loan Processing"
}
```

---

## Addition 2: Fragment-Level Assertion Classification

**Insert as**: New Section 5.3 in KM4ProcessBot

### 5.3 Assertion Classification

A single interview produces multiple types of assertions. The Survey Bot MUST classify each response fragment in real time as one of four assertion types. This classification becomes a property on the `EvidenceFragment` and feeds the consensus algorithm's novelty detection.

#### The Four Assertion Types

**Corroborative** — Confirms something already present in other evidence sources.

- Signal: The entity or relationship extracted from this fragment already exists in the graph from a different evidence source.
- Example: Respondent says "They fill out a purchase requisition in SAP" — the Camunda BPMN model already shows a "Create PR" task.
- Weight impact: Neutral (standard base weight applies). The value is in cross-source confirmation, which the triangulation step already rewards.

**Elaborative** — Adds detail, context, or nuance to a known entity or relationship.

- Signal: The entity exists in the graph, but this fragment adds new properties (thresholds, timing, conditions, exceptions) not present in other sources.
- Example: Respondent says "If it's over $10K, it also needs VP sign-off" — the approval activity is known, but the threshold detail is new.
- Weight impact: Moderate boost (+0.10 to base weight). Elaborative evidence enriches the model even though it doesn't introduce new entities.

**Revelatory** — Introduces an entirely new entity, relationship, or process path not present in any other evidence source.

- Signal: Entity extraction produces a node or edge with zero matches in the existing graph or evidence corpus. AND the respondent's `process_proximity` is `owner` or `participant`.
- Example: Respondent says "There's a manual override in Oracle that lets AP push payments without a completed match" — no SOP, no BPMN model, no system log mentions this.
- Weight impact: Flagged for human validation (see Addition 4). If confirmed, receives substantial boost. If unconfirmed, remains single-source with low triangulation.
- Critical: Revelatory evidence from a process owner is the primary mechanism for **shadow work discovery**. The system MUST NOT silently bury it with a low confidence score.

**Contradictory** — Directly conflicts with evidence from another source.

- Signal: The fragment asserts something that contradicts an existing graph assertion from a different source.
- Example: Respondent describes three approval tiers; the Camunda BPMN shows only two.
- Weight impact: Routes to the contradiction resolution step (Step 5 of the consensus algorithm). The winning assertion is determined by weighted evidence authority.

#### Bot Classification Logic

The bot classifies fragments using a combination of:

1. **Graph lookup**: At capture time, check whether the extracted entity/relationship already exists in the engagement's graph. If yes → corroborative or elaborative. If no → revelatory.
2. **Conflict detection**: If the assertion contradicts an existing assertion (different value for the same attribute), classify as contradictory.
3. **Hedge language detection**: If the respondent uses hedging language ("I think", "maybe", "I've heard"), this affects the certainty tier (see Addition 6) but not the assertion classification.

#### Fragment Metadata

Each fragment carries:

```json
{
  "assertion_type": "revelatory",
  "respondent_proximity": "owner",
  "certainty_tier": "definite",
  "related_entities": ["Manual Override", "AP Payment Processing"],
  "novel_entity": true,
  "shadow_work_candidate": true
}
```

---

## Addition 3: Numeric Weight Modifiers

**Insert as**: New Section 7.3 in KM4ProcessBot

### 7.3 Evidence Weight Computation

The consensus algorithm computes an effective weight for each evidence fragment using three factors:

```
effective_weight = base_type_weight × respondent_authority_multiplier × assertion_novelty_factor
```

#### Base Type Weights

These are the existing evidence type weights from the KMFlow consensus algorithm. They reflect the inherent reliability of each evidence category:

| Evidence Type | Base Weight | Rationale |
|---|---|---|
| Structured data (system logs, exports) | 1.00 | Machine-generated, timestamped, auditable |
| Task mining | 0.90 | Observed behavior, not self-reported |
| BPM process models | 0.85 | Designed intent, formally modeled |
| Documents (SOPs, procedures) | 0.75 | Authored and reviewed, but may be outdated |
| Controls evidence | 0.70 | Governance artifacts, tested periodically |
| Regulatory/policy | 0.70 | Authoritative but abstract |
| SaaS exports | 0.65 | System data but often summarized |
| Domain communications (email, chat) | 0.50 | Operational reality but noisy |
| Images | 0.45 | Visual evidence, context-dependent |
| Audio (interviews) | 0.40 | Human testimony, subject to bias |
| Video | 0.40 | Visual + audio, same limitations |
| KM4Work | 0.35 | Knowledge artifacts, variable quality |
| Job aids/edge cases | 0.30 | Informal, unvalidated |

#### Respondent Authority Multiplier

Applied ONLY to human-sourced evidence (interviews, surveys, workshops). Computed from the respondent metadata captured in Section 5.2:

| Process Proximity | Authority Scope | Multiplier | Resulting Effective Weight (from 0.40 base) |
|---|---|---|---|
| owner | own_activities | **1.50x** | 0.60 |
| owner | team_activities | 1.25x | 0.50 |
| participant | own_activities | **1.30x** | 0.52 |
| participant | team_activities | 1.15x | 0.46 |
| supervisor | team_activities | 1.10x | 0.44 |
| supervisor | department_activities | 1.00x | 0.40 |
| consumer | own_activities | 1.00x | 0.40 |
| consumer | team_activities | 0.90x | 0.36 |
| observer | any | 0.80x | 0.32 |
| any | hearsay | 0.50x | 0.20 |

**Tenure bonus**: For respondents with `years_in_role >= 5`, add +0.05 to the multiplier. For `years_in_role >= 10`, add +0.10. Capped at +0.10.

**Interview type bonus**: `structured_walkthrough` adds +0.05; `validation_session` adds +0.10 (because the respondent is reviewing and confirming existing evidence, not generating it from memory).

**Example**: A process owner (1.50x) with 12 years in role (+0.10) in a structured walkthrough (+0.05) has an effective multiplier of 1.65. Their interview fragments have an effective weight of `0.40 × 1.65 = 0.66` — now higher than SaaS exports and approaching documents.

#### Assertion Novelty Factor

Applied per-fragment based on the assertion classification from Section 5.3:

| Assertion Type | Novelty Factor | Notes |
|---|---|---|
| Corroborative | 1.00x | Standard — value comes from cross-source triangulation bonus, not weight boost |
| Elaborative | 1.10x | Adds detail to known entities |
| Revelatory (unconfirmed) | 1.00x | No boost until human validation; but flagged for review |
| Revelatory (confirmed) | **1.40x** | Human validation acts as a second source |
| Contradictory | 1.00x | Weight determines which side wins in contradiction resolution |

#### Complete Example

A Senior Loan Processor (process owner, 12 years, structured walkthrough) reveals shadow work:

```
base_weight:       0.40  (audio/interview)
authority:       × 1.65  (owner + tenure + walkthrough type)
novelty:         × 1.00  (revelatory but unconfirmed)
────────────────────────
effective_weight:  0.66  (before human validation)

After human confirms the shadow work:
novelty:         × 1.40  (revelatory confirmed)
────────────────────────
effective_weight:  0.92  (now among the highest-weighted evidence)
```

This is the correct outcome: a process owner's confirmed testimony about shadow work they personally perform should carry weight comparable to structured system data.

---

## Addition 4: Shadow Work Validation Queue

**Insert as**: New Section 10.3 in KM4ProcessBot

### 10.3 Shadow Work Discovery and Validation

Shadow work — undocumented process steps, workarounds, informal handoffs, phone calls, emails, and manual overrides that are not captured in any formal evidence source — is often the most valuable discovery in a process mapping engagement. It represents the gap between "how the process is designed" and "how the process actually works."

The KM4ProcessBot framework MUST include a dedicated mechanism for surfacing, validating, and incorporating shadow work into the consensus model.

#### Detection Criteria

A fragment is classified as a **shadow work candidate** when ALL of the following are true:

1. The assertion is classified as `revelatory` (see Section 5.3)
2. The respondent's `process_proximity` is `owner` or `participant`
3. The respondent's `certainty_tier` is `definite` or `confident` (see Section 5.4)
4. Entity extraction produces at least one entity with zero matches in the existing graph

When these criteria are met, the fragment is auto-tagged with `shadow_work_candidate: true` and routed to the Shadow Work Validation Queue.

#### The Validation Queue

The Shadow Work Validation Queue is a prioritized list of revelatory evidence awaiting human review. It is distinct from the general evidence gap backlog (Section 10.1) because shadow work candidates have a specific respondent who provided the evidence — they are not "missing knowledge" but "unconfirmed knowledge."

Each queue item contains:

| Field | Description |
|---|---|
| Fragment content | The respondent's exact statement |
| Extracted entities | Activities, decisions, roles, systems discovered |
| Respondent profile | Role, proximity, tenure, authority scope |
| Certainty tier | How confident the respondent was |
| Related known entities | Adjacent entities in the graph that connect to the shadow work |
| Corroboration status | Explicitly: "No other evidence source mentions this" |

#### Resolution Actions

A consultant reviewing the queue has three options:

**Confirm**: The shadow work is real. This action:
- Sets the assertion's `validation_status` to `validated`
- Applies the revelatory confirmed novelty factor (1.40x) to the fragment's weight
- The entity is promoted in the graph with an evidence grade of **"R"** (Revelatory-Confirmed)
- The human validation is recorded as a second evidence source, enabling the cross-source triangulation bonus
- On next consensus run, the entity's confidence score increases substantially

**Reject**: The respondent was mistaken or describing a deprecated practice. This action:
- Sets the assertion's `validation_status` to `rejected`
- The entity is suppressed from BPMN generation (excluded from assembly step)
- The rejection reason is recorded for audit trail

**Investigate**: The shadow work is plausible but needs corroboration. This action:
- Triggers a **targeted follow-up evidence request**:
  - Schedule a validation interview with an adjacent swim lane participant (the upstream provider or downstream consumer)
  - Target KMFlow extraction at domain communications (email, chat, tickets) for keywords matching the shadow work entity
  - Check system access logs for behavioral evidence of the shadow work
- The entity remains in the queue with status `investigating` until corroboration is found or the investigation closes

#### Priority Scoring

Queue items are prioritized by:

```
priority = respondent_authority × certainty_weight × process_criticality
```

Where:
- `respondent_authority` = the respondent authority multiplier from Section 7.3
- `certainty_weight` = 1.0 (definite), 0.6 (confident), 0.3 (uncertain)
- `process_criticality` = 1.5 if the shadow work involves a regulated activity, 1.0 otherwise

Shadow work in a SOX-controlled process described definitively by a 10-year process owner gets the highest priority. Shadow work in a non-regulated process mentioned uncertainly by a participant gets lower priority.

---

## Addition 5: Structured Upstream/Downstream Impact Chains

**Insert as**: Extension to Section 5.1 (Sequence Probe and Dependency Probe)

### 5.1.2 Structured Impact Chain Capture (Sequence Probe Extension)

When a respondent describes their upstream and downstream relationships, the bot MUST capture this as **structured triples** rather than narrative text. Each triple maps directly to a PRECEDES or DEPENDS_ON edge in the knowledge graph with per-link confidence based on the respondent's proximity to each link.

#### The Three-Link Chain

For any respondent describing their activity, capture:

```
(upstream_activity) --[relationship]--> (my_activity) --[relationship]--> (downstream_activity)
```

With metadata on each link:

| Link | Respondent's Proximity | Confidence Modifier |
|---|---|---|
| my_activity (center) | `owner` or `participant` — they perform it | Full authority multiplier |
| upstream → my_activity (inbound) | `consumer` — they receive the upstream output | 0.85x of authority multiplier (direct experience of receiving, not producing) |
| my_activity → downstream (outbound) | `producer` — they create the output the downstream consumes | 0.90x of authority multiplier (direct experience of producing, less knowledge of consumption) |
| upstream_activity (the step itself) | `observer` — they know it exists but don't perform it | 0.60x of authority multiplier |
| downstream_activity (the step itself) | `observer` — they know it exists but don't perform it | 0.60x of authority multiplier |

#### Elicitation Pattern

The bot captures chains through a structured sequence:

1. **Center**: "Walk me through what YOU do — your specific activity, step by step."
   → Captures `my_activity` with full owner/participant authority

2. **Inbound**: "What do you receive to start your work? Who sends it to you, and what does it need to look like?"
   → Captures the `upstream_activity → my_activity` link with the respondent as consumer of the upstream output

3. **Outbound**: "When you're done, what do you hand off? Who receives it, and what do they need from you?"
   → Captures the `my_activity → downstream_activity` link with the respondent as producer of the downstream input

4. **Upstream detail**: "Do you know what the person before you does to create what you receive? Can you describe their step?"
   → Captures `upstream_activity` as an entity, but with observer proximity (lower confidence)

5. **Downstream detail**: "Do you know what happens after the next person receives your output?"
   → Captures `downstream_activity` as an entity, but with observer proximity (lower confidence)

#### Why This Matters

When the consensus algorithm processes chains from multiple respondents, the overlapping links create high-confidence edges:

- **Respondent A** (Loan Processor, owner): describes receiving credit report from Credit Analyst → processing → handing to Underwriter
- **Respondent B** (Underwriter, owner): describes receiving validated file from Loan Processor → making decision → sending to Closer

The `Loan Processor → Underwriter` link now has TWO high-confidence sources:
- Respondent A describes it as their outbound handoff (producer, 0.90x)
- Respondent B describes it as their inbound receipt (consumer, 0.85x)

This overlap is exactly what the triangulation step rewards — and the structured capture ensures the algorithm can detect it automatically.

---

## Addition 6: Certainty Tier on Every Probe Response

**Insert as**: New Section 5.4 in KM4ProcessBot

### 5.4 Certainty Tier Capture

Every probe response — not just the Uncertainty probe (Part 4) — MUST carry a certainty signal. This feeds the `certainty_tier` field used by the graph's claim write-back system and directly affects the weight of assertions in the consensus algorithm.

#### The Four Certainty Tiers

| Tier | Weight | Linguistic Signals | Bot Elicitation |
|---|---|---|---|
| `definite` | 1.0 | "Always", "Every time", "It's required", "Without exception", "I do this daily" | No hedging detected; respondent speaks from direct, repeated experience |
| `confident` | 0.6 | "Usually", "Almost always", "In most cases", "Typically", "Nine times out of ten" | Mild hedging; respondent acknowledges occasional variation |
| `uncertain` | 0.3 | "I think", "I believe", "Probably", "As far as I know", "I'm pretty sure" | Moderate hedging; respondent is drawing from memory or limited experience |
| `speculative` | -0.5 | "I'm not sure", "Maybe", "I've heard", "Someone told me", "I assume" | Strong hedging; respondent is guessing or relaying secondhand information |

Note: The `speculative` tier has a **negative weight** (-0.5). This means speculative assertions actively *reduce* the confidence of an entity if they are the only source — which is the correct behavior. An entity that only exists because someone said "I've heard there's a step where..." should not receive positive confidence.

#### Detection Methods

The bot determines certainty tier through two mechanisms:

**1. Linguistic analysis (automatic)**: Parse the respondent's language for hedge words and certainty markers. This runs on every fragment in real time.

| Pattern | Tier |
|---|---|
| Imperative or declarative with no hedges | `definite` |
| "Usually" / "typically" / "most of the time" | `confident` |
| "I think" / "I believe" / "probably" | `uncertain` |
| "Maybe" / "I've heard" / "I'm not sure" / "I assume" | `speculative` |

**2. Explicit elicitation (triggered)**: When the automatic classification is ambiguous, or when the respondent makes a claim that is particularly significant (e.g., revelatory evidence, contradiction with existing sources), the bot SHOULD ask directly:

- "How confident are you in that? Is this something you do every day, or more of an occasional thing?"
- "Is that from your direct experience, or something you've been told?"
- "Would you say that's always the case, or are there exceptions?"

#### Integration with Consensus Algorithm

The certainty tier feeds the consensus algorithm at two points:

1. **Claim write-back** (graph layer): When survey claims are written to the graph, the `SUPPORTS` and `CONTRADICTS` edges carry `weight = CERTAINTY_WEIGHTS[tier]`. Activity node confidence is recomputed as `sum(r.weight) / count`.

2. **Consensus building** (Step 4): The certainty tier modulates the respondent authority multiplier:
   ```
   effective_weight = base_type_weight × respondent_authority_multiplier × certainty_weight × assertion_novelty_factor
   ```
   Where `certainty_weight` = 1.0 / 0.6 / 0.3 / -0.5 per tier.

#### Example

A process owner (authority multiplier 1.65) makes two statements:

- "We ALWAYS run the three-way match before payment" → `definite` (1.0)
  - Effective weight: `0.40 × 1.65 × 1.0 = 0.66`

- "I think there might be a manual override for urgent payments" → `uncertain` (0.3)
  - Effective weight: `0.40 × 1.65 × 0.3 = 0.20`

Both come from the same person in the same interview, but the algorithm correctly assigns very different weights. The definite statement about the three-way match carries more than 3x the weight of the uncertain statement about the override — which is appropriate, because the respondent is far more authoritative about their routine process than about an edge case they're unsure of.

---

## Integration Summary

### How These Seven Additions Flow Through the Consensus Algorithm

```
Interview Session Start
    │
    ├── Addition 1: Capture respondent metadata
    │   (role, proximity, authority scope, tenure, interview type)
    │
    ▼
Probing (8 probe types)
    │
    ├── Addition 5: Capture structured impact chains
    │   (upstream → my_activity → downstream with per-link proximity)
    │
    ├── Addition 6: Tag each fragment with certainty tier
    │   (definite / confident / uncertain / speculative)
    │
    ├── Addition 2: Classify each fragment
    │   (corroborative / elaborative / revelatory / contradictory)
    │
    ▼
Fragment Ingestion into KMFlow
    │
    ├── Addition 3: Compute effective weight per fragment
    │   (base × authority × certainty × novelty)
    │
    ├── If revelatory + owner/participant + definite/confident:
    │   ├── Addition 4: Route to Shadow Work Validation Queue
    │   │
    │   ├── Human confirms → novelty factor 1.40x, re-run consensus
    │   ├── Human rejects → suppress entity
    │   └── Human investigates → targeted follow-up
    │
    ▼
Consensus Algorithm (8 steps)
    │
    ├── Step 3 (Triangulation): Structured chains from multiple
    │   respondents create overlapping high-confidence edges
    │
    ├── Step 4 (Consensus): Effective weights (not flat 0.40)
    │   feed the weighted voting
    │
    ├── Step 5 (Contradiction): Contradictory fragments routed
    │   with weight-based resolution
    │
    ├── Step 6 (Scoring): Certainty tiers affect the agreement
    │   and reliability factors
    │
    ├── Step 7 (BPMN Assembly): Confirmed shadow work appears
    │   in the BPMN with appropriate confidence coloring
    │
    └── Step 8 (Gap Detection): Unconfirmed revelatory evidence
        appears as shadow work gaps with investigation recommendations
    │
    ▼
Post-Consensus Reporting
    │
    ├── Addition 7: Generate Stakeholder Contradiction Report
    │   ├── Group contradictions by element → disagreement type → swim lane
    │   ├── Enrich with respondent names, roles, tenure, authority
    │   ├── Priority score: confidence impact × weight divergence × criticality
    │   └── Consensus Heatmap: all elements ranked by confidence
    │
    ├── Facilitation sessions with disagreeing parties
    │   └── Session output = new validation_session evidence
    │       └── Re-run consensus → scores shift → BPMN updates
    │
    └── Iterate until high-priority contradictions are resolved
```

---

## Addition 7: Stakeholder Contradiction Report

**Insert as**: New Section 9.3 in KM4ProcessBot

### 9.3 Stakeholder Contradiction Report

The consensus algorithm detects and persists contradictions as first-class objects (see Section 9.1–9.2). However, the raw contradiction data — stored per-element with evidence IDs — is insufficient for driving follow-up stakeholder conversations. This addition defines a **grouped, respondent-enriched contradiction report** designed to be presented to a room of process participants to resolve disagreements.

#### Report Purpose

After the consensus algorithm runs across all evidence sources (potentially 100+ interviews plus dozens of structured data sources), the Stakeholder Contradiction Report answers three questions:

1. **Where do people disagree?** — Which process elements have contradictory evidence?
2. **Who disagrees with whom?** — Named respondents, their roles, swim lanes, and authority — not anonymous evidence IDs.
3. **What is each side's basis?** — The specific claims, the evidence type backing each claim, and the weighted authority behind each position.

This report is the input artifact for a targeted facilitation session where the disagreeing parties are brought together to resolve the contradiction with a consultant mediating.

#### Report Structure

The report groups contradictions by process element, then by disagreement type, then shows both sides with full respondent provenance:

```
┌─────────────────────────────────────────────────────────────────┐
│ CONTRADICTION REPORT: Loan Origination Process                  │
│ Generated: 2026-03-20 | Evidence Sources: 47 interviews,       │
│ 12 structured sources | Contradictions Found: 8                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ❶ ELEMENT: "Approve Loan" (Activity)                           │
│    Confidence: 0.72 (HIGH) | Brightness: DIM                   │
│    Disagreement Type: Step Definition Mismatch                  │
│                                                                 │
│    POSITION A: Manual review required for all applications      │
│    ├── Weight: 0.68 (winning position)                          │
│    ├── Sources (6):                                             │
│    │   • Sarah Chen, Senior Underwriter, 12yr, owner            │
│    │     "Every application gets a manual review — no            │
│    │      exceptions." (definite, structured_walkthrough)        │
│    │   • James Park, Underwriting Manager, 8yr, supervisor      │
│    │     "Manual review is policy." (definite, open_ended)       │
│    │   • SOP: Underwriting Procedures v4.2, Section 3.1         │
│    │   • Controls Matrix: UW-007, quarterly audit               │
│    │   • + 2 more interviews (underwriting swim lane)           │
│    │                                                            │
│    POSITION B: Automated above 700 credit score                 │
│    ├── Weight: 0.54                                             │
│    ├── Sources (4):                                             │
│    │   • Maria Lopez, Loan Processor, 5yr, participant          │
│    │     "If the score is above 700, it auto-approves —         │
│    │      we just see the approval come through." (confident)    │
│    │   • Camunda BPMN Model v2.1 (18 months old)                │
│    │     Gateway: "Credit Score > 700?" → Auto-approve path     │
│    │   • + 2 more interviews (processing swim lane)             │
│    │                                                            │
│    RESOLUTION: Position A wins (higher weighted authority)       │
│    RECOMMENDED ACTION: Facilitate session with Underwriting      │
│    + Processing swim lanes. Possible BPM model drift —          │
│    the Camunda model may reflect a prior process version.        │
│    Verify whether auto-approve path was disabled or never        │
│    existed in practice.                                         │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ❷ ELEMENT: "Three-Way Match" (Activity)                        │
│    Confidence: 0.85 (HIGH) | Brightness: BRIGHT                │
│    Disagreement Type: Rule Mismatch                             │
│    ...                                                          │
└─────────────────────────────────────────────────────────────────┘
```

#### Data Requirements

To produce this report, the following data must be available per contradiction:

| Field | Source | Already Captured? |
|---|---|---|
| Element name, type, confidence | `ProcessElement` record | Yes |
| Disagreement type | `Contradiction.field_name` | Yes |
| Competing values | `Contradiction.values` | Yes |
| Resolution value and reason | `Contradiction.resolution_value`, `resolution_reason` | Yes |
| Evidence IDs for each side | `Contradiction.evidence_ids` | Yes |
| **Respondent name** | `EvidenceItem.metadata_json.respondent_name` | **NEW — Addition 1 extended** |
| **Respondent role** | `EvidenceItem.metadata_json.respondent_role` | Addition 1 |
| **Respondent proximity** | `EvidenceItem.metadata_json.process_proximity` | Addition 1 |
| **Respondent tenure** | `EvidenceItem.metadata_json.years_in_role` | Addition 1 |
| **Respondent swim lane** | `EvidenceItem.metadata_json.swim_lane` | Addition 1 |
| **Certainty tier of the claim** | `EvidenceFragment.metadata_json.certainty_tier` | Addition 6 |
| **Interview type** | `EvidenceItem.metadata_json.interview_type` | Addition 1 |
| **Fragment text** | `EvidenceFragment.content` | Yes |
| Effective weight per side | Computed from Addition 3 formula | Addition 3 |

Note: `respondent_name` was not in the original Addition 1 field list. It MUST be added — without it, the report shows roles but not people, which defeats the purpose of driving a targeted conversation. The name is captured at interview start alongside the other respondent metadata.

#### Report Grouping Logic

Contradictions are grouped and prioritized for maximum stakeholder impact:

**Level 1 — Group by process element**: All contradictions about the same activity/decision/handoff appear together. This gives a complete picture of how contested each element is.

**Level 2 — Group by disagreement type**: Within an element, separate step definition mismatches from sequence mismatches from rule mismatches. Each type may require a different resolution approach.

**Level 3 — Group by swim lane alignment**: Show which swim lanes are on each side of the disagreement. Contradictions that split cleanly along swim lane boundaries (e.g., all Underwriters say X, all Processors say Y) are the most actionable — you know exactly which teams to bring together.

**Priority scoring**:

```
contradiction_priority =
    element_confidence_impact     ← how much does this contradiction suppress the element's score?
  × evidence_weight_divergence    ← how close are the two sides in weighted authority?
  × process_criticality           ← is this a regulated/SOX-controlled element?
  × respondent_count              ← how many people are involved on each side?
```

High priority = a regulated element where the two sides are nearly equal in authority and many people are involved. This is the contradiction most likely to affect the BPMN output AND most likely to benefit from a facilitated conversation.

Low priority = a non-regulated element where one side has overwhelming evidence and the other is a single speculative comment. The algorithm already resolved this correctly.

#### Consensus Heatmap

Alongside the detailed contradiction report, generate a **consensus heatmap** that shows all process elements on a single view:

| Element | Confidence | Sources | Contradictions | Consensus Status |
|---|---|---|---|---|
| Create Requisition | 0.94 | 34/47 interviews + SAP logs + SOP + BPMN | 0 | **Strong consensus** |
| Approve Loan | 0.72 | 28/47 interviews + SOP + Controls | 1 (step definition) | **Contested** — facilitation needed |
| Manual Override | 0.31 | 3/47 interviews only | 0 | **Weak** — shadow work candidate |
| Three-Way Match | 0.85 | 22/47 interviews + SOX controls + BPMN + logs | 1 (rule mismatch) | **Strong with exception** |
| Mexico Subsidiary Controls | 0.08 | 1/47 interviews (speculative) | 0 | **Dark** — no evidence |

This heatmap is the "pull back and see confidence across the entire process" view you described. Sorted by confidence ascending, it immediately tells you: these are the elements we're most confident in (green), these are contested and need facilitation (yellow), these are weak and need more evidence (red).

#### API Endpoint

```
GET /api/v1/pov/{model_id}/contradiction-report
```

Returns the grouped, respondent-enriched contradiction report as JSON. Query parameters:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `min_priority` | float | 0.0 | Filter to contradictions above this priority score |
| `swim_lane` | string | null | Filter to contradictions involving this swim lane |
| `disagreement_type` | string | null | Filter by disagreement type |
| `include_heatmap` | bool | true | Include the consensus heatmap summary |
| `format` | enum | `json` | `json` or `pdf` (for stakeholder distribution) |

#### Facilitation Workflow

The contradiction report drives a specific downstream workflow:

1. **Generate report** after consensus algorithm completes
2. **Prioritize** — focus on high-priority contradictions (contested, regulated, many participants)
3. **Schedule facilitation sessions** — invite the specific named respondents on each side of high-priority contradictions, plus a neutral consultant as mediator
4. **Conduct session** — present the contradiction with both sides' evidence. The goal is not to determine who is "right" but to understand WHY the disagreement exists (is it swim lane perspective? outdated knowledge? a real process variant? BPM model drift?)
5. **Capture resolution** — the facilitation session itself produces new evidence (a `validation_session` interview type) that feeds back into the consensus algorithm
6. **Re-run consensus** — with the facilitation evidence added, contradictions may resolve, confidence scores shift, and the BPMN updates accordingly
7. **Iterate** — move to the next priority contradiction

This is the continuous improvement loop described in Section 11.3, but made concrete and actionable through the contradiction report.

---

### Data Model Impact

These additions require the following changes to the KMFlow data model:

| Model | New Fields | Source |
|---|---|---|
| `EvidenceItem.metadata_json` | `respondent_name`, `respondent_role`, `process_proximity`, `authority_scope`, `years_in_role`, `interview_type`, `swim_lane` | Additions 1, 7 |
| `EvidenceFragment.metadata_json` | `assertion_type`, `certainty_tier`, `shadow_work_candidate`, `novel_entity`, `chain_position`, `chain_link_proximity` | Additions 2, 5, 6 |
| `EvidenceGap` | New `gap_type`: `shadow_work_candidate` | Addition 4 |
| `src/pov/constants.py` | `RESPONDENT_AUTHORITY_MULTIPLIERS`, `CERTAINTY_WEIGHTS`, `ASSERTION_NOVELTY_FACTORS`, `TENURE_BONUS_THRESHOLD` | Addition 3 |
| `src/pov/consensus.py` | `_compute_effective_weight()` function using three-factor formula | Addition 3 |
| Knowledge Graph Ontology | `certainty_tier` on SUPPORTS/CONTRADICTS edges, `assertion_type` on SUPPORTED_BY edges | Additions 2, 6 |
| `src/api/routes/pov.py` | New endpoint: `GET /api/v1/pov/{model_id}/contradiction-report` with grouping, respondent enrichment, priority scoring, heatmap | Addition 7 |
| `src/pov/reporting.py` | New module: `generate_contradiction_report()`, `generate_consensus_heatmap()`, `compute_contradiction_priority()` | Addition 7 |

### KM4ProcessBot Document Insertion Points

| Addition | Insert Location | Section Number |
|---|---|---|
| 1. Respondent Metadata | After Section 5.1 (The Eight Probe Types) | New 5.2 |
| 2. Assertion Classification | After new Section 5.2 | New 5.3 |
| 3. Numeric Weight Modifiers | After Section 7.2 (Evidence Grading Ladder) | New 7.3 |
| 4. Shadow Work Validation | After Section 10.2 (Practical Thresholds) | New 10.3 |
| 5. Structured Impact Chains | Within Section 5.1, after Dependency Probe | New 5.1.2 |
| 6. Certainty Tier Capture | After new Section 5.3 | New 5.4 |
| 7. Stakeholder Contradiction Report | After Section 9.2 (Process-Specific Disagreement Taxonomy) | New 9.3 |
