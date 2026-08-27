"""
Evidence Normalizer & Cross-System Correlator.

Transforms heterogeneous evidence from Neo4j Graph, Qdrant Vectors,
and Canonical Metadata into a standardized NormalizedInvestigationResult.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import (
    EvidenceItem,
    InvestigationMetadata,
    NormalizedInvestigationResult,
    SourceLocation,
    SystemInspectionResult,
)


class EvidenceNormalizer:
    """
    Normalizes multi-source evidence across COBOL, SSIS, and SQL systems.
    """

    def __init__(self, knowledge_dir: Optional[Path] = None):
        self.knowledge_dir = knowledge_dir or (
            Path(__file__).resolve().parents[1] / "output" / "knowledge"
        )
        self._pkg_cache: Dict[str, Dict[str, Any]] = {}
        self._load_knowledge_packages()

    def _load_knowledge_packages(self):
        """Preload available canonical knowledge packages for rich metadata lookup."""
        if not self.knowledge_dir.exists():
            return
        for pkg_path in self.knowledge_dir.glob("*_knowledge_package.json"):
            try:
                with open(pkg_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                file_name = data.get("source", {}).get("file_name", "")
                if file_name:
                    self._pkg_cache[file_name] = data
                    self._pkg_cache[Path(file_name).stem] = data
            except Exception:
                pass

    def normalize(
        self,
        question: str,
        intent: str,
        graph_records: List[Dict[str, Any]],
        vector_chunks: List[Dict[str, Any]],
        vector_summaries: List[Dict[str, Any]],
        synthesized_answer: str,
    ) -> NormalizedInvestigationResult:
        """
        Produce a normalized investigation result across all systems.
        """
        all_evidence: List[EvidenceItem] = []
        seen_keys: Set[Tuple[str, str, str]] = set()

        # 1. Process Vector Code Chunks
        for hit in vector_chunks:
            pay = hit.get("payload", {})
            file_name = pay.get("file_name", "")
            if not file_name:
                continue

            system = self._infer_system(file_name, pay.get("source_type", ""))
            start_line = int(pay.get("line_start", 0))
            end_line = int(pay.get("line_end", 0))
            raw_text = pay.get("text", "")
            score = float(hit.get("score", 1.0))

            dedup_key = (system, file_name, f"{start_line}-{end_line}")
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            item = self._build_evidence_from_chunk(
                system=system,
                file_name=file_name,
                start_line=start_line,
                end_line=end_line,
                raw_text=raw_text,
                score=score,
            )
            all_evidence.append(item)

        # 2. Process Knowledge Graph Records
        for rec in graph_records:
            items_from_graph = self._build_evidence_from_graph_record(rec)
            for item in items_from_graph:
                dedup_key = (item.system, item.file_name, f"{item.table}:{item.logic}")
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    all_evidence.append(item)

        # 3. If a system has zero evidence, try looking up knowledge packages matching key terms
        systems_present = {e.system for e in all_evidence}
        for sys_name in ["SQL", "SSIS", "COBOL"]:
            if sys_name not in systems_present:
                pkg_items = self._search_packages_for_system(question, sys_name)
                for item in pkg_items:
                    dedup_key = (item.system, item.file_name, item.logic)
                    if dedup_key not in seen_keys:
                        seen_keys.add(dedup_key)
                        all_evidence.append(item)

        # 4. Partition by System
        systems_map: Dict[str, SystemInspectionResult] = {}
        for sys_name in ["SQL", "SSIS", "COBOL"]:
            sys_evidence = [e for e in all_evidence if e.system == sys_name]
            if sys_evidence:
                summary = f"Found {len(sys_evidence)} matching components in {sys_name}."
                systems_map[sys_name] = SystemInspectionResult(
                    system=sys_name,
                    status="FOUND",
                    evidence=sys_evidence,
                    summary=summary,
                )
            else:
                systems_map[sys_name] = SystemInspectionResult(
                    system=sys_name,
                    status="NOT_FOUND",
                    evidence=[],
                    summary=f"No matching logic or components found in {sys_name}.",
                )

        # 5. Extract Cross-System Correlations and Differences
        correlations, differences = self._extract_correlations_and_diffs(
            all_evidence, synthesized_answer
        )

        metadata = InvestigationMetadata(
            query=question,
            intent=intent,
            systems_checked=["COBOL", "SSIS", "SQL"],
        )

        return NormalizedInvestigationResult(
            investigation=metadata,
            evidence=all_evidence,
            systems=systems_map,
            correlations=correlations,
            differences=differences,
        )

    def _infer_system(self, file_name: str, source_type: str = "") -> str:
        st = source_type.upper()
        if st in ("COBOL", "MAINFRAME") or any(file_name.lower().endswith(ext) for ext in (".cbl", ".cob", ".cpy")):
            return "COBOL"
        elif st in ("SSIS", "ETL") or file_name.lower().endswith(".dtsx"):
            return "SSIS"
        elif st in ("SQL", "DATABASE") or file_name.lower().endswith(".sql"):
            return "SQL"
        return "SQL"

    def _build_evidence_from_chunk(
        self,
        system: str,
        file_name: str,
        start_line: int,
        end_line: int,
        raw_text: str,
        score: float,
    ) -> EvidenceItem:
        pkg = self._pkg_cache.get(file_name) or self._pkg_cache.get(Path(file_name).stem) or {}
        summary = pkg.get("summary", {})
        profile = pkg.get("knowledge_profile", {})

        # Extract table / dataset
        table_name = "N/A"
        db_name = "N/A"
        schema_name = "N/A"
        columns: List[str] = []

        if system == "SQL":
            db_name = "PolicyCenterDB / Guidewire"
            schema_name = "dbo"
            # Find SQL table references
            matches = re.findall(r"(?:FROM|JOIN)\s+([a-zA-Z0-9_]+)", raw_text, re.IGNORECASE)
            if matches:
                table_name = matches[0]
            # Find columns
            cols = re.findall(r"(?:SELECT|,)\s+([a-zA-Z0-9_]+)", raw_text)
            columns = list(dict.fromkeys(cols))[:6]

        elif system == "SSIS":
            db_name = "StagingDB"
            table_name = "Staging_Extract"
            # Check for DTS tasks
            tbl_match = re.findall(r'TableOrViewName="([^"]+)"', raw_text)
            if tbl_match:
                table_name = tbl_match[0]

        elif system == "COBOL":
            db_name = "Mainframe Flat Files"
            # Look for 01 or FD
            fd_match = re.findall(r"FD\s+([A-Z0-9-]+)", raw_text)
            rec_match = re.findall(r"01\s+([A-Z0-9-]+)", raw_text)
            if fd_match:
                table_name = fd_match[0]
            elif rec_match:
                table_name = rec_match[0]
            # Columns (05 levels)
            cols = re.findall(r"05\s+([A-Z0-9-]+)", raw_text)
            columns = list(dict.fromkeys(cols))[:6]

        # Business Logic extraction from text or package
        logic_summary = self._extract_logic_snippet(raw_text, profile, summary)

        # Check for business rules in package (handles both dict and str items)
        rules = profile.get("business_rules", [])
        rule_id = None
        rule_cond = None
        if rules:
            first_rule = rules[0]
            if isinstance(first_rule, dict):
                rule_id = first_rule.get("rule_id")
                rule_cond = first_rule.get("condition")
            elif isinstance(first_rule, str):
                rule_id = f"RULE-{system}"
                rule_cond = first_rule

        transforms = profile.get("transformations", [])
        transform_expr = None
        if transforms:
            first_trans = transforms[0]
            if isinstance(first_trans, dict):
                transform_expr = first_trans.get("expression") or first_trans.get("description")
            elif isinstance(first_trans, str):
                transform_expr = first_trans

        return EvidenceItem(
            system=system,
            file_name=file_name,
            database=db_name,
            schema_name=schema_name,
            table=table_name,
            columns=columns,
            logic=logic_summary,
            source_location=SourceLocation(start_line=start_line, end_line=end_line),
            confidence=min(max(score, 0.70), 1.0),
            rule_id=rule_id,
            condition=rule_cond,
            transformation=transform_expr,
            data_flow_type="PROCESSES",
        )

    def _extract_logic_snippet(self, raw_text: str, profile: dict, summary: dict) -> str:
        # First check transformations from profile
        transforms = profile.get("transformations", [])
        if transforms:
            first_trans = transforms[0]
            if isinstance(first_trans, dict) and first_trans.get("description"):
                return first_trans.get("description")
            elif isinstance(first_trans, str):
                return first_trans

        # Check rules
        rules = profile.get("business_rules", [])
        if rules:
            first_rule = rules[0]
            if isinstance(first_rule, dict) and first_rule.get("description"):
                return first_rule.get("description")
            elif isinstance(first_rule, str):
                return first_rule

        # Extract COMPUTE or CASE statement from raw text
        compute_match = re.search(r"COMPUTE\s+([^\.]+)\.", raw_text, re.IGNORECASE)
        if compute_match:
            return f"COMPUTE {compute_match.group(1).strip()}"

        case_match = re.search(r"CASE\s+(?:WHEN[^\n]+)+END", raw_text, re.IGNORECASE)
        if case_match:
            return case_match.group(0).strip()[:100]

        if summary.get("purpose"):
            return summary.get("purpose")[:120]

        first_clean_line = " ".join([l.strip() for l in raw_text.splitlines() if l.strip() and not l.strip().startswith("*")][:2])
        return first_clean_line[:120] if first_clean_line else "Business calculation / validation logic"

    def _build_evidence_from_graph_record(self, record: Dict[str, Any]) -> List[EvidenceItem]:
        items = []
        file_name = record.get("source_file") or record.get("file_name") or record.get("a.file_name") or ""
        if not file_name:
            for v in record.values():
                if isinstance(v, str) and any(v.endswith(ext) for ext in (".cbl", ".sql", ".dtsx", ".cpy")):
                    file_name = v
                    break

        if not file_name:
            return items

        system = self._infer_system(file_name)
        entity_name = record.get("entity_name") or record.get("p.name") or record.get("e.name") or "N/A"
        logic = record.get("expression") or record.get("rule_desc") or record.get("logic") or record.get("t.expression") or "Graph relationship mapping"
        rel_type = record.get("relationship_type") or record.get("type(r)") or "RELATES_TO"

        item = EvidenceItem(
            system=system,
            file_name=file_name,
            table=entity_name if entity_name != "N/A" else "N/A",
            logic=str(logic),
            data_flow_type=str(rel_type),
            source_location=SourceLocation(start_line=1, end_line=50),
            confidence=0.90,
        )
        items.append(item)
        return items

    def _search_packages_for_system(self, query: str, target_system: str) -> List[EvidenceItem]:
        items = []
        query_words = set(re.findall(r"\w+", query.lower()))

        for file_name, pkg in self._pkg_cache.items():
            if not file_name.endswith((".cbl", ".sql", ".dtsx")):
                continue
            sys_name = self._infer_system(file_name)
            if sys_name != target_system:
                continue

            summary = pkg.get("summary", {})
            profile = pkg.get("knowledge_profile", {})
            pkg_text = (summary.get("purpose", "") + " " + json.dumps(profile)).lower()

            # Check overlap
            if any(w in pkg_text for w in query_words if len(w) > 3):
                items.append(
                    EvidenceItem(
                        system=target_system,
                        file_name=file_name,
                        table=summary.get("business_domain", "Core Engine"),
                        logic=summary.get("purpose", "Component performs data processing")[:140],
                        source_location=SourceLocation(start_line=1, end_line=pkg.get("source", {}).get("total_lines", 100)),
                        confidence=0.85,
                    )
                )
                if len(items) >= 2:
                    break
        return items

    def _extract_correlations_and_diffs(
        self, evidence: List[EvidenceItem], answer: str
    ) -> Tuple[List[str], List[str]]:
        correlations = []
        differences = []

        has_sql = any(e.system == "SQL" for e in evidence)
        has_ssis = any(e.system == "SSIS" for e in evidence)
        has_cobol = any(e.system == "COBOL" for e in evidence)

        if has_sql and has_ssis and has_cobol:
            correlations.append(
                "PolicyCenter SQL extracts source transactions → SSIS (Extract_Premium.dtsx) stages & validates → COBOL (PREMCALC.CBL & EARNPREM.CBL) calculates written/earned premium."
            )
            differences.append(
                "SQL performs database-level row aggregation; SSIS enforces ETL data type validation & staging lookups; COBOL executes pro-rata daily arithmetic with rounding and capping rules."
            )
        elif has_sql and has_cobol:
            correlations.append(
                "SQL views define the relational schema structure which feeds mainframe sequential file layouts in COBOL."
            )
        elif has_ssis and has_cobol:
            correlations.append(
                "SSIS packages stage and format sequential data records consumed by COBOL batch processing tasks."
            )

        # Parse bullet points from DATA FLOW or KEY POINTS if present in answer
        data_flow_match = re.search(r"DATA FLOW\s*\n([^\n\r]+)", answer, re.IGNORECASE)
        if data_flow_match:
            correlations.append(data_flow_match.group(1).strip())

        return list(dict.fromkeys(correlations)), list(dict.fromkeys(differences))
