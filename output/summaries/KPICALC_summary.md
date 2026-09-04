# Source Code Summary: KPICALC

**Business Domain:** Insurance - Personal Lines Policy and Premium Reporting

## Purpose
Calculate Policy and Premium KPI Metrics & Reconciliation for TFG Personal Lines Reporting by matching policy and premium extracts, computing policy counts by status and product type, aggregating written/earned/unearned premiums, and validating reconciliation (Written = Earned + Unearned within 0.01 tolerance).

## High-Level Narrative
The program opens four sequential files: POLICY-IN (policy extract), PREMIUM-IN (premium extract), KPI-OUT (KPI report), and ERROR-OUT (error/exception report). It reads the first record from each input file, then enters a merge loop that processes records in policy-number order. When policy numbers match, it increments total policy counters, classifies by status (AC, PN, EX, CN) and product type (HO, AU), accumulates premium totals (written, earned, unearned) overall and by product, and performs reconciliation check. If a policy has no matching premium record, it logs error K001; if a premium record has no matching policy, it logs error K002. Unknown status or product type generate errors K003/K004. Reconciliation mismatches beyond 0.01 generate error K005. Sequence validation ensures both input files are sorted ascending by policy number. After processing all records, it writes a formatted 80-byte KPI report with counts and premium totals, closes files, and sets return code: 12 for fatal errors, 4 for data quality errors, 0 otherwise.

## Inputs
- POLICY-IN (Task 8 Status-updated Policy Extract, 77-byte records)
- PREMIUM-IN (Task 7 Earned Premium Extract, 65-byte records)

## Outputs
- KPI-OUT (Formatted 80-byte Monthly KPI Metrics Report)
- ERROR-OUT (Reconciliation and Sequence Error Exceptions, 80-byte records)

## Key Transformations
- Sequential merge join on policy number between policy and premium extracts
- Policy count aggregation by status: Active (AC), Pending (PN), Expired (EX), Cancelled (CN)
- Policy count aggregation by product type: Homeowners (HO), Auto (AU)
- Premium aggregation: Written, Earned, Unearned totals overall and by product type
- Reconciliation validation: Written Premium = Earned + Unearned (tolerance 0.01)
- Missing premium detection (policy without premium) -> error K001
- Orphan premium detection (premium without policy) -> error K002
- Data quality validation: unknown policy status -> error K003, unknown product type -> error K004
- Reconciliation mismatch -> error K005
- Input sequence validation (ascending policy number)

## Key Dependencies
- POLICY-IN file (assigned to POLIN)
- PREMIUM-IN file (assigned to PREMIN)
- KPI-OUT file (assigned to KPIOUT)
- ERROR-OUT file (assigned to ERROUT)
- No copybooks or external procedures referenced

## Business Rules
- Policy statuses: AC=Active, PN=Pending, EX=Expired, CN=Cancelled; any other value is invalid (K003)
- Product types: HO=Homeowners, AU=Auto; any other value is invalid (K004)
- Reconciliation rule: Written Premium must equal Earned Premium + Unearned Premium within 0.01 tolerance (K005)
- Every policy must have a matching premium record; missing premium is error K001
- Every premium record must have a matching policy; orphan premium is error K002
- Input files must be sorted ascending by policy number; out-of-sequence is fatal I/O error
- File open/read errors are fatal (return code 12)
- Data quality errors (K001-K005) set return code 4 if any occur
- KPI report includes: total policies, active/pending/expired/cancelled counts, HO/AU counts, unknown status/product counts, missing/orphan/reconciliation error counts, written/earned/unearned premiums overall and by product
