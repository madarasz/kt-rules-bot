"""Database migration for multi-hop retrieval support.

Adds multi_hop_enabled, hops_used columns to queries table.
Adds hop_number column to retrieved_chunks table.
Creates hop_evaluations table.

Safe to run multiple times (idempotent).
"""

import sqlite3
from pathlib import Path


def migrate():
    """Run database migration."""
    db_path = Path("data/analytics.db")

    if not db_path.exists():
        print("No database found, skipping migration")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check and add queries columns
    cursor.execute("PRAGMA table_info(queries)")
    columns = [row[1] for row in cursor.fetchall()]

    if "multi_hop_enabled" not in columns:
        print("Adding multi_hop_enabled column to queries...")
        cursor.execute("""
            ALTER TABLE queries
            ADD COLUMN multi_hop_enabled INTEGER DEFAULT 0
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_multi_hop
            ON queries(multi_hop_enabled)
        """)
        print("✓ Added multi_hop_enabled")
    else:
        print("✓ multi_hop_enabled already exists")

    if "hops_used" not in columns:
        print("Adding hops_used column to queries...")
        cursor.execute("""
            ALTER TABLE queries
            ADD COLUMN hops_used INTEGER DEFAULT 0
        """)
        print("✓ Added hops_used")
    else:
        print("✓ hops_used already exists")

    # Check and add retrieved_chunks column
    cursor.execute("PRAGMA table_info(retrieved_chunks)")
    chunk_columns = [row[1] for row in cursor.fetchall()]

    if "hop_number" not in chunk_columns:
        print("Adding hop_number column to retrieved_chunks...")
        cursor.execute("""
            ALTER TABLE retrieved_chunks
            ADD COLUMN hop_number INTEGER DEFAULT 0
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_hop_number
            ON retrieved_chunks(hop_number)
        """)
        print("✓ Added hop_number to retrieved_chunks")
    else:
        print("✓ hop_number already exists in retrieved_chunks")

    # Check and create hop_evaluations table
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='hop_evaluations'
    """)

    if not cursor.fetchone():
        print("Creating hop_evaluations table...")
        cursor.execute("""
            CREATE TABLE hop_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id TEXT NOT NULL,
                hop_number INTEGER NOT NULL,
                can_answer INTEGER NOT NULL,
                reasoning TEXT NOT NULL,
                missing_query TEXT,
                evaluation_model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (query_id) REFERENCES queries(query_id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE INDEX idx_hop_eval_query_id ON hop_evaluations(query_id)
        """)
        cursor.execute("""
            CREATE INDEX idx_hop_eval_hop_num ON hop_evaluations(query_id, hop_number)
        """)
        print("✓ Created hop_evaluations table")
    else:
        print("✓ hop_evaluations table already exists")

    conn.commit()
    conn.close()
    print("\n✅ Migration complete!")


if __name__ == "__main__":
    migrate()
