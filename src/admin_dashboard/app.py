"""Main application entry point for the admin dashboard.

This module provides a clean entry point with navigation and page routing.
"""

import streamlit as st

from src.lib.database import AnalyticsDatabase

from . import auth
from .pages import analytics, query_browser, query_detail, rag_tests, settings
from .utils.constants import PAGE_NAMES
from .utils.session import get_current_page, initialize_session_state, navigate_to_page


def configure_page() -> None:
    """Configure Streamlit page settings."""
    st.set_page_config(
        page_title="Kill Team Bot Admin Dashboard",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def initialize_database() -> AnalyticsDatabase | None:
    """Initialize and validate database connection.

    Returns:
        Database instance or None if initialization failed
    """
    try:
        db = AnalyticsDatabase.from_config()

        if not db.enabled:
            st.error("❌ Analytics database is disabled. Set ENABLE_ANALYTICS_DB=true in .env")
            return None

        return db

    except Exception as e:
        st.error(f"Failed to initialize database: {e}")
        return None


def render_sidebar(db: AnalyticsDatabase) -> None:
    """Render sidebar with navigation.

    Args:
        db: Database instance
    """
    st.sidebar.title("🤖 Kill Team Bot")
    st.sidebar.write("Admin Dashboard")

    st.sidebar.write("**Navigation**")

    pages = [
        PAGE_NAMES["QUERY_BROWSER"],
        PAGE_NAMES["QUERY_DETAIL"],
        PAGE_NAMES["ANALYTICS"],
        PAGE_NAMES["RAG_TESTS"],
        PAGE_NAMES["SETTINGS"],
    ]

    current_page = get_current_page()

    for page_option in pages:
        button_type = "primary" if current_page == page_option else "secondary"
        if st.sidebar.button(
            page_option, key=f"nav_{page_option}", type=button_type, use_container_width=True
        ):
            navigate_to_page(page_option)


def route_to_page(page: str, db: AnalyticsDatabase) -> None:
    """Route to the appropriate page renderer.

    Args:
        page: Page name to render
        db: Database instance
    """
    if page == PAGE_NAMES["QUERY_BROWSER"]:
        query_browser.render(db)
    elif page == PAGE_NAMES["QUERY_DETAIL"]:
        query_detail.render(db)
    elif page == PAGE_NAMES["ANALYTICS"]:
        analytics.render(db)
    elif page == PAGE_NAMES["RAG_TESTS"]:
        rag_tests.render(db)
    elif page == PAGE_NAMES["SETTINGS"]:
        settings.render(db)


def main() -> None:
    """Main application entry point."""
    # Configure page
    configure_page()

    # Check authentication
    if not auth.check_password():
        st.stop()

    # Initialize session state
    initialize_session_state()

    # Initialize database
    db = initialize_database()
    if not db:
        st.stop()

    # Render sidebar navigation
    render_sidebar(db)

    # Get current page and route to it
    current_page = get_current_page()
    route_to_page(current_page, db)


if __name__ == "__main__":
    main()
