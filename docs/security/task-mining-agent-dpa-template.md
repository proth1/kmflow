# Data Processing Agreement — KMFlow Task Mining Agent

**Document ID**: KMF-SEC-002
**Version**: 1.0
**Template Date**: 2026-02-25
**Classification**: Confidential — Legal Template

> **Instructions for Use**: This template must be completed and executed as a standalone agreement or as a Data Processing Addendum (DPA) appended to the Master Services Agreement between the parties. Fields in `[brackets]` must be completed. Do not use this template without legal review for your jurisdiction.

---

## DATA PROCESSING AGREEMENT

This Data Processing Agreement ("Agreement") is entered into as of `[EFFECTIVE DATE]` between:

**Controller**:
`[CLIENT ORGANIZATION LEGAL NAME]`, a `[jurisdiction]` company, with principal place of business at `[ADDRESS]` ("Controller" or "Client")

and

**Processor**:
`[CONSULTING FIRM LEGAL NAME]`, a `[jurisdiction]` company, with principal place of business at `[ADDRESS]`, operating the KMFlow platform ("Processor" or "Consultant")

The parties are referred to individually as a "Party" and collectively as the "Parties."

---

## Article 1 — Subject Matter and Duration

### 1.1 Subject Matter

This Agreement governs the processing of personal data by the Processor on behalf of the Controller in connection with the deployment of the KMFlow Task Mining Agent (the "Agent") on employee workstations as part of a business process analysis and optimization engagement (the "Engagement") described in the Master Services Agreement or Statement of Work referenced herein: `[MSA/SOW REFERENCE NUMBER]`.

### 1.2 Duration

This Agreement is effective from the date of execution and continues for the duration of the Engagement plus any retention period specified in Article 6. Obligations that survive termination are specified in Article 12.

---

## Article 2 — Nature and Purpose of Processing

### 2.1 Nature of Processing

The Processor shall collect, store, transmit, analyze, and delete desktop activity data captured by the Agent from enrolled employee workstations. Processing operations include:

- Automated collection of application usage signals via macOS system APIs
- On-device PII filtering and scrubbing prior to storage
- Encrypted local buffering and batch transmission to the KMFlow backend
- Aggregation and pattern analysis for process mining purposes
- Storage in an engagement-scoped backend partition
- Deletion upon engagement close or as directed by the Controller

### 2.2 Purpose

Processing is limited to the following purposes:

1. **Primary purpose**: Business process analysis — identifying how employees allocate time across applications and tasks to support process optimization and Target Operating Model (TOM) design.
2. **Quality assurance**: Validating that PII filtering operates correctly via statistical sampling of quarantine records.
3. **Platform operation**: Agent registration, configuration management, revocation, and audit logging necessary for the secure operation of the Agent.

Processing for any other purpose requires a written amendment to this Agreement executed by both Parties.

---

## Article 3 — Categories of Personal Data

### 3.1 Data Collected

The following categories of personal data are collected by the Agent:

| Data Category | Description | PII Sensitivity |
|--------------|-------------|-----------------|
| Application usage patterns | Names of macOS applications used (e.g., "Microsoft Excel", "Salesforce CRM"), duration per application, transition sequences | Low — application names are not personal data per se; identifiable only in aggregate |
| Window titles (PII-scrubbed) | Frontmost window title text after L2 PII regex scrubbing; any match replaced with `[PII_REDACTED]` | Low after scrubbing; Medium before scrubbing (may contain document names, record IDs) |
| Keyboard and mouse interaction counts | Aggregate count of keystrokes and mouse clicks per application per time window; no keystroke content | Low — aggregate counts only |
| Active and idle time intervals | Timestamps marking periods of activity and inactivity | Low |
| App switch timestamps | Timestamps of transitions between applications | Low |
| Device identifier | Agent ID (UUID assigned at registration), not linked to hardware serial number | Low |
| Consent record | Employee name or user identifier, consent timestamp, consent version, scope acknowledged | Medium |

### 3.2 Data Not Collected

The Agent is designed and configured **not** to collect the following:

- Keystroke content (individual keystrokes, typed text, passwords)
- Clipboard content
- File names, file contents, or file system metadata
- Email content, subject lines, or recipients
- Communication content (instant messages, video call content)
- Browser history or URLs
- Screenshot pixel content (unless Screen Recording is explicitly enabled per Article 7.2)
- Audio or video from microphone or camera
- Location data
- Biometric data

---

## Article 4 — Categories of Data Subjects

Data subjects are employees (including contractors and temporary workers) of the Controller whose workstations have the Agent installed. The Agent is deployed only on workstations where:

1. The employee has been notified in writing of the monitoring and its scope.
2. The applicable legal basis for processing has been established (see Article 5).
3. The employee has completed the Agent's consent flow (where consent is the legal basis).

The Controller is responsible for maintaining a register of enrolled employees and providing it to the Processor upon request.

---

## Article 5 — Legal Basis for Processing

### 5.1 Controller's Responsibility

The Controller bears sole responsibility for establishing and documenting the applicable legal basis for processing under applicable data protection law (e.g., GDPR Article 6). The Processor makes no representations about the legal basis and will not make legal basis determinations on behalf of the Controller.

### 5.2 Supported Legal Bases

The Agent's architecture supports deployment under the following legal bases:

**Legitimate Interests (GDPR Art. 6(1)(f))**: The Controller has a legitimate interest in understanding how employees perform business processes for the purpose of operational optimization. A Legitimate Interests Assessment (LIA) must be completed by the Controller prior to deployment. The Processor can supply a template LIA upon request.

**Employee Consent (GDPR Art. 6(1)(a))**: Where the Controller chooses consent as the legal basis, the Agent's built-in consent flow collects explicit, informed, and withdrawable consent at first launch. Consent records are stored in the macOS Keychain on the device and uploaded to the KMFlow backend.

**Legal Obligation / Contract Performance**: May apply in certain jurisdictions. The Controller's legal counsel must verify applicability.

### 5.3 Works Council and Collective Agreement Requirements

In jurisdictions where employee monitoring requires works council consultation, collective agreement, or similar employee representation approval (including Germany, France, the Netherlands, and others), the Controller must complete that process before deploying the Agent. The Processor can provide technical documentation to support the approval process but will not deploy the Agent in a jurisdiction where the Controller has confirmed that required approvals are outstanding.

---

## Article 6 — Data Retention

### 6.1 On-Device Retention

Captured data is retained on the employee's device only until it is successfully uploaded to the KMFlow backend. The local encrypted buffer is capped at 100 MB (FIFO pruning). See the Security Whitepaper (KMF-SEC-001) for full on-device retention details.

### 6.2 Backend Retention

| Data Category | Default Retention | Maximum Retention | Deletion Trigger |
|--------------|-------------------|-------------------|-----------------|
| Event records (activity data) | 90 days from engagement close | `[SPECIFIED IN SOW]` | Engagement close + retention period; or Controller deletion request |
| Consent records | Duration of Agreement + 3 years | 7 years | Controller deletion request; statutory minimum |
| Audit logs (access, upload, revocation) | 1 year | 3 years | Controller deletion request; statutory minimum |
| Quarantine records (PII review artifacts) | 30 days from review completion | 90 days | Reviewer disposition or TTL expiry |

### 6.3 Deletion Upon Termination

Upon termination of the Engagement or this Agreement, the Processor shall:

1. Within **30 days**: Delete all event records from the backend analytical layer.
2. Within **30 days**: Revoke all Agent registrations and trigger on-device buffer deletion.
3. Within **30 days**: Provide the Controller with a written deletion certification.
4. Retain consent records and audit logs for the periods specified in Article 6.2 unless instructed otherwise in writing.

---

## Article 7 — Processor Obligations

### 7.1 Instructions

The Processor shall process personal data only on documented instructions from the Controller, unless required to do so by applicable law. This Agreement and the accompanying Statement of Work constitute the Controller's complete processing instructions as of the effective date.

### 7.2 Confidentiality

The Processor shall ensure that persons authorized to process the personal data are under an appropriate obligation of confidentiality.

### 7.3 Security Measures

The Processor shall implement and maintain the technical and organizational measures described in the KMFlow Task Mining Agent Security Whitepaper (KMF-SEC-001), which is incorporated by reference. The current version of the Security Whitepaper shall be made available to the Controller upon request at any time.

Minimum security measures include:

- AES-256-GCM encryption of data at rest on endpoint devices (planned — not yet implemented; see Whitepaper Sec. 5 for current status)
- TLS 1.3 encryption for all data in transit
- Two-layer on-device PII protection architecture (L1 capture context prevention, L2 regex scrubbing). Additional layers (L3 ML-based NER and L4 human quarantine review) are planned for a future phase and are not yet implemented.
- macOS Keychain storage of encryption keys and credentials
- Server-side agent revocation capability with maximum 5-minute latency
- Signed and notarized software distribution

### 7.4 Sub-Processors

The Processor is authorized to engage sub-processors as listed in Annex 1. The Processor shall:

- Ensure sub-processors are bound by data protection obligations at least as stringent as this Agreement.
- Remain liable to the Controller for sub-processor compliance.
- Notify the Controller at least **30 days** in advance of adding or replacing sub-processors.
- Give the Controller the right to object to sub-processor changes on reasonable grounds.

### 7.5 Data Subject Rights Assistance

The Processor shall assist the Controller in fulfilling data subject rights requests (access, erasure, rectification, portability, restriction) to the extent that the request relates to data in the Processor's systems. The Processor shall respond to Controller requests for assistance within **5 business days**. Fulfillment timelines are the Controller's responsibility.

### 7.6 Security Assistance

The Processor shall assist the Controller with:

- Data Protection Impact Assessments related to the Agent deployment (the PIA template KMF-SEC-003 is provided for this purpose).
- Incident response, including providing technical information necessary to notify supervisory authorities within 72 hours under GDPR Art. 33.
- Demonstrating compliance with this Agreement.

### 7.7 Audit Rights

The Controller has the right to:

- Request written evidence of the Processor's compliance with this Agreement (including current Security Whitepaper, penetration test summaries, and SOC 2 report) once per calendar year at no charge.
- Conduct an on-site audit of processing activities with **30 days' written notice**, subject to reasonable confidentiality conditions and at the Controller's expense.
- Commission a third-party auditor under the same conditions.

---

## Article 8 — Sub-Processors

### Annex 1 — Authorized Sub-Processors

| Sub-Processor | Role | Data Processed | Location | Legal Mechanism |
|--------------|------|---------------|----------|----------------|
| `[CLOUD INFRASTRUCTURE PROVIDER]` (e.g., AWS, Azure, GCP) | Backend infrastructure hosting | Event records, consent records, audit logs | `[REGION(S)]` | Standard Contractual Clauses (SCCs) / Data Processing Addendum |
| `[EMAIL SERVICE PROVIDER]` (if used for notifications) | Transactional notifications | Email address of engagement manager only | `[REGION(S)]` | SCCs / DPA |

---

## Article 9 — International Data Transfers

Where personal data is transferred outside the European Economic Area (EEA) or the United Kingdom, the Processor shall ensure that an appropriate transfer mechanism is in place, including:

- Standard Contractual Clauses (Module 2: Controller to Processor) as set out in EU Commission Decision 2021/914, or
- The UK International Data Transfer Agreement (IDTA) for UK transfers, or
- Another lawful mechanism recognized by the applicable supervisory authority.

The Controller acknowledges that the KMFlow backend may be hosted in `[REGION]`. Transfer impact assessment documentation is available upon request.

---

## Article 10 — Personal Data Breach Notification

### 10.1 Processor Notification to Controller

The Processor shall notify the Controller of a personal data breach affecting data processed under this Agreement within **24 hours** of becoming aware of the breach, and in all cases within **48 hours**. Notification shall include, to the extent available:

- Nature of the breach (categories and approximate number of records affected)
- Contact details of the data protection contact
- Likely consequences of the breach
- Measures taken or proposed to address the breach

### 10.2 Controller Notification to Supervisory Authority

The Controller is responsible for notifying the relevant supervisory authority within **72 hours** of becoming aware of a breach (GDPR Art. 33). The Processor shall provide all reasonable assistance and technical information required to support this notification.

### 10.3 Agent-Specific Breach Mitigations

Due to the Agent's security architecture, the following factors limit the impact of breach scenarios:

- **Device loss or theft**: Local buffer is currently plaintext SQLite (AES-256-GCM encryption planned); data is PII-scrubbed by L2 regex; agent can be remotely revoked; 100 MB FIFO cap limits exposure.
- **Backend breach**: Event records contain only PII-scrubbed data (L2 regex applied before storage). Residual PII risk is limited to patterns not covered by the L2 regex. Note: L3 ML-based NER and L4 human quarantine review are planned for a future phase but are not yet active mitigations.
- **Agent compromise**: Python integrity manifest verification prevents tampered binaries from operating; tamper events are logged to the backend.

---

## Article 11 — Liability and Indemnification

Liability and indemnification obligations are governed by the Master Services Agreement between the Parties. In the event of conflict, the data protection obligations of this Agreement take precedence over the MSA with respect to personal data processing.

---

## Article 12 — Termination and Survival

### 12.1 Termination

This Agreement terminates upon the later of: (a) the termination of the Engagement; or (b) the completion of all deletion obligations under Article 6.

### 12.2 Survival

The following obligations survive termination:

- Confidentiality obligations (indefinitely)
- Audit rights (for the retention periods specified in Article 6.2)
- Deletion certification obligation
- Breach notification obligations (for any breach discovered after termination)
- Record-keeping obligations required by applicable law

---

## Article 13 — Governing Law and Jurisdiction

This Agreement is governed by the laws of `[JURISDICTION]`. Disputes shall be resolved in the courts of `[JURISDICTION]`, subject to any dispute resolution provisions in the Master Services Agreement.

---

## Article 14 — Entire Agreement

This Agreement, together with the Security Whitepaper (KMF-SEC-001) incorporated by reference and the Annexes hereto, constitutes the entire agreement between the Parties with respect to the processing of personal data in connection with the KMFlow Task Mining Agent. It supersedes any prior agreements, representations, or understandings relating to that subject matter.

---

## Signatures

**For the Controller**:

| Field | Value |
|-------|-------|
| Name | |
| Title | |
| Organization | |
| Date | |
| Signature | |

**For the Processor**:

| Field | Value |
|-------|-------|
| Name | |
| Title | |
| Organization | |
| Date | |
| Signature | |

---

*Document ID: KMF-SEC-002 | Template Version: 1.0 | Review Date: 2026-08-25*
*This is a template. It does not constitute legal advice. Have your legal counsel review before execution.*
