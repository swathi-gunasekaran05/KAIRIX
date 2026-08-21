import json
from groq import Groq

from config import (
    LLM_API_KEY,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    EVIDENCE_REQUIRED,
)

from state import InvestigationState


# ============================================================
# GROQ CLIENT
# ============================================================

client = Groq(
    api_key=LLM_API_KEY
)


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are an Investigation Agent for a legacy reverse-engineering system.

The system analyzes knowledge extracted from technologies such as:

- COBOL / Mainframe
- SQL
- SSIS

You receive evidence retrieved from:

1. Qdrant
   Semantic and business-logic evidence.

2. Neo4j
   Graph relationships, dependencies and lineage.

Your responsibility is to investigate the user's question using ONLY
the supplied project evidence.

STRICT RULES:

1. Do not invent project-specific facts.

2. Do not create formulas, table names, column names, programs,
   files, relationships or business rules that are not present
   in the supplied evidence.

3. Clearly distinguish facts from interpretations.

4. If evidence is incomplete, explicitly say that the available
   evidence is insufficient.

5. Preserve exact source names whenever available.

6. Every important conclusion should be traceable to evidence.

7. Do not use general knowledge to fill missing project information.

8. If two evidence items conflict, report the conflict instead
   of choosing one without evidence.

Return valid JSON only.

Required JSON structure:

{
    "answer": "Concise answer to the user's question",

    "business_logic": [
        "Evidence-supported business logic"
    ],

    "findings": [
        {
            "finding": "Finding",
            "source_file": "Source file if available",
            "source_location": "Program/paragraph/table/column if available"
        }
    ],

    "relationships": [
        "Evidence-supported relationship"
    ],

    "gaps": [
        "Missing or insufficient information"
    ],

    "confidence": "high | medium | low"
}
"""


# ============================================================
# BUILD EVIDENCE TEXT
# ============================================================

def build_evidence_context(evidence):
    """
    Convert retrieved evidence into a compact JSON representation
    for the LLM.
    """

    if not evidence:
        return "NO PROJECT EVIDENCE WAS RETRIEVED."

    return json.dumps(
        evidence,
        indent=2,
        ensure_ascii=False,
        default=str
    )


# ============================================================
# INVESTIGATION NODE
# ============================================================

def investigate(state: InvestigationState) -> dict:
    """
    Use the LLM to reason over retrieved project evidence.
    """

    query = state.get(
        "user_query",
        ""
    ).strip()

    evidence = state.get(
        "combined_evidence",
        []
    )

    errors = list(
        state.get("errors", [])
    )

    # --------------------------------------------------------
    # VALIDATE QUERY
    # --------------------------------------------------------

    if not query:

        errors.append(
            "Investigation cannot run because the user query is empty."
        )

        return {
            "investigation_result": None,
            "errors": errors
        }

    # --------------------------------------------------------
    # EVIDENCE-FIRST PROTECTION
    # --------------------------------------------------------

    if EVIDENCE_REQUIRED and not evidence:

        return {
            "investigation_result": {
                "answer": (
                    "The available project evidence is insufficient "
                    "to answer this question."
                ),
                "business_logic": [],
                "findings": [],
                "relationships": [],
                "gaps": [
                    "No supporting evidence was retrieved from "
                    "the project knowledge stores."
                ],
                "confidence": "low"
            },
            "errors": errors
        }

    # --------------------------------------------------------
    # BUILD LLM INPUT
    # --------------------------------------------------------

    evidence_context = build_evidence_context(
        evidence
    )

    user_prompt = f"""
USER REQUEST:

{query}


REQUEST TYPE:

{state.get("request_type", "nlq")}


RETRIEVED PROJECT EVIDENCE:

{evidence_context}


Investigate the request using only the evidence above.

Return valid JSON following the required schema.
"""

    # --------------------------------------------------------
    # CALL LLM
    # --------------------------------------------------------

    try:

        response = client.chat.completions.create(

            model=LLM_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],

            temperature=LLM_TEMPERATURE,

            max_tokens=LLM_MAX_TOKENS,

            response_format={
                "type": "json_object"
            }
        )

        content = response.choices[0].message.content

        result = json.loads(content)

        return {
            "investigation_result": result,
            "errors": errors
        }

    # --------------------------------------------------------
    # HANDLE FAILURE
    # --------------------------------------------------------

    except Exception as exc:

        errors.append(
            f"LLM investigation failed: {str(exc)}"
        )

        return {
            "investigation_result": None,
            "errors": errors
        }