"""Query browser page for the admin dashboard."""

import pandas as pd
import streamlit as st

from src.lib.database import AnalyticsDatabase

from ..components.filters import QueryFilters
from ..components.query_card import QueryCard
from ..utils.session import set_selected_query


def render(db: AnalyticsDatabase) -> None:
    """Render the query browser page.

    Args:
        db: Database instance
    """
    st.title("📋 Query Browser")

    # Get available LLM models
    all_queries = db.get_all_queries(limit=1000)
    llm_models = {q["llm_model"] for q in all_queries}

    # Render filters
    filters_component = QueryFilters(list(llm_models))
    filters = filters_component.render()

    # Fetch filtered queries
    queries = db.get_all_queries(filters=filters, limit=100)

    if not queries:
        st.info("No queries found matching filters.")
        return

    # Display query cards
    st.subheader(f"Found {len(queries)} queries")

    for query in queries:
        card = QueryCard(query, db)
        card.render()

    # Query selector at the bottom
    _render_query_selector(queries, db)


def _render_query_selector(queries: list[dict], db: AnalyticsDatabase) -> None:
    """Render query selector dropdown with view button.

    Args:
        queries: List of query data dictionaries
        db: Database instance
    """
    st.subheader("View Query Details")

    df = pd.DataFrame(queries)
    df["query_preview"] = df["query_text"].str[:80] + "..."

    selected_query_id = st.selectbox(
        "Select query to view",
        options=[q["query_id"] for q in queries],
        format_func=lambda qid: df[df["query_id"] == qid]["query_preview"].iloc[0],
        key="query_selector",
    )

    if st.button("View Details", type="primary"):
        set_selected_query(selected_query_id)
