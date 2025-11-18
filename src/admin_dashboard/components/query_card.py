"""Query card component for displaying query information."""

import streamlit as st

from src.lib.database import AnalyticsDatabase

from ..utils.constants import ADMIN_STATUS_COLORS
from ..utils.formatters import format_confidence_score, format_feedback, format_timestamp, truncate_text
from ..utils.icons import get_quote_validation_icon
from ..utils.session import set_selected_query
from .deletion import DeletionButton


class QueryCard:
    """Component for displaying a single query in a card format."""

    def __init__(self, query: dict, db: AnalyticsDatabase):
        """Initialize query card.

        Args:
            query: Query data dictionary
            db: Database instance
        """
        self.query = query
        self.db = db

    def render(self) -> None:
        """Render the query card."""
        with st.container():
            cols = st.columns([2, 3, 1, 1, 1, 1, 0.7, 0.7, 1, 0.5])

            self._render_timestamp(cols[0])
            self._render_query_preview(cols[1])
            self._render_status(cols[2])
            self._render_feedback(cols[3])
            self._render_model(cols[4])
            self._render_confidence(cols[5])
            self._render_hops(cols[6])
            self._render_quote_validation(cols[7])
            self._render_view_button(cols[8])
            self._render_delete_button(cols[9])

            st.divider()

    def _render_timestamp(self, col) -> None:
        """Render timestamp column."""
        with col:
            timestamp = format_timestamp(self.query["timestamp"])
            st.write(f"**{timestamp}**")

    def _render_query_preview(self, col) -> None:
        """Render query preview column."""
        with col:
            preview = truncate_text(self.query["query_text"], max_length=80)
            st.write(preview)

    def _render_status(self, col) -> None:
        """Render admin status column."""
        with col:
            status = self.query["admin_status"]
            icon = ADMIN_STATUS_COLORS.get(status, "⚪")
            st.write(f"{icon} {status}")

    def _render_feedback(self, col) -> None:
        """Render feedback column."""
        with col:
            feedback = format_feedback(self.query["upvotes"], self.query["downvotes"])
            st.write(feedback)

    def _render_model(self, col) -> None:
        """Render LLM model column."""
        with col:
            st.write(self.query["llm_model"])

    def _render_confidence(self, col) -> None:
        """Render confidence score column."""
        with col:
            score = format_confidence_score(self.query.get("confidence_score"))
            st.write(score)

    def _render_hops(self, col) -> None:
        """Render hop count column."""
        with col:
            hops_used = self.query.get("hops_used", 0)
            if hops_used > 0:
                st.write(f"🔄 {hops_used}")
            else:
                st.write("-")

    def _render_quote_validation(self, col) -> None:
        """Render quote validation column."""
        with col:
            quote_score = self.query.get("quote_validation_score")
            quote_icon = get_quote_validation_icon(
                quote_score,
                self.query.get("quote_valid_count"),
                self.query.get("quote_total_count"),
            )
            st.write(quote_icon)

    def _render_view_button(self, col) -> None:
        """Render view button column."""
        with col:
            if st.button("👁️", key=f"view_{self.query['query_id']}", help="View details"):
                set_selected_query(self.query["query_id"])

    def _render_delete_button(self, col) -> None:
        """Render delete button column."""
        with col:
            deletion_btn = DeletionButton(self.query["query_id"], item_type="query")
            deletion_btn.render(self.db)
