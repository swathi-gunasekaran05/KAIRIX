"""
Investigation Agent result models and normalized evidence data contracts.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SourceLocation(BaseModel):
    """Line-anchored source code location."""
    file_path: Optional[str] = Field(default=None, description="Relative or absolute file path")
    start_line: int = Field(default=0, description="1-indexed start line number")
    end_line: int = Field(default=0, description="1-indexed end line number")

    def to_display(self) -> str:
        if self.start_line > 0 and self.end_line > 0:
            if self.start_line == self.end_line:
                return f"line {self.start_line}"
            return f"lines {self.start_line}-{self.end_line}"
        elif self.start_line > 0:
            return f"line {self.start_line}"
        return "N/A"


class EvidenceItem(BaseModel):
    """Normalized evidence record from Knowledge Graph, Parsers, or Vector Search."""
    system: str = Field(..., description="Source system: COBOL | SSIS | SQL")
    file_name: str = Field(..., description="Name of the source file")
    database: str = Field(default="N/A", description="Database name if applicable")
    schema_name: str = Field(default="N/A", description="Schema name if applicable")
    table: str = Field(default="N/A", description="Table, dataset, or record structure")
    columns: List[str] = Field(default_factory=list, description="Associated columns or variables")
    logic: str = Field(default="N/A", description="Business logic, transformation, or rule summary")
    source_location: SourceLocation = Field(default_factory=SourceLocation, description="Exact code location")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Evidence confidence score")
    
    # Additional contextual attributes for flexible formatting
    rule_id: Optional[str] = Field(default=None, description="Unique Business Rule ID if found")
    condition: Optional[str] = Field(default=None, description="Trigger condition if applicable")
    transformation: Optional[str] = Field(default=None, description="Mathematical or mapping expression")
    upstream_source: Optional[str] = Field(default=None, description="Upstream data source or caller")
    downstream_target: Optional[str] = Field(default=None, description="Downstream consumer or target")
    data_flow_type: Optional[str] = Field(default=None, description="FEEDS_INTO | DERIVES_FROM | WRITES_TO | READS_FROM")


class SystemInspectionResult(BaseModel):
    """Investigation status and evidence for a specific source system."""
    system: str = Field(..., description="COBOL | SSIS | SQL")
    status: str = Field(..., description="FOUND | NOT_FOUND")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="Evidence items for this system")
    summary: str = Field(default="", description="Summary of findings for this system")


class InvestigationMetadata(BaseModel):
    """Metadata describing the query and systems checked."""
    query: str = Field(..., description="The original user query")
    intent: str = Field(default="combined", description="Investigation intent classification")
    systems_checked: List[str] = Field(
        default_factory=lambda: ["COBOL", "SSIS", "SQL"],
        description="All source systems inspected",
    )


class NormalizedInvestigationResult(BaseModel):
    """Normalized cross-system investigation data model."""
    investigation: InvestigationMetadata = Field(..., description="Query metadata")
    evidence: List[EvidenceItem] = Field(default_factory=list, description="All normalized evidence items")
    systems: Dict[str, SystemInspectionResult] = Field(
        default_factory=dict,
        description="Per-system status and evidence mapping (COBOL, SSIS, SQL)",
    )
    correlations: List[str] = Field(
        default_factory=list,
        description="Cross-system correlation notes and data flows",
    )
    differences: List[str] = Field(
        default_factory=list,
        description="Implementation differences detected across systems",
    )


class InvestigationResult(BaseModel):
    """
    Structured answer from the Investigation Agent.
    Supports both default conversational output and structured presentation formats.
    """

    question: str = Field(..., description="The original user question")
    answer: str = Field(..., description="The synthesised natural-language answer (default 7-section blueprint)")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Overall answer confidence"
    )
    intent: str = Field(
        default="combined",
        description="Classified intent: lineage | semantic | combined",
    )
    source_files: List[str] = Field(
        default_factory=list,
        description="Source files that contributed evidence to this answer",
    )
    graph_evidence: List[str] = Field(
        default_factory=list,
        description="Neo4j Cypher results / entity paths supporting the answer",
    )
    vector_evidence: List[str] = Field(
        default_factory=list,
        description="Relevant source code / summary excerpts from Qdrant",
    )
    trace_path: List[str] = Field(
        default_factory=list,
        description="Step-by-step reasoning trace for auditability",
    )
    
    # Enhanced output format extensions
    format_type: str = Field(
        default="default",
        description="The presentation format used (default, lineage, db_table_column, source_target, business_logic, cross_system, custom)",
    )
    formatted_output: str = Field(
        default="",
        description="The rendered output matching the user's selected format",
    )
    normalized_result: Optional[NormalizedInvestigationResult] = Field(
        default=None,
        description="The underlying normalized multi-system investigation model",
    )
