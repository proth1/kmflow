# Loan Processor Desktop Procedure Guide
**Meridian National Bank**
**Document ID**: LO-DPG-003 | **Version**: 2.1 | **Effective**: 2022-08-01
**Owner**: Loan Processing Manager - James Whitfield

---

## Overview

This guide covers the day-to-day responsibilities and system steps for Loan Processors at Meridian National Bank. All processing activity occurs within the Encompass LOS unless otherwise noted.

## 1. New File Setup

When a loan file is assigned to your queue:

1. **Encompass**: Open loan file > Verify borrower info matches application
2. **Encompass**: Run compliance check (Tools > Compliance > TRID Check)
3. **Order Services** (within 1 business day of Intent to Proceed):
   - Credit report (if not already pulled): Tools > Services > Order Credit
   - Appraisal: Tools > Services > AMC Portal (ValuTrac)
   - Flood cert: Tools > Services > Flood Zone
   - Title: Tools > Services > Title Order (preferred vendor list)
   - VOE/VOD: Tools > Services > Verifications
4. **Create Processor Checklist**: Forms > Processing > Checklist Template
5. **Set milestones**: Pipeline > Milestones > Set Expected Dates

**Target**: File setup complete within 4 hours of assignment.

## 2. Document Collection and Follow-Up

### 2.1 Initial Document Request
Email borrower using Encompass template: Templates > Borrower Communication > Initial Doc Request

Standard request list:
- Items per product type (auto-populated from AUS findings)
- Government photo ID
- Signed authorizations (4506-C, credit, VOE)

### 2.2 Follow-Up Cadence
| Day | Action |
|-----|--------|
| Day 0 | Initial document request sent |
| Day 3 | First follow-up call/email if no response |
| Day 5 | Second follow-up; escalate to LO |
| Day 7 | LO direct contact with borrower |
| Day 10 | Manager review of stalled file |
| Day 15 | Withdrawal consideration per policy |

### 2.3 Document Receipt and Validation
For each received document:
1. Verify it matches what was requested
2. Check all pages present (bank statements especially)
3. Verify dates are within required windows
4. Scan/upload to Encompass document vault
5. Index with correct document type code
6. Update processor checklist

**Common rejection reasons**: Missing pages, expired documents, illegible copies, unsigned forms.

## 3. Ordering Third-Party Services

### 3.1 Appraisal
- Order ONLY after receiving Intent to Proceed
- Use AMC rotation (ValuTrac system handles automatically)
- Rush fee ($150) requires LO approval and borrower consent
- Track status daily; escalate if no assignment within 48 hours
- Review returned appraisal for completeness before forwarding to underwriting

### 3.2 Title
- Order from preferred vendor list (rotate quarterly)
- Review preliminary title report for:
  - Correct legal description
  - No unexpected liens or judgments
  - No boundary/easement issues
  - Vesting matches application
- Request clearance of any exceptions before submission to underwriting

### 3.3 Flood Determination
- Auto-ordered through ServiceLink
- If property in SFHA: notify LO immediately, require flood insurance quote
- Maintain LOMA/LOMR documentation if applicable

## 4. File Submission to Underwriting

### 4.1 Pre-Submission Checklist
Before moving file to underwriting queue:
- [ ] All AUS conditions have corresponding documentation
- [ ] Credit report is current (within 120 days)
- [ ] Income calculation worksheet completed
- [ ] Asset verification complete with sourcing
- [ ] Appraisal received and reviewed
- [ ] Title commitment received
- [ ] All disclosures delivered and signed
- [ ] Compliance checks passing (no TRID violations)
- [ ] Processor notes summarize any file complexities

### 4.2 Submission
1. Update Encompass milestone: Processing Complete
2. Move to underwriting queue: Pipeline > Route > Underwriting
3. Add processor summary note with:
   - Loan highlights (product, LTV, DTI, FICO)
   - Any items of note or concern
   - AUS recommendation reference

## 5. Post-Underwriting: Condition Management

### 5.1 Condition Receipt
When file returns from underwriting:
1. Review all conditions listed in Encompass Conditions tab
2. Categorize: Prior to Doc (PTD) vs Prior to Close (PTC) vs Prior to Fund (PTF)
3. Create borrower communication listing outstanding items
4. Set internal deadlines (PTD: 48 hours, PTC: 5 business days)

### 5.2 Condition Clearing
For each condition:
1. Obtain required documentation
2. Upload to Encompass and attach to specific condition
3. Add clearing notes explaining how condition is satisfied
4. Mark condition as "Submitted for Review"
5. Underwriter reviews and accepts/rejects within 24 hours

### 5.3 Clear to Close (CTC)
Once all conditions cleared:
1. Order final Closing Disclosure preparation
2. Verify CD figures match LE within tolerances
3. Deliver CD to borrower (3 business day waiting period begins)
4. Coordinate closing date with title company, borrower, and LO
5. Prepare closing package in Encompass

## 6. Closing Coordination

### 6.1 Pre-Closing
- Confirm wire instructions with title company (verbal callback required)
- Verify closing agent and location
- Send closing package to title company minimum 24 hours prior
- Confirm borrower has cashier's check or wire for funds to close

### 6.2 Post-Closing
- Receive executed closing documents from title company within 24 hours
- Review for completeness and proper execution
- Upload to Encompass document vault
- Update milestone: Closed
- Forward to post-close team for funding and shipping

## 7. System Notes and Communication Standards

### 7.1 Encompass Notes
Every borrower contact and material action must be logged:
```
[DATE] [PROCESSOR NAME] - [ACTION TYPE]
Description of action taken or information received.
```
Example:
```
10/15/2025 J.WHITFIELD - DOCUMENT RECEIPT
Received 2023 and 2024 W-2s from borrower via secure upload.
Both years consistent with application income. Filed to doc vault.
```

### 7.2 Email Standards
- Always use Encompass email templates when available
- CC the Loan Officer on all borrower communications
- Never discuss specific loan terms in unsecured email
- Use secure portal for document exchange

## 8. Common Issues and Workarounds

### 8.1 AUS Resubmission
If changes to loan data require AUS rerun:
1. Notify LO before making changes
2. Document reason for resubmission in notes
3. Run new AUS
4. If findings change, re-route to underwriting

### 8.2 Rate Lock Extensions
If rate lock is expiring:
1. Alert LO minimum 5 days before expiration
2. LO requests extension through secondary marketing
3. Extension fee (0.125% per 7 days) may apply
4. Update lock expiration in Encompass

### 8.3 Stale Documents
If documents expire during processing:
- Pay stubs: Re-request if >30 days old at closing
- Bank statements: Re-request if >60 days old at submission
- Credit report: Re-pull if >120 days from closing
- Appraisal: Valid for 120 days from effective date; recertification possible

---

**Note**: This guide is supplementary to official policy (LO-POL-001) and SOPs (LO-SOP-002). In case of conflict, policy documents govern.

**Last Reviewed**: James Whitfield, 2022-07-20
**Next Review**: 2023-08-01 (OVERDUE - under revision)
