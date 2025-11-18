"""Session state management for the admin dashboard."""

import streamlit as st

from .constants import PAGE_NAMES


def initialize_session_state() -> None:
    """Initialize default session state values."""
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = PAGE_NAMES["QUERY_BROWSER"]


def navigate_to_page(page_name: str) -> None:
    """Navigate to a specific page.

    Args:
        page_name: Name of the page to navigate to
    """
    st.session_state["current_page"] = page_name
    st.rerun()


def set_selected_query(query_id: str) -> None:
    """Set the selected query ID and navigate to detail page.

    Args:
        query_id: Query ID to select
    """
    st.session_state["selected_query_id"] = query_id
    navigate_to_page(PAGE_NAMES["QUERY_DETAIL"])


def get_current_page() -> str:
    """Get the current page name from session state.

    Returns:
        Current page name
    """
    return st.session_state.get("current_page", PAGE_NAMES["QUERY_BROWSER"])


def get_selected_query_id() -> str | None:
    """Get the selected query ID from session state.

    Returns:
        Selected query ID or None
    """
    return st.session_state.get("selected_query_id")


def init_chunk_relevance_state(chunk_id: int, initial_value: int | None) -> None:
    """Initialize chunk relevance in session state if not present.

    Args:
        chunk_id: Chunk ID
        initial_value: Initial relevance value
    """
    key = f"chunk_relevance_{chunk_id}"
    if key not in st.session_state:
        st.session_state[key] = initial_value


def get_chunk_relevance_state(chunk_id: int) -> int | None:
    """Get chunk relevance from session state.

    Args:
        chunk_id: Chunk ID

    Returns:
        Relevance value (1, 0, or None)
    """
    key = f"chunk_relevance_{chunk_id}"
    return st.session_state.get(key)


def set_chunk_relevance_state(chunk_id: int, value: int | None) -> None:
    """Set chunk relevance in session state.

    Args:
        chunk_id: Chunk ID
        value: Relevance value (1, 0, or None)
    """
    key = f"chunk_relevance_{chunk_id}"
    st.session_state[key] = value


def init_admin_fields_state(query_id: str, status: str, notes: str) -> None:
    """Initialize admin fields in session state if not present.

    Args:
        query_id: Query ID
        status: Initial admin status
        notes: Initial admin notes
    """
    if f"admin_status_{query_id}" not in st.session_state:
        st.session_state[f"admin_status_{query_id}"] = status
    if f"admin_notes_{query_id}" not in st.session_state:
        st.session_state[f"admin_notes_{query_id}"] = notes or ""


def get_admin_status_state(query_id: str) -> str:
    """Get admin status from session state.

    Args:
        query_id: Query ID

    Returns:
        Admin status
    """
    return st.session_state.get(f"admin_status_{query_id}", "pending")


def set_admin_status_state(query_id: str, status: str) -> None:
    """Set admin status in session state.

    Args:
        query_id: Query ID
        status: Admin status
    """
    st.session_state[f"admin_status_{query_id}"] = status


def get_admin_notes_state(query_id: str) -> str:
    """Get admin notes from session state.

    Args:
        query_id: Query ID

    Returns:
        Admin notes
    """
    return st.session_state.get(f"admin_notes_{query_id}", "")


def set_admin_notes_state(query_id: str, notes: str) -> None:
    """Set admin notes in session state.

    Args:
        query_id: Query ID
        notes: Admin notes
    """
    st.session_state[f"admin_notes_{query_id}"] = notes
