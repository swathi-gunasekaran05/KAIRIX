# Source Code Summary: EARNPREM

**Business Domain:** Insurance Premium Calculation / Policy Billing

## Purpose
Calculate Earned and Unearned Pro-Rata Premium for insurance policies by matching premium records to policy effective/expiry dates, validating calendar dates, computing term days and earned days using integer date arithmetic, and applying the pro-rata formula: Earned = Written * EarnedDays / TermDays (inclusive), Unearned = Written - Earned (floored at zero).

## High-Level Narrative
The program opens four sequential files (Policy-In, Premium-In, Premium-Out, Error-Out). It reads the first policy record, then enters a loop reading each premium record. For each premium, it searches the policy file (assumed sorted by policy number) to find a matching policy. If not found, writes error E001. If found, validates three dates (policy effective, policy expiry, premium calculation date) for valid calendar format including leap year logic. Validates expiry >= effective. Computes term days (expiry - effective + 1) and earned days based on calculation date: before effective = 0, after expiry = term days, within term = calc - effective + 1. Calculates earned premium with rounding, caps at written premium, computes unearned as written - earned floored at zero. Writes result to Premium-Out. On any validation failure, writes error record to Error-Out with specific error code. Continues until premium file exhausted, then closes all files.

## Inputs
- POLICY-IN (sequential file: policy number, effective date, expiry date)
- PREMIUM-IN (sequential file: premium ID, policy number, written premium, earned premium, unearned premium, calculation date)

## Outputs
- PREMIUM-OUT (sequential file: premium ID, policy number, written premium, earned premium, unearned premium, calculation date)
- ERROR-OUT (sequential file: policy number, error code, error message)

## Key Transformations
- Date validation with leap year calculation (Gregorian calendar rules)
- Integer date conversion using FUNCTION INTEGER-OF-DATE for day counting
- Term days calculation: Expiry - Effective + 1 (inclusive)
- Earned days determination based on calculation date relative to policy term
- Pro-rata earned premium: Written * EarnedDays / TermDays with rounding
- Earned premium cap at written premium
- Unearned premium = Written - Earned, floored at zero
- Sequential file matching on policy number (merge-like logic)

## Key Dependencies
- COBOL intrinsic functions: INTEGER-OF-DATE, MOD
- Sequential file system (POLIN, PREMIN, PREMOUT, ERROUT)
- Sorted input assumption: Policy-In and Premium-In ordered by policy number

## Business Rules
- Policy record must exist for each premium record (E001)
- All dates must be valid calendar dates (E002, E003, E006)
- Policy expiry date must be on or after effective date (E004)
- Policy term days must be positive (E005)
- Calculation date before effective date => 0 earned days
- Calculation date after expiry date => full term earned days
- Calculation date within term => inclusive days from effective
- Earned premium cannot exceed written premium
- Unearned premium cannot be negative (minimum zero)
- Day counts are inclusive (+1) for both term and earned periods
