from state import InvestigationState

from retrievers.qdrant_retriever import retrieve_from_qdrant
from retrievers.neo4j_retriever import retrieve_from_neo4j


def retrieve_evidence(state: InvestigationState) -> dict:

    query = state.get("user_query", "").strip()

    if not query:
        return {
            "qdrant_results": [],
            "neo4j_results": [],
            "combined_evidence": [],
            "errors": ["User query is empty."]
        }

    errors = []

    # Qdrant
    try:
        qdrant_results = retrieve_from_qdrant(query)
    except Exception as e:
        qdrant_results = []
        errors.append(f"Qdrant error: {e}")

    # Neo4j
    try:
        neo4j_results = retrieve_from_neo4j(query)
    except Exception as e:
        neo4j_results = []
        errors.append(f"Neo4j error: {e}")

    # Combine both evidence sources
    combined_evidence = (
        qdrant_results +
        neo4j_results
    )

    return {
        "qdrant_results": qdrant_results,
        "neo4j_results": neo4j_results,
        "combined_evidence": combined_evidence,
        "errors": errors
    }