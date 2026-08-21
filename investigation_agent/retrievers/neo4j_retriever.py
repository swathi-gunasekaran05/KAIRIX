from typing import List, Dict, Any
from config import USE_MOCK_RETRIEVERS


MOCK_NEO4J_DATA = [
    {
        "source": "neo4j",
        "file_name": "EARNPREM.CBL",
        "source_type": "COBOL",
        "program": "EARNPREM",
        "content": (
            "EARNPREM is related to the Earned Premium "
            "business concept."
        ),
        "relationship": (
            "EARNPREM -> CALCULATES -> EARNED_PREMIUM"
        ),
        "metadata": {
            "from_entity": "EARNPREM",
            "relationship_type": "CALCULATES",
            "to_entity": "EARNED_PREMIUM"
        }
    },
    {
        "source": "neo4j",
        "file_name": "PREMCALC.CBL",
        "source_type": "COBOL",
        "program": "PREMCALC",
        "content": (
            "PREMCALC is related to premium calculation."
        ),
        "relationship": (
            "PREMCALC -> CALCULATES -> PREMIUM"
        ),
        "metadata": {
            "from_entity": "PREMCALC",
            "relationship_type": "CALCULATES",
            "to_entity": "PREMIUM"
        }
    }
]


def retrieve_from_neo4j(
    query: str,
    limit: int = 20
) -> List[Dict[str, Any]]:

    if not USE_MOCK_RETRIEVERS:
        raise NotImplementedError(
            "Real Neo4j integration will be added later."
        )

    query_words = {
        word.lower().strip("?,.")
        for word in query.split()
        if len(word) > 2
    }

    matched = []

    for item in MOCK_NEO4J_DATA:

        searchable = " ".join([
            item.get("file_name", ""),
            item.get("program", ""),
            item.get("content", ""),
            item.get("relationship", ""),
            str(item.get("metadata", {}))
        ]).lower()

        if any(word in searchable for word in query_words):
            matched.append(item)

    return matched[:limit]