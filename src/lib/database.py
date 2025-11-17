"""Analytics database for query tracking and admin review.

Stores queries, responses, feedback, and RAG chunks for analytics.
Optional - controlled by ENABLE_ANALYTICS_DB env var.
"""

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from src.lib.config import load_config
from src.lib.logging import get_logger

logger = get_logger(__name__)


# SQL Schema
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS queries (
    query_id TEXT PRIMARY KEY,
    discord_server_id TEXT NOT NULL,
    discord_server_name TEXT,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    username TEXT NOT NULL,
    query_text TEXT NOT NULL,
    response_text TEXT NOT NULL,
    llm_model TEXT NOT NULL,
    confidence_score REAL,
    rag_score REAL,
    validation_passed INTEGER,
    latency_ms INTEGER,
    timestamp TEXT NOT NULL,
    upvotes INTEGER DEFAULT 0,
    downvotes INTEGER DEFAULT 0,
    admin_status TEXT DEFAULT 'pending',
    admin_notes TEXT,
    multi_hop_enabled INTEGER DEFAULT 0,
    hops_used INTEGER DEFAULT 0,
    cost REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_timestamp ON queries(timestamp);
CREATE INDEX IF NOT EXISTS idx_admin_status ON queries(admin_status);
CREATE INDEX IF NOT EXISTS idx_llm_model ON queries(llm_model);
CREATE INDEX IF NOT EXISTS idx_channel_id ON queries(channel_id);
CREATE INDEX IF NOT EXISTS idx_multi_hop ON queries(multi_hop_enabled);
CREATE INDEX IF NOT EXISTS idx_cost ON queries(cost);

CREATE TABLE IF NOT EXISTS retrieved_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    chunk_header TEXT,
    chunk_text TEXT NOT NULL,
    document_name TEXT,
    document_type TEXT,
    vector_similarity REAL,
    bm25_score REAL,
    rrf_score REAL,
    final_score REAL NOT NULL,
    relevant INTEGER DEFAULT NULL,
    hop_number INTEGER DEFAULT 0,
    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_query_id ON retrieved_chunks(query_id);
CREATE INDEX IF NOT EXISTS idx_rank ON retrieved_chunks(query_id, rank);
CREATE INDEX IF NOT EXISTS idx_relevant ON retrieved_chunks(relevant);
CREATE INDEX IF NOT EXISTS idx_hop_number ON retrieved_chunks(hop_number);

CREATE TABLE IF NOT EXISTS hop_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id TEXT NOT NULL,
    hop_number INTEGER NOT NULL,
    can_answer INTEGER NOT NULL,
    reasoning TEXT NOT NULL,
    missing_query TEXT,
    evaluation_model TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hop_eval_query_id ON hop_evaluations(query_id);
CREATE INDEX IF NOT EXISTS idx_hop_eval_hop_num ON hop_evaluations(query_id, hop_number);
"""


class AnalyticsDatabase:
    """SQLite database for query analytics and admin review.

    All operations are no-ops if enabled=False.
    Thread-safe using connection-per-operation pattern.
    """

    def __init__(self, db_path: str, enabled: bool, retention_days: int = 30):
        """Initialize analytics database.

        Args:
            db_path: Path to SQLite database file
            enabled: If False, all operations are no-ops
            retention_days: Auto-delete records older than this (default: 30)
        """
        self.db_path = db_path
        self.enabled = enabled
        self.retention_days = retention_days

        if self.enabled:
            self._initialize_db()
            logger.info(
                "Analytics database initialized",
                extra={"db_path": db_path, "retention_days": retention_days},
            )

    def _initialize_db(self) -> None:
        """Create database file and tables if not exists."""
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create schema
        with self._get_connection() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

        # Enable WAL mode for better concurrency
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def _get_connection(self) -> None:
        """Get database connection context manager.

        Yields:
            sqlite3.Connection
        """
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def insert_query(self, query_data: dict[str, Any]) -> None:
        """Insert query + response record.

        Args:
            query_data: Dictionary with query fields (see schema)
        """
        if not self.enabled:
            return

        try:
            now = datetime.now(UTC).isoformat()

            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO queries (
                        query_id, discord_server_id, discord_server_name,
                        channel_id, channel_name, username,
                        query_text, response_text, llm_model,
                        confidence_score, rag_score, validation_passed,
                        latency_ms, timestamp, upvotes, downvotes,
                        admin_status, admin_notes, multi_hop_enabled, hops_used,
                        cost, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        query_data["query_id"],
                        query_data["discord_server_id"],
                        query_data.get("discord_server_name"),
                        query_data["channel_id"],
                        query_data.get("channel_name"),
                        query_data["username"],
                        query_data["query_text"],
                        query_data["response_text"],
                        query_data["llm_model"],
                        query_data.get("confidence_score"),
                        query_data.get("rag_score"),
                        1 if query_data.get("validation_passed") else 0,
                        query_data.get("latency_ms"),
                        query_data["timestamp"],
                        0,  # upvotes
                        0,  # downvotes
                        "pending",  # admin_status
                        None,  # admin_notes
                        query_data.get("multi_hop_enabled", 0),
                        query_data.get("hops_used", 0),
                        query_data.get("cost", 0.0),
                        now,
                        now,
                    ),
                )
                conn.commit()

            logger.debug(
                "Query inserted into analytics DB", extra={"query_id": query_data["query_id"]}
            )

        except Exception as e:
            logger.error(f"Failed to insert query: {e}", exc_info=True)

    def insert_chunks(self, query_id: str, chunks: list[dict[str, Any]]) -> None:
        """Insert retrieved chunks for a query.

        Args:
            query_id: Query UUID
            chunks: List of chunk dictionaries (see schema)
        """
        if not self.enabled:
            return

        try:
            with self._get_connection() as conn:
                for chunk in chunks:
                    conn.execute(
                        """
                        INSERT INTO retrieved_chunks (
                            query_id, rank, chunk_header, chunk_text,
                            document_name, document_type,
                            vector_similarity, bm25_score, rrf_score,
                            final_score, relevant, hop_number
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            query_id,
                            chunk["rank"],
                            chunk.get("chunk_header"),
                            chunk["chunk_text"],
                            chunk.get("document_name"),
                            chunk.get("document_type"),
                            chunk.get("vector_similarity"),
                            chunk.get("bm25_score"),
                            chunk.get("rrf_score"),
                            chunk["final_score"],
                            None,  # relevant (default NULL)
                            chunk.get(
                                "hop_number", 0
                            ),  # hop_number (default 0 for backward compat)
                        ),
                    )
                conn.commit()

            logger.debug(
                "Chunks inserted into analytics DB",
                extra={"query_id": query_id, "chunk_count": len(chunks)},
            )

        except Exception as e:
            logger.error(f"Failed to insert chunks: {e}", exc_info=True)

    def insert_hop_evaluations(
        self, query_id: str, evaluations: list[dict[str, Any]], evaluation_model: str
    ) -> None:
        """Insert hop evaluation results for a query.

        Args:
            query_id: Query UUID
            evaluations: List of HopEvaluation dictionaries
            evaluation_model: Model used for evaluation
        """
        if not self.enabled:
            return

        try:
            now = datetime.now(UTC).isoformat()

            with self._get_connection() as conn:
                for hop_num, evaluation in enumerate(evaluations, 1):
                    conn.execute(
                        """
                        INSERT INTO hop_evaluations (
                            query_id, hop_number, can_answer, reasoning,
                            missing_query, evaluation_model, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            query_id,
                            hop_num,
                            1 if evaluation["can_answer"] else 0,
                            evaluation["reasoning"],
                            evaluation.get("missing_query"),
                            evaluation_model,
                            now,
                        ),
                    )
                conn.commit()

            logger.debug(
                "Hop evaluations inserted",
                extra={"query_id": query_id, "hop_count": len(evaluations)},
            )

        except Exception as e:
            logger.error(f"Failed to insert hop evaluations: {e}", exc_info=True)

    def get_hop_evaluations_for_query(self, query_id: str) -> list[dict[str, Any]]:
        """Get hop evaluation results for a query.

        Args:
            query_id: Query UUID

        Returns:
            List of hop evaluation dictionaries
        """
        if not self.enabled:
            return []

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT
                        hop_number, can_answer, reasoning, missing_query,
                        evaluation_model, created_at
                    FROM hop_evaluations
                    WHERE query_id = ?
                    ORDER BY hop_number ASC
                """,
                    (query_id,),
                )

                rows = cursor.fetchall()
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get hop evaluations: {e}", exc_info=True)
            return []

    def increment_vote(self, query_id: str, vote_type: Literal["upvote", "downvote"]) -> None:
        """Increment upvote or downvote count for a query.

        Args:
            query_id: Query UUID
            vote_type: "upvote" or "downvote"
        """
        if not self.enabled:
            return

        try:
            now = datetime.now(UTC).isoformat()

            # Use explicit SQL to avoid bandit B608 warning about string interpolation
            with self._get_connection() as conn:
                if vote_type == "upvote":
                    conn.execute(
                        """
                        UPDATE queries
                        SET upvotes = upvotes + 1,
                            updated_at = ?
                        WHERE query_id = ?
                    """,
                        (now, query_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE queries
                        SET downvotes = downvotes + 1,
                            updated_at = ?
                        WHERE query_id = ?
                    """,
                        (now, query_id),
                    )
                conn.commit()

            logger.debug(
                "Vote incremented in analytics DB",
                extra={"query_id": query_id, "vote_type": vote_type},
            )

        except Exception as e:
            logger.error(f"Failed to increment vote: {e}", exc_info=True)

    def cleanup_old_records(self) -> int:
        """Delete records older than retention_days.

        Returns:
            Number of queries deleted
        """
        if not self.enabled:
            return 0

        try:
            cutoff_date = (datetime.now(UTC) - timedelta(days=self.retention_days)).isoformat()

            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    DELETE FROM queries
                    WHERE timestamp < ?
                """,
                    (cutoff_date,),
                )
                deleted_count = cursor.rowcount
                conn.commit()

            if deleted_count > 0:
                logger.info(
                    f"Cleaned up {deleted_count} old records",
                    extra={"retention_days": self.retention_days, "deleted_count": deleted_count},
                )

            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old records: {e}", exc_info=True)
            return 0

    def get_all_queries(
        self, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Get all queries with optional filters.

        Args:
            filters: Optional filters (admin_status, llm_model, channel_id, etc.)
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of query dictionaries
        """
        if not self.enabled:
            return []

        try:
            query = "SELECT * FROM queries WHERE 1=1"
            params = []

            if filters:
                if "admin_status" in filters and filters["admin_status"]:
                    query += " AND admin_status = ?"
                    params.append(filters["admin_status"])

                if "llm_model" in filters and filters["llm_model"]:
                    query += " AND llm_model = ?"
                    params.append(filters["llm_model"])

                if "channel_id" in filters and filters["channel_id"]:
                    query += " AND channel_id = ?"
                    params.append(filters["channel_id"])

                if "search" in filters and filters["search"]:
                    query += " AND (query_text LIKE ? OR response_text LIKE ?)"
                    search_term = f"%{filters['search']}%"
                    params.extend([search_term, search_term])

                if "start_date" in filters and filters["start_date"]:
                    query += " AND timestamp >= ?"
                    params.append(filters["start_date"])

                if "end_date" in filters and filters["end_date"]:
                    query += " AND timestamp <= ?"
                    params.append(filters["end_date"])

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get queries: {e}", exc_info=True)
            return []

    def get_query_by_id(self, query_id: str) -> dict[str, Any] | None:
        """Get a single query by ID.

        Args:
            query_id: Query UUID

        Returns:
            Query dictionary or None if not found
        """
        if not self.enabled:
            return None

        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM queries WHERE query_id = ?", (query_id,))
                row = cursor.fetchone()

            return dict(row) if row else None

        except Exception as e:
            logger.error(f"Failed to get query: {e}", exc_info=True)
            return None

    def get_chunks_for_query(self, query_id: str) -> list[dict[str, Any]]:
        """Get all retrieved chunks for a query.

        Args:
            query_id: Query UUID

        Returns:
            List of chunk dictionaries
        """
        if not self.enabled:
            return []

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT * FROM retrieved_chunks
                    WHERE query_id = ?
                    ORDER BY rank ASC
                """,
                    (query_id,),
                )
                rows = cursor.fetchall()

            return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get chunks: {e}", exc_info=True)
            return []

    def update_query_admin_fields(
        self, query_id: str, admin_status: str | None = None, admin_notes: str | None = None
    ) -> None:
        """Update admin status and/or notes for a query.

        Args:
            query_id: Query UUID
            admin_status: New admin status (pending/approved/reviewed/issues/flagged)
            admin_notes: New admin notes (freeform text)
        """
        if not self.enabled:
            return

        try:
            now = datetime.now(UTC).isoformat()

            # Build safe SQL with explicit column names (not user-controlled)
            # Using explicit construction to avoid bandit B608 warning
            set_clauses = []
            params = []

            if admin_status is not None:
                set_clauses.append("admin_status = ?")
                params.append(admin_status)

            if admin_notes is not None:
                set_clauses.append("admin_notes = ?")
                params.append(admin_notes)

            if not set_clauses:
                return

            set_clauses.append("updated_at = ?")
            params.append(now)
            params.append(query_id)

            # Safe: all column names are hardcoded above, not user input
            # nosec B608: set_clauses only contains hardcoded SQL fragments ("admin_status = ?", "admin_notes = ?", "updated_at = ?")
            query_sql = "UPDATE queries SET " + ", ".join(set_clauses) + " WHERE query_id = ?"  # nosec B608

            with self._get_connection() as conn:
                conn.execute(query_sql, params)
                conn.commit()

            logger.info(
                "Query admin fields updated",
                extra={"query_id": query_id, "admin_status": admin_status},
            )

        except Exception as e:
            logger.error(f"Failed to update query admin fields: {e}", exc_info=True)

    def update_chunk_relevance(self, chunk_id: int, relevant: bool | None) -> None:
        """Update relevance flag for a chunk.

        Args:
            chunk_id: Chunk ID (autoincrement primary key)
            relevant: True (relevant), False (not relevant), None (not reviewed)
        """
        if not self.enabled:
            return

        try:
            value = None if relevant is None else (1 if relevant else 0)

            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE retrieved_chunks
                    SET relevant = ?
                    WHERE id = ?
                """,
                    (value, chunk_id),
                )
                conn.commit()

            logger.debug(
                "Chunk relevance updated", extra={"chunk_id": chunk_id, "relevant": relevant}
            )

        except Exception as e:
            logger.error(f"Failed to update chunk relevance: {e}", exc_info=True)

    def delete_query(self, query_id: str) -> bool:
        """Delete a query and its associated chunks.

        Args:
            query_id: Query UUID

        Returns:
            True if query was deleted, False if not found or error
        """
        if not self.enabled:
            return False

        try:
            with self._get_connection() as conn:
                # Delete query (chunks will be deleted automatically due to CASCADE)
                cursor = conn.execute(
                    """
                    DELETE FROM queries
                    WHERE query_id = ?
                """,
                    (query_id,),
                )
                deleted_count = cursor.rowcount
                conn.commit()

            if deleted_count > 0:
                logger.info("Query deleted from analytics DB", extra={"query_id": query_id})
                return True
            else:
                logger.warning("Query not found for deletion", extra={"query_id": query_id})
                return False

        except Exception as e:
            logger.error(f"Failed to delete query: {e}", exc_info=True)
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics for dashboard.

        Returns:
            Dictionary with stats (total_queries, avg_latency, helpful_rate, etc.)
        """
        if not self.enabled:
            return {}

        try:
            with self._get_connection() as conn:
                # Total queries
                cursor = conn.execute("SELECT COUNT(*) FROM queries")
                total_queries = cursor.fetchone()[0]

                # Avg latency
                cursor = conn.execute("SELECT AVG(latency_ms) FROM queries")
                avg_latency = cursor.fetchone()[0] or 0

                # Feedback stats
                cursor = conn.execute("""
                    SELECT
                        SUM(upvotes) as total_upvotes,
                        SUM(downvotes) as total_downvotes
                    FROM queries
                """)
                row = cursor.fetchone()
                total_upvotes = row[0] or 0
                total_downvotes = row[1] or 0
                total_feedback = total_upvotes + total_downvotes
                helpful_rate = total_upvotes / total_feedback if total_feedback > 0 else 0

                # Admin status counts
                cursor = conn.execute("""
                    SELECT admin_status, COUNT(*)
                    FROM queries
                    GROUP BY admin_status
                """)
                status_counts = dict(cursor.fetchall())

                # Chunk relevance stats
                cursor = conn.execute("""
                    SELECT
                        SUM(CASE WHEN relevant = 1 THEN 1 ELSE 0 END) as relevant_count,
                        SUM(CASE WHEN relevant = 0 THEN 1 ELSE 0 END) as not_relevant_count,
                        SUM(CASE WHEN relevant IS NULL THEN 1 ELSE 0 END) as not_reviewed_count
                    FROM retrieved_chunks
                """)
                row = cursor.fetchone()

                return {
                    "total_queries": total_queries,
                    "avg_latency_ms": round(avg_latency, 0),
                    "total_upvotes": total_upvotes,
                    "total_downvotes": total_downvotes,
                    "helpful_rate": round(helpful_rate, 2),
                    "status_counts": status_counts,
                    "chunks_relevant": row[0] or 0,
                    "chunks_not_relevant": row[1] or 0,
                    "chunks_not_reviewed": row[2] or 0,
                }

        except Exception as e:
            logger.error(f"Failed to get stats: {e}", exc_info=True)
            return {}

    def get_queries_with_relevant_chunks(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get queries that have at least one chunk marked as relevant.

        Returns queries ordered by timestamp descending, with their relevant chunks.

        Args:
            limit: Maximum number of queries to return

        Returns:
            List of dictionaries with query info and relevant chunks:
            [
                {
                    "query_id": str,
                    "query_text": str,
                    "timestamp": str,
                    "relevant_chunks": [
                        {"chunk_header": str, "rank": int, ...},
                        ...
                    ]
                },
                ...
            ]
        """
        if not self.enabled:
            return []

        try:
            with self._get_connection() as conn:
                # Get queries that have at least one relevant chunk
                cursor = conn.execute(
                    """
                    SELECT DISTINCT q.query_id, q.query_text, q.timestamp
                    FROM queries q
                    INNER JOIN retrieved_chunks rc ON q.query_id = rc.query_id
                    WHERE rc.relevant = 1
                    ORDER BY q.timestamp DESC
                    LIMIT ?
                """,
                    (limit,),
                )

                query_rows = cursor.fetchall()

                results = []
                for query_row in query_rows:
                    query_id = query_row["query_id"]

                    # Get all relevant chunks for this query
                    chunk_cursor = conn.execute(
                        """
                        SELECT chunk_header, rank, chunk_text,
                               vector_similarity, bm25_score, rrf_score, final_score
                        FROM retrieved_chunks
                        WHERE query_id = ? AND relevant = 1
                        ORDER BY rank ASC
                    """,
                        (query_id,),
                    )

                    chunks = [dict(row) for row in chunk_cursor.fetchall()]

                    results.append(
                        {
                            "query_id": query_id,
                            "query_text": query_row["query_text"],
                            "timestamp": query_row["timestamp"],
                            "relevant_chunks": chunks,
                        }
                    )

                return results

        except Exception as e:
            logger.error(f"Failed to get queries with relevant chunks: {e}", exc_info=True)
            return []

    @classmethod
    def from_config(cls) -> "AnalyticsDatabase":
        """Create AnalyticsDatabase from config.

        Returns:
            AnalyticsDatabase instance
        """
        config = load_config()
        return cls(
            db_path=config.analytics_db_path,
            enabled=config.enable_analytics_db,
            retention_days=config.analytics_retention_days,
        )
