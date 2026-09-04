# Source Code Summary: PolicyCenter_CPP_Breakdown

**Business Domain:** PolicyCenter / Commercial Package Policy (CPP) / Agribusiness / Premium Accounting

## Purpose
Extracts Commercial Package Policy (CPP) line-level written premium breakdowns across multiple lines of business (Property, General Liability, Commercial Auto, Crime, Inland Marine, Workers Comp) for Agribusiness, including transaction-level detail for renewals, submissions, cancellations, reinstatements, and policy changes.

## High-Level Narrative
The script declares date parameters (@POLSTARTDATE, @POLENDDATE, @CHANGESTARTDATE, @curmthyr) and executes a UNION ALL of two major queries. The first query retrieves granular line-level transactions for each coverage line within a Commercial Package policy, joining policy period, policy, job, account, producer, organization, and numerous lookup tables. It calculates written premium per line via correlated subqueries against line-specific transaction tables (pcx_cp7transaction, pcx_gl7transaction_gle, pcx_ca7transaction, pcx_cr7transaction, pc_imtransaction, pcx_wc7transaction). The second query provides a policy-level summary row (LineOfBusiness = 'C.P.P.') using the policy period's TransactionCostRPT. The outer SELECT applies conditional logic to allocate premium amounts and dates based on transaction type (TranType): Renewal/Submission, Cancellation, Reinstatement, PolicyChange. Results are filtered to bound/audit-complete policy periods with job close dates before @POLENDDATE.

## Inputs
- PolicyCenter.dbo.pc_policyperiod
- PolicyCenter.dbo.pc_policy
- PolicyCenter.dbo.pc_policyTerm
- PolicyCenter.dbo.pc_policyline
- PolicyCenter.dbo.pc_job
- PolicyCenter.dbo.pc_account
- PolicyCenter.dbo.pc_producercode
- PolicyCenter.dbo.pc_organization
- PolicyCenter.dbo.pctl_job
- PolicyCenter.dbo.pctl_policyperiodstatus
- PolicyCenter.dbo.pctl_bindoption
- PolicyCenter.dbo.pctl_uwcompanycode
- PolicyCenter.dbo.pctl_jobdescription_ext
- PolicyCenter.dbo.pctl_policyperiodsourcetype
- PolicyCenter.dbo.pctl_profitcentertype
- PolicyCenter.dbo.pctl_orgfarmuwterritory
- PolicyCenter.dbo.pcx_cp7transaction
- PolicyCenter.dbo.pcx_gl7transaction_gle
- PolicyCenter.dbo.pcx_ca7transaction
- PolicyCenter.dbo.pcx_cr7transaction
- PolicyCenter.dbo.pc_imtransaction
- PolicyCenter.dbo.pcx_wc7transaction
- @POLSTARTDATE
- @POLENDDATE
- @CHANGESTARTDATE
- @curmthyr

## Outputs
- Result set with columns: ProfitCenter, ProductCode, LineOfBusiness, PolicyNumber, OriginalEffectiveDate, PeriodStart, PeriodEnd, AccountNumber, Company, PrimaryInsuredName, AgentCode, AgentName, FarmUWTerritory, MostRecentTran, SubWritten_Premium, SubWritten_Date, CancelledDate, CancelledEffDate, CancelledPremium, ReinstatedPremium, ReinstatedDate, ReinstatedEffDate, ChangePremium, ChangeDate

## Key Transformations
- Map PatternCode to LineOfBusiness (e.g., 'cp7line' -> 'Commercial Property Line')
- Map UW company name to short code (LRM, WRM, SON, UNK)
- Format producer code to rightmost 3 characters or '999' if null
- Calculate written premium per line via correlated subqueries on line-specific transaction tables
- Conditional allocation of premium and dates based on TranType (Renewal, Submission, Cancellation, Reinstatement, PolicyChange)
- Union of line-level detail with policy-level summary row (C.P.P.)
- Filter on policy period status (Bound, AuditComplete) and job close date before @POLENDDATE
- Derive primary insured name from most recent model policy period

## Key Dependencies
- PolicyCenter.dbo.pc_policyperiod
- PolicyCenter.dbo.pc_policy
- PolicyCenter.dbo.pc_policyTerm
- PolicyCenter.dbo.pc_policyline
- PolicyCenter.dbo.pc_job
- PolicyCenter.dbo.pc_account
- PolicyCenter.dbo.pc_producercode
- PolicyCenter.dbo.pc_organization
- PolicyCenter.dbo.pctl_job
- PolicyCenter.dbo.pctl_policyperiodstatus
- PolicyCenter.dbo.pctl_bindoption
- PolicyCenter.dbo.pctl_uwcompanycode
- PolicyCenter.dbo.pctl_jobdescription_ext
- PolicyCenter.dbo.pctl_policyperiodsourcetype
- PolicyCenter.dbo.pctl_profitcentertype
- PolicyCenter.dbo.pctl_orgfarmuwterritory
- PolicyCenter.dbo.pcx_cp7transaction
- PolicyCenter.dbo.pcx_gl7transaction_gle
- PolicyCenter.dbo.pcx_ca7transaction
- PolicyCenter.dbo.pcx_cr7transaction
- PolicyCenter.dbo.pc_imtransaction
- PolicyCenter.dbo.pcx_wc7transaction

## Business Rules
- Only policies with non-null IssueDate and PolicyNumber are considered
- Policy period status must be 'Bound' or 'AuditComplete'
- Job close date must be before @POLENDDATE
- Line-level detail only for ProductCode = 'CommercialPackage'
- Line effective/expiration dates must differ from period start/end (first query)
- MostRecentModel = 1 used to identify most recent transaction and primary insured name
- Transaction type determines which premium/date columns are populated: Renewal/Submission -> SubWritten_Premium/SubWritten_Date; Cancellation -> CancelledDate/CancelledEffDate/CancelledPremium; Reinstatement -> ReinstatedPremium/ReinstatedDate/ReinstatedEffDate; PolicyChange -> ChangePremium/ChangeDate
- Written premium for line-level detail sourced from line-specific transaction tables; policy-level summary uses TransactionCostRPT
