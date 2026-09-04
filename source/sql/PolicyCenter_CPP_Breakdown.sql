-- ============================================================================
-- SCRIPT: PolicyCenter_CPP_Breakdown.sql
-- DOMAIN: PolicyCenter / Commercial Package Policy (CPP) Line Breakdown
-- PURPOSE: Extracts Commercial Package Policy line-level transactions,
--          written premium breakdowns across multiple lines (Property, GL,
--          Auto, Crime, Inland Marine, Workers Comp) for Agribusiness.
-- SOURCE TABLES:
--   - PolicyCenter.dbo.pc_policyperiod (pp)
--   - PolicyCenter.dbo.pc_policy (pol)
--   - PolicyCenter.dbo.pc_policyTerm (polt)
--   - PolicyCenter.dbo.pc_policyline (polline)
--   - PolicyCenter.dbo.pc_job (j)
--   - PolicyCenter.dbo.pc_account (act)
--   - PolicyCenter.dbo.pc_producercode (prod)
--   - PolicyCenter.dbo.pc_organization (org)
--   - PolicyCenter.dbo.pctl_job (jt)
--   - PolicyCenter.dbo.pctl_policyperiodstatus (ppst)
--   - PolicyCenter.dbo.pctl_bindoption (bopt)
--   - PolicyCenter.dbo.pctl_uwcompanycode (uwc)
--   - PolicyCenter.dbo.pctl_jobdescription_ext (jdt)
--   - PolicyCenter.dbo.pctl_policyperiodsourcetype (ppstype)
--   - PolicyCenter.dbo.pctl_profitcentertype (profit)
--   - PolicyCenter.dbo.pctl_orgfarmuwterritory (farmterr)
--   - Line Transaction Tables: pcx_cp7transaction, pcx_gl7transaction_gle,
--                              pcx_ca7transaction, pcx_cr7transaction,
--                              pc_imtransaction, pcx_wc7transaction
-- TARGET: Commercial Package Line-Level Premium Extract (Agribusiness)
-- ============================================================================

DECLARE @POLSTARTDATE AS Date;
DECLARE @POLENDDATE AS Date;
DECLARE @CHANGESTARTDATE AS Date;
DECLARE @curmthyr AS int = concat(month(GETUTCDATE()) - 1, year(GETUTCDATE()));

SET @POLSTARTDATE = '8/1/2025';
SET @POLENDDATE = '7/31/2026';
SET @CHANGESTARTDATE = '7/1/2026';

SELECT
    ProfitCenter,
    ProductCode,
    LineOfBusiness,
    PolicyNumber,
    OriginalEffectiveDate,
    PeriodStart,
    PeriodEnd,
    AccountNumber,
    Company,
    PrimaryInsuredName,
    AgentCode,
    AgentName,
    FarmUWTerritory,
    CASE
        WHEN MostRecentModel = 1 THEN TranType
        ELSE NULL
    END AS MostRecentTran,
    CASE
        WHEN TranType IN ('Renewal', 'Submission') THEN Written_Premium
        ELSE NULL
    END AS SubWritten_Premium,
    CASE 
        WHEN TranType IN ('Renewal', 'Submission') THEN WrittenDate
        ELSE NULL
    END AS SubWritten_Date,
    CASE
        WHEN TranType IN ('Cancellation') THEN CancellationDate
        ELSE NULL
    END AS CancelledDate,
    CASE
        WHEN TranType IN ('Cancellation') THEN JobCloseDate
        ELSE NULL
    END AS CancelledEffDate,
    CASE
        WHEN TranType IN ('Cancellation') THEN Written_Premium
        ELSE NULL
    END AS CancelledPremium,
    CASE
        WHEN TranType IN ('Reinstatement') THEN Written_Premium
        ELSE NULL
    END AS ReinstatedPremium,
    CASE 
        WHEN TranType IN ('Reinstatement') THEN WrittenDate
        ELSE NULL
    END AS ReinstatedDate,
    CASE 
        WHEN TranType IN ('Reinstatement') THEN JobCloseDate
        ELSE NULL
    END AS ReinstatedEffDate,
    CASE
        WHEN TranType IN ('PolicyChange') THEN Written_Premium
        ELSE NULL
    END AS ChangePremium,
    CASE 
        WHEN TranType IN ('PolicyChange') THEN EditEffectiveDate
        ELSE NULL
    END AS ChangeDate
FROM (
    SELECT  
        profit.NAME AS ProfitCenter,
        pp.ProductCode,
        CASE
            WHEN pp.PatternCode = 'cp7line'                  THEN 'Commercial Property Line'		
            WHEN pp.PatternCode = 'GeneralLiabilityLine_GLE' THEN 'General Liability Line'
            WHEN pp.PatternCode = 'ca7line'                  THEN 'Commercial Auto Line'
            WHEN pp.PatternCode = 'cr7line'                  THEN 'Crime Line'
            WHEN pp.PatternCode = 'imline'                   THEN 'Inland Marine Line'
            WHEN pp.PatternCode = 'WC7Line'                  THEN 'Workers Comp Line'
            ELSE pp.PatternCode					
        END AS LineOfBusiness,
        pp.PolicyNumber,
        pp.LegacyPolicyNumber,
        pp.AccountNumber,
        CASE 
            WHEN uwc.name = 'Lightning Rod Mutual'   THEN 'LRM'
            WHEN uwc.name = 'Western Reserve Mutual' THEN 'WRM'
            WHEN uwc.name = 'Sonnenberg Mutual'      THEN 'SON'
            ELSE 'UNK'
        END AS Company,
        pp.ID AS PolPerID,
        pp.PeriodID,
        pp.TermNumber,
        (
            SELECT DISTINCT pp2.PrimaryInsuredName 
            FROM [PolicyCenter].[dbo].[pc_policyperiod] pp2 
            WHERE pp.PolicyNumber = pp2.PolicyNumber
              AND pp.PeriodStart  = pp2.PeriodStart
              AND pp2.MostRecentModel = 1
        ) AS PrimaryInsuredName,
        CAST((rtrim(org.Code_Ext)) AS char(6)) AS AgentCode,
        org.Name AS AgentName,
        farmterr.NAME AS FarmUWTerritory,
        CASE 
            WHEN prod.code IS NULL THEN '999' 
            ELSE right(rtrim(prod.code), 3)
        END AS ProducerCode,
        pp.JobNumber,
        j.CloseDate AS JobCloseDate,
        jt.TYPECODE AS TranType,
        ISNULL(bopt.NAME, '') AS BindOpt,
        jdt.name AS JobDesc,
        ppst.TYPECODE AS PolPerStatus,
        pp.MostRecentModel,
        pp.CreateTime,
        pp.EditEffectiveDate,
        pol.IssueDate,
        pol.OriginalEffectiveDate,
        pp.PeriodStart,	 
        pp.PeriodEnd,	 
        pp.CancellationDate,
        pp.WrittenDate,
        CASE
            WHEN pp.ProductCode = 'CommercialPackage' THEN
                CASE
                    WHEN pp.PatternCode = 'cp7line' THEN
                        (SELECT ISNULL(SUM(amount), 0.00) FROM [PolicyCenter].[dbo].[pcx_cp7transaction] tr WHERE tr.BranchID = pp.id)
                    WHEN pp.PatternCode = 'GeneralLiabilityLine_GLE' THEN
                        (SELECT ISNULL(SUM(amount), 0.00) FROM [PolicyCenter].[dbo].[pcx_gl7transaction_gle] tr WHERE tr.BranchID = pp.id)
                    WHEN pp.PatternCode = 'ca7line' THEN
                        (SELECT ISNULL(SUM(amount), 0.00) FROM [PolicyCenter].[dbo].[pcx_ca7transaction] tr WHERE tr.BranchID = pp.id)
                    WHEN pp.PatternCode = 'cr7line' THEN
                        (SELECT ISNULL(SUM(amount), 0.00) FROM [PolicyCenter].[dbo].[pcx_cr7transaction] tr WHERE tr.BranchID = pp.id)
                    WHEN pp.PatternCode = 'imline' THEN
                        (SELECT ISNULL(SUM(amount), 0.00) FROM [PolicyCenter].[dbo].[pc_imtransaction] tr WHERE tr.BranchID = pp.id)
                    WHEN pp.PatternCode = 'WC7Line' THEN
                        (SELECT ISNULL(SUM(amount), 0.00) FROM [PolicyCenter].[dbo].[pcx_wc7transaction] tr WHERE tr.BranchID = pp.id)
                END
            ELSE pp.TransactionCostRPT
        END AS Written_Premium,
        pp.TotalPremiumRPT,
        pp.TotalCostRPT 
    FROM [PolicyCenter].[dbo].[pc_policyperiod] pp
    LEFT JOIN [PolicyCenter].[dbo].[pc_policy] pol (NOLOCK) 
        ON pp.policyid = pol.id
    LEFT JOIN [PolicyCenter].[dbo].[pc_policyTerm] polt (NOLOCK) 
        ON pp.policytermid = polt.id
    LEFT JOIN [PolicyCenter].[dbo].[pc_policyline] polline (NOLOCK) 
        ON polline.branchid = pp.id
       AND COALESCE(polline.EffectiveDate, pp.PeriodStart) <> COALESCE(polline.ExpirationDate, pp.PeriodEnd)
    LEFT JOIN [PolicyCenter].[dbo].[pc_job] j (NOLOCK) 
        ON pp.jobid = j.id
    LEFT JOIN [PolicyCenter].[dbo].[pc_account] act (NOLOCK) 
        ON pol.AccountID = act.id
    LEFT JOIN [PolicyCenter].[dbo].[pc_producercode] prod (NOLOCK) 
        ON pp.ProducerCodeOfRecordID = prod.id 
    LEFT JOIN [PolicyCenter].[dbo].[pc_organization] org (NOLOCK) 
        ON prod.OrganizationID = org.id
    LEFT JOIN [PolicyCenter].[dbo].[pctl_job] jt (NOLOCK) 
        ON j.SubType = jt.id
    LEFT JOIN [PolicyCenter].[dbo].[pctl_policyperiodstatus] ppst (NOLOCK) 
        ON pp.status = ppst.ID
    LEFT JOIN [PolicyCenter].[dbo].[pctl_bindoption] bopt (NOLOCK) 
        ON j.BindOption = bopt.id
    LEFT JOIN [PolicyCenter].[dbo].[pctl_uwcompanycode] uwc (NOLOCK) 
        ON pp.UWCompany = uwc.TYPECODE
    LEFT JOIN [PolicyCenter].[dbo].[pctl_jobdescription_ext] jdt (NOLOCK) 
        ON j.DescriptionTL = jdt.id
    LEFT JOIN [PolicyCenter].[dbo].[pctl_policyperiodsourcetype] ppstype (NOLOCK) 
        ON ppstype.id = pp.PolicyPeriodSource
    LEFT JOIN [PolicyCenter].[dbo].[pctl_profitcentertype] profit (NOLOCK) 
        ON pp.ProfitCenterType = profit.id
    LEFT JOIN [PolicyCenter].[dbo].[pctl_orgfarmuwterritory] farmterr (NOLOCK) 
        ON pp.FarmUWTerritory = farmterr.id
    WHERE pol.IssueDate IS NOT NULL 
      AND pp.Policynumber IS NOT NULL
      AND (ppst.TYPECODE IN ('Bound', 'AuditComplete'))
      AND j.CloseDate < @POLENDDATE

    UNION ALL

    SELECT  
        profit.NAME AS ProfitCenter,
        pp.ProductCode,
        'C.P.P.' AS LineOfBusiness,
        pp.PolicyNumber,
        pp.LegacyPolicyNumber,
        pp.AccountNumber,
        CASE 
            WHEN uwc.name = 'Lightning Rod Mutual'   THEN 'LRM'
            WHEN uwc.name = 'Western Reserve Mutual' THEN 'WRM'
            WHEN uwc.name = 'Sonnenberg Mutual'      THEN 'SON'
            ELSE 'UNK'
        END AS Company,
        pp.ID AS PolPerID,
        pp.PeriodID,
        pp.TermNumber,
        (
            SELECT DISTINCT pp2.PrimaryInsuredName 
            FROM [PolicyCenter].[dbo].[pc_policyperiod] pp2 
            WHERE pp.PolicyNumber = pp2.PolicyNumber
              AND pp.PeriodStart  = pp2.PeriodStart
              AND pp2.MostRecentModel = 1
        ) AS PrimaryInsuredName,
        CAST((rtrim(org.Code_Ext)) AS char(6)) AS AgentCode,
        org.Name AS AgentName,
        farmterr.NAME AS FarmUWTerritory,
        CASE 
            WHEN prod.code IS NULL THEN '999' 
            ELSE right(rtrim(prod.code), 3)
        END AS ProducerCode,
        pp.JobNumber,
        j.CloseDate AS JobCloseDate,
        jt.TYPECODE AS TranType,
        ISNULL(bopt.NAME, '') AS BindOpt,
        jdt.name AS JobDesc,
        ppst.TYPECODE AS PolPerStatus,
        pp.MostRecentModel,
        pp.CreateTime,
        pp.EditEffectiveDate,
        pol.IssueDate,
        pol.OriginalEffectiveDate,
        pp.PeriodStart,	 
        pp.PeriodEnd,	 
        pp.CancellationDate,
        pp.WrittenDate,
        pp.TransactionCostRPT AS Written_Premium,
        pp.TotalPremiumRPT,
        pp.TotalCostRPT 
    FROM [PolicyCenter].[dbo].[pc_policyperiod] pp
    LEFT JOIN [PolicyCenter].[dbo].[pc_policy] pol (NOLOCK) 
        ON pp.policyid = pol.id
    LEFT JOIN [PolicyCenter].[dbo].[pc_policyTerm] polt (NOLOCK) 
        ON pp.policytermid = polt.id
    LEFT JOIN [PolicyCenter].[dbo].[pc_job] j (NOLOCK) 
        ON pp.jobid = j.id
    LEFT JOIN [PolicyCenter].[dbo].[pc_account] act (NOLOCK) 
        ON pol.AccountID = act.id
    LEFT JOIN [PolicyCenter].[dbo].[pc_producercode] prod (NOLOCK) 
        ON pp.ProducerCodeOfRecordID = prod.id 
    LEFT JOIN [PolicyCenter].[dbo].[pc_organization] org (NOLOCK) 
        ON prod.OrganizationID = org.id
    LEFT JOIN [PolicyCenter].[dbo].[pctl_job] jt (NOLOCK) 
        ON j.SubType = jt.id
    LEFT JOIN [PolicyCenter].[dbo].[pctl_policyperiodstatus] ppst (NOLOCK) 
        ON pp.status = ppst.ID
    LEFT JOIN [PolicyCenter].[dbo].[pctl_bindoption] bopt (NOLOCK) 
        ON j.BindOption = bopt.id
    LEFT JOIN [PolicyCenter].[dbo].[pctl_uwcompanycode] uwc (NOLOCK) 
        ON pp.UWCompany = uwc.TYPECODE
    LEFT JOIN [PolicyCenter].[dbo].[pctl_jobdescription_ext] jdt (NOLOCK) 
        ON j.DescriptionTL = jdt.id
    LEFT JOIN [PolicyCenter].[dbo].[pctl_policyperiodsourcetype] ppstype (NOLOCK) 
        ON ppstype.id = pp.PolicyPeriodSource
    LEFT JOIN [PolicyCenter].[dbo].[pctl_profitcentertype] profit (NOLOCK) 
        ON pp.ProfitCenterType = profit.id
    LEFT JOIN [PolicyCenter].[dbo].[pctl_orgfarmuwterritory] farmterr (NOLOCK) 
        ON pp.FarmUWTerritory = farmterr.id
    WHERE j.CloseDate IS NOT NULL 
      AND pol.IssueDate IS NOT NULL 
      AND pp.Policynumber IS NOT NULL
      AND (ppst.TYPECODE IN ('Bound', 'AuditComplete'))
      AND pp.ProductCode = 'CommercialPackage' 
      AND j.CloseDate < @POLENDDATE
) jj
WHERE ((PeriodStart BETWEEN @POLSTARTDATE AND @POLENDDATE) OR (JobCloseDate BETWEEN @POLSTARTDATE AND @POLENDDATE))
  AND ((ProductCode = 'CommercialPackage' AND LineOfBusiness NOT IN ('C.P.P.')))
  AND ProfitCenter = 'Agribusiness'
ORDER BY PolicyNumber;