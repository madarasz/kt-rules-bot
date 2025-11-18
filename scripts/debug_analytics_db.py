#!/usr/bin/env python3
"""Debug script to inspect analytics database contents."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.lib.database import AnalyticsDatabase


def main():
    """Inspect database contents."""
    print("=" * 60)
    print("Analytics Database Debug Inspector")
    print("=" * 60)
    print()

    # Initialize database
    db = AnalyticsDatabase.from_config()

    if not db.enabled:
        print("❌ Analytics database is DISABLED")
        print("   Set ENABLE_ANALYTICS_DB=true in config/.env")
        return

    print("✅ Analytics database is ENABLED")
    print(f"   Path: {db.db_path}")
    print(f"   Retention: {db.retention_days} days")
    print()

    # Get stats
    stats = db.get_stats()
    print("📊 Database Statistics:")
    print(f"   Total queries: {stats.get('total_queries', 0)}")
    print(f"   Total upvotes: {stats.get('total_upvotes', 0)}")
    print(f"   Total downvotes: {stats.get('total_downvotes', 0)}")
    print(f"   Helpful rate: {stats.get('helpful_rate', 0):.1%}")
    print()

    # Get all queries
    queries = db.get_all_queries(limit=10)

    if not queries:
        print("⚠️  No queries found in database")
        print()
        print("Possible reasons:")
        print("1. Bot hasn't processed any queries yet")
        print("2. Analytics DB was disabled when bot ran")
        print("3. Database insertion is failing (check bot logs)")
        print()
        print("To populate database:")
        print("1. Ensure ENABLE_ANALYTICS_DB=true in config/.env")
        print("2. Restart bot: python -m src.cli run")
        print("3. Ask bot a question via Discord")
        print("4. Run this script again")
        return

    print(f"📋 Recent Queries (showing {len(queries)} of {stats.get('total_queries', 0)}):")
    print()

    for i, query in enumerate(queries, 1):
        print(f"{i}. Query ID: {query['query_id'][:8]}...")
        print(f"   Timestamp: {query['timestamp']}")
        print(f"   User: @{query['username']}")
        print(f"   Query: {query['query_text'][:60]}...")
        print(f"   Response: {query['response_text'][:60]}...")
        print(f"   Model: {query['llm_model']}")
        print(f"   Feedback: {query['upvotes']}👍 / {query['downvotes']}👎")
        print(f"   Admin Status: {query['admin_status']}")

        # Check chunks
        chunks = db.get_chunks_for_query(query["query_id"])
        if chunks:
            print(f"   Chunks: {len(chunks)} retrieved")
            for j, chunk in enumerate(chunks[:3], 1):  # Show first 3
                print(f"      {j}. Rank {chunk['rank']}: {chunk['chunk_header'] or 'No header'}")
                print(f"         Score: {chunk['final_score']:.3f}")
                print(
                    f"         Vector: {chunk['vector_similarity']}, BM25: {chunk['bm25_score']}, RRF: {chunk['rrf_score']}"
                )
        else:
            print("   ⚠️  Chunks: NONE (this is the bug!)")

        print()

    # Admin status breakdown
    status_counts = stats.get("status_counts", {})
    if status_counts:
        print("📈 Admin Status Breakdown:")
        for status, count in status_counts.items():
            print(f"   {status}: {count}")
        print()

    # Chunk relevance stats
    print("🎯 Chunk Relevance Stats:")
    print(f"   Relevant: {stats.get('chunks_relevant', 0)}")
    print(f"   Not relevant: {stats.get('chunks_not_relevant', 0)}")
    print(f"   Not reviewed: {stats.get('chunks_not_reviewed', 0)}")
    print()

    print("=" * 60)
    print("✅ Inspection complete!")
    print()
    print("Next steps:")
    print("1. If no queries: Ask bot a question via Discord")
    print("2. If no chunks: Check bot logs for DB insertion errors")
    print("3. If no feedback: Click 👍/👎 reactions in Discord")
    print("4. View in dashboard: streamlit run src/cli/admin_dashboard.py")


if __name__ == "__main__":
    main()
