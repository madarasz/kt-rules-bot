"""Filter components for the admin dashboard."""

from datetime import datetime, timedelta

import streamlit as st

from ..utils.constants import ADMIN_STATUS_OPTIONS


class QueryFilters:
    """Query filter component for the browser page."""

    def __init__(self, llm_models: list[str]):
        """Initialize query filters.

        Args:
            llm_models: List of available LLM models
        """
        self.llm_models = ["All"] + sorted(llm_models)

    def render(self) -> dict:
        """Render filter UI and return filter values.

        Returns:
            Dictionary of filter values
        """
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            date_range = st.selectbox(
                "Date Range",
                ["Last 24 hours", "Last 7 days", "Last 30 days", "All time"],
                index=3,
            )

        with col2:
            admin_status = st.selectbox("Admin Status", ["All"] + ADMIN_STATUS_OPTIONS)

        with col3:
            llm_model_filter = st.selectbox("LLM Model", self.llm_models)

        with col4:
            search_query = st.text_input("Search", placeholder="Search query text...")

        return self._build_filters_dict(date_range, admin_status, llm_model_filter, search_query)

    def _build_filters_dict(
        self, date_range: str, admin_status: str, llm_model: str, search_query: str
    ) -> dict:
        """Build filters dictionary from UI inputs.

        Args:
            date_range: Selected date range
            admin_status: Selected admin status
            llm_model: Selected LLM model
            search_query: Search query text

        Returns:
            Dictionary of filter values for database query
        """
        filters = {}

        if admin_status != "All":
            filters["admin_status"] = admin_status

        if llm_model != "All":
            filters["llm_model"] = llm_model

        if search_query:
            filters["search"] = search_query

        # Date range filter
        if date_range == "Last 24 hours":
            filters["start_date"] = (datetime.utcnow() - timedelta(days=1)).isoformat()
        elif date_range == "Last 7 days":
            filters["start_date"] = (datetime.utcnow() - timedelta(days=7)).isoformat()
        elif date_range == "Last 30 days":
            filters["start_date"] = (datetime.utcnow() - timedelta(days=30)).isoformat()

        return filters
