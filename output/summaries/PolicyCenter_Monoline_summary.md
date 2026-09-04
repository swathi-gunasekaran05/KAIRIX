# Source Code Summary: PolicyCenter_Monoline

**Business Domain:** PolicyCenter / Commercial Lines Underwriting (Agribusiness)

## Purpose
Extracts monoline policy transactions, premium breakdowns, agent details, and job status for commercial lines underwriting (Agribusiness) within specified policy period and job close date ranges.

## High-Level Narrative
The script declares date parameters for policy period start/end and change start date. It then executes a UNION ALL of two major SELECT statements. The first SELECT retrieves detailed line-level transactions for Commercial Package product lines (Commercial Property, General Liability, Commercial Auto, Crime, Inland Marine, Workers Comp) by joining policy period, policy, policy term, policy line, job, account, producer code, organization, and numerous lookup tables. It calculates written premium per line using correlated subqueries against line-specific transaction tables (pcx_cp7transaction, pcx_gl7transaction_gle, pcx_ca7transaction, pcx_cr7transaction, pc_imtransaction, pcx_wc7transaction). The second SELECT retrieves the Commercial Package Policy (C.P.P.) as a whole with a static LineOfBusiness 'C.P.P.' and uses the policy period's TransactionCostRPT as written premium. Both SELECTs map UW company codes to abbreviations (LRM, WRM, SON, UNK), derive agent code/name, farm underwriting territory, producer code, job details, and policy period status. The outer query then pivots transaction-level data into separate columns based on transaction type (Renewal, Submission, Cancellation, Reinstatement, PolicyChange) using CASE expressions, outputting premium amounts and effective dates per transaction type. Filtering ensures only bound or audit-complete policy periods with job close dates before the policy end date are included.

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

## Outputs
- Monoline Policy Transaction Extract (result set with columns: ProfitCenter, ProductCode, LineOfBusiness, PolicyNumber, OriginalEffectiveDate, PeriodStart, PeriodEnd, AccountNumber, Company, PrimaryInsuredName, AgentCode, AgentName, FarmUWTerritory, MostRecentTran, SubWritten_Premium, SubWritten_Date, CancelledDate, CancelledEffDate, CancelledPremium, ReinstatedPremium, ReinstatedDate, ReinstatedEffDate, ChangePremium, ChangeDate)

## Key Transformations
- Mapping PatternCode to LineOfBusiness descriptive names
- Mapping UW company names to abbreviations (LRM, WRM, SON, UNK)
- Deriving AgentCode from organization Code_Ext padded to 6 chars
- Deriving ProducerCode as last 3 digits of producer code or '999'
- Calculating Written_Premium per line via correlated subqueries summing amount from line-specific transaction tables keyed by BranchID = policy period ID
- Using UNION ALL to combine line-level detail with CPP summary row
- Pivoting transaction types (Renewal, Submission, Cancellation, Reinstatement, PolicyChange) into separate premium and date columns using CASE expressions
- Filtering on policy period status (Bound, AuditComplete) and job close date before @POLENDDATE

## Key Dependencies
- PolicyCenter database schema
- Line-specific transaction tables (pcx_cp7transaction, pcx_gl7transaction_gle, pcx_ca7transaction, pcx_cr7transaction, pc_imtransaction, pcx_wc7transaction)
- Lookup tables for job types, policy period status, bind options, UW company codes, job descriptions, policy period source types, profit center types, farm UW territories

## Business Rules
- Only policy periods with status 'Bound' or 'AuditComplete' are included
- Job close date must be before policy end date parameter (@POLENDDATE)
- Policy must have an IssueDate and PolicyNumber
- For Commercial Package product, premium is summed from line-specific transaction tables; otherwise uses TransactionCostRPT
- PrimaryInsuredName taken from most recent model (MostRecentModel = 1) for same policy number and period start
- Agent code derived from producer's organization Code_Ext
- Producer code defaults to '999' if missing, else last 3 characters
- Transaction type determines which premium/date columns are populated: Renewal/Submission -> SubWritten_Premium/SubWritten_Date; Cancellation -> CancelledDate/CancelledEffDate/CancelledPremium; Reinstatement -> ReinstatedPremium/ReinstatedDate/ReinstatedEffDate; PolicyChange -> ChangePremium/ChangeDate
- MostRecentTran only shown when MostRecentModel = 1
