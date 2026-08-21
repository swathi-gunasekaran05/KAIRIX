from typing import List, Dict, Any
from config import USE_MOCK_RETRIEVERS


MOCK_QDRANT_DATA = [
    {
        "source": "qdrant",
        "file_name": "EARNPREM.CBL",
        "source_type": "COBOL",
        "program": "EARNPREM",
        "paragraph": "CALCULATE-EARNED",
        "content": (
            "Earned premium calculation uses written premium, "
            "earned days and policy term days."
        ),
        "score": 0.94,
        "metadata": {
            "concept": "earned premium"
        }
    },
    {
        "source": "qdrant",
        "file_name": "PREMCALC.CBL",
        "source_type": "COBOL",
        "program": "PREMCALC",
        "paragraph": "CALC-HO",
        "content": (
            "Premium calculation contains base premium, "
            "risk component, coverage component and discount."
        ),
        "score": 0.88,
        "metadata": {
            "concept": "premium calculation"
        }
    }
]


def retrieve_from_qdrant(
    query: str,
    top_k: int = 5
) -> List[Dict[str, Any]]:

    if not USE_MOCK_RETRIEVERS:
        raise NotImplementedError(
            "Real Qdrant integration will be added later."
        )

    query_words = {
        word.lower().strip("?,.")
        for word in query.split()
        if len(word) > 2
    }

    matched = []

    for item in MOCK_QDRANT_DATA:

        searchable = " ".join([
            item.get("file_name", ""),
            item.get("program", ""),
            item.get("paragraph", ""),
            item.get("content", ""),
            str(item.get("metadata", {}))
        ]).lower()

        if any(word in searchable for word in query_words):
            matched.append(item)

    return matched[:top_k]