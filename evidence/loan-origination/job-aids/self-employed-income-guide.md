# Self-Employed Borrower Income Calculation Guide
**INFORMAL - NOT OFFICIAL SOP**

*Created by: Lisa Chen (Senior Underwriter)*
*Last Updated: 2024-06-10*
*Shared via: Team SharePoint > Underwriting > Helpful Docs*

---

> **Disclaimer**: This is a quick-reference guide I put together based on common SE scenarios we see. Always check the official SOP (LO-SOP-002) for the authoritative rules. If something here conflicts with the SOP, the SOP wins.

## When to Use This Guide

Use this when the borrower has ANY of the following:
- Sole proprietorship (Schedule C)
- S-Corp ownership >25% (Schedule E / K-1)
- Partnership/LLC (K-1)
- Multiple business entities
- Rental income used for qualifying (Schedule E)

## Step 1: Gather the Right Tax Returns

You need **2 full years** of personal + business returns:
- Form 1040 (both years)
- All schedules (especially C, D, E)
- K-1s from all entities
- Corporate returns (1120S, 1065) if available

**Gotcha**: If borrower files extension, you need the extension AND the most recent filed year. Don't accept just the extension.

## Step 2: Calculate Net Income by Entity Type

### Sole Prop (Schedule C)
```
Line 31 (Net profit/loss)
+ Line 13 (Depreciation)
+ Line 12 (Depletion) [rare]
+ Amortization/Casualty (from 4562)
+ 50% of Line 24b (Meals) <-- SEE NOTE BELOW
- Line 6 (if claiming home office and it inflates income)
= Adjusted Net Income
```

### S-Corp (1120S + K-1)
```
K-1 Box 1 (Ordinary income)
+ W-2 wages from the S-Corp
+ Depreciation (from 1120S)
+ Amortization (from 1120S)
+ 50% Meals/Entertainment
- Distributions in excess of basis (red flag - document!)
= Adjusted Net Income
```

### Partnership/LLC (1065 + K-1)
```
K-1 Box 1 (Ordinary income)
+ Depreciation (from 1065, prorated to ownership %)
+ Amortization (prorated)
+ 50% Meals (prorated)
= Adjusted Net Income
```

## Step 3: Addback Rules

### What to Add Back (Always)
- Depreciation (all forms)
- Depletion
- Amortization
- Business use of home (line 30 on Schedule C)

### What to Add Back (Partial)
- Meals/Entertainment: **Add back 50%**
  - *Note: Some underwriters use 100% addback for the pre-2018 portion if the returns span the tax law change. I recommend 50% across the board for consistency, but check with your UW manager if the borrower's income is borderline.*

### What NOT to Add Back
- Vehicle expenses (these are real costs)
- Supplies and materials
- Contract labor
- Rent on business property
- Insurance premiums

## Step 4: Average or Most Recent Year?

**General Rule**: Average the 2 years.

**Exception - Use MOST RECENT year only if**:
- Income declined >15% YOY (per SOP)
- Business changed structure (e.g., sole prop to LLC)
- One year had clearly non-recurring income

**Exception - Use the HIGHER year if**:
- Income is trending up AND borrower can document reason (new contract, expansion)
- **This is not in the SOP** but I've seen it approved for jumbo portfolio loans with strong compensating factors. Get manager approval if you do this.

## Step 5: Multiple Entities - How to Combine

For borrowers with multiple businesses:
1. Calculate each entity SEPARATELY using steps above
2. If any entity shows a LOSS, you MUST include it (subtract from total)
3. Sum all adjusted net incomes
4. Divide by 24 for monthly qualifying income

**Common Mistake**: Don't forget to include the W-2 wages separately from K-1 income for S-Corp owners. They pay themselves a salary AND take distributions.

## Step 6: YTD P&L Requirements

If more than 90 days from most recent tax filing:
- Need CPA-prepared YTD P&L (not borrower-prepared)
- Compare YTD P&L to prior year same period
- If YTD significantly lower, may need to use annualized YTD instead of tax return average

**Tip**: "CPA-prepared" means signed by CPA. A P&L that the borrower made in QuickBooks and emailed to us doesn't count, even if they have a CPA.

## Quick Decision Tree

```
Is borrower self-employed?
  |
  Yes -> Do they own >25% of the business?
           |
           Yes -> Full analysis required (this guide)
           |
           No  -> Use W-2 income only (standard calc)
  |
  No -> Standard income calc per SOP Section 3
```

## Common Issues I See

1. **Processors confusing gross revenue with net income** - Always use NET after expenses
2. **Missing pages from tax returns** - Need ALL pages, including schedules
3. **K-1 not matching corporate return** - If you have both, reconcile them
4. **Declining income not flagged** - Always compare YOY; if >15% decline, must document
5. **Addback inconsistency** - Different underwriters using different meals% - we should standardize this

## Need Help?

Ping me on Teams or email. For really complex scenarios (multiple entities + rental + non-arm's length transactions), loop in Maria Santos.

---

*This guide is not a substitute for the official SOP. When in doubt, check LO-SOP-002 or ask your UW manager.*
