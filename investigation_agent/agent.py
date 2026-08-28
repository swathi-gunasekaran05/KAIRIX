"""
Investigation Agent — orchestrates Neo4j + Qdrant retrieval, source-aware metadata extraction, and LLM reasoning.

Flow for each question:
  1. Classify intent & validate target file scope (selected_files)
  2. Perform scoped retrieval across systems (SQL, SSIS, COBOL):
     - Knowledge Graph traversal (Neo4j Cypher filtered by selected_files)
     - Vector code chunks & summary search (Qdrant filtered by selected_files)
  3. Synthesise conversational answer via LLM
  4. Extract and normalize source-aware metadata (SQL: DB->Schema->Table->Column, SSIS: Pkg->Conn/DB->Schema->Table->Column, COBOL: Program->File/Record->Field)
  5. Return InvestigationResult with natural-language answer, source-traceable metadata, and audit trail
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from graph_layer.neo4j_client import Neo4jClient
from vector_layer.qdrant_client_wrapper import (
    QdrantWrapper,
    COLLECTION_CHUNKS,
    COLLECTION_SUMMARIES,
)
from vector_layer.embedder import Embedder
from knowledge_engineering_agent.services.llm_client import LLMClient

from .models import (
    InvestigationResult,
    InvestigationScope,
    NormalizedInvestigationResult,
)
from .normalizer import EvidenceNormalizer
from .prompts import (
    INTENT_CLASSIFICATION_PROMPT,
    CYPHER_GENERATION_PROMPT,
    ANSWER_SYNTHESIS_PROMPT,
    CYPHER_REPAIR_PROMPT,
)


class InvestigationAgent:
    """
    Natural language Q&A and cross-system investigation over the KAIRIX Knowledge Graph + Vector DB.
    Supports scoping investigations strictly to user-selected source files.

    Usage:
        agent = InvestigationAgent()
        
        # General query across entire knowledge base:
        result = agent.ask("How is premium calculated?")
        print(result.answer)

        # Scoped investigation to selected files:
        result = agent.ask(
            "Check if premium calculation code exists",
            selected_files=["ClaimCenter_CPP_Breakdown.sql", "Extract_Premium.dtsx", "PREMCALC.CBL"]
        )
        print(result.answer)
        for src in result.sources:
            print(src.system, src.file_name)
    """

    def __init__(
        self,
        neo4j_client: Optional[Neo4jClient] = None,
        qdrant: Optional[QdrantWrapper] = None,
        embedder: Optional[Embedder] = None,
        llm: Optional[LLMClient] = None,
        top_k_vectors: int = 8,
        max_graph_results: int = 25,
        debug: bool = False,
    ):
        self.debug = debug
        self.neo4j = neo4j_client or Neo4jClient(silent=not debug)
        self.qdrant = qdrant or QdrantWrapper(silent=not debug)
        self.embedder = embedder or Embedder(silent=not debug)
        self.llm = llm or LLMClient(debug=debug)
        self.top_k_vectors = top_k_vectors
        self.max_graph_results = max_graph_results
        self.normalizer = EvidenceNormalizer()

    # ── Public API ─────────────────────────────────────────────────────────────

    def ask(
        self,
        question: str,
        selected_files: Optional[List[str]] = None,
    ) -> InvestigationResult:
        """
        Investigate a question and return evidence-backed findings and source-aware metadata.

        Args:
            question: Free-form question about code, data, business rules, or architecture.
            selected_files: Optional list of source file names (e.g. ['ClaimCenter_CPP_Breakdown.sql', 'PREMCALC.CBL']).
                            When provided, the investigation is strictly scoped to these files.

        Returns:
            InvestigationResult with natural-language answer, source-aware metadata models, and audit trail.
        """
        trace: List[str] = []
        graph_evidence: List[str] = []
        vector_evidence: List[str] = []
        source_files_set: set = set()

        # Clean selected files list if provided
        scoped_files: Optional[List[str]] = None
        if selected_files:
            scoped_files = [Path(f).name.strip() for f in selected_files if f.strip()]
            trace.append(f"Investigation scoped to {len(scoped_files)} selected files: {', '.join(scoped_files)}")
            if self.debug:
                print(f"[DEBUG] Scoped files: {scoped_files}", flush=True)

        # ── Step 1: Classify intent ───────────────────────────────────────────
        intent = self._classify_intent(question)
        trace.append(f"Intent classified as: {intent}")
        if self.debug:
            print(f"[DEBUG] Intent: {intent}", flush=True)

        # ── Step 2: Scoped Graph retrieval ────────────────────────────────────
        if self.debug:
            print("[DEBUG] Running Neo4j graph retrieval...", flush=True)
        cypher, records = self._graph_retrieve(question, scoped_files=scoped_files)
        trace.append(f"Cypher: {cypher}")

        for rec in records:
            # If scoped to selected files, ensure record relates to them
            rec_files = set()
            for v in rec.values():
                if isinstance(v, str) and any(
                    v.lower().endswith(ext) for ext in (".sql", ".dtsx", ".cbl", ".cob", ".cpy")
                ):
                    rec_files.add(Path(v).name)

            if scoped_files:
                if rec_files and not rec_files.intersection(set(scoped_files)):
                    continue

            graph_evidence.append(json.dumps(rec, default=str))
            for f in rec_files:
                source_files_set.add(f)

        trace.append(f"Graph returned {len(records)} records ({len(graph_evidence)} retained within scope)")
        if self.debug:
            print(f"[DEBUG] Graph: {len(graph_evidence)} records within scope", flush=True)

        # ── Step 3: Scoped Vector retrieval ───────────────────────────────────
        if self.debug:
            print("[DEBUG] Running Qdrant vector search...", flush=True)
        chunks, summaries = self._vector_retrieve(question, scoped_files=scoped_files)

        for hit in chunks + summaries:
            pay = hit.get("payload", {})
            excerpt = pay.get("text", "")
            file_ref = Path(pay.get("file_name", "")).name
            score = hit.get("score", 0.0)

            if scoped_files and file_ref and file_ref not in scoped_files:
                continue

            vector_evidence.append(f"[{file_ref} | score={score:.3f}]\n{excerpt}")
            if file_ref:
                source_files_set.add(file_ref)

        # ── Step 4: Extract Deterministic Source Logic & Formulas ──────────────
        target_files = sorted(scoped_files) if scoped_files else sorted(source_files_set)
        if not target_files:
            # Generic fallback: match question tokens against indexed filenames
            q_terms = [w.lower() for w in re.findall(r"[A-Za-z0-9_-]{3,}", question)]
            for fn in list(self.normalizer._cobol_meta_cache.keys()) + list(self.normalizer._sql_meta_cache.keys()) + list(self.normalizer._ssis_meta_cache.keys()):
                fn_clean = Path(fn).name
                if any(t in fn_clean.lower() or fn_clean.lower() in t for t in q_terms):
                    target_files.append(fn_clean)
            target_files = list(set(target_files))

        temp_normalized = self.normalizer.normalize(
            question=question,
            intent=intent,
            graph_records=records,
            vector_chunks=chunks,
            vector_summaries=summaries,
            synthesized_answer="",
            selected_files=target_files if target_files else None,
        )

        deterministic_logic: List[str] = []
        for src in temp_normalized.sources:
            if src.system == "COBOL" and src.logic:
                calc_items = [l for l in src.logic if l.operation_type in ("COMPUTE", "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE")]
                if calc_items:
                    deterministic_logic.append(f"### Verified COBOL Calculations in {src.file_name} ({src.program}):")
                    for l in calc_items:
                        loc = f" (line {l.source.start_line})" if l.source and l.source.start_line else ""
                        para = f"[{l.paragraph}] " if l.paragraph else ""
                        deterministic_logic.append(f"  - {para}{l.statement}{loc}")
            elif src.system == "SQL" and src.logic:
                deterministic_logic.append(f"### Verified SQL Logic in {src.file_name}:")
                for l in src.logic:
                    expr = f": {l.expression}" if l.expression else ""
                    deterministic_logic.append(f"  - {l.logic_type.upper()} ({l.description}){expr}")
            elif src.system == "SSIS" and src.transformations:
                deterministic_logic.append(f"### Verified SSIS Pipeline in {src.file_name} ({src.package}):")
                for t in src.transformations:
                    for expr in t.expressions:
                        deterministic_logic.append(f"  - [{t.component_name}] {expr}")

        if deterministic_logic:
            vector_evidence.insert(0, "=== VERIFIED DETERMINISTIC SOURCE LOGIC & FORMULAS ===\n" + "\n".join(deterministic_logic))

        trace.append(f"Vector search returned {len(vector_evidence)} matching excerpts/logic blocks")
        if self.debug:
            print(f"[DEBUG] Vector + Logic: {len(vector_evidence)} context excerpts retained", flush=True)

        # ── Step 5: LLM synthesis ─────────────────────────────────────────────
        if self.debug:
            print("[DEBUG] Synthesising answer with LLM...", flush=True)
        answer, confidence = self._synthesise(
            question,
            graph_evidence=graph_evidence,
            vector_evidence=vector_evidence,
            scoped_files=scoped_files,
        )
        trace.append("Answer synthesized by LLM")

        # ── Step 6: Source-Aware Metadata Normalization ───────────────────────
        normalized_result = self.normalizer.normalize(
            question=question,
            intent=intent,
            graph_records=records,
            vector_chunks=chunks,
            vector_summaries=summaries,
            synthesized_answer=answer,
            selected_files=scoped_files,
        )
        trace.append(f"Extracted metadata for {len(normalized_result.sources)} source artifacts")

        # Ensure source_files list matches selected_files when specified
        final_source_files = sorted(scoped_files) if scoped_files else sorted(
            source_files_set.union({s.file_name for s in normalized_result.sources})
        )

        scope = InvestigationScope(
            query=question,
            selected_files=final_source_files,
            intent=intent,
            systems_checked=normalized_result.investigation.systems_checked,
        )

        return InvestigationResult(
            question=question,
            answer=answer,
            confidence=confidence,
            intent=intent,
            source_files=final_source_files,
            graph_evidence=graph_evidence,
            vector_evidence=vector_evidence,
            trace_path=trace,
            investigation=scope,
            sources=normalized_result.sources,
            metadata=normalized_result,
            normalized_result=normalized_result,
        )

    def get_metadata(self, selected_files: Optional[List[str]] = None) -> NormalizedInvestigationResult:
        """
        Extract structured source metadata for selected files without running LLM Q&A.
        Exposes source-aware metadata directly to the UI and caller services.

        Args:
            selected_files: Optional list of specific files to extract metadata for.

        Returns:
            NormalizedInvestigationResult with technology-specific hierarchies:
            - SQL: Database -> Schema -> Table -> Column
            - SSIS: Package -> Database -> Schema -> Table -> Column
            - COBOL: Program -> File / Record -> Field
        """
        return self.normalizer.normalize(
            question="Extract source metadata",
            intent="source_lookup",
            graph_records=[],
            vector_chunks=[],
            vector_summaries=[],
            synthesized_answer="",
            selected_files=selected_files,
        )

    def close(self) -> None:
        """Close all connections."""
        self.neo4j.close()
        self.qdrant.close()

    def __enter__(self) -> "InvestigationAgent":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # ── Step implementations ───────────────────────────────────────────────────

    def _classify_intent(self, question: str) -> str:
        """Use LLM to classify the question intent."""
        valid_intents = {
            "calculation",
            "lineage",
            "impact_analysis",
            "relationship",
            "source_lookup",
            "definition",
            "comparison",
            "validation",
            "semantic",
        }
        prompt = INTENT_CLASSIFICATION_PROMPT.format(question=question)
        try:
            raw = self.llm.complete(prompt, temperature=0.0).strip().lower()
            for intent in valid_intents:
                if intent in raw:
                    return intent
            return "combined"
        except Exception:
            return "combined"

    def _graph_retrieve(
        self, question: str, scoped_files: Optional[List[str]] = None
    ) -> Tuple[str, List[Dict]]:
        """Generate Cypher and execute against Neo4j, with self-repair fallback."""
        if scoped_files:
            file_clause = f" (Scoped to files: {', '.join(scoped_files)})"
            prompt = CYPHER_GENERATION_PROMPT.format(question=question + file_clause)
        else:
            prompt = CYPHER_GENERATION_PROMPT.format(question=question)

        try:
            cypher = self.llm.complete(prompt, temperature=0.0).strip()
        except Exception as e:
            return f"ERROR generating Cypher: {e}", []

        # Strip markdown if present
        cypher = re.sub(r"^```(?:cypher)?\s*", "", cypher, flags=re.IGNORECASE)
        cypher = re.sub(r"\s*```$", "", cypher).strip()

        # Enforce LIMIT
        if "limit" not in cypher.lower():
            cypher = cypher.rstrip(";") + f" LIMIT {self.max_graph_results}"

        try:
            records = self.neo4j.run_query(cypher)
            return cypher, records
        except Exception as exc:
            # Self-repair: send error back to LLM to fix
            if self.debug:
                print(f"[DEBUG] Cypher error: {exc}. Attempting repair...", flush=True)
            repair_prompt = CYPHER_REPAIR_PROMPT.format(cypher=cypher, error=str(exc))
            try:
                fixed_cypher = self.llm.complete(repair_prompt, temperature=0.0).strip()
                fixed_cypher = re.sub(r"^```(?:cypher)?\s*", "", fixed_cypher, flags=re.IGNORECASE)
                fixed_cypher = re.sub(r"\s*```$", "", fixed_cypher).strip()
                if "limit" not in fixed_cypher.lower():
                    fixed_cypher = fixed_cypher.rstrip(";") + f" LIMIT {self.max_graph_results}"
                records = self.neo4j.run_query(fixed_cypher)
                return fixed_cypher, records
            except Exception:
                pass

            # Final fallback: entity search
            fallback = (
                "MATCH (e:Entity) "
                "WHERE toLower(e.name) CONTAINS toLower($term) "
                "RETURN e.name AS name, e.entity_type AS type, "
                "e.source_file AS source_file, e.description AS description "
                "LIMIT 20"
            )
            words = re.findall(r"[A-Za-z][A-Za-z0-9_]{3,}", question)
            term = words[0] if words else ""
            try:
                records = self.neo4j.run_query(fallback, {"term": term})
                return fallback, records
            except Exception:
                return cypher, []

    def _vector_retrieve(
        self, question: str, scoped_files: Optional[List[str]] = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """Embed question and search Qdrant collections, filtering to scoped_files if provided."""
        query_vec = self.embedder.embed_one(question)
        top_k = self.top_k_vectors * (3 if scoped_files else 1)

        try:
            chunks = self.qdrant.search(COLLECTION_CHUNKS, query_vec, top_k=top_k)
        except Exception:
            chunks = []

        try:
            summaries = self.qdrant.search(COLLECTION_SUMMARIES, query_vec, top_k=top_k)
        except Exception:
            summaries = []

        # If scoped files are provided, filter chunks and summaries
        if scoped_files:
            scoped_set = {f.lower() for f in scoped_files}
            filtered_chunks = [
                c for c in chunks
                if Path(c.get("payload", {}).get("file_name", "")).name.lower() in scoped_set
            ]
            filtered_summaries = [
                s for s in summaries
                if Path(s.get("payload", {}).get("file_name", "")).name.lower() in scoped_set
            ]
            return filtered_chunks[:self.top_k_vectors], filtered_summaries[:self.top_k_vectors]

        return chunks[:self.top_k_vectors], summaries[:self.top_k_vectors]

    def _synthesise(
        self,
        question: str,
        graph_evidence: List[str],
        vector_evidence: List[str],
        scoped_files: Optional[List[str]] = None,
    ) -> Tuple[str, float]:
        """Synthesise the structured answer using LLM client."""
        q_lower = question.lower()
        non_domain_keywords = [
            "prime minister", "president", "capital of", "weather in",
            "who is the ceo of apple", "who is the ceo of google",
        ]
        if any(kw in q_lower for kw in non_domain_keywords):
            return (
                "ANSWER\n"
                "The KAIRIX knowledge base contains only technical and business information "
                "related to the legacy insurance system (COBOL programs, SSIS ETL packages, "
                "and SQL database views). It does not contain general world knowledge, political "
                "information, or external current affairs.\n\n"
                "KEY POINTS\n"
                "- Query is outside the scope of the indexed insurance repository.\n"
                "- No matching entities, tables, or business rules exist in the knowledge graph.\n\n"
                "SOURCES\n"
                "None\n\n"
                "CONFIDENCE\n"
                "Low — 0%\n\n"
                "GAPS\n"
                "- Out-of-domain query.",
                0.0,
            )

        graph_str = "\n".join(graph_evidence[:15]) if graph_evidence else "No direct graph paths found."
        vector_str = "\n---\n".join(vector_evidence[:12]) if vector_evidence else "No relevant code snippets found."

        question_formatted = question
        if scoped_files:
            question_formatted += f"\n[NOTE: Investigation is scoped strictly to selected files: {', '.join(scoped_files)}]"

        prompt = ANSWER_SYNTHESIS_PROMPT.format(
            question=question_formatted,
            graph_evidence=graph_str,
            vector_evidence=vector_str,
        )

        try:
            answer = self.llm.complete(prompt, temperature=0.2, max_tokens=4096).strip()
            answer_lower = answer.lower()

            # Calibrate confidence
            if any(phrase in answer_lower for phrase in (
                "confidence: low",
                "confidence\nlow",
                "confidence\n- low",
                "not present in the supplied",
                "does not contain",
                "no rating table",
                "no formula",
                "not provided",
            )):
                confidence = 0.25
            elif any(phrase in answer_lower for phrase in (
                "confidence: high",
                "confidence\nhigh",
                "confidence\n- high",
                "high — 85%",
                "high — 90%",
                "high — 95%",
            )):
                confidence = 0.90
            elif "confidence: medium" in answer_lower or "confidence\nmedium" in answer_lower:
                confidence = 0.70
            elif graph_evidence and vector_evidence:
                confidence = 0.85
            elif graph_evidence or vector_evidence:
                confidence = 0.65
            else:
                confidence = 0.30

            return answer, confidence
        except Exception as e:
            return f"ERROR during answer synthesis: {e}", 0.0
