"""Deletion confirmation component for the admin dashboard."""

import streamlit as st

from src.lib.database import AnalyticsDatabase


class DeletionButton:
    """Reusable deletion button with confirmation."""

    def __init__(self, item_id: str, item_type: str = "query"):
        """Initialize deletion button.

        Args:
            item_id: Unique identifier for the item
            item_type: Type of item being deleted (for key generation)
        """
        self.item_id = item_id
        self.item_type = item_type
        self.delete_key = f"delete_{item_type}_{item_id}"
        self.confirm_key = f"confirm_delete_{item_type}_{item_id}"

    def render(self, db: AnalyticsDatabase, callback: callable = None) -> None:
        """Render deletion button with confirmation.

        Args:
            db: Database instance for deletion
            callback: Optional callback to execute on successful deletion
        """
        # Check if we're in confirmation mode
        if self.confirm_key in st.session_state and st.session_state[self.confirm_key]:
            self._render_confirmation(db, callback)
        else:
            self._render_delete_button()

    def _render_delete_button(self) -> None:
        """Render initial delete button."""
        if st.button("🗑️", key=self.delete_key, help="Delete"):
            st.session_state[self.confirm_key] = True
            st.rerun()

    def _render_confirmation(self, db: AnalyticsDatabase, callback: callable = None) -> None:
        """Render confirmation buttons.

        Args:
            db: Database instance for deletion
            callback: Optional callback to execute on successful deletion
        """
        col_yes, col_no = st.columns(2)

        with col_yes:
            if st.button("✅", key=f"yes_{self.item_id}", help="Confirm delete"):
                if db.delete_query(self.item_id):
                    st.success("Deleted successfully!")
                    st.session_state[self.confirm_key] = False
                    if callback:
                        callback()
                    st.rerun()
                else:
                    st.error("Failed to delete")

        with col_no:
            if st.button("❌", key=f"no_{self.item_id}", help="Cancel delete"):
                st.session_state[self.confirm_key] = False
                st.rerun()
