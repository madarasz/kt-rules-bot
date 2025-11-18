"""Metric display components for the admin dashboard."""

import streamlit as st


def render_overview_metrics(stats: dict) -> None:
    """Render overview metrics in a 4-column layout.

    Args:
        stats: Dictionary of statistics from database
    """
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Queries", stats["total_queries"])

    with col2:
        st.metric("Avg Latency", f"{stats['avg_latency_ms']:.0f}ms")

    with col3:
        st.metric("Helpful Rate", f"{stats['helpful_rate']:.0%}")

    with col4:
        total_feedback = stats["total_upvotes"] + stats["total_downvotes"]
        st.metric("Total Feedback", total_feedback)


def render_cost_metrics(total_cost: float, avg_cost: float) -> None:
    """Render cost metrics in a 2-column layout.

    Args:
        total_cost: Total cost across all queries
        avg_cost: Average cost per query
    """
    col1, col2 = st.columns(2)

    with col1:
        st.metric("Total Cost", f"${total_cost:.5f}")

    with col2:
        st.metric("Avg Cost/Query", f"${avg_cost:.5f}")


def render_chunk_relevance_metrics(stats: dict) -> None:
    """Render chunk relevance metrics.

    Args:
        stats: Dictionary of statistics from database
    """
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Relevant Chunks", stats["chunks_relevant"])

    with col2:
        st.metric("Not Relevant Chunks", stats["chunks_not_relevant"])

    with col3:
        st.metric("Not Reviewed Chunks", stats["chunks_not_reviewed"])

    total_reviewed = stats["chunks_relevant"] + stats["chunks_not_relevant"]
    if total_reviewed > 0:
        relevance_rate = stats["chunks_relevant"] / total_reviewed
        st.info(f"📈 Relevance Rate: {relevance_rate:.1%} (of reviewed chunks)")


def render_database_info(
    db_path: str, total_queries: int, retention_days: int, enabled: bool
) -> None:
    """Render database information metrics.

    Args:
        db_path: Path to database file
        total_queries: Total number of queries
        retention_days: Number of days records are retained
        enabled: Whether analytics database is enabled
    """
    col1, col2 = st.columns(2)

    with col1:
        st.write(f"**Database Path:** `{db_path}`")
        st.write(f"**Total Queries:** {total_queries}")

    with col2:
        st.write(f"**Retention Days:** {retention_days}")
        st.write(f"**Database Enabled:** {'✅ Yes' if enabled else '❌ No'}")
