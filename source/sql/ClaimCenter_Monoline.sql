-- ============================================================================
-- SCRIPT: ClaimCenter_Monoline.sql
-- DOMAIN: ClaimCenter / Loss Accounting & Claims Reporting
-- PURPOSE: Extracts monoline incurred losses, financial recovery details,
--          claim representative assignments, and TFG transaction code mapping.
-- SOURCE VIEWS:
--   - vw_curr_cc_transactionlineitem (tl)
--   - vw_curr_cc_transaction (t)
--   - vw_curr_cc_transactionset (tset)
--   - vw_curr_cc_claim (cl)
--   - vw_curr_cc_policy (po)
--   - vw_curr_cc_check (ck)
--   - vw_curr_cc_reserveline (rl)
--   - vw_curr_cc_exposure (ex)
--   - vw_curr_cc_coverage (cv)
--   - vw_curr_cc_contact (clmcont)
--   - vw_curr_cc_user (u1, u2)
--   - vw_curr_cc_riskunit (ru)
--   - vw_curr_cc_classcode (cls)
--   - Type Views: vw_curr_cctl_lobcode, vw_curr_cctl_policytype,
--                 vw_curr_cctl_transaction, vw_curr_cctl_losscause,
--                 vw_curr_cctl_transactionstatus, vw_curr_cctl_costtype,
--                 vw_curr_cctl_costcategory, vw_curr_cctl_linecategory,
--                 vw_curr_cctl_transactionlifecyclestate,
--                 vw_curr_cctl_recoverycategory,
--                 vw_curr_cctl_underwritingcompanytype,
--                 vw_curr_cctl_coveragesubtype, vw_curr_cctl_coveragetype,
--                 vw_curr_cctl_checkbatching, vw_curr_cctl_paymenttype
-- TARGET: Monoline Incurred Losses Summary by Policy and LOB
-- ============================================================================

DECLARE @PV_STARTDATE datetime = '2026-06-30 00:00:00';
DECLARE @PV_ENDDATE datetime = '2026-08-01 00:00:00';

SELECT DISTINCT 
    PolSource,
    LOBCode,
    SUM(TransAmount) AS IncurredAmount,
    PolicyNumber
FROM (
    SELECT 
        PolSource,
        PolicyPrefix_Ext,
        LOBCode,
        ClaimNumber,
        PolicyType,
        PolicyType2,
        ClaimRep1,
        ClaimRep2,
        ClaimState,
        PolicyState,
        PolicyNumber,
        PolicyDec,
        Producer,
        Company,
        PolOrgEffDate,
        PolEffDate,
        PolExpDate,
        ReportedDate,
        LossDate,
        CauseOfLoss,
        Costtype,
        TranCode,
        RecoveryCat,
        CASE
            WHEN TFGTran = '431' AND CostType = 'Indemnity' AND rownum = 1 THEN '421'
            WHEN TFGTran = '431' AND CostType = 'Indemnity' AND rownum <> 1 THEN '431'
            WHEN TFGTran = '431' AND CostType <> 'Indemnity' AND rownum = 1 THEN '422'
            WHEN TFGTran = '431' AND CostType <> 'Indemnity' AND rownum <> 1 THEN '432'
            ELSE TFGTran
        END AS TFGTran,
        AcctDate_sql,
        AcctDate, 
        RIGHT('000' + CAST(ClmtNumber AS varchar(3)), 3) AS ClmtNumber,
        RIGHT('00000000' + ISNULL(LTRIM(Class), '0'), 8) AS Class,
        CoveragePatternCode,
        CovSubType, 
        CheckNumber,
        IssueDate,
        DoesNotErodeReserves,
        ReinCo,
        ReinsAmt,
        Amount,
        TransAmount
    FROM (
        SELECT 
            CASE
                WHEN po.PolicyPrefix_Ext IS NULL THEN 'Legacy'
                ELSE 'Guidewire'
            END AS PolSource,
            po.PolicyPrefix_Ext,
            CASE 
                WHEN tt.TYPECODE = 'Reserve' THEN
                    ROW_NUMBER() OVER(
                        PARTITION BY cl.ClaimNumber, ex.id, tt.TYPECODE, CST.NAME
                        ORDER BY tl.CreateTime
                    )
                ELSE 0 
            END AS rownum,
            CAST(cl.ClaimNumber AS char(13)) AS ClaimNumber,
            CAST(po.PolicyPrefix_Ext AS char(3)) AS PolicyType,
            lob.TYPECODE AS LOBCode,
            po.PolicyTypePrefix_Ext AS PolicyType2,
            CAST(LEFT(cl.ProducerCode, 2) AS char(2)) AS ClaimState,
            CAST(LEFT(cl.ProducerCode, 2) AS char(2)) AS PolicyState,
            CASE 
                WHEN LEFT(cl.ProducerCode, 2) = '13' THEN LEFT(ISNULL(u1.InRepID_ext, '00000'), 5)
                ELSE LEFT(ISNULL(u1.OhRepID_ext, '00000'), 5)
            END AS ClaimRep1,
            CASE
                WHEN cl.SubroRepresentative_Ext IS NULL THEN '00000'
                ELSE ISNULL(LEFT(u2.SubroRepId_Ext, 5), '00000') 
            END AS ClaimRep2,
            CAST(po.Policynumber AS char(10)) AS PolicyNumber,
            po.PolicyDecNo_Ext AS PolicyDec,
            CASE 
                WHEN uw.name = 'Lightning Rod Mutual Insurance Company'  THEN 'LRM'
                WHEN uw.name = 'Western Reserve Mutual Casualty Company' THEN 'WRM'
                WHEN uw.name = 'Sonnenberg Mutual Insurance Company'     THEN 'SON'
                ELSE 'UNK'
            END AS Company,
            CAST(REPLACE(CONVERT(char(10), po.OrigEffectiveDate, 101), '/', '') AS CHAR(8)) AS PolOrgEffDate,
            CAST(REPLACE(CONVERT(char(10), po.EffectiveDate, 101), '/', '')     AS CHAR(8)) AS PolEffDate,
            CAST(REPLACE(CONVERT(char(10), po.ExpirationDate, 101), '/', '')    AS CHAR(8)) AS PolExpDate,
            cl.ReportedDate,
            cl.Lossdate,
            UPPER(CAST(LEFT(tlc.TYPECODE, 45) AS CHAR(45))) AS CauseOfLoss,
            cv.CicsClaimCov_Ext AS TFGCov,
            CASE
                WHEN ct.typecode IN ('CPEquipBrkCov')                  THEN '270'
                WHEN ct.typecode IN ('CPINCCCov')                      THEN '010'
                WHEN cv.CicsClaimCov_Ext IN ('615','616','617','618')  THEN '010'
                ELSE '021' 
            END AS TFGASL,
            CASE
                WHEN ct.typecode IN ('CPEquipBrkCov')                  THEN '270'
                WHEN ct.typecode IN ('CPINCCCov')                      THEN '010'
                WHEN tlc.TYPECODE IN ('fire','fire-wood_coal-stove','ightning','vandalism',
                                      'explosion','sprinkler','sprinkler_leakage') THEN '010'
                ELSE '021' 
            END AS GWASL,
            tl.CreateTime AS TLICreate,
            ISNULL(tset.ApprovalDate, '01/01/2000') AS ApprovalDate,
            ck.ScheduledSendDate,
            CASE 
                WHEN tl.CreateTime >= ISNULL(tset.ApprovalDate, '01/01/2000') THEN CAST(tl.CreateTime AS date)
                ELSE CAST(tset.approvaldate AS date)
            END AS AcctDate_sql,
            CAST(REPLACE(CONVERT(char(10), 
                CASE 
                    WHEN tl.CreateTime >= ISNULL(tset.ApprovalDate, '01/01/2000') THEN tl.CreateTime 
                    ELSE tset.approvaldate 
                END, 101), '/', '') AS CHAR(8)) AS AcctDate,
            CAST(LEFT(cl.ProducerCode, 9) AS CHAR(9)) AS Producer,
            CAST(ISNULL(ex.CicsClaimantNum_Ext, 0) AS numeric(3)) AS ClmtNumber,
            CAST(cls.Code AS char(8)) AS Class,
            t.DoesNotErodeReserves,
            ex.CicsUnitLocNum_Ext,
            ex.CicsClassCode_Ext,
            cv.CicsClaimCov_Ext AS CovCicsClaimCov,
            ex.CicsClaimCov_Ext AS ExpCicsClaimCov,
            CASE 
                WHEN tt.TYPECODE = 'Reserve' AND cst.NAME = 'Indemnity' THEN '431'
                WHEN tt.TYPECODE = 'Reserve' AND cst.NAME <> 'Indemnity' THEN '432'
                WHEN tt.TYPECODE = 'Payment' AND cst.NAME = 'Indemnity' AND t.DoesNotErodeReserves = 1 THEN '321'
                WHEN tt.TYPECODE = 'Payment' AND cst.NAME = 'Indemnity' AND t.DoesNotErodeReserves <> 1 THEN '331'
                WHEN tt.TYPECODE = 'Payment' AND cst.NAME <> 'Indemnity' AND t.DoesNotErodeReserves = 1 THEN '322'
                WHEN tt.TYPECODE = 'Payment' AND cst.NAME <> 'Indemnity' AND t.DoesNotErodeReserves <> 1 THEN '332'
                WHEN tt.TYPECODE = 'Recovery' AND rv.TypeCode = 'Credit_loss' AND cst.NAME = 'Indemnity' THEN '321'
                WHEN tt.TYPECODE = 'Recovery' AND rv.TYPECODE = 'Credit_loss' AND cst.NAME <> 'Indemnity' THEN '322'
                WHEN tt.TYPECODE = 'Recovery' AND cst.NAME = 'EXPENSE - OTHERS' THEN '322'
                WHEN tt.TYPECODE = 'Recovery' AND rv.TYPECODE = 'credit_exp' THEN '322'
                WHEN tt.TYPECODE = 'Recovery' AND rv.TYPECODE = 'deductible' THEN '321'
                WHEN tt.TYPECODE = 'Recovery' AND rv.TYPECODE = 'salvage' AND cst.NAME = 'Indemnity' THEN '341'
                WHEN tt.TYPECODE = 'Recovery' AND rv.TYPECODE = 'salvage' AND cst.NAME <> 'Indemnity' THEN '342'
                WHEN tt.TYPECODE = 'Recovery' AND rv.TYPECODE = 'subro' AND cst.NAME = 'Indemnity' THEN '351'
                WHEN tt.TYPECODE = 'Recovery' AND rv.TYPECODE = 'subro' AND cst.NAME <> 'Indemnity' THEN '353'
                ELSE 'XXX'
            END AS TFGTran,
            rv.typecode AS RecoveryCat,
            UPPER(CAST(ct.typecode AS char(64))) AS CoveragePatternCode,
            ct.typecode AS CoverageTypeCode,
            UPPER(CAST(st.typecode AS char(50))) AS CovSubType,
            tt.TYPECODE AS TranCode,
            UPPER(CAST(CST.NAME AS char(25))) AS CostType,
            CASE
                WHEN CST.NAME = 'Indemnity' THEN '                                             '
                WHEN ccat.TYPECODE IN ('legalexpense_ext', 'appraisal_ext') THEN UPPER(CAST(ccat.TYPECODE AS char(45)))
                WHEN lc.TYPECODE IN ('deductible', 'formerdeductible') THEN UPPER(CAST(ccat.TYPECODE AS char(45)))
                WHEN lc.TYPECODE IS NOT NULL THEN UPPER(CAST(lc.TYPECODE AS char(45)))
                WHEN lc.TYPECODE IS NULL AND ccat.TYPECODE = 'autoparts' THEN 'OTHER                                        '
                ELSE UPPER(CAST(ccat.TYPECODE AS char(45)))
            END AS ExpCode,
            ISNULL(CAST(ck.CheckNumber AS char(9)), '') AS CheckNumber,
            ISNULL(CAST(REPLACE(CONVERT(char(10), ck.IssueDate, 101), '/', '') AS CHAR(8)), '') AS IssueDate,
            '  ' AS ReinCo,
            '000000000.00' AS ReinsAmt,
            CASE 
                WHEN tt.TYPECODE = 'Payment' THEN
                    CASE
                        WHEN t.DoesNotErodeReserves = 0 THEN ISNULL(tl.TransactionAmount, 0.00) * -1
                        ELSE tl.TransactionAmount
                    END
                WHEN tt.TYPECODE = 'Recovery' THEN ISNULL(tl.TransactionAmount, 0.00) * -1
                ELSE ISNULL(tl.TransactionAmount, 0.00)
            END AS TransAmount,
            CASE 
                WHEN tt.TYPECODE = 'Recovery' THEN
                    CASE
                        WHEN ISNULL(tl.TransactionAmount, 0.00) > 0 THEN 
                            CONCAT('-', RIGHT(CAST((-100000000 + ISNULL(-1 * tl.TransactionAmount, 0.00)) AS numeric(11,2)), 11)) 
                        ELSE 
                            RIGHT(CONCAT('00000000', CAST(ISNULL(-1 * tl.TransactionAmount, 0.00) AS numeric(11,2))), 12) 
                    END  
                ELSE
                    CASE
                        WHEN ISNULL(tl.TransactionAmount, 0.00) < 0 THEN 
                            CONCAT('-', RIGHT(CAST((-100000000 + ISNULL(tl.TransactionAmount, 0.00)) AS numeric(11,2)), 11)) 
                        ELSE 
                            RIGHT(CONCAT('00000000', CAST(ISNULL(tl.TransactionAmount, 0.00) AS numeric(11,2))), 12) 
                    END  
            END AS Amount, 						
            tl.id AS TransLineItemID,
            t.id AS TransactionID,
            cv.PolicySystemId AS CovPolSystemID,
            CASE 
                WHEN UPPER(CAST(ct.typecode AS char(50))) IN ('BP7EmploymentPracticesLiabilityInsurance', 'BP7SupplementalExtendReportingPeriodEPLI') THEN
                    CASE 
                        WHEN cv.Deductible > 99999 THEN '99999     '
                        ELSE CAST(ISNULL(cv.Deductible, '          ') AS char(10))  
                    END
                ELSE '          '
            END AS DedStatAmount,
            CAST(REPLACE(CONVERT(char(10), cl.CloseDate, 101), '/', '') AS CHAR(8)) AS Claim_CloseDate,
            CAST(REPLACE(CONVERT(char(10), cl.ReOpenDate, 101), '/', '') AS CHAR(8)) AS Claim_ReOpenDate
        FROM vw_curr_cc_transactionlineitem tl
        LEFT JOIN vw_curr_cc_transaction t (NOLOCK) 
            ON tl.TransactionID = t.id
        LEFT JOIN vw_curr_cc_transactionset tset (NOLOCK) 
            ON t.TransactionSetID = tset.id
        LEFT JOIN vw_curr_cc_claim cl (NOLOCK) 
            ON t.ClaimID = cl.id
        LEFT JOIN vw_curr_cc_policy po (NOLOCK) 
            ON cl.PolicyID = po.id
        LEFT JOIN vw_curr_cc_check ck (NOLOCK) 
            ON t.CheckID = ck.id
        LEFT JOIN vw_curr_cc_reserveline rl (NOLOCK) 
            ON t.ReserveLineID = rl.id
        LEFT JOIN vw_curr_cc_exposure ex (NOLOCK) 
            ON t.ExposureID = ex.id
        LEFT JOIN vw_curr_cc_coverage cv (NOLOCK) 
            ON ex.CoverageID = cv.id
        LEFT JOIN vw_curr_cc_contact clmcont (NOLOCK) 
            ON ex.ClaimantDenormID = clmcont.id
        LEFT JOIN vw_curr_cc_user u1 (NOLOCK) 
            ON cl.AssignedUserID = u1.id
        LEFT JOIN vw_curr_cc_user u2 (NOLOCK) 
            ON cl.SubroRepresentative_Ext = u2.id
        LEFT JOIN vw_curr_cc_riskunit ru (NOLOCK) 
            ON cv.RiskUnitID = ru.id
        LEFT JOIN vw_curr_cc_classcode cls (NOLOCK) 
            ON ru.ClassCodeID = cls.id
        LEFT JOIN vw_curr_cctl_lobcode lob 
            ON cl.LOBCode = lob.id
        LEFT JOIN vw_curr_cctl_policytype polt (NOLOCK) 
            ON po.PolicyType = polt.id
        LEFT JOIN vw_curr_cctl_transaction tt (NOLOCK) 
            ON t.Subtype = tt.id
        LEFT JOIN vw_curr_cctl_losscause tlc (NOLOCK) 
            ON cl.LossCause = tlc.id
        LEFT JOIN vw_curr_cctl_transactionstatus ts (NOLOCK) 
            ON t.Status = ts.id
        LEFT JOIN vw_curr_cctl_costtype CST (NOLOCK) 
            ON t.CostType = CST.ID
        LEFT JOIN vw_curr_cctl_costcategory ccat (NOLOCK) 
            ON t.CostCategory = ccat.ID
        LEFT JOIN vw_curr_cctl_linecategory lc (NOLOCK) 
            ON tl.LineCategory = lc.ID
        LEFT JOIN vw_curr_cctl_transactionlifecyclestate tls (NOLOCK) 
            ON t.LifeCycleState = tls.ID
        LEFT JOIN vw_curr_cctl_recoverycategory rv (NOLOCK) 
            ON t.RecoveryCategory = rv.ID
        LEFT JOIN vw_curr_cctl_underwritingcompanytype uw (NOLOCK) 
            ON po.UnderwritingCo = uw.id
        LEFT JOIN vw_curr_cctl_coveragesubtype st (NOLOCK) 
            ON ex.CoverageSubType = st.id
        LEFT JOIN vw_curr_cctl_coveragetype ct (NOLOCK) 
            ON cv.type = ct.id
        LEFT JOIN vw_curr_cctl_checkbatching cb (NOLOCK) 
            ON ck.CheckBatching = cb.ID
        LEFT JOIN vw_curr_cctl_paymenttype pt (NOLOCK) 
            ON t.PaymentType = pt.id
        WHERE tls.name = 'committed'
          AND tset.ApprovalStatus = 1
          AND tl.Retired = 0
    ) x
) a	
WHERE TFGTran IN ('321', '351', '341', '421', '431')
  AND AcctDate_sql > @PV_STARTDATE 
  AND AcctDate_sql < @PV_ENDDATE
  AND PolSource = 'Guidewire'
GROUP BY 
    PolSource,
    LOBCode,
    PolicyNumber
HAVING SUM(TransAmount) <> 0
ORDER BY 
    PolSource DESC;