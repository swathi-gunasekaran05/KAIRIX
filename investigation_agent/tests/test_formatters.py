"""
Unit tests for Investigation Agent formatters, normalizer, and multi-format result rendering.
"""
from __future__ import annotations

import unittest
from investigation_agent.models import (
    EvidenceItem,
    InvestigationMetadata,
    InvestigationResult,
    NormalizedInvestigationResult,
    SourceLocation,
    SystemInspectionResult,
)
from investigation_agent.formatters.processor import ResultFormatProcessor
from investigation_agent.formatters.default_formatter import DefaultFormatter
from investigation_agent.formatters.table_column_formatter import DbTableColumnFormatter
from investigation_agent.formatters.cross_system_formatter import CrossSystemFormatter
from investigation_agent.formatters.lineage_formatter import FileLineageFormatter, SourceToTargetFormatter
from investigation_agent.formatters.business_logic_formatter import BusinessLogicFormatter
from investigation_agent.formatters.custom_formatter import CustomStructuredFormatter
from investigation_agent.normalizer import EvidenceNormalizer


class TestInvestigationFormatters(unittest.TestCase):

    def setUp(self):
        self.processor = ResultFormatProcessor()
        
        # Sample normalized evidence spanning SQL, SSIS, and COBOL
        self.item_sql = EvidenceItem(
            system="SQL",
            file_name="PolicyCenter_Monoline.sql",
            database="PolicyCenterDB",
            schema_name="dbo",
            table="pc_policyperiod",
            columns=["ID", "PolicyNumber", "PeriodStart", "PeriodEnd"],
            logic="Extracts active policy periods and written transactions",
            source_location=SourceLocation(start_line=10, end_line=45),
            confidence=0.95,
            upstream_source="PolicyCenter Database",
            downstream_target="Extract_Premium.dtsx",
            data_flow_type="FEEDS_INTO",
        )
        self.item_ssis = EvidenceItem(
            system="SSIS",
            file_name="Extract_Premium.dtsx",
            database="StagingDB",
            schema_name="staging",
            table="Staging_Premium",
            columns=["PolicyPeriodID", "WrittenPremium", "EarnedPremium"],
            logic="Validates BR-07, aggregates transactions, and stages records",
            source_location=SourceLocation(start_line=100, end_line=180),
            confidence=0.90,
            rule_id="BR-07",
            condition="EarnedPremium <= WrittenPremium",
            transformation="SUM(TransactionAmount) GROUP BY PolicyPeriodID",
            upstream_source="PolicyCenter_Monoline.sql",
            downstream_target="PREMCALC.CBL",
            data_flow_type="FEEDS_INTO",
        )
        self.item_cobol = EvidenceItem(
            system="COBOL",
            file_name="EARNPREM.CBL",
            database="Mainframe",
            schema_name="N/A",
            table="PI-REC",
            columns=["PI-POLICY-NO", "PI-EFFECTIVE-DATE", "PI-EXPIRY-DATE"],
            logic="Pro-rata daily earned premium calculation: EARNED = WRITTEN * DAYS / TERM",
            source_location=SourceLocation(start_line=120, end_line=165),
            confidence=0.95,
            rule_id="RULE-EARN-01",
            condition="EARNED > WRITTEN",
            transformation="ROUND(PRI-WRITTEN-PREMIUM * WS-EARNED-DAYS / WS-TERM-DAYS)",
            upstream_source="PREMCALC.CBL",
            downstream_target="PREMIUM-OUT",
            data_flow_type="WRITES_TO",
        )

        self.normalized = NormalizedInvestigationResult(
            investigation=InvestigationMetadata(
                query="Check if premium calculation exists in SQL, SSIS, and COBOL",
                intent="comparison",
                systems_checked=["COBOL", "SSIS", "SQL"],
            ),
            evidence=[self.item_sql, self.item_ssis, self.item_cobol],
            systems={
                "SQL": SystemInspectionResult(
                    system="SQL",
                    status="FOUND",
                    evidence=[self.item_sql],
                    summary="Found 1 matching component in SQL.",
                ),
                "SSIS": SystemInspectionResult(
                    system="SSIS",
                    status="FOUND",
                    evidence=[self.item_ssis],
                    summary="Found 1 matching component in SSIS.",
                ),
                "COBOL": SystemInspectionResult(
                    system="COBOL",
                    status="FOUND",
                    evidence=[self.item_cobol],
                    summary="Found 1 matching component in COBOL.",
                ),
            },
            correlations=[
                "PolicyCenter SQL extracts source transactions → SSIS stages & validates → COBOL calculates earned premium."
            ],
            differences=[
                "SQL handles row aggregation, SSIS validates schema, COBOL computes pro-rata day math."
            ],
        )

    def test_default_formatter(self):
        default_ans = "ANSWER\nSample answer\n\nKEY POINTS\n- Fact 1\n\nSOURCES\nEARNPREM.CBL\n\nCONFIDENCE\nHigh — 90%"
        res = self.processor.format_result(self.normalized, default_ans, format_type="default")
        self.assertEqual(res, default_ans)

    def test_db_table_column_formatter(self):
        res = self.processor.format_result(self.normalized, "", format_type="db_table_column")
        self.assertIn("DATABASE / TABLE / COLUMN INVESTIGATION", res)
        self.assertIn("pc_policyperiod", res)
        self.assertIn("Staging_Premium", res)
        self.assertIn("PI-REC", res)
        self.assertIn("lines 10-45", res)

    def test_cross_system_formatter(self):
        res = self.processor.format_result(self.normalized, "", format_type="cross_system")
        self.assertIn("CROSS-SYSTEM INVESTIGATION", res)
        self.assertIn("PolicyCenter_Monoline.sql", res)
        self.assertIn("Extract_Premium.dtsx", res)
        self.assertIn("EARNPREM.CBL", res)
        self.assertIn("FOUND", res)
        self.assertIn("RELATIONSHIP / CORRELATION", res)
        self.assertIn("IMPLEMENTATION DIFFERENCES", res)

    def test_lineage_and_source_target_formatters(self):
        res_lineage = self.processor.format_result(self.normalized, "", format_type="lineage")
        self.assertIn("FILE LINEAGE INVESTIGATION", res_lineage)
        self.assertIn("Extract_Premium.dtsx", res_lineage)

        res_st = self.processor.format_result(self.normalized, "", format_type="source_target")
        self.assertIn("SOURCE-TO-TARGET MAPPINGS", res_st)
        self.assertIn("PolicyCenter_Monoline.sql", res_st)

    def test_business_logic_formatter(self):
        res = self.processor.format_result(self.normalized, "", format_type="business_logic")
        self.assertIn("BUSINESS LOGIC & RULES INVESTIGATION", res)
        self.assertIn("BR-07", res)
        self.assertIn("RULE-EARN-01", res)

    def test_custom_formatter(self):
        custom_fields = ["System", "File Name", "Database", "Table", "Column", "Logic", "Source Location"]
        res = self.processor.format_result(
            self.normalized,
            "",
            format_type="custom",
            custom_fields=custom_fields,
        )
        self.assertIn("CUSTOM STRUCTURED INVESTIGATION", res)
        self.assertIn("PolicyCenterDB", res)
        self.assertIn("StagingDB", res)
        self.assertIn("Mainframe", res)

    def test_custom_formatter_na_handling(self):
        custom_fields = ["System", "File Name", "NonExistentColumn", "Table"]
        res = self.processor.format_result(
            self.normalized,
            "",
            format_type="custom",
            custom_fields=custom_fields,
        )
        self.assertIn("NonExistentColumn", res)
        self.assertIn("N/A", res)

    def test_not_found_system_handling(self):
        # Test a case where SSIS is not found
        norm_partial = NormalizedInvestigationResult(
            investigation=InvestigationMetadata(
                query="Find customer validation",
                intent="lookup",
                systems_checked=["COBOL", "SSIS", "SQL"],
            ),
            evidence=[self.item_cobol],
            systems={
                "SQL": SystemInspectionResult(system="SQL", status="NOT_FOUND", evidence=[]),
                "SSIS": SystemInspectionResult(system="SSIS", status="NOT_FOUND", evidence=[]),
                "COBOL": SystemInspectionResult(system="COBOL", status="FOUND", evidence=[self.item_cobol]),
            },
        )
        res = self.processor.format_result(norm_partial, "", format_type="cross_system")
        self.assertIn("NOT FOUND", res)
        self.assertIn("FOUND", res)


if __name__ == "__main__":
    unittest.main()
