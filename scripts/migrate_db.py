#!/usr/bin/env python3
"""Database migration script to add missing columns to analytics database.

This script safely adds new columns to an existing analytics database without
losing any data.
"""

import sqlite3
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.lib.config import load_config
from src.lib.logging import get_logger

logger = get_logger(__name__)


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns


def migrate_analytics_db(db_path: str) -> None:
    """Add missing columns to analytics database.

    Args:
        db_path: Path to analytics database
    """
    if not Path(db_path).exists():
        print(f"❌ Database not found at {db_path}")
        print("   No migration needed - database will be created with correct schema on first use.")
        return

    print(f"🔍 Checking database at {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Migrations to apply
        migrations = [
            # Cost tracking (added 2025-01-15)
            ("queries", "cost", "REAL DEFAULT 0.0"),
            # Quote validation columns (added 2025-01-17)
            ("queries", "quote_validation_score", "REAL DEFAULT NULL"),
            ("queries", "quote_total_count", "INTEGER DEFAULT 0"),
            ("queries", "quote_valid_count", "INTEGER DEFAULT 0"),
            ("queries", "quote_invalid_count", "INTEGER DEFAULT 0"),
            # RAG test runs sort order (added 2025-01-27)
            ("rag_test_runs", "sort_order", "INTEGER DEFAULT NULL"),
            # Cost and latency breakdown (added 2025-12-12)
            ("queries", "hop_evaluation_cost", "REAL DEFAULT 0.0"),
            ("queries", "main_llm_cost", "REAL DEFAULT 0.0"),
            ("queries", "retrieval_latency_ms", "INTEGER DEFAULT 0"),
            ("queries", "hop_evaluation_latency_ms", "INTEGER DEFAULT 0"),
            # Total measured latency (added 2026-02-11)
            ("queries", "total_latency_ms", "INTEGER DEFAULT 0"),
        ]

        applied_count = 0

        for table, column, column_type in migrations:
            if not column_exists(conn, table, column):
                print(f"  ➕ Adding column {table}.{column}")
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
                applied_count += 1
            else:
                print(f"  ✅ Column {table}.{column} already exists")

        conn.commit()

        # Create missing indexes
        print("\n🔍 Checking indexes...")

        indexes = [
            ("idx_cost", "queries", "cost"),
            ("idx_quote_validation_score", "queries", "quote_validation_score"),
            ("idx_rag_test_runs_sort_order", "rag_test_runs", "sort_order"),
        ]

        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        existing_indexes = {row[0] for row in cursor.fetchall()}

        for idx_name, table, column in indexes:
            if idx_name not in existing_indexes:
                print(f"  ➕ Creating index {idx_name}")
                conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})")
                applied_count += 1
            else:
                print(f"  ✅ Index {idx_name} already exists")

        conn.commit()

        # Create missing tables (if any)
        print("\n🔍 Checking tables...")

        # Check for invalid_quotes table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='invalid_quotes'"
        )
        if not cursor.fetchone():
            print("  ➕ Creating table invalid_quotes")
            conn.execute(
                """
                CREATE TABLE invalid_quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT NOT NULL,
                    quote_title TEXT,
                    quote_text TEXT NOT NULL,
                    claimed_chunk_id TEXT,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
                )
            """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_invalid_quotes_query_id ON invalid_quotes(query_id)"
            )
            applied_count += 1
        else:
            print("  ✅ Table invalid_quotes already exists")

        # Check for rag_test_runs table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rag_test_runs'"
        )
        if not cursor.fetchone():
            print("  ➕ Creating table rag_test_runs")
            conn.execute(
                """
                CREATE TABLE rag_test_runs (
                    run_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    test_set TEXT,
                    runs_per_test INTEGER,
                    avg_retrieval_time REAL,
                    avg_retrieval_cost REAL,
                    context_recall REAL,
                    avg_hops_used REAL,
                    can_answer_recall REAL,
                    full_report_md TEXT,
                    run_name TEXT DEFAULT '',
                    comments TEXT DEFAULT '',
                    favorite INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_test_runs_timestamp ON rag_test_runs(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_test_runs_test_set ON rag_test_runs(test_set)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_test_runs_favorite ON rag_test_runs(favorite)"
            )
            applied_count += 1
        else:
            print("  ✅ Table rag_test_runs already exists")

        conn.commit()

        if applied_count > 0:
            print(f"\n✅ Migration complete! Applied {applied_count} changes.")
        else:
            print("\n✅ Database is up to date! No migration needed.")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


def main():
    """Run database migration."""
    print("=" * 60)
    print("Analytics Database Migration")
    print("=" * 60)
    print()

    config = load_config()

    if not config.enable_analytics_db:
        print("⚠️  Analytics database is disabled in config (.env)")
        print("   Set ENABLE_ANALYTICS_DB=true to enable it.")
        print()
        sys.exit(0)

    db_path = config.analytics_db_path

    try:
        migrate_analytics_db(db_path)
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
