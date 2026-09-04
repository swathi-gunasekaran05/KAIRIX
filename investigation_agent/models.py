"""
Investigation Agent source-aware metadata models and normalized contracts.

Preserves technology-specific concepts:
- SQL:   Database -> Schema -> Table -> Column
- SSIS:  Package -> Connection / Database -> Schema -> Table -> Column
- COBOL: Program -> File / Record -> Field
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# ── Line & Source Traceability ──────────────────────────────────────────────────

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


class SourceTrace(BaseModel):
    """Fine-grained traceability information for any extracted entity."""
    system: str = Field(..., description="SQL | SSIS | COBOL")
    file: str = Field(..., description="Source file name")
    file_path: Optional[str] = Field(default=None, description="Path to source file")
    start_line: int = Field(default=0, description="Start line number")
    end_line: int = Field(default=0, description="End line number")
    parser: str = Field(default="N/A", description="Parser used for extraction")


# ── SQL Source Metadata Model (Database -> Schema -> Table -> Column) ─────────

class SQLColumn(BaseModel):
    """SQL Column metadata with source lineage and derivation."""
    name: str = Field(..., description="Column name")
    alias: Optional[str] = Field(default=None, description="Column alias if assigned")
    data_type: str = Field(default="N/A", description="Data type if declared/extracted")
    source_columns: List[str] = Field(default_factory=list, description="Underlying source columns")
    is_derived: bool = Field(default=False, description="True if column is computed / expression")
    expression: Optional[str] = Field(default=None, description="Computation expression if derived")
    source: Optional[SourceTrace] = Field(default=None, description="Line traceability")


class SQLTable(BaseModel):
    """SQL Table or View."""
    name: str = Field(..., description="Table or view name")
    alias: Optional[str] = Field(default=None, description="Table alias in queries")
    columns: List[Union[SQLColumn, str]] = Field(default_factory=list, description="Columns belonging to table")
    joins: List[Dict[str, Any]] = Field(default_factory=list, description="Join definitions")
    filters: List[str] = Field(default_factory=list, description="WHERE / filter conditions")
    subqueries: List[str] = Field(default_factory=list, description="Subqueries involving this table")
    source: Optional[SourceTrace] = Field(default=None, description="Line traceability")


class SQLSchema(BaseModel):
    """SQL Schema (e.g. dbo, public, stg)."""
    name: str = Field(default="N/A", description="Schema name or 'N/A' if undetermined")
    tables: List[SQLTable] = Field(default_factory=list, description="Tables within schema")


class SQLDatabase(BaseModel):
    """SQL Database."""
    name: str = Field(default="N/A", description="Database name or 'N/A' if undetermined")
    schemas: List[SQLSchema] = Field(default_factory=list, description="Schemas within database")


class SQLLogicItem(BaseModel):
    """SQL Business Logic, Calculation, Aggregation, or CASE expression."""
    logic_type: str = Field(..., description="calculation | aggregation | case | function | rule")
    description: str = Field(..., description="Readable explanation or formula")
    expression: Optional[str] = Field(default=None, description="Raw SQL expression / formula")
    referenced_columns: List[str] = Field(default_factory=list, description="Columns used in logic")
    source: Optional[SourceTrace] = Field(default=None, description="Line traceability")


class SQLSourceMetadata(BaseModel):
    """Source-specific metadata for a SQL file."""
    system: Literal["SQL"] = "SQL"
    file_name: str = Field(..., description="File name")
    file_path: Optional[str] = Field(default=None, description="Relative or absolute path")
    parser: str = Field(default="SQLGlot (T-SQL)", description="Parser used")
    databases: List[SQLDatabase] = Field(default_factory=list, description="Databases hierarchy")
    logic: List[SQLLogicItem] = Field(default_factory=list, description="Calculations, CASE, functions")
    views: List[str] = Field(default_factory=list, description="Defined views")
    summary: Optional[str] = Field(default=None, description="Summary of SQL artifact")


# ── SSIS Source Metadata Model (Package -> Connection/DB -> Schema -> Table -> Column) ─

class SSISColumn(BaseModel):
    """SSIS Data Flow Column."""
    name: str = Field(..., description="Column name")
    data_type: str = Field(default="N/A", description="Data type if declared")
    column_type: str = Field(default="source", description="source | destination | derived | lookup")
    expression: Optional[str] = Field(default=None, description="Expression if derived")
    source: Optional[SourceTrace] = Field(default=None, description="Line traceability")


class SSISTable(BaseModel):
    """SSIS Source, Destination, or Lookup Table."""
    name: str = Field(..., description="Table name")
    columns: List[Union[SSISColumn, str]] = Field(default_factory=list, description="Columns in table")
    role: str = Field(default="N/A", description="source | destination | lookup | staging")
    source: Optional[SourceTrace] = Field(default=None, description="Line traceability")


class SSISSchema(BaseModel):
    """SSIS Target/Source Schema."""
    name: str = Field(default="N/A", description="Schema name or 'N/A' if undetermined")
    tables: List[SSISTable] = Field(default_factory=list, description="Tables within schema")


class SSISDatabase(BaseModel):
    """SSIS Database context."""
    name: str = Field(default="N/A", description="Database name or 'N/A' if undetermined")
    server: Optional[str] = Field(default=None, description="Server name if explicitly present")
    schemas: List[SSISSchema] = Field(default_factory=list, description="Schemas within database")


class SSISConnection(BaseModel):
    """SSIS Connection Manager."""
    name: str = Field(..., description="Connection manager name")
    connection_type: str = Field(default="N/A", description="OLEDB | ADO.NET | FlatFile")
    server: str = Field(default="N/A", description="Server name if present")
    database: str = Field(default="N/A", description="Database name if present")


class SSISTransformation(BaseModel):
    """SSIS Transformation, Derived Column, Lookup, or SQL Task."""
    component_name: str = Field(..., description="Task or component name")
    component_type: str = Field(..., description="Component type / creation name")
    description: Optional[str] = Field(default=None, description="Component description")
    expressions: List[str] = Field(default_factory=list, description="Derived expressions")
    sql_commands: List[str] = Field(default_factory=list, description="Embedded SQL queries")
    source: Optional[SourceTrace] = Field(default=None, description="Line traceability")


class SSISSourceMetadata(BaseModel):
    """Source-specific metadata for an SSIS package."""
    system: Literal["SSIS"] = "SSIS"
    file_name: str = Field(..., description="File name")
    file_path: Optional[str] = Field(default=None, description="Relative or absolute path")
    package: str = Field(..., description="Package name")
    parser: str = Field(default="SSIS XML Parser", description="Parser used")
    connections: List[SSISConnection] = Field(default_factory=list, description="Connection managers")
    databases: List[SSISDatabase] = Field(default_factory=list, description="Databases hierarchy")
    transformations: List[SSISTransformation] = Field(default_factory=list, description="Transformations & SQL tasks")
    summary: Optional[str] = Field(default=None, description="Summary of SSIS artifact")


# ── COBOL Source Metadata Model (Program -> File / Record -> Field) ───────────

class COBOLField(BaseModel):
    """COBOL Field definition."""
    name: str = Field(..., description="Field name")
    level: int = Field(default=5, description="COBOL level number (e.g. 1, 5, 10)")
    picture: Optional[str] = Field(default=None, description="PIC clause if defined")
    redefines: Optional[str] = Field(default=None, description="Redefined field if applicable")
    usage: Optional[str] = Field(default=None, description="COMP, COMP-3, DISPLAY, etc.")
    source: Optional[SourceTrace] = Field(default=None, description="Line traceability")


class COBOLRecord(BaseModel):
    """COBOL Record structure (01 level)."""
    name: str = Field(..., description="Record name")
    level: int = Field(default=1, description="Level number")
    fields: List[Union[COBOLField, str]] = Field(default_factory=list, description="Fields in record")
    source: Optional[SourceTrace] = Field(default=None, description="Line traceability")


class COBOLFile(BaseModel):
    """COBOL File declaration (SELECT / FD)."""
    name: str = Field(..., description="File / Record identifier")
    assign_to: Optional[str] = Field(default=None, description="ASSIGN TO target")
    organization: Optional[str] = Field(default=None, description="INDEXED | SEQUENTIAL | RELATIVE")
    access_mode: Optional[str] = Field(default=None, description="SEQUENTIAL | RANDOM | DYNAMIC")
    records: List[COBOLRecord] = Field(default_factory=list, description="Records under this file")
    fields: List[str] = Field(default_factory=list, description="Direct field names under this file")
    source: Optional[SourceTrace] = Field(default=None, description="Line traceability")


class COBOLLogicItem(BaseModel):
    """COBOL Calculation or Procedural Logic."""
    operation_type: str = Field(..., description="COMPUTE | ADD | SUBTRACT | MULTIPLY | DIVIDE | IF | EVALUATE | PERFORM | MOVE")
    statement: str = Field(..., description="Exact statement or calculation")
    target_field: Optional[str] = Field(default=None, description="Target field receiving computation")
    source_fields: List[str] = Field(default_factory=list, description="Source fields participating in computation")
    paragraph: Optional[str] = Field(default=None, description="Enclosing paragraph name")
    source: Optional[SourceTrace] = Field(default=None, description="Line traceability")


class COBOLSourceMetadata(BaseModel):
    """Source-specific metadata for a COBOL program."""
    system: Literal["COBOL"] = "COBOL"
    file_name: str = Field(..., description="File name")
    file_path: Optional[str] = Field(default=None, description="Relative or absolute path")
    program: str = Field(..., description="Program name")
    parser: str = Field(default="Tree-sitter COBOL", description="Parser used")
    files: List[COBOLFile] = Field(default_factory=list, description="COBOL files / records")
    working_storage_records: List[COBOLRecord] = Field(default_factory=list, description="Working-Storage records")
    logic: List[COBOLLogicItem] = Field(default_factory=list, description="Computations and procedural logic")
    copybooks: List[str] = Field(default_factory=list, description="Included copybooks")
    summary: Optional[str] = Field(default=None, description="Summary of COBOL program")


# ── Polymorphic Source Union ──────────────────────────────────────────────────

SourceMetadata = Union[SQLSourceMetadata, SSISSourceMetadata, COBOLSourceMetadata]


# ── Scope & Normalized Backend Response Models ───────────────────────────────

class InvestigationScope(BaseModel):
    """Investigation metadata describing user query and file scoping."""
    query: str = Field(..., description="The user query")
    selected_files: List[str] = Field(
        default_factory=list,
        description="Specific source files selected for this investigation",
    )
    intent: str = Field(default="combined", description="Investigation intent classification")
    systems_checked: List[str] = Field(
        default_factory=lambda: ["COBOL", "SSIS", "SQL"],
        description="Source systems inspected",
    )


class NormalizedInvestigationResult(BaseModel):
    """
    Source-aware normalized backend investigation response.
    Each source preserves its exact technology hierarchy without forcing all into tables.
    """
    investigation: InvestigationScope = Field(..., description="Investigation scope & query metadata")
    sources: List[SourceMetadata] = Field(
        default_factory=list,
        description="Source-specific metadata models for each investigated file",
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
    Contains synthesized natural language answer and source-aware normalized metadata.
    """
    question: str = Field(..., description="The original user question")
    answer: str = Field(..., description="The synthesized natural-language answer")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall answer confidence")
    intent: str = Field(default="combined", description="Classified intent")
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
        description="Relevant source code / summary excerpts from Pinecone",
    )
    trace_path: List[str] = Field(
        default_factory=list,
        description="Step-by-step reasoning trace for auditability",
    )
    investigation: InvestigationScope = Field(
        ...,
        description="Query and file selection scope",
    )
    sources: List[SourceMetadata] = Field(
        default_factory=list,
        description="Normalized source-aware models for UI rendering",
    )
    metadata: Optional[NormalizedInvestigationResult] = Field(
        default=None,
        description="The separate structured source metadata model for UI consumption",
    )
    normalized_result: NormalizedInvestigationResult = Field(
        ...,
        description="The complete underlying normalized investigation structure",
    )
