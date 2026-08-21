from state import InvestigationState
from templates.predefined_documents import get_document_template


def format_output(state: InvestigationState) -> dict:
    """
    Format the validated investigation result according
    to the requested output type.

    Supported:
        1. nlq
        2. table
        3. document
    """

    request_type = state.get("request_type", "nlq")

    investigation = state.get(
        "investigation_result"
    ) or {}

    validation = state.get(
        "validation_result"
    ) or {}

    evidence = state.get(
        "combined_evidence",
        []
    )

    # ========================================================
    # 1. NLQ OUTPUT
    # ========================================================

    if request_type == "nlq":

        return {
            "final_output": {
                "type": "nlq",

                "answer": investigation.get(
                    "answer",
                    "No evidence-backed answer could be generated."
                ),

                "business_logic": investigation.get(
                    "business_logic",
                    []
                ),

                "findings": investigation.get(
                    "findings",
                    []
                ),

                "relationships": investigation.get(
                    "relationships",
                    []
                ),

                "gaps": investigation.get(
                    "gaps",
                    []
                ),

                "confidence": validation.get(
                    "confidence",
                    "low"
                ),

                "validation_issues": validation.get(
                    "issues",
                    []
                )
            }
        }

    # ========================================================
    # 2. TABLE OUTPUT
    # ========================================================

    if request_type == "table":

        columns = [
            "Source",
            "File",
            "Source Type",
            "Program",
            "Location",
            "Relationship",
            "Content",
            "Score"
        ]

        rows = []

        for item in evidence:

            location = (
                item.get("paragraph")
                or item.get("section")
                or item.get("table_name")
                or item.get("column_name")
                or ""
            )

            rows.append([
                item.get("source", ""),
                item.get("file_name", ""),
                item.get("source_type", ""),
                item.get("program", ""),
                location,
                item.get("relationship", ""),
                item.get("content", ""),
                item.get("score", "")
            ])

        return {
            "final_output": {
                "type": "table",
                "title": "Investigation Evidence",
                "columns": columns,
                "rows": rows,
                "confidence": validation.get(
                    "confidence",
                    "low"
                )
            }
        }

    # ========================================================
    # 3. DOCUMENT OUTPUT
    # ========================================================

    if request_type == "document":

        document_type = state.get(
            "document_type",
            "generic_investigation_report"
        )

        template = get_document_template(
            document_type
        )

        sections = []

        for section_name in template["sections"]:

            content = build_document_section(
                section_name=section_name,
                investigation=investigation,
                evidence=evidence,
                validation=validation
            )

            sections.append({
                "heading": section_name,
                "content": content
            })

        return {
            "final_output": {
                "type": "document",

                "document_type": document_type,

                "title": template["title"],

                "sections": sections,

                "confidence": validation.get(
                    "confidence",
                    "low"
                ),

                "validation_issues": validation.get(
                    "issues",
                    []
                )
            }
        }

    # ========================================================
    # UNKNOWN REQUEST TYPE
    # ========================================================

    return {
        "final_output": {
            "type": "error",
            "message": (
                f"Unsupported request type: {request_type}"
            )
        }
    }


# ============================================================
# DOCUMENT SECTION BUILDER
# ============================================================

def build_document_section(
    section_name,
    investigation,
    evidence,
    validation
):
    """
    Populate predefined document sections using
    investigation results and retrieved evidence.

    No unsupported project information is invented.
    """

    section = section_name.lower()

    # --------------------------------------------------------
    # EXECUTIVE SUMMARY
    # --------------------------------------------------------

    if section == "executive summary":

        return investigation.get(
            "answer",
            "No evidence-backed summary available."
        )

    # --------------------------------------------------------
    # BUSINESS CONCEPT
    # --------------------------------------------------------

    if section == "business concept":

        concepts = []

        for item in evidence:

            concept = (
                item.get("metadata", {})
                .get("concept")
            )

            if concept:
                concepts.append(concept)

        concepts = unique_values(concepts)

        return concepts or [
            "No explicit business concept found."
        ]

    # --------------------------------------------------------
    # SOURCE SYSTEM / SOURCE SYSTEMS
    # --------------------------------------------------------

    if section in [
        "source system",
        "source systems"
    ]:

        systems = [
            item.get("source_type")
            for item in evidence
            if item.get("source_type")
        ]

        return unique_values(systems) or [
            "No source system evidence available."
        ]

    # --------------------------------------------------------
    # SOURCE FILE / SOURCE FILES / AFFECTED FILES
    # --------------------------------------------------------

    if section in [
        "source file",
        "source files",
        "affected files"
    ]:

        files = [
            item.get("file_name")
            for item in evidence
            if item.get("file_name")
        ]

        return unique_values(files) or [
            "No source file evidence available."
        ]

    # --------------------------------------------------------
    # BUSINESS LOGIC / CALCULATION
    # --------------------------------------------------------

    if section in [
        "business logic",
        "calculation logic",
        "transformation / calculation logic",
        "transformation rule",
        "business rules"
    ]:

        logic = investigation.get(
            "business_logic",
            []
        )

        return logic or [
            "No explicit business logic found in evidence."
        ]

    # --------------------------------------------------------
    # RELATIONSHIPS
    # --------------------------------------------------------

    if section == "relationships":

        relationships = investigation.get(
            "relationships",
            []
        )

        return relationships or [
            "No relationships found."
        ]

    # --------------------------------------------------------
    # DEPENDENCIES
    # --------------------------------------------------------

    if section in [
        "dependencies",
        "upstream dependencies",
        "downstream dependencies"
    ]:

        relationships = [
            item.get("relationship")
            for item in evidence
            if item.get("relationship")
        ]

        return unique_values(relationships) or [
            "No dependency evidence available."
        ]

    # --------------------------------------------------------
    # PROGRAMS
    # --------------------------------------------------------

    if section in [
        "programs / packages",
        "affected programs"
    ]:

        programs = [
            item.get("program")
            for item in evidence
            if item.get("program")
        ]

        return unique_values(programs) or [
            "No program evidence available."
        ]

    # --------------------------------------------------------
    # SOURCE ENTITY
    # --------------------------------------------------------

    if section == "source entity":

        values = []

        for item in evidence:

            value = (
                item.get("metadata", {})
                .get("from_entity")
            )

            if value:
                values.append(value)

        return unique_values(values) or [
            "No source entity evidence available."
        ]

    # --------------------------------------------------------
    # SOURCE FIELD
    # --------------------------------------------------------

    if section == "source field":

        fields = [
            item.get("column_name")
            for item in evidence
            if item.get("column_name")
        ]

        return unique_values(fields) or [
            "No source field evidence available."
        ]

    # --------------------------------------------------------
    # TARGET TABLE / AFFECTED TABLES
    # --------------------------------------------------------

    if section in [
        "target table",
        "affected tables"
    ]:

        tables = [
            item.get("table_name")
            for item in evidence
            if item.get("table_name")
        ]

        return unique_values(tables) or [
            "No table evidence available."
        ]

    # --------------------------------------------------------
    # TARGET COLUMN / AFFECTED COLUMNS
    # --------------------------------------------------------

    if section in [
        "target column",
        "affected columns"
    ]:

        columns = [
            item.get("column_name")
            for item in evidence
            if item.get("column_name")
        ]

        return unique_values(columns) or [
            "No column evidence available."
        ]

    # --------------------------------------------------------
    # EVIDENCE
    # --------------------------------------------------------

    if section == "evidence":

        evidence_output = []

        for item in evidence:

            evidence_output.append({
                "source": item.get("source"),
                "file": item.get("file_name"),
                "program": item.get("program"),
                "paragraph": item.get("paragraph"),
                "relationship": item.get(
                    "relationship"
                ),
                "content": item.get("content"),
                "score": item.get("score")
            })

        return evidence_output or [
            "No evidence retrieved."
        ]

    # --------------------------------------------------------
    # KNOWLEDGE GAPS
    # --------------------------------------------------------

    if section == "knowledge gaps":

        gaps = investigation.get(
            "gaps",
            []
        )

        return gaps or [
            "No explicit knowledge gaps identified."
        ]

    # --------------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------------

    if section == "confidence":

        return validation.get(
            "confidence",
            "low"
        )

    # --------------------------------------------------------
    # FINDINGS
    # --------------------------------------------------------

    if section == "findings":

        return investigation.get(
            "findings",
            []
        ) or [
            "No findings available."
        ]

    # --------------------------------------------------------
    # EVERYTHING ELSE
    # --------------------------------------------------------

    return [
        "No evidence available for this section."
    ]


# ============================================================
# HELPER
# ============================================================

def unique_values(values):
    """
    Remove duplicates while preserving order.
    """

    seen = set()
    result = []

    for value in values:

        if value and value not in seen:
            seen.add(value)
            result.append(value)

    return result