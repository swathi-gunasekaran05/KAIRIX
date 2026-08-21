from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ============================================================
# 1. REQUEST CLASSIFICATION
# ============================================================

RequestType = Literal["nlq", "table", "document"]


class RequestClassification(BaseModel):
    """
    Result produced after understanding the user's request.
    """

    request_type: RequestType
    intent: str
    confidence: float = Field(ge=0.0, le=1.0)

    # Optional document/report type identified from the request.
    document_type: Optional[str] = None


# ============================================================
# 2. SOURCE EVIDENCE
# ============================================================

class EvidenceItem(BaseModel):
    """
    One piece of evidence retrieved from Neo4j or Qdrant.
    """

    source: Literal["neo4j", "qdrant"]

    file_name: Optional[str] = None
    source_type: Optional[str] = None

    program: Optional[str] = None
    section: Optional[str] = None
    paragraph: Optional[str] = None

    table_name: Optional[str] = None
    column_name: Optional[str] = None

    content: str

    relationship: Optional[str] = None

    score: Optional[float] = None

    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# 3. RETRIEVED EVIDENCE
# ============================================================

class RetrievedEvidence(BaseModel):
    """
    Combined evidence returned by our retrieval layer.
    """

    neo4j_results: List[EvidenceItem] = Field(default_factory=list)

    qdrant_results: List[EvidenceItem] = Field(default_factory=list)


# ============================================================
# 4. NLQ OUTPUT
# ============================================================

class NLQOutput(BaseModel):
    """
    Natural-language investigation result.
    """

    answer: str

    business_logic: List[str] = Field(default_factory=list)

    evidence: List[EvidenceItem] = Field(default_factory=list)

    confidence: Literal["high", "medium", "low"]

    gaps: List[str] = Field(default_factory=list)


# ============================================================
# 5. TABLE OUTPUT
# ============================================================

class TableOutput(BaseModel):
    """
    Structured table result.

    Example:
        columns = ["Source File", "Source Field", "Target Column"]
        rows = [
            ["PREMCALC.CBL", "WS-PREMIUM", "Written_Premium"]
        ]
    """

    title: str

    columns: List[str]

    rows: List[List[Any]]

    evidence: List[EvidenceItem] = Field(default_factory=list)


# ============================================================
# 6. DOCUMENT OUTPUT
# ============================================================

class DocumentSection(BaseModel):
    """
    Individual section inside a generated document.
    """

    heading: str

    content: Optional[str] = None

    table: Optional[TableOutput] = None


class DocumentOutput(BaseModel):
    """
    Predefined document/report output.
    """

    document_type: str

    title: str

    sections: List[DocumentSection]

    evidence: List[EvidenceItem] = Field(default_factory=list)

    confidence: Literal["high", "medium", "low"]


# ============================================================
# 7. VALIDATION RESULT
# ============================================================

class ValidationResult(BaseModel):
    """
    Determines whether the generated answer is sufficiently
    supported by retrieved evidence.
    """

    valid: bool

    confidence: Literal["high", "medium", "low"]

    issues: List[str] = Field(default_factory=list)

    missing_evidence: List[str] = Field(default_factory=list)