from typing import Dict, Any


# ============================================================
# PREDEFINED DOCUMENT TEMPLATES
# ============================================================

DOCUMENT_TEMPLATES = {

    # --------------------------------------------------------
    # 1. LINEAGE REPORT
    # --------------------------------------------------------
    "lineage_report": {
        "title": "Data & Business Logic Lineage Report",

        "sections": [
            "Executive Summary",
            "Business Concept",
            "Source Systems",
            "Source Files",
            "Source Entities and Fields",
            "Transformation / Calculation Logic",
            "Dependencies",
            "Relationships",
            "Target Entities and Fields",
            "Evidence",
            "Knowledge Gaps",
            "Confidence"
        ]
    },

    # --------------------------------------------------------
    # 2. MAPPING REPORT
    # --------------------------------------------------------
    "mapping_report": {
        "title": "Source-to-Target Mapping Report",

        "sections": [
            "Executive Summary",
            "Source System",
            "Source File",
            "Source Entity",
            "Source Field",
            "Transformation Rule",
            "Target System",
            "Target Table",
            "Target Column",
            "Evidence",
            "Knowledge Gaps",
            "Confidence"
        ]
    },

    # --------------------------------------------------------
    # 3. BUSINESS RULE REPORT
    # --------------------------------------------------------
    "business_rule_report": {
        "title": "Business Rule Investigation Report",

        "sections": [
            "Executive Summary",
            "Business Concept",
            "Business Rules",
            "Calculation Logic",
            "Conditions",
            "Source Files",
            "Programs / Packages",
            "Dependencies",
            "Evidence",
            "Knowledge Gaps",
            "Confidence"
        ]
    },

    # --------------------------------------------------------
    # 4. IMPACT ANALYSIS
    # --------------------------------------------------------
    "impact_analysis_report": {
        "title": "Impact Analysis Report",

        "sections": [
            "Executive Summary",
            "Investigated Component",
            "Upstream Dependencies",
            "Downstream Dependencies",
            "Affected Files",
            "Affected Programs",
            "Affected Tables",
            "Affected Columns",
            "Business Rules",
            "Relationships",
            "Evidence",
            "Knowledge Gaps",
            "Confidence"
        ]
    },

    # --------------------------------------------------------
    # GENERIC FALLBACK
    # --------------------------------------------------------
    "generic_investigation_report": {
        "title": "Investigation Report",

        "sections": [
            "Executive Summary",
            "Findings",
            "Business Logic",
            "Relationships",
            "Evidence",
            "Knowledge Gaps",
            "Confidence"
        ]
    }
}


# ============================================================
# GET TEMPLATE
# ============================================================

def get_document_template(
    document_type: str
) -> Dict[str, Any]:
    """
    Return the requested predefined document template.

    If the requested document type does not exist,
    return the generic investigation template.
    """

    return DOCUMENT_TEMPLATES.get(
        document_type,
        DOCUMENT_TEMPLATES["generic_investigation_report"]
    )