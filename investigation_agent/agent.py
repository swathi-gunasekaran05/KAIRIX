"""
Investigation Agent — orchestrates Neo4j + Qdrant retrieval, multi-system evidence normalization, and pluggable result formatting.

Flow for each question:
  1. Classify intent & identify target systems (COBOL, SSIS, SQL)
  2. Perform cross-system retrieval:
     - Knowledge Graph traversal (Neo4j Cypher)
     - Vector code chunks & summary search (Qdrant)
  3. Synthesise conversational answer via LLM
  4. Normalize multi-system evidence into NormalizedInvestigationResult
  5. Process & render selected presentation format (Default, Lineage, Tables, Cross-System, Custom)
  6. Return InvestigationResult with formatted_output and full audit trail
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from graph_layer.neo4j_client import Neo4jClient
from vector_layer.qdrant_client_wrapper import (
    QdrantWrapper,
    COLLECTION_CHUNKS,
    COLLECTION_SUMMARIES,
)
from vector_layer.embedder import Embedder
from knowledge_engineering_agent.services.llm_client import LLMClient

from .models import InvestigationResult, NormalizedInvestigationResult
from .normalizer import EvidenceNormalizer
from .formatters.processor import ResultFormatProcessor
from .prompts import (
    INTENT_CLASSIFICATION_PROMPT,
    CYPHER_GENERATION_PROMPT,
    ANSWER_SYNTHESIS_PROMPT,
    CYPHER_REPAIR_PROMPT,
)


class InvestigationAgent:
    """
    Natural language Q&A and cross-system investigation over the KAIRIX Knowledge Graph + Vector DB.

    Usage:
        agent = InvestigationAgent()
        
        # Default conversational format:
        result = agent.ask("How is premium calculated?")
        print(result.answer)

        # Cross-system structured comparison format:
        result = agent.ask("Check if premium calculation code exists in SQL, SSIS, and COBOL", format_type="cross_system")
        print(result.formatted_output)

        # Custom structured format:
        result = agent.ask("Where is premium calculated?", format_type="custom", custom_fields=["System", "File Name", "Table", "Column", "Logic", "Location"])
        print(result.formatted_output)
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
        self.format_processor = ResultFormatProcessor()

    # ── Public API ─────────────────────────────────────────────────────────────

    def ask(
        self,
        question: str,
        format_type: str = "default",
        custom_fields: Optional[List[str]] = None,
    ) -> InvestigationResult:
        """
        Investigate a question and return evidence-backed findings in the requested format.

        Args:
            question: Free-form question about code, data, or lineage.
            format_type: Presentation format (default, lineage, db_table_column, source_target, business_logic, cross_system, custom).
            custom_fields: Optional list of field names for custom format.

        Returns:
            InvestigationResult with answer, formatted_output, normalized_result, and audit trail.
        """
        trace: List[str] = []
        graph_evidence: List[str] = []
        vector_evidence: List[str] = []
        source_files: set = set()

        # ── Step 1: Classify intent ───────────────────────────────────────────
        intent = self._classify_intent(question)
        trace.append(f"Intent classified as: {intent}")
        if self.debug:
            print(f"[DEBUG] Intent: {intent}", flush=True)

        # ── Step 2: Graph retrieval across systems ────────────────────────────
        if self.debug:
            print("[DEBUG] Running Neo4j graph retrieval...", flush=True)
        cypher, records = self._graph_retrieve(question)
        trace.append(f"Cypher: {cypher}")
        for rec in records:
            graph_evidence.append(json.dumps(rec, default=str))
            for v in rec.values():
                if isinstance(v, str) and any(
                    v.endswith(ext) for ext in (".sql", ".dtsx", ".cbl", ".cpy")
                ):
                    source_files.add(v)
        trace.append(f"Graph returned {len(records)} records")
        if self.debug:
            print(f"[DEBUG] Graph: {len(records)} records (Cypher: {cypher})", flush=True)

        # ── Step 3: Vector retrieval across all systems ───────────────────────
        if self.debug:
            print("[DEBUG] Running Qdrant vector search...", flush=True)
        chunks, summaries = self._vector_retrieve(question)
        for hit in chunks + summaries:
            pay = hit.get("payload", {})
            excerpt = pay.get("text", "")[:500]
            file_ref = pay.get("file_name", "")
            score = hit.get("score", 0.0)
            vector_evidence.append(
                f"[{file_ref} | score={score:.3f}]\n{excerpt}"
            )
            if file_ref:
                source_files.add(file_ref)
        trace.append(f"Vector search returned {len(chunks)} chunks + {len(summaries)} summaries")
        if self.debug:
            print(f"[DEBUG] Vector: {len(chunks)} chunks, {len(summaries)} summaries", flush=True)

        # ── Step 4: LLM synthesis (default conversational answer) ─────────────
        if self.debug:
            print("[DEBUG] Synthesising answer with LLM...", flush=True)
        answer, confidence = self._synthesise(
            question,
            graph_evidence=graph_evidence,
            vector_evidence=vector_evidence,
        )
        trace.append("Answer synthesised by LLM")

        # ── Step 5: Evidence normalization across COBOL, SSIS, SQL ───────────
        normalized_result = self.normalizer.normalize(
            question=question,
            intent=intent,
            graph_records=records,
            vector_chunks=chunks,
            vector_summaries=summaries,
            synthesized_answer=answer,
        )
        trace.append("Evidence normalized across COBOL, SSIS, and SQL systems")

        # ── Step 6: Result Format Processing ──────────────────────────────────
        formatted_output = self.format_processor.format_result(
            normalized=normalized_result,
            default_answer=answer,
            format_type=format_type,
            custom_fields=custom_fields,
        )
        trace.append(f"Rendered format: {format_type}")

        # Update source files from normalized evidence as well
        for ev in normalized_result.evidence:
            if ev.file_name and ev.file_name != "N/A":
                source_files.add(ev.file_name)

        return InvestigationResult(
            question=question,
            answer=answer,
            confidence=confidence,
            intent=intent,
            source_files=sorted(source_files),
            graph_evidence=graph_evidence,
            vector_evidence=vector_evidence,
            trace_path=trace,
            format_type=format_type,
            formatted_output=formatted_output,
            normalized_result=normalized_result,
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
            # Clean up response
            for intent in valid_intents:
                if intent in raw:
                    return intent
            return "combined"
        except Exception:
            return "combined"

    def _graph_retrieve(self, question: str) -> Tuple[str, List[Dict]]:
        """Generate Cypher and execute against Neo4j, with self-repair fallback."""
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

            # Final fallback: broad entity search
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
        self, question: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """Embed question and search both Qdrant collections."""
        query_vec = self.embedder.embed_one(question)
        try:
            chunks = self.qdrant.search(
                COLLECTION_CHUNKS, query_vec, top_k=self.top_k_vectors
            )
        except Exception:
            chunks = []
        try:
            summaries = self.qdrant.search(
                COLLECTION_SUMMARIES, query_vec, top_k=self.top_k_vectors
            )
        except Exception:
            summaries = []
        return chunks, summaries

    def _synthesise(
        self,
        question: str,
        graph_evidence: List[str],
        vector_evidence: List[str],
    ) -> Tuple[str, float]:
        """Synthesise the structured answer using NVIDIA NIM."""
        # Handle out-of-domain / negative questions
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
        vector_str = "\n---\n".join(vector_evidence[:6]) if vector_evidence else "No relevant code snippets found."

        prompt = ANSWER_SYNTHESIS_PROMPT.format(
            question=question,
            graph_evidence=graph_str,
            vector_evidence=vector_str,
        )

        try:
            answer = self.llm.complete(prompt, temperature=0.2).strip()
            answer_lower = answer.lower()

            # Calibrate confidence based on LLM's evidence analysis
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
