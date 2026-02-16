# BSA/AML Screening Requirements for Mortgage Lending
**Meridian National Bank**
**Document ID**: LO-REG-003 | **Version**: 1.6 | **Effective**: 2023-09-01
**Owner**: BSA Officer - Raymond Keller | **Next Review**: 2024-09-01 (OVERDUE)

---

## 1. Purpose

These procedures establish the Bank Secrecy Act (BSA) and Anti-Money Laundering (AML) screening requirements specific to residential mortgage loan origination at Meridian National Bank. They supplement the Bank's enterprise BSA/AML program and address mortgage-specific risk indicators.

## 2. Regulatory Framework

- Bank Secrecy Act (31 USC 5311-5332)
- USA PATRIOT Act (Title III)
- FinCEN CDD Rule (31 CFR 1020.210)
- OFAC Sanctions Programs (31 CFR Part 500)
- OCC BSA/AML Examination Manual

## 3. Customer Identification Program (CIP)

### 3.1 Identity Verification Requirements
Before closing any mortgage transaction, the Bank must verify the identity of each borrower and co-borrower:

| Requirement | Documentation |
|------------|--------------|
| Full legal name | Government-issued photo ID |
| Date of birth | Government-issued photo ID or birth certificate |
| Address | Government-issued photo ID + utility bill or bank statement |
| Tax Identification Number | SSN card or W-2/tax return |

### 3.2 Non-US Citizens
Additional requirements for non-US citizen borrowers:
- Valid passport + visa documentation
- ITIN if no SSN available (FHA only; conventional requires SSN)
- Permanent Resident Card (if applicable)
- Employment Authorization Document (EAD)

### 3.3 Verification Methods
| Method | When Used |
|--------|-----------|
| Documentary | Primary method for all borrowers |
| Non-documentary (credit bureau, LexisNexis) | Supplemental for discrepancy resolution |
| Database verification (SSA, DHS via E-Verify) | Non-US citizens and identity fraud indicators |

## 4. OFAC Screening

### 4.1 Screening Points
OFAC screening is mandatory at the following milestones:

| Milestone | Screened Parties | System |
|-----------|-----------------|--------|
| Application | Borrower(s) | Encompass (auto-screen via LexisNexis) |
| Pre-Closing | Borrower(s) + Seller + Closing Agent | Encompass (auto-screen) |
| Funding | Borrower(s) | Encompass (manual confirmation) |

### 4.2 Screening Against Lists
- OFAC Specially Designated Nationals (SDN) List
- OFAC Consolidated Sanctions List
- FinCEN 314(a) Subject List
- FBI Most Wanted / Terrorism Watch List (via LexisNexis)

### 4.3 Potential Match Procedures
If screening returns a potential match:
1. **Processing STOPS** - No further action on the loan
2. Processor notifies BSA Officer within 2 hours
3. BSA Officer reviews match details within 24 hours
4. If **true match**: File SAR, block transaction, notify legal counsel
5. If **false positive**: Document disposition in screening log, resume processing
6. All potential matches logged regardless of disposition

### 4.4 System Controls
- Encompass configured to block milestone advancement if OFAC screening incomplete
- Daily batch re-screening of pipeline loans against updated lists
- Screening results retained in loan file for life of loan + 5 years

## 5. Mortgage-Specific Red Flags

### 5.1 Money Laundering Indicators
Origination staff trained to identify and report:

**Application Red Flags**:
- Borrower unable or unwilling to provide required documentation
- Income or assets significantly inconsistent with borrower profile
- Borrower insists on paying large amounts in cash at closing
- Frequent address changes or use of mail drop addresses
- Employment information cannot be verified

**Transaction Red Flags**:
- Purchase price significantly above or below market value without explanation
- Rapid succession of refinance transactions (churning)
- Cash-out refinance shortly after purchase with no apparent need
- Borrower directing funds to third-party accounts at closing
- Use of multiple entities or trusts to obscure beneficial ownership
- Unusual earnest money deposits from unrelated parties

**Property Red Flags**:
- Property appears vacant or in disrepair despite borrower claiming occupancy
- Multiple applications for properties in same development by unrelated borrowers
- Straw buyer indicators (occupancy misrepresentation)

### 5.2 Fraud Indicators Requiring BSA Escalation
The following fraud indicators must be escalated to BSA Officer (separate from standard fraud referral to QC):
- Suspected identity theft or synthetic identity
- Organized fraud rings (multiple applications with connected parties)
- Wire fraud attempts targeting closing proceeds
- Suspicious Activity Report (SAR) consideration for any confirmed fraud

## 6. Suspicious Activity Reporting

### 6.1 SAR Filing Obligations
A SAR must be filed for mortgage transactions involving:
- Known or suspected criminal violations aggregating $5,000 or more
- Transactions designed to evade BSA reporting requirements
- Transactions with no business or apparent lawful purpose
- Use of the Bank to facilitate criminal activity

### 6.2 SAR Filing Process
1. Origination staff report suspicious activity to BSA Officer via internal SAR referral form
2. BSA Officer reviews and determines if SAR filing warranted within 5 business days
3. SAR filed via BSA E-Filing system within 30 calendar days of determination
4. SAR narrative includes all known facts, suspect information, and Bank actions taken
5. SAR filing is confidential; borrower and origination staff not notified of filing

### 6.3 Reporting Metrics (2024)
| Metric | Count |
|--------|-------|
| SAR referrals from mortgage origination | 4 |
| SARs filed related to mortgage | 2 |
| False positive OFAC matches resolved | 18 |
| 314(a) matches | 0 |

## 7. Enhanced Due Diligence (EDD)

### 7.1 EDD Triggers for Mortgage
Enhanced due diligence required when:
- Borrower is a Politically Exposed Person (PEP)
- Transaction involves foreign source of funds
- Property located in known high-risk geographic area (per BSA risk assessment)
- Borrower has prior SAR filings at any financial institution (if known)
- Transaction exceeds $1,000,000 with limited documented income

### 7.2 EDD Procedures
1. Senior Underwriter and BSA Officer jointly review file
2. Source of funds fully documented and verified through independent means
3. Purpose of transaction clearly established and documented
4. Ongoing monitoring flag set in Encompass for post-close activity
5. EDD memo prepared and retained in loan file

## 8. Training

### 8.1 Required BSA/AML Training for Mortgage Staff
| Role | Training Module | Frequency |
|------|---------------|-----------|
| All origination staff | BSA/AML Awareness | Annual |
| Loan Officers | Red Flag Identification | Annual + new hire |
| Processors | OFAC Screening and CIP | Annual |
| Underwriters | SAR Referral Procedures | Annual |
| Closers | Wire Fraud Prevention | Annual |

### 8.2 Training Completion
- 2024 BSA training completion: 92% (target: 95%)
- 3 staff members on leave at collection date; deadline extended

## 9. Recordkeeping

| Record Type | Retention Period |
|-------------|-----------------|
| CIP documentation | 5 years after account closure |
| OFAC screening results | Life of loan + 5 years |
| SAR filings and supporting documentation | 5 years from filing date |
| BSA training records | 5 years |
| EDD memos | Life of loan + 5 years |

---

**Approved**: Raymond Keller, BSA Officer
**Reviewed**: BSA/AML Compliance Committee, 2023-08-15
**Note**: Document review is overdue. Update pending to incorporate 2024 FinCEN mortgage-specific guidance.
