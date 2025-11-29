"""RAG Test Results page for the admin dashboard."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_sortables import sort_items

from src.lib.database import AnalyticsDatabase

from ..utils.session import set_selected_rag_test_run

_COLUMN_WIDTHS = [0.5, 1.5, 2, 1.5, 0.8, 1, 1, 1, 0.8, 1.2, 0.5]

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

    # Reorder mode toggle
    if "reorder_mode" not in st.session_state:
        st.session_state.reorder_mode = False

    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader(f"Found {len(test_runs)} test runs")
    with col2:
        if st.button(
            "📝 Reorder Mode" if not st.session_state.reorder_mode else "✅ Done Reordering",
            use_container_width=True,
        ):
            st.session_state.reorder_mode = not st.session_state.reorder_mode
            st.rerun()

    # Show reorder mode or normal view
    if st.session_state.reorder_mode:
        _render_reorder_mode(test_runs, db)
    else:
        # Render comparison chart for favorite runs
        _render_comparison_chart(test_runs)

        # Display test runs table
        st.divider()

        # Render table header
        _render_table_header()

        # Render table with clickable rows
        for run in test_runs:
            _render_test_run_row(run, db)


def _render_reorder_mode(test_runs: list[dict], db: AnalyticsDatabase) -> None:
    """Render drag-and-drop reordering interface.

    Args:
        test_runs: List of test run dictionaries
        db: Database instance
    """
    st.info("🔄 Drag and drop to reorder test runs. Changes will affect both the table and chart order.")

    # Initialize sort_order for runs that don't have it
    needs_initialization = any(run.get("sort_order") is None for run in test_runs)
    if needs_initialization:
        st.warning(
            "⚠️ First time reordering: This will assign sort order to all runs based on their current position."
        )

    # Prepare items for sorting with display names
    items = []
    run_id_map = {}
    for run in test_runs:
        display_name = run.get("run_name") if run.get("run_name") else run["run_id"]
        fav_marker = "⭐ " if run.get("favorite", 0) else ""
        label = f"{fav_marker}{display_name}"
        items.append(label)
        run_id_map[label] = run["run_id"]

    # Render sortable list
    st.markdown("### Drag to Reorder")
    sorted_items = sort_items(items, multi_containers=False, direction="vertical")

    # Save button
    if st.button("💾 Save New Order", type="primary", use_container_width=True):
        # Create sort_order mapping (1-indexed)
        sort_orders = {}
        for idx, label in enumerate(sorted_items, start=1):
            run_id = run_id_map[label]
            sort_orders[run_id] = idx

        # Update database
        success = db.update_rag_test_runs_sort_order(sort_orders)

        if success:
            st.success("✅ Order saved successfully!")
            st.session_state.reorder_mode = False
            st.rerun()
        else:
            st.error("❌ Failed to save order. Please try again.")


def _render_comparison_chart(test_runs: list[dict]) -> None:
    """Render comparison bar chart for favorite RAG test runs.

    Displays a grouped bar chart with 4 Y-axes.

    Args:
        test_runs: List of test run dictionaries from database
    """
    # Filter to favorite runs only
    favorite_runs = [run for run in test_runs if run.get("favorite", 0)]

    if not favorite_runs:
        st.info("💡 Mark test runs as favorite (⭐) to see them in the comparison chart.")
        return

    # Prepare data
    df = pd.DataFrame(favorite_runs)

    # Reverse order for chart display (right to left)
    df = df.iloc[::-1]

    # Use run_name if available, otherwise fallback to run_id
    df["display_name"] = df.apply(
        lambda row: row["run_name"] if row.get("run_name") else row["run_id"],
        axis=1
    )

    # Create figure with secondary y-axis
    fig = go.Figure()

    # Recall bar (left y-axis) - green
    fig.add_trace(go.Bar(
        name="Recall",
        x=df["display_name"],
        y=df["context_recall"] * 100,  # Convert to percentage
        marker_color="#4CAF50",
        yaxis="y",
        offsetgroup=0
    ))

    # Hops bar (fourth y-axis, overlaid on right) - purple
    # Uses yaxis4 with custom range to scale [0,1] to match Recall [0,100]
    if "avg_hops_used" in df.columns:
        fig.add_trace(go.Bar(
            name="Hops",
            x=df["display_name"],
            y=df["avg_hops_used"],
            marker_color="#9C27B0",
            yaxis="y4",
            offsetgroup=1
        ))

    # Avg Cost bar (third y-axis, overlaid on right) - red
    # Uses yaxis3 with custom range to make bars appear 2x bigger
    if "avg_retrieval_cost" in df.columns:
        fig.add_trace(go.Bar(
            name="Avg Cost",
            x=df["display_name"],
            y=df["avg_retrieval_cost"],
            marker_color="#F44336",
            yaxis="y3",
            offsetgroup=2
        ))

    # Avg Time bar (right y-axis) - blue
    if "avg_retrieval_time" in df.columns:
        fig.add_trace(go.Bar(
            name="Avg Time",
            x=df["display_name"],
            y=df["avg_retrieval_time"],
            marker_color="#2196F3",
            yaxis="y2",
            offsetgroup=3
        ))

    max_cost = df["avg_retrieval_cost"].max() if "avg_retrieval_cost" in df.columns else 1
    max_hops = df["avg_hops_used"].max() if "avg_hops_used" in df.columns else 1
    max_hops = max_hops if max_hops > 1 else 1

    # Update layout with quad y-axes
    fig.update_layout(
        title="Favorite Test Runs Comparison",
        xaxis={"title": "Run Name"},
        yaxis={
            "title": {"text": "Recall (%)", "font": {"color": "#4CAF50"}},
            "tickfont": {"color": "#4CAF50"},
            "range": [0, 100]
        },
        yaxis2={
            "title": {"text": "Time (s)", "font": {"color": "#666666"}},
            "tickfont": {"color": "#666666"},
            "overlaying": "y",
            "side": "right"
        },
        yaxis3={
            "overlaying": "y",
            "side": "right",
            "range": [0, max_cost],
            "showticklabels": False,
            "showgrid": False
        },
        yaxis4={
            "overlaying": "y",
            "side": "right",
            "range": [0, max_hops],
            "showticklabels": False,
            "showgrid": False
        },
        barmode="group",
        height=500,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1
        }
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_table_header() -> None:
    """Render table header row."""
    col_fav, col_timestamp, col_name, col_test_set, col_runs, col_time, col_cost, col_recall, col_hops, col_can_answer, col_delete = st.columns(
        _COLUMN_WIDTHS
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
        _COLUMN_WIDTHS
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
