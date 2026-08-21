from typing import Any, Dict, List

from state import InvestigationState
from config import MIN_EVIDENCE_FOR_HIGH_CONFIDENCE


# ============================================================
# VALIDATION NODE
# ============================================================

def validate_investigation(
    state: InvestigationState
) -> dict:
    """
    Validate the Investigation Agent result against the
    evidence retrieved from Neo4j and Qdrant.

    This is deterministic validation.

    The validator does NOT ask another LLM to decide whether
    the first LLM is correct.
    """

    investigation = state.get("investigation_result")

    evidence = state.get(
        "combined_evidence",
        []
    )

    existing_errors = list(
        state.get("errors", [])
    )

    issues: List[str] = []
    missing_evidence: List[str] = []

    # ========================================================
    # 1. DID INVESTIGATION RUN?
    # ========================================================

    if not investigation:

        return {
            "validation_result": {
                "valid": False,
                "confidence": "low",
                "issues": [
                    "No investigation result was generated."
                ],
                "missing_evidence": []
            }
        }

    # ========================================================
    # 2. WAS ANY EVIDENCE RETRIEVED?
    # ========================================================

    evidence_count = len(evidence)

    if evidence_count == 0:

        issues.append(
            "No supporting project evidence was retrieved."
        )

        missing_evidence.append(
            "Neo4j/Qdrant supporting evidence"
        )

    # ========================================================
    # 3. CHECK FINDINGS
    # ========================================================

    findings = investigation.get(
        "findings",
        []
    )

    if not findings:

        issues.append(
            "The investigation contains no evidence-backed findings."
        )

    # ========================================================
    # 4. CHECK SOURCE TRACEABILITY
    # ========================================================

    findings_with_sources = 0

    for finding in findings:

        if not isinstance(finding, dict):
            continue

        source_file = finding.get("source_file")
        source_location = finding.get("source_location")

        if source_file or source_location:
            findings_with_sources += 1

    if findings and findings_with_sources == 0:

        issues.append(
            "Findings do not contain source traceability."
        )

    # ========================================================
    # 5. CHECK REPORTED GAPS
    # ========================================================

    gaps = investigation.get(
        "gaps",
        []
    )

    # Gaps are not errors.
    # They indicate that the evidence is incomplete.

    # ========================================================
    # 6. DETERMINE CONFIDENCE
    # ========================================================

    if evidence_count == 0:

        confidence = "low"

    elif existing_errors:

        confidence = "low"

    elif gaps:

        # The LLM itself identified incomplete evidence.
        # Therefore we should not allow HIGH confidence.
        confidence = "medium"

    elif (
        evidence_count >= MIN_EVIDENCE_FOR_HIGH_CONFIDENCE
        and findings_with_sources > 0
    ):

        confidence = "high"

    else:

        confidence = "medium"

    # ========================================================
    # 7. DETERMINE VALIDITY
    # ========================================================

    valid = (
        evidence_count > 0
        and investigation is not None
        and len(findings) > 0
        and findings_with_sources > 0
        and not existing_errors
    )

    # ========================================================
    # 8. COMPARE LLM CONFIDENCE
    # ========================================================

    llm_confidence = investigation.get(
        "confidence",
        "low"
    )

    if llm_confidence == "high" and confidence != "high":

        issues.append(
            "LLM reported high confidence, but validation "
            f"adjusted confidence to {confidence}."
        )

    # ========================================================
    # 9. RETURN VALIDATION
    # ========================================================

    validation_result: Dict[str, Any] = {
        "valid": valid,
        "confidence": confidence,
        "issues": issues,
        "missing_evidence": missing_evidence
    }

    return {
        "validation_result": validation_result
    }