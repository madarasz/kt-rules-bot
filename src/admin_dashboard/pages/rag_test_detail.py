"""RAG Test Detail page for the admin dashboard."""

import streamlit as st

from src.lib.database import AnalyticsDatabase

from ..utils.constants import PAGE_NAMES
from ..utils.session import get_selected_rag_test_run, navigate_to_page


def render(db: AnalyticsDatabase) -> None:
    """Render the RAG test detail page.

    Args:
        db: Database instance
    """
    st.title("🔬 RAG Test Detail")

    # Back button
    if st.button("⬅️ Back to RAG Test Results"):
        navigate_to_page(PAGE_NAMES["RAG_TEST_RESULTS"])

    # Get run ID
    run_id = get_selected_rag_test_run()
    if not run_id:
        st.info("Select a test run from RAG Test Results to view details.")
        return

    # Fetch test run
    run = db.get_rag_test_run_by_id(run_id)
    if not run:
        st.error(f"Test run not found: {run_id}")
        return

    # Render sections
    _render_editable_fields(run_id, run, db)
    _render_full_report(run)


def _render_editable_fields(run_id: str, run: dict, db: AnalyticsDatabase) -> None:
    """Render editable fields for the test run.

    Args:
        run_id: Test run ID
        run: Test run data dictionary
        db: Database instance
    """
    st.subheader("📝 Test Run Information")

    # Initialize session state for editable fields
    if f"run_name_{run_id}" not in st.session_state:
        st.session_state[f"run_name_{run_id}"] = run.get("run_name", "")
    if f"comments_{run_id}" not in st.session_state:
        st.session_state[f"comments_{run_id}"] = run.get("comments", "")
    if f"favorite_{run_id}" not in st.session_state:
        st.session_state[f"favorite_{run_id}"] = bool(run.get("favorite", 0))

    # Create form layout
    col1, col2 = st.columns([3, 1])

    with col1:
        # Test run name
        new_run_name = st.text_input(
            "Test Run Name",
            value=st.session_state[f"run_name_{run_id}"],
            key=f"input_run_name_{run_id}",
            help="Give this test run a descriptive name",
        )
        st.session_state[f"run_name_{run_id}"] = new_run_name

        # Comments
        new_comments = st.text_area(
            "Comments",
            value=st.session_state[f"comments_{run_id}"],
            key=f"input_comments_{run_id}",
            height=100,
            help="Add notes about this test run",
        )
        st.session_state[f"comments_{run_id}"] = new_comments

    with col2:
        # Favorite checkbox
        new_favorite = st.checkbox(
            "⭐ Favorite",
            value=st.session_state[f"favorite_{run_id}"],
            key=f"input_favorite_{run_id}",
            help="Mark as favorite",
        )
        st.session_state[f"favorite_{run_id}"] = new_favorite

        # Display metadata
        st.write("**Run ID:**")
        st.code(run_id, language=None)

        st.write("**Timestamp:**")
        st.text(run.get("timestamp", "N/A"))

    # Check if values have changed
    has_changes = (
        new_run_name != run.get("run_name", "")
        or new_comments != run.get("comments", "")
        or new_favorite != bool(run.get("favorite", 0))
    )

    # Update button
    if st.button("💾 Update", disabled=not has_changes, type="primary"):
        db.update_rag_test_run(
            run_id,
            run_name=new_run_name,
            comments=new_comments,
            favorite=new_favorite,
        )
        st.success("Test run updated successfully!")
        st.rerun()

    st.divider()


def _render_full_report(run: dict) -> None:
    """Render the full test report markdown.

    Args:
        run: Test run data dictionary
    """
    st.subheader("📊 Test Report")

    full_report = run.get("full_report_md", "")

    if not full_report:
        st.info("No report available for this test run.")
        return

    # Display the markdown report
    # Replace single newlines with <br> tags for proper line breaks in markdown
    # This ensures metrics display on separate lines
    report_with_breaks = full_report.replace('\n', '  \n')  # Two spaces + newline = line break in markdown

    st.markdown(report_with_breaks, unsafe_allow_html=True)
