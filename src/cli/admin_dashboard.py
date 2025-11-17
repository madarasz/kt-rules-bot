"""Admin dashboard for query analytics and review.

Streamlit web UI for reviewing queries, responses, feedback, and RAG chunks.
Password-protected access.

Usage:
    streamlit run src/cli/admin_dashboard.py --server.port 8501
"""
# ruff: noqa: E402

import sys
from pathlib import Path

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import json
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.lib.config import load_config
from src.lib.database import AnalyticsDatabase
from src.models.structured_response import StructuredLLMResponse

# Constants
ADMIN_STATUS_OPTIONS = [
    "pending",
    "approved",
    "reviewed",
    "issues",
    "flagged",
    "RAG issue",
    "LLM issue",
]


# Page configuration
st.set_page_config(
    page_title="Kill Team Bot Admin Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


def check_password() -> bool:
    """Returns True if user entered correct password."""

    def password_entered() -> None:
        """Check if entered password is correct."""
        config = load_config()
        if st.session_state["password"] == config.admin_dashboard_password:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    # First run or not logged in
    if "password_correct" not in st.session_state:
        st.title("🔒 Admin Dashboard Login")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.info("Enter the admin dashboard password from your .env configuration")
        return False

    # Password incorrect
    elif not st.session_state["password_correct"]:
        st.title("🔒 Admin Dashboard Login")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("😕 Password incorrect")
        return False

    # Password correct
    else:
        return True


def render_query_browser(db: AnalyticsDatabase) -> None:
    """Render the query browser page."""
    st.title("📋 Query Browser")

    # Filters
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        date_range = st.selectbox(
            "Date Range", ["Last 24 hours", "Last 7 days", "Last 30 days", "All time"], index=3
        )

    with col2:
        admin_status = st.selectbox("Admin Status", ["All"] + ADMIN_STATUS_OPTIONS)

    with col3:
        # Get unique LLM models from DB
        all_queries = db.get_all_queries(limit=1000)
        llm_models = ["All"] + sorted({q["llm_model"] for q in all_queries})
        llm_model_filter = st.selectbox("LLM Model", llm_models)

    with col4:
        search_query = st.text_input("Search", placeholder="Search query text...")

    # Build filters dict
    filters = {}

    if admin_status != "All":
        filters["admin_status"] = admin_status

    if llm_model_filter != "All":
        filters["llm_model"] = llm_model_filter

    if search_query:
        filters["search"] = search_query

    # Date range filter
    if date_range == "Last 24 hours":
        filters["start_date"] = (datetime.utcnow() - timedelta(days=1)).isoformat()
    elif date_range == "Last 7 days":
        filters["start_date"] = (datetime.utcnow() - timedelta(days=7)).isoformat()
    elif date_range == "Last 30 days":
        filters["start_date"] = (datetime.utcnow() - timedelta(days=30)).isoformat()

    # Fetch queries
    queries = db.get_all_queries(filters=filters, limit=100)

    if not queries:
        st.info("No queries found matching filters.")
        return

    # Display as table with delete buttons
    st.subheader(f"Found {len(queries)} queries")

    # Create DataFrame for display
    df = pd.DataFrame(queries)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["query_preview"] = df["query_text"].str[:80] + "..."
    df["feedback"] = df["upvotes"].astype(str) + "👍 / " + df["downvotes"].astype(str) + "👎"
    df["confidence"] = df["confidence_score"].round(2)

    # Display queries in individual rows with delete buttons
    for _idx, query in enumerate(queries):
        with st.container():
            col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns(
                [2, 3, 1, 1, 1, 1, 0.7, 1, 0.5]
            )

            with col1:
                st.write(f"**{pd.to_datetime(query['timestamp']).strftime('%Y-%m-%d %H:%M')}**")

            with col2:
                preview = (
                    query["query_text"][:80] + "..."
                    if len(query["query_text"]) > 80
                    else query["query_text"]
                )
                st.write(preview)

            with col3:
                # Admin status with color coding
                status_color = {
                    "pending": "🟡",
                    "approved": "🟢",
                    "reviewed": "🔵",
                    "issues": "🟠",
                    "flagged": "🔴",
                    "RAG issue": "🟣",
                    "LLM issue": "🟤",
                }
                st.write(f"{status_color.get(query['admin_status'], '⚪')} {query['admin_status']}")

            with col4:
                feedback_text = f"{query['upvotes']}👍 / {query['downvotes']}👎"
                st.write(feedback_text)

            with col5:
                st.write(query["llm_model"])

            with col6:
                conf_score = query.get("confidence_score")
                if conf_score is not None:
                    st.write(f"{conf_score:.2f}")
                else:
                    st.write("N/A")

            with col7:
                # Hop count
                hops_used = query.get("hops_used", 0)
                if hops_used > 0:
                    st.write(f"🔄 {hops_used}")
                else:
                    st.write("-")

            with col8:
                # View button to navigate to detail
                if st.button("👁️", key=f"view_{query['query_id']}", help="View details"):
                    st.session_state["selected_query_id"] = query["query_id"]
                    st.session_state["current_page"] = "🔍 Query Detail"
                    st.rerun()

            with col9:
                # Delete button with confirmation
                delete_key = f"delete_{query['query_id']}"
                confirm_key = f"confirm_delete_{query['query_id']}"

                if confirm_key in st.session_state and st.session_state[confirm_key]:
                    # Show confirmation buttons
                    col_yes, col_no = st.columns(2)
                    with col_yes:
                        if st.button("✅", key=f"yes_{query['query_id']}", help="Confirm delete"):
                            if db.delete_query(query["query_id"]):
                                st.success("Query deleted!")
                                # Reset confirmation state
                                st.session_state[confirm_key] = False
                                st.rerun()
                            else:
                                st.error("Failed to delete query")
                    with col_no:
                        if st.button("❌", key=f"no_{query['query_id']}", help="Cancel delete"):
                            st.session_state[confirm_key] = False
                            st.rerun()
                else:
                    # Show delete button
                    if st.button("🗑️", key=delete_key, help="Delete query"):
                        st.session_state[confirm_key] = True
                        st.rerun()

            st.divider()

    # View details button
    st.subheader("View Query Details")
    selected_query_id = st.selectbox(
        "Select query to view",
        options=[q["query_id"] for q in queries],
        format_func=lambda qid: df[df["query_id"] == qid]["query_preview"].iloc[0],
        key="query_selector",
    )

    if st.button("View Details", type="primary"):
        st.session_state["selected_query_id"] = selected_query_id
        st.session_state["current_page"] = "🔍 Query Detail"
        st.rerun()


def bool_to_icon(value: bool) -> str:
    if value is True:
        return "✅"
    return "❌"


def render_query_detail(db: AnalyticsDatabase):
    """Render the query detail page."""
    st.title("🔍 Query Detail")

    # Back button
    if st.button("⬅️ Back to Query Browser"):
        st.session_state["current_page"] = "📋 Query Browser"
        st.rerun()

    # Get query ID from URL or session state
    query_id = st.session_state.get("selected_query_id")

    if not query_id:
        st.info("Select a query from the Query Browser to view details.")
        return

    # Fetch query
    query = db.get_query_by_id(query_id)
    if not query:
        st.error(f"Query not found: {query_id}")
        return

    # Fetch chunks
    chunks = db.get_chunks_for_query(query_id)

    # Display query info
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📝 Query Text")
        st.text_area("Query", value=query["query_text"], height=100, disabled=True)

        st.subheader("🤖 Response Text")
        try:
            structuredResponse = StructuredLLMResponse.from_json(query["response_text"])
            st.write(f"**smalltalk:** {bool_to_icon(structuredResponse.smalltalk)}")
            st.write(f"**short answer:** {structuredResponse.short_answer}")
            st.write(f"**persona short answer:** *{structuredResponse.persona_short_answer}*")
            for quote in structuredResponse.quotes:
                st.write(f"> **{quote.quote_title}**\n> {quote.quote_text}")
            st.write(f"**explanation:** {structuredResponse.explanation}")
            st.write(f"**persona afterword:** *{structuredResponse.persona_afterword}*")

        except ValueError:
            st.text_area("Response", value=query["response_text"], height=200, disabled=True)

    with col2:
        st.subheader("📊 Metadata")
        st.write(f"**Query ID:** `{query['query_id'][:8]}...`")
        st.write(f"**Timestamp:** {query['timestamp']}")
        st.write(f"**Channel:** {query['channel_name']} ({query['discord_server_name']})")
        st.write(f"**User:** @{query['username']}")
        st.write(f"**Model:** {query['llm_model']}")
        st.write(f"**Confidence:** {query['confidence_score']:.2f}")
        st.write(f"**RAG Score:** {query['rag_score']:.2f}")
        st.write(f"**Latency:** {query['latency_ms']}ms")
        st.write(f"**Validation:** {'✅ Passed' if query['validation_passed'] else '❌ Failed'}")

        # Feedback
        total_votes = query["upvotes"] + query["downvotes"]
        helpful_rate = query["upvotes"] / total_votes if total_votes > 0 else 0
        st.write(
            f"**Feedback:** ⬆️ {query['upvotes']} / ⬇️ {query['downvotes']} ({helpful_rate:.0%} helpful)"
        )

        # Multi-hop info
        multi_hop_enabled = query.get("multi_hop_enabled", 0)
        hops_used = query.get("hops_used", 0)
        if multi_hop_enabled:
            st.write(f"**Multi-Hop:** 🔄 {hops_used} hops")
        else:
            st.write("**Multi-Hop:** Disabled")

        # Cost
        cost = query.get("cost", 0.0)
        st.write(f"**Cost:** ${cost:.5f}")

    # Hop evaluations (if multi-hop was used)
    if query.get("hops_used", 0) > 0:
        st.subheader("🔄 Multi-Hop Evaluations")
        hop_evaluations = db.get_hop_evaluations_for_query(query_id)

        if hop_evaluations:
            for hop_eval in hop_evaluations:
                hop_num = hop_eval["hop_number"]
                can_answer = "✅ Can answer" if hop_eval["can_answer"] else "❌ Cannot answer"

                with st.expander(f"Hop {hop_num}: {can_answer}"):
                    st.write(f"**Reasoning:** {hop_eval['reasoning']}")
                    if hop_eval.get("missing_query"):
                        st.write(f"**Missing Query:** {hop_eval['missing_query']}")
                    if hop_eval.get("evaluation_model"):
                        st.write(f"**Model:** {hop_eval['evaluation_model']}")
                    if hop_eval.get("timestamp"):
                        st.write(f"**Timestamp:** {hop_eval['timestamp']}")
        else:
            st.info("No hop evaluations recorded (may be an older query)")

    # Retrieved chunks
    st.subheader("📚 Retrieved Chunks")

    if chunks:
        for chunk in chunks:
            # Initialize session state for chunk relevance if needed (for icon display)
            chunk_rel_key = f"chunk_relevance_{chunk['id']}"
            if chunk_rel_key not in st.session_state:
                st.session_state[chunk_rel_key] = chunk["relevant"]

            # Determine status icon based on relevance
            current_rel = st.session_state[chunk_rel_key]
            if current_rel == 1:
                status_icon = "✅"
            elif current_rel == 0:
                status_icon = "❌"
            else:
                status_icon = "⍰"

            # Add hop number to the expander title
            hop_number = chunk.get("hop_number", 0)
            hop_label = f" [Hop {hop_number}]" if hop_number is not None else ""

            with st.expander(
                f"{status_icon} Rank {chunk['rank']}: {chunk['chunk_header'] or 'No header'}{hop_label} "
                f"(Score: {chunk['final_score']:.2f})"
            ):
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.write(f"**Document:** {chunk['document_name']}")
                    st.write(f"**Type:** {chunk['document_type']}")
                    st.text_area(
                        "Preview",
                        value=chunk["chunk_text"],
                        height=150,
                        disabled=True,
                        key=f"chunk_{chunk['id']}",
                    )

                with col2:
                    st.write(
                        f"**Vector Sim:** {chunk['vector_similarity']:.3f}"
                        if chunk["vector_similarity"]
                        else "N/A"
                    )
                    st.write(
                        f"**BM25:** {chunk['bm25_score']:.1f}" if chunk["bm25_score"] else "N/A"
                    )
                    st.write(f"**RRF:** {chunk['rrf_score']:.3f}" if chunk["rrf_score"] else "N/A")
                    st.write(f"**Final:** {chunk['final_score']:.3f}")

                    # Show current relevance status first (already initialized above)
                    current_rel = st.session_state[chunk_rel_key]
                    st.write("**Status:**")
                    if current_rel == 1:
                        st.success("✓ Relevant")
                    elif current_rel == 0:
                        st.error("✗ Not relevant")
                    else:
                        st.info("? Not reviewed")

                    # Relevance buttons - use unique keys per chunk
                    st.write("**Mark as:**")
                    col_a, col_b, col_c = st.columns(3)

                    # Check which button was clicked in this render cycle
                    button_clicked_key = f"chunk_button_clicked_{chunk['id']}"

                    with col_a:
                        if st.button(
                            "✓",
                            key=f"rel_yes_{chunk['id']}",
                            help="Mark as relevant",
                            type="primary" if current_rel == 1 else "secondary",
                        ):
                            db.update_chunk_relevance(chunk["id"], True)
                            st.session_state[chunk_rel_key] = 1
                            st.session_state[button_clicked_key] = True
                            st.rerun()
                    with col_b:
                        if st.button(
                            "✗",
                            key=f"rel_no_{chunk['id']}",
                            help="Mark as not relevant",
                            type="primary" if current_rel == 0 else "secondary",
                        ):
                            db.update_chunk_relevance(chunk["id"], False)
                            st.session_state[chunk_rel_key] = 0
                            st.session_state[button_clicked_key] = True
                            st.rerun()
                    with col_c:
                        if st.button(
                            "?",
                            key=f"rel_none_{chunk['id']}",
                            help="Clear relevance",
                            type="primary" if current_rel is None else "secondary",
                        ):
                            db.update_chunk_relevance(chunk["id"], None)
                            st.session_state[chunk_rel_key] = None
                            st.session_state[button_clicked_key] = True
                            st.rerun()
    else:
        st.info("No chunks retrieved for this query.")

    # Admin controls
    st.subheader("🗒️ Admin Controls")

    # Initialize session state for admin fields if not present
    if f"admin_status_{query_id}" not in st.session_state:
        st.session_state[f"admin_status_{query_id}"] = query["admin_status"]
    if f"admin_notes_{query_id}" not in st.session_state:
        st.session_state[f"admin_notes_{query_id}"] = query["admin_notes"] or ""

    col1, col2 = st.columns(2)

    with col1:
        new_status = st.selectbox(
            "Admin Status",
            ADMIN_STATUS_OPTIONS,
            index=ADMIN_STATUS_OPTIONS.index(st.session_state[f"admin_status_{query_id}"]),
            key=f"status_select_{query_id}",
        )
        # Update session state when selectbox changes
        st.session_state[f"admin_status_{query_id}"] = new_status

    with col2:
        new_notes = st.text_area(
            "Admin Notes",
            value=st.session_state[f"admin_notes_{query_id}"],
            height=100,
            key=f"notes_area_{query_id}",
        )
        # Update session state when text area changes
        st.session_state[f"admin_notes_{query_id}"] = new_notes

    # Show save button if there are changes
    has_changes = new_status != query["admin_status"] or new_notes != (query["admin_notes"] or "")

    col_save, col_reset = st.columns([1, 4])
    with col_save:
        if st.button("💾 Save Changes", type="primary", disabled=not has_changes):
            db.update_query_admin_fields(
                query_id=query_id, admin_status=new_status, admin_notes=new_notes
            )
            # Update the session state to reflect saved values
            st.session_state[f"admin_status_{query_id}"] = new_status
            st.session_state[f"admin_notes_{query_id}"] = new_notes
            st.success("✅ Changes saved successfully!")
            # Force reload of query data by removing session state for this query
            # (this will refresh the query on next rerun)
            # Don't navigate away, just show success message

    if has_changes:
        st.info("💡 You have unsaved changes. Click 'Save Changes' to persist them.")


def render_analytics(db: AnalyticsDatabase):
    """Render the analytics page."""
    st.title("📊 Analytics Dashboard")

    # Get stats
    stats = db.get_stats()

    if not stats:
        st.info("No analytics data available yet.")
        return

    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Queries", stats["total_queries"])

    with col2:
        st.metric("Avg Latency", f"{stats['avg_latency_ms']:.0f}ms")

    with col3:
        st.metric("Helpful Rate", f"{stats['helpful_rate']:.0%}")

    with col4:
        total_feedback = stats["total_upvotes"] + stats["total_downvotes"]
        st.metric("Total Feedback", total_feedback)

    # Admin status distribution
    st.subheader("📈 Admin Status Distribution")
    status_data = pd.DataFrame(list(stats["status_counts"].items()), columns=["Status", "Count"])
    fig = px.pie(status_data, names="Status", values="Count", title="Queries by Admin Status")
    st.plotly_chart(fig, use_container_width=True)

    # Feedback over time
    st.subheader("📉 Feedback Trends")
    queries = db.get_all_queries(limit=1000)
    if queries:
        df = pd.DataFrame(queries)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = df["timestamp"].dt.date

        daily_feedback = (
            df.groupby("date").agg({"upvotes": "sum", "downvotes": "sum"}).reset_index()
        )

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=daily_feedback["date"],
                y=daily_feedback["upvotes"],
                mode="lines+markers",
                name="Upvotes",
                line={"color": "green"},
            )
        )
        fig.add_trace(
            go.Scatter(
                x=daily_feedback["date"],
                y=daily_feedback["downvotes"],
                mode="lines+markers",
                name="Downvotes",
                line={"color": "red"},
            )
        )
        fig.update_layout(title="Daily Feedback Trends", xaxis_title="Date", yaxis_title="Count")
        st.plotly_chart(fig, use_container_width=True)

    # Cost over time
    st.subheader("💰 Daily Cost Breakdown")
    if queries:
        daily_costs = df.groupby("date").agg({"cost": "sum"}).reset_index()

        fig = px.bar(
            daily_costs,
            x="date",
            y="cost",
            title="Daily Query Costs (USD)",
            labels={"cost": "Total Cost (USD)", "date": "Date"},
        )
        fig.update_traces(marker_color="#4CAF50")
        fig.update_layout(xaxis_title="Date", yaxis_title="Cost (USD)", yaxis_tickformat="$.5f")
        st.plotly_chart(fig, use_container_width=True)

        # Show total cost
        total_cost = df["cost"].sum()
        avg_cost_per_query = df["cost"].mean()
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Cost", f"${total_cost:.5f}")
        with col2:
            st.metric("Avg Cost/Query", f"${avg_cost_per_query:.5f}")

    # LLM model performance
    st.subheader("🤖 LLM Model Performance")
    if queries:
        model_stats = (
            df.groupby("llm_model")
            .agg(
                {
                    "query_id": "count",
                    "confidence_score": "mean",
                    "upvotes": "sum",
                    "downvotes": "sum",
                }
            )
            .reset_index()
        )
        model_stats.columns = ["Model", "Queries", "Avg Confidence", "Upvotes", "Downvotes"]
        model_stats["Helpful Rate"] = model_stats["Upvotes"] / (
            model_stats["Upvotes"] + model_stats["Downvotes"]
        )
        model_stats["Helpful Rate"] = model_stats["Helpful Rate"].fillna(0)

        st.dataframe(model_stats, use_container_width=True, hide_index=True)

    # Top downvoted queries
    st.subheader("🚨 Top 10 Most Downvoted Queries")
    if queries:
        top_downvoted = df.nlargest(10, "downvotes")[
            [
                "timestamp",
                "query_text",
                "upvotes",
                "downvotes",
                "confidence_score",
                "admin_status",
                "query_id",
            ]
        ]
        st.dataframe(top_downvoted, use_container_width=True, hide_index=True)

    # Chunk relevance stats
    st.subheader("🎯 RAG Chunk Relevance Analysis")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Relevant Chunks", stats["chunks_relevant"])

    with col2:
        st.metric("Not Relevant Chunks", stats["chunks_not_relevant"])

    with col3:
        st.metric("Not Reviewed Chunks", stats["chunks_not_reviewed"])

    total_reviewed = stats["chunks_relevant"] + stats["chunks_not_relevant"]
    if total_reviewed > 0:
        relevance_rate = stats["chunks_relevant"] / total_reviewed
        st.info(f"📈 Relevance Rate: {relevance_rate:.1%} (of reviewed chunks)")


def render_rag_tests(db: AnalyticsDatabase):
    """Render the RAG tests page."""
    st.title("🧪 RAG Tests")

    st.write("""
    Generate RAG test cases from queries with relevant chunks marked by admin.
    Test cases are ordered by timestamp (newest first).
    """)

    # Fetch queries with relevant chunks
    queries_with_chunks = db.get_queries_with_relevant_chunks(limit=500)

    if not queries_with_chunks:
        st.info(
            "No queries with relevant chunks found. Mark chunks as relevant in Query Detail to generate test cases."
        )
        return

    st.success(f"Found {len(queries_with_chunks)} queries with relevant chunks")

    # Generate YAML
    def generate_test_id(query_text: str) -> str:
        """Generate test_id from first 3 words of query."""
        words = query_text.lower().split()[:3]
        return "-".join(word.strip(".,!?;:") for word in words)

    def generate_yaml(queries_data: list[dict[str, Any]]) -> str:
        """Generate YAML content for test cases."""
        yaml_lines = []

        for query_data in queries_data:
            test_id = generate_test_id(query_data["query_text"])
            query_text = query_data["query_text"]

            # Get chunk headers (required_chunks)
            chunk_headers = [
                chunk["chunk_header"] or "No header" for chunk in query_data["relevant_chunks"]
            ]

            # Format YAML entry
            yaml_lines.append(f"- test_id: {test_id}")
            yaml_lines.append("  query: >")

            # Format multi-line query text (indent by 4 spaces)
            for line in query_text.split("\n"):
                yaml_lines.append(f"    {line}")

            yaml_lines.append("  required_chunks:")
            for header in chunk_headers:
                # Escape quotes in header
                escaped_header = header.replace('"', '\\"')
                yaml_lines.append(f'    - "{escaped_header}"')

        return "\n".join(yaml_lines)

    yaml_content = generate_yaml(queries_with_chunks)

    # Display YAML preview
    st.subheader("📄 Generated YAML")
    st.code(yaml_content, language="yaml")

    # Download button
    st.download_button(
        label="⬇️ Download YAML file",
        data=yaml_content,
        file_name=f"rag_test_cases_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.yaml",
        mime="text/yaml",
    )

    # Display table of test cases
    st.subheader("📊 Test Cases Preview")

    test_cases_data = []
    for query_data in queries_with_chunks:
        test_id = generate_test_id(query_data["query_text"])
        chunk_count = len(query_data["relevant_chunks"])
        chunk_headers = ", ".join(
            [chunk["chunk_header"] or "No header" for chunk in query_data["relevant_chunks"]]
        )

        test_cases_data.append(
            {
                "Test ID": test_id,
                "Query": query_data["query_text"][:100] + "..."
                if len(query_data["query_text"]) > 100
                else query_data["query_text"],
                "Timestamp": query_data["timestamp"],
                "Relevant Chunks": chunk_count,
                "Chunk Headers": chunk_headers[:100] + "..."
                if len(chunk_headers) > 100
                else chunk_headers,
            }
        )

    df = pd.DataFrame(test_cases_data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_settings(db: AnalyticsDatabase):
    """Render the settings page."""
    st.title("⚙️ Settings")

    # Database info
    st.subheader("📦 Database Information")

    stats = db.get_stats()

    col1, col2 = st.columns(2)

    with col1:
        st.write(f"**Database Path:** `{db.db_path}`")
        st.write(f"**Total Queries:** {stats.get('total_queries', 0)}")

    with col2:
        st.write(f"**Retention Days:** {db.retention_days}")
        st.write(f"**Database Enabled:** {'✅ Yes' if db.enabled else '❌ No'}")

    # Cleanup
    st.subheader("🗑️ Database Cleanup")
    st.write(f"Delete records older than **{db.retention_days} days**")

    if st.button("🗑️ Run Cleanup Now"):
        with st.spinner("Cleaning up old records..."):
            deleted_count = db.cleanup_old_records()
        st.success(f"✅ Deleted {deleted_count} old records")

    # Export
    st.subheader("📦 Export Data")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("📄 Export to CSV"):
            queries = db.get_all_queries(limit=10000)
            df = pd.DataFrame(queries)
            csv = df.to_csv(index=False)
            st.download_button(
                label="⬇️ Download CSV",
                data=csv,
                file_name=f"queries_{datetime.utcnow().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

    with col2:
        if st.button("📋 Export to JSON"):
            queries = db.get_all_queries(limit=10000)
            json_data = json.dumps(queries, indent=2, default=str)
            st.download_button(
                label="⬇️ Download JSON",
                data=json_data,
                file_name=f"queries_{datetime.utcnow().strftime('%Y%m%d')}.json",
                mime="application/json",
            )


def main():
    """Main dashboard application."""

    # Check password
    if not check_password():
        st.stop()

    # Initialize database
    try:
        db = AnalyticsDatabase.from_config()

        if not db.enabled:
            st.error("❌ Analytics database is disabled. Set ENABLE_ANALYTICS_DB=true in .env")
            st.stop()

    except Exception as e:
        st.error(f"Failed to initialize database: {e}")
        st.stop()

    # Sidebar navigation
    st.sidebar.title("🤖 Kill Team Bot")
    st.sidebar.write("Admin Dashboard")

    # Initialize current_page in session state if not present
    if "current_page" not in st.session_state:
        st.session_state["current_page"] = "📋 Query Browser"

    # Use sidebar buttons instead of radio to have better control
    st.sidebar.write("**Navigation**")

    pages = ["📋 Query Browser", "🔍 Query Detail", "📊 Analytics", "🧪 RAG Tests", "⚙️ Settings"]

    for page_option in pages:
        # Highlight current page
        button_type = "primary" if st.session_state["current_page"] == page_option else "secondary"
        if st.sidebar.button(
            page_option, key=f"nav_{page_option}", type=button_type, use_container_width=True
        ):
            st.session_state["current_page"] = page_option
            st.rerun()

    page = st.session_state["current_page"]

    # Render selected page
    if page == "📋 Query Browser":
        render_query_browser(db)
    elif page == "🔍 Query Detail":
        render_query_detail(db)
    elif page == "📊 Analytics":
        render_analytics(db)
    elif page == "🧪 RAG Tests":
        render_rag_tests(db)
    elif page == "⚙️ Settings":
        render_settings(db)


if __name__ == "__main__":
    main()
