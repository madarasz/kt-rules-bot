"""Filter components for the admin dashboard."""

from datetime import datetime, timedelta

import streamlit as st

from ..utils.constants import ADMIN_STATUS_OPTIONS


class QueryFilters:
    """Query filter component for the browser page."""

    def __init__(self, llm_models: list[str], servers: list[tuple[str, str]]):
        """Initialize query filters.

        Args:
            llm_models: List of available LLM models
            servers: List of (server_id, server_name) tuples
        """
        self.llm_models = ["All"] + sorted(llm_models)
        # Servers already sorted by timestamp descending in query_browser.py
        self.servers = [("All", "All")] + servers

    def render(self) -> dict:
        """Render filter UI and return filter values.

        Returns:
            Dictionary of filter values
        """
        # First row - existing filters
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            date_range = st.selectbox(
                "Date Range", ["Last 24 hours", "Last 7 days", "Last 30 days", "All time"], index=3
            )

        with col2:
            admin_status = st.selectbox("Admin Status", ["All"] + ADMIN_STATUS_OPTIONS)

        with col3:
            llm_model_filter = st.selectbox("LLM Model", self.llm_models)

        with col4:
            search_query = st.text_input("Search", placeholder="Search query text...")

        # Second row - server filter
        # Find default index for "Sector Hungaricus - Skirmish wargame community"
        default_server = "Sector Hungaricus - Skirmish wargame community"
        default_idx = next(
            (i for i, (_, name) in enumerate(self.servers) if name == default_server),
            0  # Fallback to "All"
        )

        selected_server = st.selectbox(
            "Discord Server",
            options=self.servers,
            format_func=lambda x: x[1],  # Display server name
            index=default_idx,
        )

        return self._build_filters_dict(
            date_range, admin_status, llm_model_filter, search_query, selected_server
        )

    def _build_filters_dict(
        self,
        date_range: str,
        admin_status: str,
        llm_model: str,
        search_query: str,
        server: tuple[str, str],
    ) -> dict:
        """Build filters dictionary from UI inputs.

        Args:
            date_range: Selected date range
            admin_status: Selected admin status
            llm_model: Selected LLM model
            search_query: Search query text
            server: Selected server (server_id, server_name) tuple

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

        # Server filter
        if server[0] != "All":
            filters["discord_server_id"] = server[0]

        # Date range filter
        if date_range == "Last 24 hours":
            filters["start_date"] = (datetime.utcnow() - timedelta(days=1)).isoformat()
        elif date_range == "Last 7 days":
            filters["start_date"] = (datetime.utcnow() - timedelta(days=7)).isoformat()
        elif date_range == "Last 30 days":
            filters["start_date"] = (datetime.utcnow() - timedelta(days=30)).isoformat()

        return filters
