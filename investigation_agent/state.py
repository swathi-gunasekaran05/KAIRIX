from typing import Any, Dict, List, Optional, TypedDict


class InvestigationState(TypedDict, total=False):
    """
    Shared state passed between all LangGraph nodes
    in the Investigation Agent.
    """

    # ---------------------------------------------------------
    # 1. USER INPUT
    # ---------------------------------------------------------
    user_query: str

    # ---------------------------------------------------------
    # 2. REQUEST CLASSIFICATION
    # ---------------------------------------------------------
    request_type: str
    # Expected:
    # "nlq"
    # "table"
    # "document"

    intent: str

    classification_confidence: float

    document_type: Optional[str]

    # ---------------------------------------------------------
    # 3. RETRIEVED EVIDENCE
    # ---------------------------------------------------------
    neo4j_results: List[Dict[str, Any]]

    qdrant_results: List[Dict[str, Any]]

    combined_evidence: List[Dict[str, Any]]

    # ---------------------------------------------------------
    # 4. INVESTIGATION RESULT
    # ---------------------------------------------------------
    investigation_result: Optional[Dict[str, Any]]

    # ---------------------------------------------------------
    # 5. VALIDATION
    # ---------------------------------------------------------
    validation_result: Optional[Dict[str, Any]]

    # ---------------------------------------------------------
    # 6. FINAL OUTPUT
    # ---------------------------------------------------------
    final_output: Any

    # ---------------------------------------------------------
    # 7. ERROR HANDLING
    # ---------------------------------------------------------
    errors: List[str]