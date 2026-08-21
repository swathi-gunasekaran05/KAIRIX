from state import InvestigationState


# ============================================================
# REQUEST CLASSIFICATION NODE
# ============================================================

def classify_request(state: InvestigationState) -> dict:
    """
    Classifies the user's request into:

    1. nlq
    2. table
    3. document
    """

    query = state.get("user_query", "").strip()

    if not query:
        return {
            "request_type": "nlq",
            "intent": "Unknown request",
            "classification_confidence": 0.0,
            "errors": ["User query is empty."]
        }

    query_lower = query.lower()

    # ========================================================
    # 1. DOCUMENT REQUEST
    # ========================================================

    document_keywords = [
        "generate report",
        "generate document",
        "create report",
        "create document",
        "lineage report",
        "mapping report",
        "impact analysis report",
        "business rule report",
        "documentation",
        "document format",
    ]

    if any(keyword in query_lower for keyword in document_keywords):

        document_type = detect_document_type(query_lower)

        return {
            "request_type": "document",
            "intent": query,
            "classification_confidence": 0.95,
            "document_type": document_type,
        }

    # ========================================================
    # 2. TABLE REQUEST
    # ========================================================

    table_keywords = [
        "show table",
        "as table",
        "in table",
        "table format",
        "rows and columns",
        "show rows",
        "show columns",
        "mapping table",
        "list mappings",
    ]

    if any(keyword in query_lower for keyword in table_keywords):

        return {
            "request_type": "table",
            "intent": query,
            "classification_confidence": 0.95,
            "document_type": None,
        }

    # ========================================================
    # 3. DEFAULT → NATURAL LANGUAGE QUESTION
    # ========================================================

    return {
        "request_type": "nlq",
        "intent": query,
        "classification_confidence": 0.90,
        "document_type": None,
    }


# ============================================================
# DOCUMENT TYPE DETECTION
# ============================================================

def detect_document_type(query: str) -> str:
    """
    Detect which predefined document template is requested.
    """

    if "lineage" in query:
        return "lineage_report"

    if "mapping" in query:
        return "mapping_report"

    if "impact" in query:
        return "impact_analysis_report"

    if "business rule" in query:
        return "business_rule_report"

    return "generic_investigation_report"