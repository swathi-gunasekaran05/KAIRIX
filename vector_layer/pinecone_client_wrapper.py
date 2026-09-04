"""
Pinecone client wrapper for KAIRIX Vector Layer.

Provides a drop-in compatible interface with QdrantWrapper using Pinecone Serverless:
  - Index: kairix (dim 384, cosine metric)
  - Namespaces:
      kairix_chunks    — code chunks
      kairix_summaries — file summaries
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

load_dotenv()

COLLECTION_CHUNKS = "kairix_chunks"
COLLECTION_SUMMARIES = "kairix_summaries"
_DEFAULT_VECTOR_DIM = 384
_DEFAULT_INDEX_NAME = "kairix"


class PineconeWrapper:
    """
    Pinecone Serverless wrapper for KAIRIX.

    Provides interface parity with QdrantWrapper (ensure_collections, upsert, search, collection_count).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        index_name: Optional[str] = None,
        vector_dim: int = _DEFAULT_VECTOR_DIM,
        cloud: str = "aws",
        region: str = "us-east-1",
        silent: bool = False,
    ):
        self.api_key = api_key or os.getenv("PINECONE_API_KEY")
        if not self.api_key:
            raise RuntimeError("PINECONE_API_KEY is required in .env or constructor.")

        self.index_name = (
            index_name or os.getenv("PINECONE_INDEX_NAME", _DEFAULT_INDEX_NAME)
        ).lower().strip()
        self.vector_dim = vector_dim
        self.cloud = cloud
        self.region = region
        self.silent = silent

        self._pc = Pinecone(api_key=self.api_key)
        self._index = None

        if not self.silent:
            print(f"[Pinecone] Connected to Pinecone Cloud (Index: '{self.index_name}')")

    @property
    def index(self):
        if self._index is None:
            self.ensure_collections()
            self._index = self._pc.Index(self.index_name)
        return self._index

    # ── Collection / Index management ──────────────────────────────────────────

    def ensure_collections(self) -> None:
        """Ensure the Pinecone index exists with the correct dimensions."""
        existing_indexes = self._pc.list_indexes().names()
        if self.index_name not in existing_indexes:
            print(
                f"[Pinecone] Creating serverless index '{self.index_name}' (dim={self.vector_dim}, metric=cosine)..."
            )
            self._pc.create_index(
                name=self.index_name,
                dimension=self.vector_dim,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud=self.cloud,
                    region=self.region,
                ),
            )
            # Wait briefly for serverless index readiness
            while not self._pc.describe_index(self.index_name).status["ready"]:
                time.sleep(1)
            print(f"[Pinecone] Index '{self.index_name}' is ready.")
        else:
            if not self.silent:
                print(f"[Pinecone] Index '{self.index_name}' exists.")

    def collection_count(self, name: str) -> int:
        """
        Return number of vectors in the given namespace.
        In Pinecone, namespaces are used for collections (e.g. kairix_chunks).
        """
        try:
            stats = self.index.describe_index_stats()
            namespaces = stats.get("namespaces", {})
            ns_info = namespaces.get(name, {})
            return ns_info.get("vector_count", 0)
        except Exception as e:
            if not self.silent:
                print(f"[Pinecone] Warning getting count for '{name}': {e}")
            return 0

    # ── Upsert ────────────────────────────────────────────────────────────────

    def upsert(
        self,
        collection: str,
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
        batch_size: int = 100,
    ) -> int:
        """
        Upsert vectors with metadata into the specified namespace.

        Args:
            collection: Namespace name (e.g. 'kairix_chunks' or 'kairix_summaries').
            vectors: One float vector per item.
            payloads: Metadata dict per item.
            ids: Optional unique string IDs.
            batch_size: Batch size (default 100).

        Returns:
            Total vectors upserted.
        """
        if not vectors:
            return 0

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in vectors]

        total = 0
        idx = self.index

        for i in range(0, len(vectors), batch_size):
            batch_vecs = vectors[i : i + batch_size]
            batch_pay = payloads[i : i + batch_size]
            batch_ids = ids[i : i + batch_size]

            # Pinecone accepts tuples: (id, vector, metadata)
            records = [
                (
                    str(bid),
                    vec,
                    # Ensure metadata values are strings, numbers, bools, or list of strings
                    self._sanitize_metadata(pay),
                )
                for bid, vec, pay in zip(batch_ids, batch_vecs, batch_pay)
            ]

            idx.upsert(vectors=records, namespace=collection)
            total += len(records)

        return total

    # ── Fetch by ID & List IDs ────────────────────────────────────────────────

    def fetch(self, ids: List[str], collection: str) -> Dict[str, Any]:
        """Fetch vectors and metadata by their exact IDs."""
        res = self.index.fetch(ids=ids, namespace=collection)
        return res.to_dict() if hasattr(res, "to_dict") else dict(res)

    def list_ids(self, collection: str, limit: int = 50) -> List[str]:
        """List vector IDs stored in a namespace."""
        try:
            results = list(self.index.list(namespace=collection))
            all_ids = []
            for batch in results:
                if hasattr(batch, "vectors") and batch.vectors:
                    all_ids.extend([v.id for v in batch.vectors])
                elif isinstance(batch, list):
                    all_ids.extend([getattr(v, "id", str(v)) for v in batch])
                if len(all_ids) >= limit:
                    break
            return all_ids[:limit]
        except Exception as e:
            if not self.silent:
                print(f"[Pinecone] Error listing IDs for '{collection}': {e}")
            return []

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        collection: str,
        query_vector: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for nearest vectors in the given namespace.

        Returns list of dicts with:
            id, score, payload fields
        """
        res = self.index.query(
            vector=query_vector,
            top_k=top_k,
            namespace=collection,
            include_metadata=True,
            filter=filter,
        )

        hits: List[Dict[str, Any]] = []
        for match in res.get("matches", []):
            meta = match.get("metadata") or {}
            item = {
                "id": match["id"],
                "score": float(match["score"]),
                "payload": meta,
            }
            item.update(meta)
            hits.append(item)

        return hits

    def close(self) -> None:
        """Close method for interface parity with QdrantWrapper."""
        pass

    @staticmethod
    def _sanitize_metadata(pay: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure metadata types are compliant with Pinecone storage."""
        clean: Dict[str, Any] = {}
        for k, v in pay.items():
            if isinstance(v, (str, int, float, bool)):
                clean[k] = v
            elif isinstance(v, list) and all(isinstance(x, str) for x in v):
                clean[k] = v
            elif v is None:
                continue
            else:
                clean[k] = str(v)
        return clean
