"""
Vector Layer — Pinecone Cloud Vector Database for KAIRIX.

Exposes:
  Embedder             — sentence-transformers wrapper (all-MiniLM-L6-v2)
  PineconeWrapper      — Pinecone Serverless client wrapper
  VectorIngestion      — chunks + embeds source files and summaries into Pinecone
  get_vector_client    — resolver for vector database client
"""

from .embedder import Embedder
from .pinecone_client_wrapper import PineconeWrapper
from .vector_ingestion import VectorIngestion, get_vector_client

__all__ = ["Embedder", "PineconeWrapper", "VectorIngestion", "get_vector_client"]
