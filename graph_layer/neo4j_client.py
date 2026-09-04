"""
Neo4j driver wrapper for KAIRIX Graph Layer.

Provides a thin, context-manager-safe wrapper around the neo4j Python driver.
All configuration is read from environment variables (.env).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import ServiceUnavailable, AuthError, SessionExpired

load_dotenv()


class Neo4jClient:
    """
    Thin wrapper around the Neo4j Python driver.

    Usage:
        client = Neo4jClient()
        results = client.run_query("MATCH (n) RETURN count(n) AS total")
        client.close()

    Or as a context manager:
        with Neo4jClient() as client:
            client.run_query(...)
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        silent: bool = False,
    ):
        self.uri = uri or os.getenv("NEO4J_URI")
        if not self.uri:
            raise RuntimeError("NEO4J_URI is required in .env (e.g. neo4j+s://<instance_id>.databases.neo4j.io)")
        self.username = username or os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD")
        self.database = database or os.getenv("NEO4J_DATABASE", "neo4j")
        self.silent = silent
        self._driver: Optional[Driver] = None
        self._connect()

    def _connect(self) -> None:
        """Establish driver connection with AuraDB cloud keepalive settings."""
        try:
            if self._driver:
                try:
                    self._driver.close()
                except Exception:
                    pass
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                keep_alive=True,
                liveness_check_timeout=0,
                max_connection_lifetime=180,  # Cycle connections before cloud proxies drop idle sockets (300s timeout)
                connection_timeout=30.0,
                notifications_min_severity="OFF",
            )
            self._driver.verify_connectivity()
            if not self.silent:
                print(f"[Neo4j] Connected to {self.uri} (db: {self.database})")
        except ServiceUnavailable as e:
            raise ConnectionError(
                f"[Neo4j] Cannot connect to {self.uri}. "
                f"Is Neo4j running? Error: {e}"
            ) from e
        except AuthError as e:
            raise PermissionError(
                f"[Neo4j] Authentication failed for user '{self.username}'. "
                f"Check NEO4J_PASSWORD in .env. Error: {e}"
            ) from e

    def run_query(
        self,
        cypher: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a read query and return all records as dicts.
        Uses execute_read with automatic driver retry and reconnect.
        """
        if self._driver is None:
            self._connect()
        params = params or {}

        def _work(tx):
            res = tx.run(cypher, params)
            return [dict(record) for record in res]

        try:
            with self._driver.session(database=self.database) as session:
                return session.execute_read(_work)
        except (SessionExpired, ServiceUnavailable, OSError):
            # Defunct connection dropped by cloud proxy; reconnect driver and retry
            self._connect()
            with self._driver.session(database=self.database) as session:
                return session.execute_read(_work)

    def run_write(
        self,
        cypher: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a write transaction (CREATE / MERGE / SET / DELETE).
        Uses execute_write with automatic retry.
        """
        if self._driver is None:
            self._connect()
        params = params or {}

        def _work(tx):
            res = tx.run(cypher, params)
            return [dict(record) for record in res]

        try:
            with self._driver.session(database=self.database) as session:
                return session.execute_write(_work)
        except (SessionExpired, ServiceUnavailable, OSError):
            self._connect()
            with self._driver.session(database=self.database) as session:
                return session.execute_write(_work)

    def run_batch(
        self,
        cypher: str,
        batch: List[Dict[str, Any]],
        batch_size: int = 500,
    ) -> int:
        """
        Execute a parameterised Cypher query against a list of items in batches.

        The query must accept a `$batch` parameter, e.g.:
            UNWIND $batch AS row
            MERGE (n:Entity {id: row.id})
            SET n += row.properties

        Returns total records processed.
        """
        total = 0
        for i in range(0, len(batch), batch_size):
            chunk = batch[i : i + batch_size]
            self.run_query(cypher, {"batch": chunk})
            total += len(chunk)
        return total

    def apply_schema(self, schema_path: str) -> None:
        """
        Execute all Cypher statements in a .cypher schema file.
        Statements are split by semicolons.
        """
        with open(schema_path, "r", encoding="utf-8") as f:
            content = f.read()
        statements = [s.strip() for s in content.split(";") if s.strip()]
        for stmt in statements:
            try:
                self.run_write(stmt)
            except Exception as e:
                print(f"[Neo4j] Schema warning (non-fatal): {e}")

    def close(self) -> None:
        """Close the driver connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            if not self.silent:
                print("[Neo4j] Connection closed.")

    def __enter__(self) -> "Neo4jClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
