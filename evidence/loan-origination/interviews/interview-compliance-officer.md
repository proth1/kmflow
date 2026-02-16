# Interview Transcript
**Subject**: Patricia Nguyen, Compliance Officer (Mortgage Compliance)
**Interviewer**: Sarah Chen (Engagement Lead)
**Date**: 2025-10-22 | **Duration**: 55 minutes
**Location**: Meridian National Bank, HQ Compliance Suite
**Evidence ID**: EV-020

---

## Role and Scope

**SC**: Patricia, can you describe your role within the mortgage compliance framework?

**PN**: I'm responsible for regulatory compliance oversight of the residential mortgage origination operation. That covers TRID compliance, HMDA data integrity, fair lending monitoring support, BSA/AML for mortgage, and state regulatory requirements. I report to Angela Torres, the Chief Compliance Officer. My team is me and one compliance analyst, Jennifer. For a bank our size doing 250+ loans a month, we're lean.

**SC**: What does your day-to-day look like?

**PN**: I split my time between proactive monitoring and reactive issues. Proactive side: monthly TRID compliance sampling, HMDA data scrubs, fair lending data pulls, training program management. Reactive side: I'm the point of contact when an origination issue has a compliance dimension - tolerance violations, disclosure timing errors, fair lending concerns, BSA escalations. I probably spend 40% of my time on reactive issues, which is more than I'd like.

## TRID Compliance

**SC**: How effective are the TRID controls in practice?

**PN**: The first-line controls in Encompass are strong. The system automatically flags when LE delivery is approaching the 3-business-day deadline, and it blocks service ordering until Intent to Proceed is recorded. Those automated controls work well and I rarely see violations on initial LE delivery.

Where we have more risk is on Closing Disclosures and the 3-business-day waiting period before consummation. The Closers are good, but we had an incident around Thanksgiving last year where a CD was delivered only 2 business days before closing because the Closer miscounted business days around the holiday. We caught it before closing and postponed, but it shouldn't have happened. I've since scheduled annual training specifically on business day counting around holidays.

**SC**: What about tolerance violations?

**PN**: We track them quarterly. Most are in the 10% cumulative tolerance bucket - recording fees and third-party services. We had 7 tolerance violations in the last year that required cures. All were cured within the 60-day window. The main driver is when circumstances change between LE and CD - rate lock extensions, appraisal comes in different than expected, or property tax estimates change. Our Closers do a CD-to-LE comparison before generating the final CD, but the comparison is manual and error-prone for complex files.

**SC**: Is there a system check for tolerance?

**PN**: Encompass has a built-in tolerance checker but it requires all the data to be entered correctly, which goes back to data quality. If the LE fees were entered incorrectly at origination, the tolerance check compares against wrong numbers. We've talked about a pre-closing compliance review checkpoint where someone independent validates the CD, but we haven't implemented it due to staffing.

## HMDA and Fair Lending

**SC**: Tell me about HMDA data quality.

**PN**: HMDA is a significant effort. We collect data at application, at action, and at denial. Encompass auto-validates most fields, but the government monitoring information - race, ethnicity, sex - depends on the Loan Officer collecting it correctly. For face-to-face applications, the LO is supposed to observe and note the information if the borrower declines to provide it. For phone and digital applications, it's self-reported only, and if the borrower declines, we have legitimate blank fields.

The data quality issue we've had recently is with phone applications in the consumer direct channel. The LOs don't always ask the monitoring questions during the call, and the application system doesn't force collection of that data. We identified 3 applications in Q2 2025 with missing monitoring data. We've done corrective training, and we're working with IT to add mandatory prompts in the digital application flow.

**SC**: On fair lending monitoring - how do you assess the program's effectiveness?

**PN**: Angela runs a solid program. The quarterly comparative file reviews are comprehensive - we do matched-pair analysis on denied minority applicants versus approved non-minority applicants with similar profiles. We've consistently found our denial rate disparities to be within expected ranges given our applicant pool.

Where I have more concern is on the pricing side. Loan Officers have discretion to adjust rates within a published range. We do semi-annual pricing analysis, and the most recent one flagged a pattern with one LO - Martinez - who has significantly higher rate concession frequency on refinance transactions compared to purchases. It's not necessarily a fair lending issue - it could be a business development strategy - but it needs further investigation. Angela has raised it with Robert Thornton.

**SC**: The exception monitoring - how does that intersect with fair lending?

**PN**: We review all exceptions quarterly for prohibited basis correlation. The exception log data doesn't include borrower demographics directly - I have to cross-reference with the HMDA LAR data. So far we haven't identified disparate patterns in exception grants or denials. But I'd flag that our exception documentation is inconsistent. Some underwriters write detailed compensating factor narratives, others are sparse. The fair lending risk is that inconsistent documentation makes it harder to demonstrate legitimate, non-discriminatory reasons for differential treatment. Maria Santos and Angela are working on standardizing exception documentation, but it's been on the to-do list for a while.

## BSA/AML

**SC**: How do the BSA/AML screening procedures work in practice for mortgage?

**PN**: The OFAC screening is mostly automated through Encompass. It screens at application and pre-closing. The system blocks milestone advancement if screening isn't complete, which is a good preventive control. We average about 18-20 false positive OFAC matches per year - all common name matches. Raymond Keller, our BSA Officer, reviews each one within 24 hours per procedure. We haven't had a true match in the mortgage portfolio, thankfully.

My concern with BSA is the age of the procedures document. Raymond's BSA/AML screening requirements for mortgage were last updated in September 2023 and the review is overdue. FinCEN issued some updated guidance on mortgage-specific money laundering typologies in 2024 that we should incorporate. Raymond's been focused on the commercial banking side and mortgage BSA hasn't been his top priority.

**SC**: What about the wire fraud risk that was flagged in the escalation tickets?

**PN**: Yes, we had a BEC attempt in February targeting closing wire instructions. Our title company's callback verification procedure caught it - that's a control we've required of all title vendors. The incident reinforced the importance of verbal callback for wire instructions. We filed a SAR and issued a bank-wide alert. The broader concern is that these attacks are getting more sophisticated, and we need to make sure our closers and title companies maintain vigilance. We added wire fraud to our annual BSA training for mortgage staff after that incident.

## Training and Compliance Culture

**SC**: How would you assess the compliance culture within the mortgage operation?

**PN**: Generally good. Robert Thornton takes compliance seriously and it filters down. The origination staff understand the importance of TRID timing and disclosure requirements. Where I see gaps is in the "second order" compliance items - things like HMDA data accuracy, fair lending documentation, and vendor oversight. These are things that don't directly impact whether a specific loan closes, so they get less attention in a production-driven environment.

**SC**: Training completion rates?

**PN**: Our annual training includes TRID, fair lending, BSA/AML, and HMDA modules. The 2025 cycle was assigned in September. As of the date you collected this data, we're at 78% completion, which is below our 90% target. That's partly timing - we have 30 days for completion and some staff are in the second half of that window. But historically we end up at about 88-92%, which means we sometimes miss the 90% target. I've escalated it to department heads but there's always a subset of staff who are either on leave, traveling, or just procrastinating.

**DO**: Is there a consequence for non-completion?

**PN**: Escalation to their manager, and ultimately it goes into their annual review. But we haven't ever taken formal disciplinary action for late completion. Maybe we should.

## Regulatory Exam Readiness

**SC**: How prepared do you feel for a regulatory exam focused on mortgage?

**PN**: We maintain an exam-readiness file that we update quarterly. Our OCC examiner was here 18 months ago and the findings were manageable - mostly around vendor management and some HMDA data corrections. I feel reasonably prepared on TRID and fair lending. The areas I'd want to shore up before an exam are: vendor management due diligence (we have overdue reviews), the BSA procedure update, and the SOP review cadence. Having key documents past their review dates doesn't look good to an examiner, even if the underlying practices are sound.

**SC**: Final question - what's the one thing you'd want us to focus on in our assessment?

**PN**: The gap between documented procedures and actual practice. Our policies and SOPs look good on paper, but there are informal workarounds that have crept in - the processor's tracking spreadsheet, the self-employed income guide that an underwriter maintains informally, the condition clearing cheat sheet that has incorrect information in it. These shadow processes are a risk because they're not governed, not reviewed, and can diverge from official policy over time. I'd rather we formalize the ones that are genuinely useful and retire the rest.

---

**Interview concluded at 10:55 AM.**
**Notes reviewed by**: Sarah Chen, 2025-10-23
**Interviewee review**: Not requested per engagement protocol
