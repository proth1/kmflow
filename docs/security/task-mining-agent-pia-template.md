# Privacy Impact Assessment — KMFlow Task Mining Agent

**Document ID**: KMF-SEC-003
**Version**: 1.0
**Assessment Date**: `[DATE]`
**Review Date**: `[DATE + 1 YEAR]`
**Classification**: Confidential
**Prepared By**: `[DATA PROTECTION OFFICER / PRIVACY OFFICER]`
**Organization**: `[CONTROLLER ORGANIZATION NAME]`

> **GDPR Note**: Employee monitoring is a high-risk processing activity under GDPR Article 35(3)(b) (systematic monitoring of a publicly accessible area — broadly interpreted to include workplace monitoring). A DPIA is therefore required before deployment. This template is designed to satisfy that requirement. Complete all sections. DPO consultation (Article 36) is required where residual risk cannot be reduced to an acceptable level.

---

## Table of Contents

1. [Assessment Scope and Context](#1-assessment-scope-and-context)
2. [Data Inventory](#2-data-inventory)
3. [Legal Basis and Necessity](#3-legal-basis-and-necessity)
4. [Necessity and Proportionality](#4-necessity-and-proportionality)
5. [Risk Assessment Matrix](#5-risk-assessment-matrix)
6. [Mitigation Measures](#6-mitigation-measures)
7. [Residual Risk Summary](#7-residual-risk-summary)
8. [DPO Consultation Record](#8-dpo-consultation-record)
9. [Stakeholder Consultation Record](#9-stakeholder-consultation-record)
10. [Decision and Sign-Off](#10-decision-and-sign-off)

---

## 1. Assessment Scope and Context

### 1.1 Processing Activity Description

| Field | Value |
|-------|-------|
| Activity name | KMFlow Task Mining Agent — Desktop Activity Monitoring |
| Controller | `[ORGANIZATION NAME]` |
| Processor | `[CONSULTING FIRM NAME]` |
| Engagement reference | `[ENGAGEMENT ID / SOW NUMBER]` |
| Deployment scope | `[NUMBER]` employee workstations in `[DEPARTMENT(S)]` |
| Geographic scope | `[COUNTRIES / SITES]` |
| Proposed start date | `[DATE]` |
| Proposed end date | `[DATE]` |
| Assessment author | `[NAME, TITLE]` |
| Assessment date | `[DATE]` |

### 1.2 Business Objective

`[ORGANIZATION NAME]` is engaging `[CONSULTING FIRM]` to conduct a business process mining engagement. The objective is to obtain objective, empirical data on how employees perform business processes across the following functional areas: `[LIST FUNCTIONAL AREAS]`.

The KMFlow Task Mining Agent will be deployed on workstations of employees who perform the processes under study. It will collect desktop activity signals (application usage, window context, interaction counts) to enable process flow reconstruction and effort estimation. The output will inform a Target Operating Model (TOM) redesign and identify automation and efficiency opportunities.

### 1.3 Technology Description

The Agent is a macOS desktop application consisting of:

- A Swift capture layer that uses macOS accessibility APIs (CGEventTap, AXUIElement, NSWorkspace) to observe application usage and interaction counts.
- A Python intelligence layer that applies PII filtering, encrypts data, and transmits it to the KMFlow backend.
- A backend analytical platform operated by `[CONSULTING FIRM]` on `[CLOUD PROVIDER]` infrastructure.

Full technical detail is provided in the KMFlow Task Mining Agent Security Whitepaper (KMF-SEC-001).

---

## 2. Data Inventory

### 2.1 Data Collected

| Data Element | Example | Sensitivity | Retention |
|-------------|---------|-------------|-----------|
| Application name | "Microsoft Excel", "Salesforce" | Low | 90 days post-engagement |
| Window title (after PII scrubbing) | "Q4 Forecast [PII_REDACTED].xlsx" | Low–Medium | 90 days post-engagement |
| App switch timestamps | 2026-02-25T14:32:11Z | Low | 90 days post-engagement |
| Keyboard/mouse counts per app | keystrokes: 342, clicks: 18 | Low | 90 days post-engagement |
| Active/idle intervals | active: 00:23:14, idle: 00:05:03 | Low | 90 days post-engagement |
| Agent ID (pseudonymous UUID) | a3f2b8c1-... | Low | 90 days post-engagement |
| Consent record | Employee ID, timestamp, version | Medium | 3 years post-engagement |

### 2.2 Data NOT Collected

The following data is explicitly excluded from collection by the Agent's design. These exclusions are enforced at the capture layer (L1) and cannot be overridden by configuration without a software update requiring re-notarization.

| Data Type | Exclusion Mechanism |
|-----------|-------------------|
| Keystroke content (typed text) | CGEventTap configured for count only; content not extracted |
| Passwords | L1: password field detection (AXIsPasswordField); secure input context blocking |
| Clipboard content | No clipboard API access requested or used |
| File names or contents | No file system access; Full Disk Access not requested |
| Email content or subject lines | Application name captured only; email body not accessible via AXUIElement for major clients |
| Browser URLs or history | URL bar content is a password field in most browsers under secure contexts; excluded by L1 |
| Browser page content | No browser extension; no DOM access |
| Screenshots (pixel content) | Screen Recording permission not requested in Phase 1; excluded by default |
| Audio or video | Microphone and Camera permissions not requested |
| Location data | No location API access |
| Biometric data | Not collected |

### 2.3 Pseudonymization

Agent IDs are UUIDs assigned at registration and are not linked to employee names, email addresses, or HR identifiers in the Agent itself. The mapping between Agent ID and employee identity is maintained in the KMFlow engagement administration console, accessible only to the engagement manager and to designated administrators at `[ORGANIZATION NAME]`. This mapping must be handled separately under appropriate access controls.

---

## 3. Legal Basis and Necessity

### 3.1 Selected Legal Basis

Select the applicable legal basis and complete the corresponding assessment:

- [ ] **GDPR Art. 6(1)(f) — Legitimate Interests** (see 3.2)
- [ ] **GDPR Art. 6(1)(a) — Consent** (see 3.3)
- [ ] **GDPR Art. 6(1)(b) — Contract Performance** (see 3.4; limited applicability for employee monitoring)
- [ ] **GDPR Art. 6(1)(c) — Legal Obligation** (see 3.5; requires statutory basis in Member State law)

### 3.2 Legitimate Interests Assessment (if Art. 6(1)(f) selected)

**Purpose test**: Is the processing for a legitimate purpose?

`[ORGANIZATION NAME]` has a legitimate interest in understanding how its employees perform business processes in order to optimize operations, reduce waste, and improve service delivery. Process mining is a recognized and widely used management practice. The interest is real, genuine, and not trivial.

_Assessor conclusion_: `[YES / NO — with rationale]`

**Necessity test**: Is the processing necessary to achieve the purpose?

Alternatives considered (see Section 4.3). The Agent provides objective, continuous data that manual observation, diary studies, and system log analysis cannot provide at scale or with sufficient granularity. The level of processing is limited to the minimum necessary to reconstruct process flows.

_Assessor conclusion_: `[YES / NO — with rationale]`

**Balancing test**: Do the interests of the data subjects override the Controller's legitimate interests?

Factors in favor of Controller: Processing is limited to work activity during work hours on employer-issued devices; data is used for business optimization, not performance management of individuals; data is pseudonymized; employees are fully informed.

Factors in favor of data subject: Workplace monitoring can feel intrusive; power imbalance in employment relationship; employees may not meaningfully object.

Mitigations applied: Transparency (pre-deployment communication, menu bar visibility, transparency log); voluntary consent flow even where legitimate interest is the legal basis; easy opt-out (manual pause via menu bar); time-limited engagement (not permanent monitoring); no content capture; no individual performance reporting without separate agreement.

_Assessor conclusion_: `[INTERESTS BALANCED — with rationale / INTERESTS OF DATA SUBJECTS OVERRIDE — escalate to DPO]`

### 3.3 Consent Assessment (if Art. 6(1)(a) selected)

Complete the following consent quality checklist:

| Requirement | Implementation | Met? |
|------------|---------------|------|
| Freely given | Employee can pause or withdraw via menu bar; no adverse consequence for non-participation documented in `[HR POLICY REFERENCE]` | `[ ]` |
| Specific | Consent covers this specific engagement only; scope disclosed at consent screen | `[ ]` |
| Informed | Privacy notice presented at consent screen; this PIA summary provided to employees | `[ ]` |
| Unambiguous | Active opt-in action required (employee completes consent flow); no pre-ticked boxes | `[ ]` |
| Withdrawable | Employee can withdraw via menu bar at any time; withdrawal triggers agent revocation within 5 minutes | `[ ]` |
| Recorded | Consent record stored in Keychain on device and uploaded to KMFlow backend; retrievable on request | `[ ]` |

---

## 4. Necessity and Proportionality

### 4.1 Why This Level of Monitoring

Process mining requires activity-level data that cannot be obtained from server-side logs alone. Many of the processes under study involve desktop applications (spreadsheets, local tools, legacy systems) that generate no server-side logs. Reconstructing process flows requires:

- Application-level time allocation (which tools are used, in what sequence, for how long)
- Transition patterns (how employees move between applications)
- Effort intensity (interaction counts as a proxy for cognitive load)

The Agent provides the minimum data necessary to answer these questions. Alternatives that would capture more data (screenshots, full keystroke logging, screen recording) are excluded by design.

### 4.2 Scope Limitation

The following scope limitations are enforced:

| Limitation | Implementation |
|-----------|---------------|
| Enrolled employees only | Agent deployed only on consented/notified workstations |
| Work applications only | L1 blocks personal browsing (private mode), password managers |
| Work hours only (configurable) | Agent can be configured to capture only within defined time windows |
| Engagement period only | Agent revoked at engagement close; backend data deleted per retention schedule |
| Pseudonymized output | Analytics reports show aggregate process patterns, not individual performance |

### 4.3 Alternatives Considered

| Alternative | Why Insufficient |
|------------|-----------------|
| System log analysis (server-side) | Does not capture desktop application usage; most relevant processes are local; gaps in coverage for offline work |
| Manual time-and-motion observation | Sampling bias; observer effect (Hawthorne effect); not scalable to `[N]` employees; costly and slow |
| Self-reported diary studies | High error rate; recall bias; sustainable only for 1–2 week studies; employees underreport context switching |
| Screen recording (screenshots) | Significantly higher privacy impact than interaction counts; captures content of screens including customer and confidential data; not proportionate for process flow analysis |
| Full keystroke logging | Captures passwords, personal communications, confidential content; not proportionate; legally prohibited in many jurisdictions for employee monitoring |

---

## 5. Risk Assessment Matrix

The following matrix assesses privacy risks associated with the Agent deployment. Each risk is assessed on **likelihood** (probability of occurrence) and **severity** (impact on data subjects' rights and freedoms) before and after mitigations are applied.

| Ref | Risk Description | Likelihood (pre-mitigation) | Severity (pre-mitigation) | Pre-Mitigation Risk | Mitigation(s) Applied | Likelihood (post-mitigation) | Severity (post-mitigation) | Post-Mitigation Risk |
|-----|-----------------|----|----|---|---|---|---|---|
| R1 | PII captured despite filtering — sensitive personal data (SSN, email, account numbers) present in window titles passes through L2 regex | Medium | High | **High** | Two-layer on-device PII architecture (L1 capture context prevention, L2 regex scrubbing). L3 ML-based NER and L4 human quarantine review are planned for a future phase but are not yet implemented. Regex patterns updated based on engagement context. | Medium | Medium | **Medium** |
| R2 | Agent software compromise — malicious actor modifies agent binary to exfiltrate raw data | Low | High | **Medium** | Python integrity manifest (SHA-256 verified at launch). Developer ID + hardened runtime + Apple notarization. Server-side revocation within 5 minutes. No raw PII on device after L2 filtering. | Very Low | High | **Low** |
| R3 | Employee discomfort or chilling effect — employees modify behavior due to awareness of monitoring, creating psychological distress or reducing authentic process observation | Medium | Medium | **Medium** | Pre-deployment communication. Voluntary consent flow. Menu bar transparency. Opt-out always available. No individual performance reporting. Time-limited engagement. Independent employee representative consultation. | Low | Low | **Low** |
| R4 | Data breach in transit — captured events intercepted in transit to backend | Low | High | **Medium** | TLS 1.3 enforced (TLS 1.2 rejected). mTLS planned Phase 2. Data is PII-scrubbed before transmission; residual PII limited. | Very Low | Medium | **Low** |
| R5 | Unauthorized access to local buffer — attacker gains access to buffer on device | Low | Medium | **Medium** | Buffer is currently plaintext SQLite (AES-256-GCM encryption planned). Any same-user process can read the buffer. Remote revocation triggers data deletion. L2 PII scrubbing reduces sensitivity of stored data. | Low | Medium | **Low** |
| R6 | Scope creep — Processor uses data for purposes beyond process mining (e.g., individual performance monitoring, profiling) | Low | High | **Medium** | DPA (KMF-SEC-002) limits processing to stated purposes. Pseudonymization by design. Engagement-scoped data partition. Controller audit rights. Processor's contractual liability for unauthorized processing. | Very Low | High | **Low** |
| R7 | Data subject rights not fulfilled — employees cannot access, correct, or delete their data | Low | Medium | **Low** | DPA Article 7.5 requires Processor to assist within 5 business days. Pseudonymous Agent IDs linkable to employees via engagement admin console. Deletion triggered by revocation or explicit request. | Very Low | Low | **Very Low** |
| R8 | Device loss or theft — device containing local buffer is lost before upload | Low | Medium | **Low** | Local buffer AES-256-GCM encrypted. Key in Keychain tied to device. Remote revocation via MDM + KMFlow console. 100 MB FIFO cap limits maximum exposure (typically 1–3 days of data). | Very Low | Low | **Very Low** |
| R9 | Employees unaware of monitoring (transparency failure) | Low | High | **Medium** | Pre-deployment notification required by deployment process. Consent flow discloses all captured data categories. Menu bar icon always visible. Transparency log available in menu bar. MDM-deployed agents show in System Preferences. | Very Low | Medium | **Low** |
| R10 | Works council / employee representation requirements not met (jurisdictional) | Medium | High | **High** | Deployment blocked until Controller confirms all required approvals obtained. DPA Article 5.3 makes this an explicit Controller pre-condition. Processor provides technical documentation to support approval processes. | Low | High | **Medium** |

### Risk Level Definitions

| Level | Likelihood | Severity |
|-------|-----------|---------|
| Very Low | < 5% probability over engagement duration | Minor inconvenience; no lasting impact on rights |
| Low | 5–15% | Some impact on rights; addressable with standard remediation |
| Medium | 15–35% | Significant impact; potential for distress or tangible harm |
| High | > 35% | Serious harm to rights and freedoms; regulatory action likely |

---

## 6. Mitigation Measures

### 6.1 Technical Measures

| Measure | Description | Reference |
|---------|------------|-----------|
| Two-layer on-device PII architecture | L1 capture context prevention (Swift), L2 regex scrubbing (Swift+Python). L3 ML NER (backend) and L4 human quarantine review are planned for a future phase and are not yet implemented. | Whitepaper Sec. 4 |
| AES-256-GCM encryption at rest | Planned — not yet implemented; local buffer currently plaintext; key infrastructure in Keychain | Whitepaper Sec. 5 |
| TLS 1.3 in transit | All backend communication encrypted | Whitepaper Sec. 5 |
| Least privilege permissions | Accessibility only; no Full Disk Access, no admin rights | Whitepaper Sec. 6 |
| Server-side revocation | Agent stops within 5 minutes of revocation command | Whitepaper Sec. 7 |
| Integrity verification | Python manifest SHA-256 checked at launch | Whitepaper Sec. 8 |
| 100 MB buffer cap | Limits on-device data accumulation | Whitepaper Sec. 9 |
| Pseudonymization | Agent ID UUID not linked to identity in Agent itself | Sec. 2.3 |

### 6.2 Organizational Measures

| Measure | Owner | Implementation Date |
|---------|-------|-------------------|
| Employee notification and communication campaign | `[HR / Communications]` | Before deployment |
| Consent flow activation | `[IT / Consulting firm]` | At agent installation |
| DPA executed between Controller and Processor | `[Legal]` | Before deployment |
| Works council / employee representative consultation | `[HR / Legal]` | Before deployment (jurisdiction-specific) |
| Engagement admin access control (agent ID to employee mapping) | `[Engagement Manager]` | At project initiation |
| Data subject rights request procedure | `[Privacy Office]` | Before deployment |
| Incident response runbook (Agent-specific) | `[IT Security]` | Before deployment |

---

## 7. Residual Risk Summary

After all mitigations are applied, the following residual risks remain above Very Low:

| Ref | Residual Risk | Post-Mitigation Level | Accepted By |
|-----|--------------|----------------------|------------|
| R10 | Works council / employee representation approval not obtained before deployment | Medium | `[DPO NAME]` must confirm jurisdictional requirements met before sign-off |

**Overall residual risk**: Low, subject to R10 being resolved prior to deployment.

**Recommendation**: The deployment of the KMFlow Task Mining Agent may proceed subject to:
1. Completion of all organizational measures in Section 6.2.
2. Confirmation that R10 (works council / employee representation requirements) is satisfied in all applicable jurisdictions.
3. DPO sign-off per Section 8.

---

## 8. DPO Consultation Record

> Complete this section when consulting the Data Protection Officer. Under GDPR Art. 36, prior consultation with the supervisory authority is required if residual risk remains high after mitigation.

| Field | Value |
|-------|-------|
| DPO Name | |
| Date of consultation | |
| Consultation method | [ ] In-person [ ] Video call [ ] Written submission |
| Summary of DPO advice | |
| DPO recommendations | |
| Changes made in response to DPO advice | |
| DPO sign-off | |
| DPO sign-off date | |
| Supervisory authority consultation required? | [ ] Yes [ ] No |
| If yes — supervisory authority notified | [ ] Yes, on: `[DATE]` [ ] No — rationale: |

### DPO Opinion

> DPO to complete this section independently.

Having reviewed this Privacy Impact Assessment and the accompanying technical documentation (Security Whitepaper KMF-SEC-001, Data Processing Agreement template KMF-SEC-002):

- [ ] I approve deployment subject to the conditions noted above.
- [ ] I approve deployment without conditions.
- [ ] I do not approve deployment. Reasons:

`[DPO WRITTEN OPINION — include any specific concerns, recommendations, or conditions]`

---

## 9. Stakeholder Consultation Record

> Document all consultations with stakeholders affected by or involved in the deployment.

### 9.1 Employee Representative / Works Council Consultation

| Field | Value |
|-------|-------|
| Representative body name | |
| Jurisdiction | |
| Legal requirement for consultation? | [ ] Yes [ ] No — basis: |
| Date consultation initiated | |
| Date consultation completed | |
| Outcome | [ ] Approved [ ] Approved with conditions [ ] Objected |
| Conditions or concerns raised | |
| Changes made in response | |
| Representative sign-off | |
| Sign-off date | |

### 9.2 IT Security Consultation

| Field | Value |
|-------|-------|
| Reviewer name and title | |
| Date of review | |
| Security review scope | [ ] Technical architecture review [ ] Penetration test [ ] Questionnaire |
| Findings | |
| Outstanding items | |
| Reviewer sign-off | |

### 9.3 Legal Counsel Review

| Field | Value |
|-------|-------|
| Reviewer name and firm | |
| Date of review | |
| Scope | [ ] Legal basis [ ] DPA review [ ] Employment law [ ] Full review |
| Key findings | |
| Legal counsel approval | [ ] Approved [ ] Approved with conditions [ ] Not approved |
| Conditions | |

### 9.4 Engagement Sponsor / Business Owner Acknowledgment

I confirm that I have reviewed this Privacy Impact Assessment and understand the data processing activities, risks, and mitigations described herein. I accept responsibility for ensuring that the organizational measures in Section 6.2 are implemented before deployment.

| Field | Value |
|-------|-------|
| Name | |
| Title | |
| Department | |
| Date | |
| Signature | |

---

## 10. Decision and Sign-Off

### 10.1 Pre-Deployment Checklist

| Item | Status | Date Completed |
|------|--------|---------------|
| Employee notification issued | [ ] Complete [ ] Pending | |
| Consent flow tested and active | [ ] Complete [ ] Pending | |
| DPA executed (KMF-SEC-002) | [ ] Complete [ ] Pending | |
| Works council consultation complete (all applicable jurisdictions) | [ ] Complete [ ] N/A | |
| Legal counsel review complete | [ ] Complete [ ] Pending | |
| IT security review complete | [ ] Complete [ ] Pending | |
| DPO sign-off obtained | [ ] Complete [ ] Pending | |
| Incident response runbook in place | [ ] Complete [ ] Pending | |
| Data subject rights procedure in place | [ ] Complete [ ] Pending | |
| Engagement admin access controls configured | [ ] Complete [ ] Pending | |

### 10.2 Deployment Decision

Based on this Privacy Impact Assessment:

- [ ] **Approved for deployment** — all checklist items complete; residual risk acceptable.
- [ ] **Conditionally approved** — deployment may proceed when outstanding items are completed. Outstanding items: `[LIST]`
- [ ] **Not approved** — risk not reducible to acceptable level. Reason: `[REASON]`

### 10.3 Final Sign-Offs

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Privacy Impact Assessment Author | | | |
| Data Protection Officer | | | |
| Engagement Sponsor | | | |
| Information Security Officer | | | |

### 10.4 Review Schedule

This PIA shall be reviewed:

- [ ] If the scope of the engagement changes (additional departments, additional data categories)
- [ ] If the Agent software version changes materially (new capture capabilities)
- [ ] If a privacy incident or near-miss occurs relating to this deployment
- [ ] On the scheduled review date: `[DATE]`
- [ ] At engagement close (to confirm deletion obligations met)

---

*Document ID: KMF-SEC-003 | Template Version: 1.0*
*This template does not constitute legal advice. Have your legal counsel and DPO review and complete all sections before deployment.*
