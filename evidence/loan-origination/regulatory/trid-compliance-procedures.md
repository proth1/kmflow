# TRID Compliance Procedures
**Meridian National Bank**
**Document ID**: LO-REG-001 | **Version**: 2.4 | **Effective**: 2024-06-01
**Owner**: Compliance Officer - Patricia Nguyen | **Next Review**: 2025-06-01

---

## 1. Purpose

These procedures implement the TILA-RESPA Integrated Disclosure (TRID) rule requirements (12 CFR 1026.19(e) and (f)) for all residential mortgage loan originations at Meridian National Bank. They govern the timing, content, and delivery of the Loan Estimate (LE) and Closing Disclosure (CD).

## 2. Scope

Applicable to all closed-end consumer mortgage transactions secured by real property, including:
- Purchase, rate/term refinance, and cash-out refinance
- Construction-to-permanent loans
- Conventional, FHA, VA, and USDA products

**Exclusions**: HELOCs (governed by TILA open-end rules), reverse mortgages, chattel-dwelling loans.

## 3. Application Trigger and Loan Estimate

### 3.1 Six-Piece Application Rule
A completed application is received when the Bank has collected all six pieces:
1. Borrower name
2. Borrower income
3. Social Security Number (to obtain credit report)
4. Property address
5. Estimated property value
6. Mortgage loan amount sought

**System Control**: Encompass flags application as "TRID-Triggered" when all six fields are populated. Compliance alert fires if LE not generated within 2 business days.

### 3.2 Loan Estimate Delivery

**Timeline**: LE must be delivered or placed in mail no later than **3 business days** after receipt of completed application.

| Delivery Method | Business Day Rule |
|----------------|------------------|
| Hand delivery / Electronic | Received same day |
| Mail (USPS) | Presumed received 3 calendar days after mailing |
| Email (eSign via DocuSign) | Received upon confirmed electronic access |

### 3.3 LE Content Requirements
All Encompass-generated LEs are validated against CFPB model forms. Key fields verified:
- Loan terms, projected payments, costs at closing
- Loan costs (origination charges, services borrower can/cannot shop for)
- Other costs (taxes, prepaids, initial escrow)
- Closing cost details with tolerance categorization

### 3.4 Intent to Proceed
No fees may be collected (other than credit report fee) until borrower indicates Intent to Proceed:
- Verbal (documented in Encompass notes with date/time)
- Written (signed LE returned)
- Electronic (eSign acceptance)

**System Control**: Encompass blocks service orders until Intent to Proceed milestone is set.

## 4. Tolerance Categories

### 4.1 Zero Tolerance (no increase permitted)
- Fees paid to creditor (origination charges)
- Fees paid to unaffiliated settlement providers where borrower was not permitted to shop
- Transfer taxes

### 4.2 10% Cumulative Tolerance
- Recording fees
- Fees for required third-party services where borrower is permitted to shop but uses provider from Bank's written list

### 4.3 Unlimited Tolerance (no cap on increases)
- Prepaid interest
- Property insurance premiums
- Fees for services where borrower selects own provider
- Escrow amounts

## 5. Changed Circumstance Procedures

### 5.1 Valid Changed Circumstances
A revised LE may be issued only upon a valid changed circumstance:
1. **Extraordinary event** beyond party control (natural disaster, title issue)
2. **Information received** that was not known at LE issuance (appraisal result, credit change)
3. **Borrower-requested change** (rate lock, product change, loan amount)
4. **Construction loan settlement delay** beyond party control
5. **Rate lock expiration** where borrower did not lock at application

### 5.2 Revised LE Timing
Revised LE must be delivered within **3 business days** of learning of the changed circumstance and no later than **4 business days** before consummation.

### 5.3 Documentation Requirements
For each revised LE, processor must document in Encompass:
- Specific changed circumstance triggering revision
- Date Bank became aware of circumstance
- Comparison of original vs revised figures
- Tolerance category analysis

## 6. Closing Disclosure

### 6.1 Delivery Timeline
CD must be received by borrower no later than **3 business days** before consummation.

| Delivery Method | Days Before Closing |
|----------------|-------------------|
| Hand delivery / Electronic | 3 business days |
| Mail (USPS) | 6 business days (3 mailing + 3 waiting) |

### 6.2 CD Accuracy Verification
Before CD generation, Closer verifies:
- All fees reconciled against LE (tolerance check)
- Final loan terms match commitment
- Property tax and insurance prorations correct
- Cash to close figure validated
- Seller credits and lender credits accurately reflected

### 6.3 Tolerance Cure
If tolerance violations are identified at closing:
1. Closer notifies Compliance immediately
2. Refund to borrower must be provided within **60 calendar days** of consummation
3. Corrected CD issued reflecting cure amount
4. Cure documented in loan file and compliance tracking system

**Tracking**: Tolerance cures logged in quarterly compliance report to Board Loan Committee.

### 6.4 Three-Day Waiting Period Resets
A new 3-business-day waiting period is required if the CD is corrected to reflect:
- APR increase exceeding 1/8 of a percent (regular) or 1/4 of a percent (irregular)
- Change in loan product
- Addition of a prepayment penalty

## 7. Electronic Delivery (E-Sign)

### 7.1 E-Sign Act Compliance
Before electronic delivery of LE or CD:
- Borrower must provide affirmative E-Sign consent via DocuSign ceremony
- Consent covers specific transaction and disclosure types
- Borrower may withdraw consent at any time (reverts to paper delivery)

### 7.2 System of Record
DocuSign audit trail constitutes proof of delivery. Encompass stores:
- Timestamp of document generation
- Timestamp of electronic delivery
- Timestamp of borrower access/signature
- IP address and device information

## 8. Compliance Monitoring

### 8.1 First-Line Controls
- Encompass automated TRID timeline alerts (LO and Processor dashboards)
- Daily compliance queue reviewed by Processing Manager
- Tolerance violation alerts trigger mandatory review before CD generation

### 8.2 Second-Line Controls
- Monthly TRID compliance sample (15 files) reviewed by Compliance team
- Quarterly tolerance violation trending report
- Annual TRID training required for all origination staff

### 8.3 Third-Line Controls
- Internal Audit conducts annual TRID compliance audit
- External regulatory exam readiness file maintained by Compliance

## 9. Record Retention

| Document | Retention Period |
|----------|-----------------|
| Loan Estimate (all versions) | Life of loan + 5 years |
| Closing Disclosure (all versions) | Life of loan + 5 years |
| Changed circumstance documentation | Life of loan + 5 years |
| E-Sign consent records | Life of loan + 5 years |
| Tolerance cure documentation | Life of loan + 5 years |

---

**Approved**: Patricia Nguyen, Compliance Officer
**Reviewed**: Regulatory Compliance Committee, 2024-05-20
