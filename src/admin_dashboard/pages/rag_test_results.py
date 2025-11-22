"""RAG Test Results page for the admin dashboard."""

import streamlit as st

from src.lib.database import AnalyticsDatabase

from ..utils.session import set_selected_rag_test_run


def render(db: AnalyticsDatabase) -> None:
    """Render the RAG test results page.

    Args:
        db: Database instance
    """
    st.title("📊 RAG Test Results")

    # Fetch test runs
    test_runs = db.get_all_rag_test_runs(limit=100)

    if not test_runs:
        st.info("No RAG test runs found. Run tests using `python -m src.cli quality-test` to populate results.")
        return

    # Display test runs table
    st.subheader(f"Found {len(test_runs)} test runs")

    # Render table header
    _render_table_header()

    # Render table with clickable rows
    for run in test_runs:
        _render_test_run_row(run, db)


def _render_table_header() -> None:
    """Render table header row."""
    col_fav, col_timestamp, col_name, col_test_set, col_runs, col_time, col_cost, col_recall, col_hops, col_can_answer, col_delete = st.columns(
        [0.5, 1.5, 2, 1.5, 0.8, 1, 1, 1, 0.8, 1.2, 0.5]
    )

    with col_fav:
        st.markdown("**Fav**")
    with col_timestamp:
        st.markdown("**Date**")
    with col_name:
        st.markdown("**Run Name**")
    with col_test_set:
        st.markdown("**Test Set**")
    with col_runs:
        st.markdown("**Runs**")
    with col_time:
        st.markdown("**Avg Time**")
    with col_cost:
        st.markdown("**Avg Cost**")
    with col_recall:
        st.markdown("**Recall**")
    with col_hops:
        st.markdown("**Hops**")
    with col_can_answer:
        st.markdown("**Hop Recall**")
    with col_delete:
        st.markdown("**Del**")

    st.divider()


def _render_test_run_row(run: dict, db: AnalyticsDatabase) -> None:
    """Render a single test run row.

    Args:
        run: Test run data dictionary
        db: Database instance
    """
    run_id = run["run_id"]

    # Create columns for the row
    col_fav, col_timestamp, col_name, col_test_set, col_runs, col_time, col_cost, col_recall, col_hops, col_can_answer, col_delete = st.columns(
        [0.5, 1.5, 2, 1.5, 0.8, 1, 1, 1, 0.8, 1.2, 0.5]
    )

    # Favorite toggle
    with col_fav:
        is_favorite = bool(run.get("favorite", 0))
        if st.button("⭐" if is_favorite else "☆", key=f"fav_{run_id}", help="Toggle favorite"):
            db.update_rag_test_run(run_id, favorite=not is_favorite)
            st.rerun()

    # Timestamp
    with col_timestamp:
        timestamp = run.get("timestamp", "")
        if timestamp:
            # Format timestamp for display
            timestamp_display = timestamp.split(".")[0].replace("T", " ")
            st.text(timestamp_display)
        else:
            st.text("-")

    # Run name (clickable)
    with col_name:
        run_name = run.get("run_name", "") or "(Unnamed)"
        if st.button(run_name, key=f"view_{run_id}", help="View details", use_container_width=True):
            set_selected_rag_test_run(run_id)

    # Test set
    with col_test_set:
        test_set = run.get("test_set", "-")
        st.text(test_set if test_set else "-")

    # Runs per test
    with col_runs:
        runs = run.get("runs_per_test", "-")
        st.text(str(runs) if runs else "-")

    # Avg retrieval time
    with col_time:
        time_val = run.get("avg_retrieval_time")
        if time_val is not None:
            st.text(f"{time_val:.3f}s")
        else:
            st.text("-")

    # Avg retrieval cost (in cents)
    with col_cost:
        cost_val = run.get("avg_retrieval_cost")
        if cost_val is not None:
            cost_cents = cost_val
            st.text(f"{cost_cents:.3f}¢")
        else:
            st.text("-")

    # Context recall
    with col_recall:
        recall_val = run.get("context_recall")
        if recall_val is not None:
            st.text(f"{recall_val:.2%}")
        else:
            st.text("-")

    # Avg hops used
    with col_hops:
        hops_val = run.get("avg_hops_used")
        if hops_val is not None:
            st.text(f"{hops_val:.2f}")
        else:
            st.text("-")

    # Can answer recall
    with col_can_answer:
        can_answer_val = run.get("can_answer_recall")
        if can_answer_val is not None:
            st.text(f"{can_answer_val:.2%}")
        else:
            st.text("-")

    # Delete button
    with col_delete:
        _render_delete_button(run_id, db)

    # Separator
    st.divider()


def _render_delete_button(run_id: str, db: AnalyticsDatabase) -> None:
    """Render delete button with confirmation.

    Args:
        run_id: Test run ID
        db: Database instance
    """
    confirm_key = f"confirm_delete_run_{run_id}"
    delete_key = f"delete_run_{run_id}"

    # Check if we're in confirmation mode
    if st.session_state.get(confirm_key, False):
        col_yes, col_no = st.columns(2)

        with col_yes:
            if st.button("✅", key=f"yes_{run_id}", help="Confirm delete"):
                if db.delete_rag_test_run(run_id):
                    st.success("Deleted!")
                    st.session_state[confirm_key] = False
                    st.rerun()
                else:
                    st.error("Failed to delete")

        with col_no:
            if st.button("❌", key=f"no_{run_id}", help="Cancel delete"):
                st.session_state[confirm_key] = False
                st.rerun()
    else:
        if st.button("🗑️", key=delete_key, help="Delete"):
            st.session_state[confirm_key] = True
            st.rerun()
