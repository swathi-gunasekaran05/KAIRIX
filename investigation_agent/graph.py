from langgraph.graph import StateGraph, START, END

from state import InvestigationState

from nodes.classify_request import classify_request
from nodes.retrieve_evidence import retrieve_evidence
from nodes.investigate import investigate
from nodes.validate import validate_investigation
from nodes.format_output import format_output


# ============================================================
# BUILD INVESTIGATION AGENT GRAPH
# ============================================================

def build_investigation_graph():

    # --------------------------------------------------------
    # 1. CREATE GRAPH
    # --------------------------------------------------------

    workflow = StateGraph(
        InvestigationState
    )

    # --------------------------------------------------------
    # 2. ADD NODES
    # --------------------------------------------------------

    workflow.add_node(
        "classify_request",
        classify_request
    )

    workflow.add_node(
        "retrieve_evidence",
        retrieve_evidence
    )

    workflow.add_node(
        "investigate",
        investigate
    )

    workflow.add_node(
        "validate",
        validate_investigation
    )

    workflow.add_node(
        "format_output",
        format_output
    )

    # --------------------------------------------------------
    # 3. DEFINE FLOW
    # --------------------------------------------------------

    workflow.add_edge(
        START,
        "classify_request"
    )

    workflow.add_edge(
        "classify_request",
        "retrieve_evidence"
    )

    workflow.add_edge(
        "retrieve_evidence",
        "investigate"
    )

    workflow.add_edge(
        "investigate",
        "validate"
    )

    workflow.add_edge(
        "validate",
        "format_output"
    )

    workflow.add_edge(
        "format_output",
        END
    )

    # --------------------------------------------------------
    # 4. COMPILE
    # --------------------------------------------------------

    return workflow.compile()


# ============================================================
# COMPILED AGENT
# ============================================================

investigation_graph = build_investigation_graph()