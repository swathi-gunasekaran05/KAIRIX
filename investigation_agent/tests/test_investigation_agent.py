"""
Comprehensive Unit tests for Investigation Agent source-aware metadata extraction, file selection, and response models.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from investigation_agent.models import (
    COBOLField,
    COBOLFile,
    COBOLLogicItem,
    COBOLRecord,
    COBOLSourceMetadata,
    InvestigationResult,
    InvestigationScope,
    NormalizedInvestigationResult,
    SQLColumn,
    SQLDatabase,
    SQLLogicItem,
    SQLSchema,
    SQLSourceMetadata,
    SQLTable,
    SSISColumn,
    SSISConnection,
    SSISDatabase,
    SSISSchema,
    SSISSourceMetadata,
    SSISTable,
    SSISTransformation,
    SourceTrace,
)
from investigation_agent.normalizer import EvidenceNormalizer
from investigation_agent.agent import InvestigationAgent


class TestSourceAwareInvestigation(unittest.TestCase):

    def setUp(self):
        self.normalizer = EvidenceNormalizer()

    def test_sql_3part_identifier_extraction(self):
        """Test SQL extraction with 3-part database.schema.table names."""
        db, schema, table = self.normalizer._parse_sql_identifier("PolicyCenter.dbo.pc_policyperiod")
        self.assertEqual(db, "PolicyCenter")
        self.assertEqual(schema, "dbo")
        self.assertEqual(table, "pc_policyperiod")

    def test_sql_2part_identifier_extraction(self):
        """Test SQL extraction with 2-part schema.table names."""
        db, schema, table = self.normalizer._parse_sql_identifier("public.policy")
        self.assertEqual(db, "N/A")
        self.assertEqual(schema, "public")
        self.assertEqual(table, "policy")

    def test_sql_1part_identifier_extraction(self):
        """Test SQL extraction with single table name (no hallucination)."""
        db, schema, table = self.normalizer._parse_sql_identifier("pc_policyperiod")
        self.assertEqual(db, "N/A")
        self.assertEqual(schema, "N/A")
        self.assertEqual(table, "pc_policyperiod")

    def test_sql_source_metadata_model(self):
        """Test SQL Source metadata structure preserves DB -> Schema -> Table -> Column."""
        col = SQLColumn(
            name="written_premium",
            data_type="decimal(18,2)",
            is_derived=True,
            expression="SUM(total_cost)",
            source=SourceTrace(system="SQL", file="PolicyCenter_CPP_Breakdown.sql", start_line=120, end_line=135),
        )
        tbl = SQLTable(name="pc_policyperiod", columns=[col])
        schema = SQLSchema(name="dbo", tables=[tbl])
        db = SQLDatabase(name="PolicyCenter", schemas=[schema])
        logic = SQLLogicItem(
            logic_type="case",
            description="Premium calculation case",
            expression="CASE WHEN type = 'STD' THEN amount END",
            referenced_columns=["type", "amount"],
            source=SourceTrace(system="SQL", file="PolicyCenter_CPP_Breakdown.sql", start_line=150, end_line=160),
        )
        sql_src = SQLSourceMetadata(
            file_name="PolicyCenter_CPP_Breakdown.sql",
            databases=[db],
            logic=[logic],
        )

        self.assertEqual(sql_src.system, "SQL")
        self.assertEqual(sql_src.databases[0].name, "PolicyCenter")
        self.assertEqual(sql_src.databases[0].schemas[0].name, "dbo")
        self.assertEqual(sql_src.databases[0].schemas[0].tables[0].name, "pc_policyperiod")
        self.assertEqual(sql_src.databases[0].schemas[0].tables[0].columns[0].name, "written_premium")
        self.assertEqual(sql_src.logic[0].logic_type, "case")
        self.assertEqual(sql_src.logic[0].source.start_line, 150)

    def test_ssis_source_metadata_model(self):
        """Test SSIS Source metadata structure preserves Package -> Connections -> DB -> Schema -> Table -> Column."""
        col = SSISColumn(name="premium_id", data_type="int", column_type="source")
        tbl = SSISTable(name="premium", columns=[col], role="source")
        schema = SSISSchema(name="public", tables=[tbl])
        db = SSISDatabase(name="N/A", schemas=[schema])
        conn = SSISConnection(name="CM_Guidewire_PG_Source", server="N/A", database="N/A")
        transform = SSISTransformation(
            component_name="DER - Derived Columns",
            component_type="Microsoft.DerivedColumn",
            expressions=["commission_rate * written_premium / 100 -> expected_commission_amount"],
        )

        ssis_src = SSISSourceMetadata(
            file_name="Extract_Premium.dtsx",
            package="Extract_Premium",
            connections=[conn],
            databases=[db],
            transformations=[transform],
        )

        self.assertEqual(ssis_src.system, "SSIS")
        self.assertEqual(ssis_src.package, "Extract_Premium")
        self.assertEqual(ssis_src.databases[0].schemas[0].tables[0].name, "premium")
        self.assertEqual(ssis_src.databases[0].schemas[0].tables[0].columns[0].name, "premium_id")
        self.assertEqual(len(ssis_src.transformations), 1)
        self.assertIn("commission_rate", ssis_src.transformations[0].expressions[0])

    def test_cobol_source_metadata_model(self):
        """Test COBOL Source metadata structure preserves Program -> File / Record -> Field."""
        fld1 = COBOLField(name="PRI-PREMIUM-ID", level=5, picture="9(9)")
        fld2 = COBOLField(name="PRI-WRITTEN-PREMIUM", level=5, picture="9(9)V99")
        rec = COBOLRecord(name="PI-REC", level=1, fields=[fld1, fld2])
        cbl_file = COBOLFile(
            name="PREMIUM-IN",
            records=[rec],
            fields=["PRI-PREMIUM-ID", "PRI-WRITTEN-PREMIUM"],
            source=SourceTrace(system="COBOL", file="PREMCALC.CBL", start_line=50, end_line=50),
        )
        compute_logic = COBOLLogicItem(
            operation_type="COMPUTE",
            statement="COMPUTE PRI-EARNED-PREMIUM = PRI-WRITTEN-PREMIUM * WS-DAYS / 365.",
            target_field="PRI-EARNED-PREMIUM",
            source_fields=["PRI-WRITTEN-PREMIUM", "WS-DAYS"],
            source=SourceTrace(system="COBOL", file="PREMCALC.CBL", start_line=380, end_line=385),
        )

        cobol_src = COBOLSourceMetadata(
            file_name="PREMCALC.CBL",
            program="PREMCALC",
            files=[cbl_file],
            logic=[compute_logic],
        )

        self.assertEqual(cobol_src.system, "COBOL")
        self.assertEqual(cobol_src.program, "PREMCALC")
        self.assertEqual(cobol_src.files[0].name, "PREMIUM-IN")
        self.assertEqual(len(cobol_src.files[0].fields), 2)
        self.assertEqual(cobol_src.files[0].fields[0], "PRI-PREMIUM-ID")
        self.assertEqual(cobol_src.logic[0].operation_type, "COMPUTE")
        self.assertEqual(cobol_src.logic[0].target_field, "PRI-EARNED-PREMIUM")

    def test_strict_file_scoping(self):
        """Test that normalization with selected_files returns ONLY the selected files."""
        selected = ["ClaimCenter_CPP_Breakdown.sql", "Extract_Premium.dtsx", "PREMCALC.CBL"]
        result = self.normalizer.normalize(
            question="Check if premium calculation code exists",
            intent="calculation",
            graph_records=[],
            vector_chunks=[],
            vector_summaries=[],
            synthesized_answer="Sample answer",
            selected_files=selected,
        )

        investigated_files = [s.file_name for s in result.sources]
        for f in selected:
            self.assertIn(f, investigated_files)

        # Ensure no unselected file is present
        for f in investigated_files:
            self.assertIn(f, selected)

        self.assertEqual(result.investigation.selected_files, selected)

    def test_single_file_scoping(self):
        """Test that selecting a single file returns exactly 1 source object."""
        selected = ["EARNPREM.CBL"]
        result = self.normalizer.normalize(
            question="How is daily earned premium computed?",
            intent="calculation",
            graph_records=[],
            vector_chunks=[],
            vector_summaries=[],
            synthesized_answer="Answer",
            selected_files=selected,
        )
        self.assertEqual(len(result.sources), 1)
        self.assertEqual(result.sources[0].system, "COBOL")
        self.assertEqual(result.sources[0].file_name, "EARNPREM.CBL")
        self.assertEqual(result.sources[0].program, "EARNPREM")

    def test_normalized_response_json_serialization(self):
        """Test that NormalizedInvestigationResult serializes to valid JSON matching UI spec."""
        selected = ["ClaimCenter_CPP_Breakdown.sql", "Extract_Premium.dtsx", "PREMCALC.CBL"]
        result = self.normalizer.normalize(
            question="Check if premium calculation code exists",
            intent="calculation",
            graph_records=[],
            vector_chunks=[],
            vector_summaries=[],
            synthesized_answer="Sample answer",
            selected_files=selected,
        )

        data = result.model_dump()
        self.assertIn("investigation", data)
        self.assertIn("sources", data)
        self.assertEqual(data["investigation"]["selected_files"], selected)
        self.assertTrue(any(s["system"] == "SQL" for s in data["sources"]))
        self.assertTrue(any(s["system"] == "SSIS" for s in data["sources"]))
        self.assertTrue(any(s["system"] == "COBOL" for s in data["sources"]))


    # ── Section 31: Formal Test Cases Matrix ──────────────────────────────────

    @patch("investigation_agent.agent.Neo4jClient")
    @patch("investigation_agent.agent.QdrantWrapper")
    @patch("investigation_agent.agent.Embedder")
    @patch("investigation_agent.agent.LLMClient")
    def test_case_01_cobol_only(self, mock_llm_cls, mock_emb_cls, mock_qdrant_cls, mock_neo_cls):
        """1. Question relevant only to COBOL -> Output contains only COBOL section."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "calculation",
            "MATCH (a:Artifact {file_name: 'PREMCALC.CBL'}) RETURN a",
            "ANSWER\nCalculation is implemented in COBOL.\n\n## COBOL\n### Key Points\n- Computes rate.\n### Formula\nCOMPUTE WS-PREM = WS-BASE\n### Sources\n- PREMCALC.CBL\n\nCONFIDENCE\nHigh — 95%",
        ]
        mock_llm_cls.return_value = mock_llm
        mock_neo = MagicMock()
        mock_neo.run_query.return_value = [{"source_file": "PREMCALC.CBL"}]
        mock_neo_cls.return_value = mock_neo
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"payload": {"file_name": "PREMCALC.CBL", "text": "COMPUTE WS-PREM = WS-BASE", "line_start": 1, "line_end": 10}, "score": 0.95}
        ]
        mock_qdrant_cls.return_value = mock_qdrant
        mock_emb = MagicMock()
        mock_emb.embed_one.return_value = [0.1] * 128
        mock_emb_cls.return_value = mock_emb

        agent = InvestigationAgent(neo4j_client=mock_neo, qdrant=mock_qdrant, embedder=mock_emb, llm=mock_llm)
        result = agent.ask("Explain the COBOL rating calculation")
        self.assertIn("## COBOL", result.answer)
        self.assertNotIn("## SSIS", result.answer)
        self.assertNotIn("## SQL", result.answer)
        self.assertNotIn("SOURCE-AWARE METADATA BREAKDOWN", result.answer)

    @patch("investigation_agent.agent.Neo4jClient")
    @patch("investigation_agent.agent.QdrantWrapper")
    @patch("investigation_agent.agent.Embedder")
    @patch("investigation_agent.agent.LLMClient")
    def test_case_02_ssis_only(self, mock_llm_cls, mock_emb_cls, mock_qdrant_cls, mock_neo_cls):
        """2. Question relevant only to SSIS -> Output contains only SSIS section."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "lineage",
            "MATCH (a:Artifact {file_name: 'Extract_Coverage.dtsx'}) RETURN a",
            "ANSWER\nPipeline transfers coverage data.\n\n## SSIS\n### Key Points\n- Stages coverage records into stg.coverage.\n### Formula\nNo independent calculation; processes/transfers data.\n### Sources\n- Extract_Coverage.dtsx\n\nCONFIDENCE\nHigh — 90%",
        ]
        mock_llm_cls.return_value = mock_llm
        mock_neo = MagicMock()
        mock_neo.run_query.return_value = [{"source_file": "Extract_Coverage.dtsx"}]
        mock_neo_cls.return_value = mock_neo
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"payload": {"file_name": "Extract_Coverage.dtsx", "text": "SELECT * FROM public.coverage", "line_start": 1, "line_end": 10}, "score": 0.92}
        ]
        mock_qdrant_cls.return_value = mock_qdrant
        mock_emb = MagicMock()
        mock_emb.embed_one.return_value = [0.1] * 128
        mock_emb_cls.return_value = mock_emb

        agent = InvestigationAgent(neo4j_client=mock_neo, qdrant=mock_qdrant, embedder=mock_emb, llm=mock_llm)
        result = agent.ask("How is coverage data extracted in ETL?")
        self.assertIn("## SSIS", result.answer)
        self.assertNotIn("## COBOL", result.answer)
        self.assertNotIn("## SQL", result.answer)

    @patch("investigation_agent.agent.Neo4jClient")
    @patch("investigation_agent.agent.QdrantWrapper")
    @patch("investigation_agent.agent.Embedder")
    @patch("investigation_agent.agent.LLMClient")
    def test_case_03_sql_only(self, mock_llm_cls, mock_emb_cls, mock_qdrant_cls, mock_neo_cls):
        """3. Question relevant only to SQL -> Output contains only SQL section."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "definition",
            "MATCH (a:Artifact {file_name: 'PolicyCenter_Monoline.sql'}) RETURN a",
            "ANSWER\nSQL view generates monoline policy report.\n\n## SQL\n### Key Points\n- Aggregates monoline policies.\n### Formula\nCOUNT(DISTINCT PolicyNumber)\n### Sources\n- PolicyCenter_Monoline.sql\n\nCONFIDENCE\nHigh — 90%",
        ]
        mock_llm_cls.return_value = mock_llm
        mock_neo = MagicMock()
        mock_neo.run_query.return_value = [{"source_file": "PolicyCenter_Monoline.sql"}]
        mock_neo_cls.return_value = mock_neo
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"payload": {"file_name": "PolicyCenter_Monoline.sql", "text": "SELECT COUNT(DISTINCT PolicyNumber) FROM pc_policy", "line_start": 1, "line_end": 10}, "score": 0.90}
        ]
        mock_qdrant_cls.return_value = mock_qdrant
        mock_emb = MagicMock()
        mock_emb.embed_one.return_value = [0.1] * 128
        mock_emb_cls.return_value = mock_emb

        agent = InvestigationAgent(neo4j_client=mock_neo, qdrant=mock_qdrant, embedder=mock_emb, llm=mock_llm)
        result = agent.ask("What is the monoline policy view logic in SQL?")
        self.assertIn("## SQL", result.answer)
        self.assertNotIn("## COBOL", result.answer)
        self.assertNotIn("## SSIS", result.answer)

    @patch("investigation_agent.agent.Neo4jClient")
    @patch("investigation_agent.agent.QdrantWrapper")
    @patch("investigation_agent.agent.Embedder")
    @patch("investigation_agent.agent.LLMClient")
    def test_case_04_cobol_and_sql(self, mock_llm_cls, mock_emb_cls, mock_qdrant_cls, mock_neo_cls):
        """4. Question where logic is verified in COBOL and SQL -> Both systems explained separately."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "calculation",
            "MATCH (n) RETURN n",
            "ANSWER\nLogic exists in COBOL and SQL.\n\n## COBOL\n### Key Points\n- PREMCALC.CBL calculates premium.\n### Formula\nCOMPUTE WS-PREM = WS-BASE\n### Sources\n- PREMCALC.CBL\n\n## SQL\n### Key Points\n- PolicyCenter_CPP_Breakdown.sql aggregates premium.\n### Sources\n- PolicyCenter_CPP_Breakdown.sql\n\nCONFIDENCE\nHigh — 90%",
        ]
        mock_llm_cls.return_value = mock_llm
        mock_neo = MagicMock()
        mock_neo.run_query.return_value = [{"source_file": "PREMCALC.CBL"}, {"source_file": "PolicyCenter_CPP_Breakdown.sql"}]
        mock_neo_cls.return_value = mock_neo
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"payload": {"file_name": "PREMCALC.CBL", "text": "COMPUTE WS-PREM", "line_start": 1, "line_end": 5}, "score": 0.9},
            {"payload": {"file_name": "PolicyCenter_CPP_Breakdown.sql", "text": "SUM(amount)", "line_start": 1, "line_end": 5}, "score": 0.88},
        ]
        mock_qdrant_cls.return_value = mock_qdrant
        mock_emb = MagicMock()
        mock_emb.embed_one.return_value = [0.1] * 128
        mock_emb_cls.return_value = mock_emb

        agent = InvestigationAgent(neo4j_client=mock_neo, qdrant=mock_qdrant, embedder=mock_emb, llm=mock_llm)
        result = agent.ask("How do COBOL and SQL handle policy breakdown?")
        self.assertIn("## COBOL", result.answer)
        self.assertIn("## SQL", result.answer)
        self.assertNotIn("## SSIS", result.answer)

    @patch("investigation_agent.agent.Neo4jClient")
    @patch("investigation_agent.agent.QdrantWrapper")
    @patch("investigation_agent.agent.Embedder")
    @patch("investigation_agent.agent.LLMClient")
    def test_case_05_cobol_ssis_and_sql(self, mock_llm_cls, mock_emb_cls, mock_qdrant_cls, mock_neo_cls):
        """5. Question where logic is verified across COBOL, SSIS, and SQL -> All three explained."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "calculation",
            "MATCH (n) RETURN n",
            "ANSWER\nVerified across all three systems.\n\n## COBOL\n### Key Points\n- PREMCALC.CBL calculates written premium.\n### Sources\n- PREMCALC.CBL\n\n## SSIS\n### Key Points\n- Extract_Premium.dtsx transfers records.\n### Sources\n- Extract_Premium.dtsx\n\n## SQL\n### Key Points\n- PolicyCenter_CPP_Breakdown.sql aggregates transactions.\n### Sources\n- PolicyCenter_CPP_Breakdown.sql\n\nCONFIDENCE\nHigh — 92%",
        ]
        mock_llm_cls.return_value = mock_llm
        mock_neo = MagicMock()
        mock_neo.run_query.return_value = [{"source_file": "PREMCALC.CBL"}, {"source_file": "Extract_Premium.dtsx"}, {"source_file": "PolicyCenter_CPP_Breakdown.sql"}]
        mock_neo_cls.return_value = mock_neo
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"payload": {"file_name": "PREMCALC.CBL", "text": "COMPUTE WS-PREM", "line_start": 1, "line_end": 5}, "score": 0.9},
            {"payload": {"file_name": "Extract_Premium.dtsx", "text": "SELECT written_premium", "line_start": 1, "line_end": 5}, "score": 0.9},
            {"payload": {"file_name": "PolicyCenter_CPP_Breakdown.sql", "text": "SELECT TransactionAmount", "line_start": 1, "line_end": 5}, "score": 0.9},
        ]
        mock_qdrant_cls.return_value = mock_qdrant
        mock_emb = MagicMock()
        mock_emb.embed_one.return_value = [0.1] * 128
        mock_emb_cls.return_value = mock_emb

        agent = InvestigationAgent(neo4j_client=mock_neo, qdrant=mock_qdrant, embedder=mock_emb, llm=mock_llm)
        result = agent.ask("How is premium handled end-to-end?")
        self.assertIn("## COBOL", result.answer)
        self.assertIn("## SSIS", result.answer)
        self.assertIn("## SQL", result.answer)

    @patch("investigation_agent.agent.Neo4jClient")
    @patch("investigation_agent.agent.QdrantWrapper")
    @patch("investigation_agent.agent.Embedder")
    @patch("investigation_agent.agent.LLMClient")
    def test_case_06_cobol_calculate_vs_ssis_transfer(self, mock_llm_cls, mock_emb_cls, mock_qdrant_cls, mock_neo_cls):
        """6. Question where COBOL calculates and SSIS transfers -> Clearly distinguish calculation from transfer."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "calculation",
            "MATCH (n) RETURN n",
            "ANSWER\nCOBOL calculates while SSIS transfers.\n\n## COBOL\n### Key Points\n- PREMCALC.CBL performs calculation.\n### Formula\nCOMPUTE WS-PREM = WS-HO-BASE + WS-RISK-VALUE\n### Sources\n- PREMCALC.CBL\n\n## SSIS\n### Key Points\n- Extract_Premium.dtsx stages values.\n### Formula\nNo independent calculation; the package processes/transfers values.\n### Sources\n- Extract_Premium.dtsx\n\nCONFIDENCE\nHigh — 92%",
        ]
        mock_llm_cls.return_value = mock_llm
        mock_neo = MagicMock()
        mock_neo.run_query.return_value = [{"source_file": "PREMCALC.CBL"}, {"source_file": "Extract_Premium.dtsx"}]
        mock_neo_cls.return_value = mock_neo
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"payload": {"file_name": "PREMCALC.CBL", "text": "COMPUTE WS-PREM", "line_start": 1, "line_end": 5}, "score": 0.95},
            {"payload": {"file_name": "Extract_Premium.dtsx", "text": "SELECT written_premium", "line_start": 1, "line_end": 5}, "score": 0.92},
        ]
        mock_qdrant_cls.return_value = mock_qdrant
        mock_emb = MagicMock()
        mock_emb.embed_one.return_value = [0.1] * 128
        mock_emb_cls.return_value = mock_emb

        agent = InvestigationAgent(neo4j_client=mock_neo, qdrant=mock_qdrant, embedder=mock_emb, llm=mock_llm)
        result = agent.ask("Does SSIS calculate premium?")
        self.assertIn("No independent calculation", result.answer)
        self.assertIn("processes/transfers values", result.answer)

    @patch("investigation_agent.agent.Neo4jClient")
    @patch("investigation_agent.agent.QdrantWrapper")
    @patch("investigation_agent.agent.Embedder")
    @patch("investigation_agent.agent.LLMClient")
    def test_case_07_similarly_named_fields_different_logic(self, mock_llm_cls, mock_emb_cls, mock_qdrant_cls, mock_neo_cls):
        """7. Question where similarly named fields exist but logic differs -> Do NOT claim logic is identical."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "comparison",
            "MATCH (n) RETURN n",
            "ANSWER\nFields share names but implement distinct logic.\n\n## COBOL\n### Key Points\n- PRI-WRITTEN-PREMIUM is calculated via rating formulas.\n### Sources\n- PREMCALC.CBL\n\n## SQL\n### Key Points\n- written_premium in pc_policyperiod represents aggregated policy total.\n### Sources\n- PolicyCenter_CPP_Breakdown.sql\n\nCONFIDENCE\nHigh — 90%",
        ]
        mock_llm_cls.return_value = mock_llm
        mock_neo = MagicMock()
        mock_neo.run_query.return_value = [{"source_file": "PREMCALC.CBL"}, {"source_file": "PolicyCenter_CPP_Breakdown.sql"}]
        mock_neo_cls.return_value = mock_neo
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"payload": {"file_name": "PREMCALC.CBL", "text": "PRI-WRITTEN-PREMIUM", "line_start": 1, "line_end": 5}, "score": 0.9},
            {"payload": {"file_name": "PolicyCenter_CPP_Breakdown.sql", "text": "written_premium", "line_start": 1, "line_end": 5}, "score": 0.9},
        ]
        mock_qdrant_cls.return_value = mock_qdrant
        mock_emb = MagicMock()
        mock_emb.embed_one.return_value = [0.1] * 128
        mock_emb_cls.return_value = mock_emb

        agent = InvestigationAgent(neo4j_client=mock_neo, qdrant=mock_qdrant, embedder=mock_emb, llm=mock_llm)
        result = agent.ask("Compare written_premium in COBOL vs SQL")
        self.assertIn("distinct logic", result.answer)

    @patch("investigation_agent.agent.Neo4jClient")
    @patch("investigation_agent.agent.QdrantWrapper")
    @patch("investigation_agent.agent.Embedder")
    @patch("investigation_agent.agent.LLMClient")
    def test_case_08_no_relevant_evidence_unverified(self, mock_llm_cls, mock_emb_cls, mock_qdrant_cls, mock_neo_cls):
        """8. Question where no relevant evidence exists -> Explicitly state could not be verified."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "unknown",
            "MATCH (n:NonExistent) RETURN n",
            "ANSWER\nCould not be verified from the available source evidence.\n\nSOURCES\nNone\n\nCONFIDENCE\nLow — 10%\n\n## GAPS\n- No source files implement this rule.",
        ]
        mock_llm_cls.return_value = mock_llm
        mock_neo = MagicMock()
        mock_neo.run_query.return_value = []
        mock_neo_cls.return_value = mock_neo
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = []
        mock_qdrant_cls.return_value = mock_qdrant
        mock_emb = MagicMock()
        mock_emb.embed_one.return_value = [0.1] * 128
        mock_emb_cls.return_value = mock_emb

        agent = InvestigationAgent(neo4j_client=mock_neo, qdrant=mock_qdrant, embedder=mock_emb, llm=mock_llm)
        result = agent.ask("How is cryptocurrency conversion handled in policy rating?")
        self.assertIn("Could not be verified", result.answer)
        self.assertTrue(result.confidence <= 0.3)

    @patch("investigation_agent.agent.Neo4jClient")
    @patch("investigation_agent.agent.QdrantWrapper")
    @patch("investigation_agent.agent.Embedder")
    @patch("investigation_agent.agent.LLMClient")
    def test_case_09_incomplete_source_low_confidence(self, mock_llm_cls, mock_emb_cls, mock_qdrant_cls, mock_neo_cls):
        """9. Question with incomplete source code -> Explain limitation and lower confidence."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "calculation",
            "MATCH (a:Artifact) RETURN a",
            "ANSWER\nPartial calculation found but external rating table is missing.\n\n## COBOL\n### Key Points\n- Logic references missing COPY member.\n### Sources\n- PREMCALC.CBL\n\nCONFIDENCE\nMedium — 50%\n\n## GAPS\n- Referenced rating table is not provided.",
        ]
        mock_llm_cls.return_value = mock_llm
        mock_neo = MagicMock()
        mock_neo.run_query.return_value = [{"source_file": "PREMCALC.CBL"}]
        mock_neo_cls.return_value = mock_neo
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"payload": {"file_name": "PREMCALC.CBL", "text": "COPY RATING-TBL.", "line_start": 1, "line_end": 5}, "score": 0.8}
        ]
        mock_qdrant_cls.return_value = mock_qdrant
        mock_emb = MagicMock()
        mock_emb.embed_one.return_value = [0.1] * 128
        mock_emb_cls.return_value = mock_emb

        agent = InvestigationAgent(neo4j_client=mock_neo, qdrant=mock_qdrant, embedder=mock_emb, llm=mock_llm)
        result = agent.ask("What are the exact rating table values used in PREMCALC?")
        self.assertIn("## GAPS", result.answer)
        self.assertIn("missing", result.answer.lower())

    @patch("investigation_agent.agent.Neo4jClient")
    @patch("investigation_agent.agent.QdrantWrapper")
    @patch("investigation_agent.agent.Embedder")
    @patch("investigation_agent.agent.LLMClient")
    def test_case_10_conflicting_implementations_reported(self, mock_llm_cls, mock_emb_cls, mock_qdrant_cls, mock_neo_cls):
        """10. Question with conflicting implementations -> Report conflict explicitly."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "comparison",
            "MATCH (n) RETURN n",
            "ANSWER\nConflicting reconciliation tolerances detected.\n\n## COBOL\n### Key Points\n- KPICALC.CBL enforces ±0.01 tolerance.\n### Sources\n- KPICALC.CBL\n\n## SSIS\n### Key Points\n- Extract_Premium.dtsx enforces ±1.00 tolerance (BR-08).\n### Sources\n- Extract_Premium.dtsx\n\nCONFIDENCE\nMedium — 75%\n\n## GAPS\n- COBOL and SSIS use different rounding tolerance limits (0.01 vs 1.00).",
        ]
        mock_llm_cls.return_value = mock_llm
        mock_neo = MagicMock()
        mock_neo.run_query.return_value = [{"source_file": "KPICALC.CBL"}, {"source_file": "Extract_Premium.dtsx"}]
        mock_neo_cls.return_value = mock_neo
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"payload": {"file_name": "KPICALC.CBL", "text": "0.01", "line_start": 1, "line_end": 5}, "score": 0.9},
            {"payload": {"file_name": "Extract_Premium.dtsx", "text": "1.00", "line_start": 1, "line_end": 5}, "score": 0.9},
        ]
        mock_qdrant_cls.return_value = mock_qdrant
        mock_emb = MagicMock()
        mock_emb.embed_one.return_value = [0.1] * 128
        mock_emb_cls.return_value = mock_emb

        agent = InvestigationAgent(neo4j_client=mock_neo, qdrant=mock_qdrant, embedder=mock_emb, llm=mock_llm)
        result = agent.ask("What is the premium reconciliation tolerance across systems?")
        self.assertIn("## GAPS", result.answer)
        self.assertIn("different", result.answer.lower())

    def test_case_11_files_command_not_required(self):
        """11. Verify that user does not need to provide :files or specify scope."""
        agent = InvestigationAgent(
            neo4j_client=MagicMock(),
            qdrant=MagicMock(),
            embedder=MagicMock(),
            llm=MagicMock(),
        )
        # ask signature takes only question as required argument
        import inspect
        sig = inspect.signature(agent.ask)
        params = list(sig.parameters.keys())
        self.assertEqual(params[0], "question")
        self.assertEqual(sig.parameters["selected_files"].default, None)

    def test_case_12_no_source_selection_needed(self):
        """12. Verify that system searches all sources automatically without manual system picker."""
        normalizer = EvidenceNormalizer()
        sources = normalizer.normalize(
            question="General query",
            intent="lookup",
            graph_records=[],
            vector_chunks=[],
            vector_summaries=[],
            synthesized_answer="",
            selected_files=None,
        )
        # Without selected_files, systems_checked includes all 3 systems
        self.assertEqual(sources.investigation.systems_checked, ["COBOL", "SSIS", "SQL"])

    @patch("investigation_agent.agent.Neo4jClient")
    @patch("investigation_agent.agent.QdrantWrapper")
    @patch("investigation_agent.agent.Embedder")
    @patch("investigation_agent.agent.LLMClient")
    def test_case_13_metadata_breakdown_not_appended(self, mock_llm_cls, mock_emb_cls, mock_qdrant_cls, mock_neo_cls):
        """13. Verify that SOURCE-AWARE METADATA BREAKDOWN is not appended to conversational answer."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = [
            "calculation",
            "MATCH (a:Artifact) RETURN a",
            "ANSWER\nDirect answer.\n\n## COBOL\n### Key Points\n- Point 1\n### Sources\n- PREMCALC.CBL\n\nCONFIDENCE\nHigh — 90%",
        ]
        mock_llm_cls.return_value = mock_llm
        mock_neo = MagicMock()
        mock_neo.run_query.return_value = [{"source_file": "PREMCALC.CBL"}]
        mock_neo_cls.return_value = mock_neo
        mock_qdrant = MagicMock()
        mock_qdrant.search.return_value = [
            {"payload": {"file_name": "PREMCALC.CBL", "text": "COMPUTE WS-PREM", "line_start": 1, "line_end": 5}, "score": 0.9}
        ]
        mock_qdrant_cls.return_value = mock_qdrant
        mock_emb = MagicMock()
        mock_emb.embed_one.return_value = [0.1] * 128
        mock_emb_cls.return_value = mock_emb

        agent = InvestigationAgent(neo4j_client=mock_neo, qdrant=mock_qdrant, embedder=mock_emb, llm=mock_llm)
        result = agent.ask("How is premium calculated?")
        self.assertNotIn("SOURCE-AWARE METADATA BREAKDOWN", result.answer)
        self.assertNotIn("Program: PREMCALC", result.answer)

    def test_case_14_metadata_available_separately(self):
        """14. Verify that metadata remains available through the separate structured response."""
        agent = InvestigationAgent(
            neo4j_client=MagicMock(),
            qdrant=MagicMock(),
            embedder=MagicMock(),
            llm=MagicMock(),
        )
        meta = agent.get_metadata(selected_files=["PREMCALC.CBL"])
        self.assertIsInstance(meta, NormalizedInvestigationResult)
        self.assertEqual(len(meta.sources), 1)
        self.assertEqual(meta.sources[0].system, "COBOL")
        self.assertEqual(meta.sources[0].program, "PREMCALC")

    def test_case_15_formulas_never_hallucinated(self):
        """15. Verify that formulas are derived from explicit source statements, not made up."""
        normalizer = EvidenceNormalizer()
        meta = normalizer._extract_cobol_source("PREMCALC.CBL", "formula test")
        computes = [l for l in meta.logic if l.operation_type == "COMPUTE"]
        self.assertTrue(len(computes) >= 4)
        for c in computes:
            self.assertIn("COMPUTE", c.statement)
            self.assertTrue(c.source.start_line > 0)

    def test_case_16_identifiers_not_invented_uses_na(self):
        """16. Verify that database/schema information is never invented and defaults to N/A."""
        normalizer = EvidenceNormalizer()
        db, schema, table = normalizer._parse_sql_identifier("only_table_name")
        self.assertEqual(db, "N/A")
        self.assertEqual(schema, "N/A")
        self.assertEqual(table, "only_table_name")

    def test_normalize_all_known_files(self):
        """Test normalizing all known files in output directory without any validation errors."""
        normalizer = EvidenceNormalizer()
        all_files = (
            list(normalizer._sql_meta_cache.keys())
            + list(normalizer._ssis_meta_cache.keys())
            + list(normalizer._cobol_meta_cache.keys())
        )
        for f in all_files:
            if not any(f.endswith(ext) for ext in (".sql", ".dtsx", ".cbl", ".cob", ".cpy", ".CBL")):
                continue
            norm = normalizer.normalize(
                question="Test query",
                intent="definition",
                graph_records=[],
                vector_chunks=[],
                vector_summaries=[],
                synthesized_answer="",
                selected_files=[f],
            )
            self.assertEqual(len(norm.sources), 1)
            self.assertEqual(norm.sources[0].file_name, f)


if __name__ == "__main__":
    unittest.main()
