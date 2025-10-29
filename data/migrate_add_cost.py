#!/usr/bin/env python3
"""Migration script to add cost column to analytics database.

Usage:
    python migrate_add_cost.py
"""

import sqlite3
from pathlib import Path

from src.lib.config import load_config
from src.lib.logging import get_logger

logger = get_logger(__name__)


def migrate_add_cost_column():
    """Add cost column to queries table."""
    config = load_config()
    db_path = config.analytics_db_path

    if not Path(db_path).exists():
        logger.error(f"Database not found at {db_path}")
        print(f"❌ Database not found at {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(queries)")
        columns = [row[1] for row in cursor.fetchall()]

        if "cost" in columns:
            print("✅ Column 'cost' already exists. No migration needed.")
            conn.close()
            return True

        print("🔄 Adding 'cost' column to queries table...")

        # Add the column
        cursor.execute("ALTER TABLE queries ADD COLUMN cost REAL DEFAULT 0.0")

        # Create the index
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cost ON queries(cost)")

        conn.commit()
        conn.close()

        print("✅ Migration completed successfully!")
        print("   - Added 'cost' column with default value 0.0")
        print("   - Created index on 'cost' column")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        print(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Migration: Add cost column to analytics database")
    print("=" * 60)
    print()

    success = migrate_add_cost_column()

    print()
    if success:
        print("🎉 You can now start the bot!")
    else:
        print("⚠️  Migration failed. Please check the logs or try manually.")
