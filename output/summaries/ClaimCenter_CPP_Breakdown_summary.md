# Source Code Summary: ClaimCenter_CPP_Breakdown

**Business Domain:** ClaimCenter / Commercial Package Policy (CPP) Claims / Incurred Loss Analysis

## Purpose
Extracts Commercial Package Policy (CPP) incurred losses with line of business remapping, transaction details, and financial amounts for incurred loss analysis in ClaimCenter.

## High-Level Narrative
The script declares date parameters (unused in visible query) and executes a multi-layered query. The innermost subquery joins core ClaimCenter views (transactionlineitem, transaction, transactionset, claim, policy, check, reserveline, exposure, coverage, contact, user, riskunit, classcode) and numerous type-code lookup views. It derives key attributes: PolSource (Legacy/Guidewire), row numbers for reserve lines, claim representatives based on state and subrogation, company codes, formatted dates, TFGASL/GWASL codes based on coverage type and loss cause, accounting date (CreateTime vs ApprovalDate), TFGTran codes via complex case logic covering Reserve, Payment, and Recovery transactions with cost type and DoesNotErodeReserves flags, and signed transaction amounts. The middle query selects these derived columns. The outer query remaps LOBCode (Business Owners Line -> BP7Line, Workers Comp% -> Workers Comp Line), groups by PolSource, remapped LOBCode, and PolicyNumber, and sums TransAmount as IncurredAmount.

## Inputs
- vw_curr_cc_transactionlineitem
- vw_curr_cc_transaction
- vw_curr_cc_transactionset
- vw_curr_cc_claim
- vw_curr_cc_policy
- vw_curr_cc_check
- vw_curr_cc_reserveline
- vw_curr_cc_exposure
- vw_curr_cc_coverage
- vw_curr_cc_contact
- vw_curr_cc_user (u1, u2)
- vw_curr_cc_riskunit
- vw_curr_cc_classcode
- vw_curr_cctl_lobcode
- vw_curr_cctl_policytype
- vw_curr_cctl_transaction
- vw_curr_cctl_losscause
- vw_curr_cctl_transactionstatus
- vw_curr_cctl_costtype
- vw_curr_cctl_costcategory
- vw_curr_cctl_linecategory
- vw_curr_cctl_transactionlifecyclestate
- vw_curr_cctl_recoverycategory
- vw_curr_cctl_underwritingcompanytype
- vw_curr_cctl_coveragesubtype
- vw_curr_cctl_coveragetype
- vw_curr_cctl_checkbatching
- vw_curr_cctl_paymenttype

## Outputs
- Result set: PolSource, LOBCode (remapped), IncurredAmount (SUM TransAmount), PolicyNumber

## Key Transformations
- PolSource derivation: 'Legacy' if PolicyPrefix_Ext NULL else 'Guidewire'
- Row numbering for reserve lines partitioned by ClaimNumber, exposure, transaction type, cost type
- ClaimRep1 assignment: InRepID_ext for state '13' else OhRepID_ext
- ClaimRep2 assignment from SubroRepresentative_Ext via user join
- Company code mapping: LRM, WRM, SON for specific underwriting companies else UNK
- Date formatting to YYYYMMDD char(8) for PolOrgEffDate, PolEffDate, PolExpDate, AcctDate
- TFGASL/GWASL mapping based on coverage typecode and loss cause typecode
- AcctDate logic: tl.CreateTime if >= tset.ApprovalDate else tset.ApprovalDate
- TFGTran code derivation: 431/432 for reserves, 321/331/322/332 for payments, 321/322/341/342/351/353 for recoveries based on cost type and recovery category
- TransAmount sign logic: Payment with DoesNotErodeReserves=0 -> negative; Recovery -> negative; else positive
- Amount formatting to fixed-width signed numeric strings (12 chars)
- LOBCode remapping: 'Business Owners Line' -> 'BP7Line', 'Workers%' -> 'Workers Comp Line'
- Aggregation: SUM(TransAmount) grouped by PolSource, remapped LOBCode, PolicyNumber

## Key Dependencies
- vw_curr_cc_transactionlineitem
- vw_curr_cc_transaction
- vw_curr_cc_transactionset
- vw_curr_cc_claim
- vw_curr_cc_policy
- vw_curr_cc_check
- vw_curr_cc_reserveline
- vw_curr_cc_exposure
- vw_curr_cc_coverage
- vw_curr_cc_contact
- vw_curr_cc_user
- vw_curr_cc_riskunit
- vw_curr_cc_classcode
- vw_curr_cctl_lobcode
- vw_curr_cctl_policytype
- vw_curr_cctl_transaction
- vw_curr_cctl_losscause
- vw_curr_cctl_transactionstatus
- vw_curr_cctl_costtype
- vw_curr_cctl_costcategory
- vw_curr_cctl_linecategory
- vw_curr_cctl_transactionlifecyclestate
- vw_curr_cctl_recoverycategory
- vw_curr_cctl_underwritingcompanytype
- vw_curr_cctl_coveragesubtype
- vw_curr_cctl_coveragetype
- vw_curr_cctl_checkbatching
- vw_curr_cctl_paymenttype

## Business Rules
- Line of Business remapping: Business Owners Line becomes BP7Line; Workers Comp lines become Workers Comp Line.
- Policy source classification: Guidewire if PolicyPrefix_Ext present, else Legacy.
- Claim representative assignment depends on producer code state (13) and subrogation representative.
- Company code limited to three known mutual insurance companies; all others default to UNK.
- TFGASL/GWASL codes assigned per coverage type (Equipment Breakdown -> 270, Inland Marine -> 010, specific CICS cov codes -> 010) and loss cause (fire, lightning, vandalism, etc. -> 010).
- Transaction type codes (TFGTran) follow a detailed matrix: Reserve Indemnity=431, Reserve Non-Indemnity=432; Payment Indemnity with DoesNotErodeReserves=1 -> 321, else 331; Payment Non-Indemnity with DoesNotErodeReserves=1 -> 322, else 332; Recovery Credit Loss Indemnity=321, Non-Indemnity=322; Credit Expense=322; Deductible=321; Salvage Indemnity=341, Non-Indemnity=342; Subrogation Indemnity=351, Non-Indemnity=353.
- Transaction amount sign convention: Payments that erode reserves (DoesNotErodeReserves=0) are negative; Recoveries are negative; all others positive.
- Amounts formatted as 12-character fixed-width strings with leading zeros and explicit sign handling.
