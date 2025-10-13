"""Admin dashboard for query analytics and review.

Streamlit web UI for reviewing queries, responses, feedback, and RAG chunks.
Password-protected access.

Usage:
    streamlit run src/cli/admin_dashboard.py --server.port 8501
"""

import sys
from pathlib import Path

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Dict, List

from src.lib.database import AnalyticsDatabase
from src.lib.config import load_config


# Page configuration
st.set_page_config(
    page_title="Kill Team Bot Admin Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


def check_password() -> bool:
    """Returns True if user entered correct password."""

    def password_entered():
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
        st.text_input(
            "Password",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.info("Enter the admin dashboard password from your .env configuration")
        return False

    # Password incorrect
    elif not st.session_state["password_correct"]:
        st.title("🔒 Admin Dashboard Login")
        st.text_input(
            "Password",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.error("😕 Password incorrect")
        return False

    # Password correct
    else:
        return True


def render_query_browser(db: AnalyticsDatabase):
    """Render the query browser page."""
    st.title("📋 Query Browser")

    # Filters
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        date_range = st.selectbox(
            "Date Range",
            ["Last 24 hours", "Last 7 days", "Last 30 days", "All time"],
        )

    with col2:
        admin_status = st.selectbox(
            "Admin Status",
            ["All", "pending", "approved", "reviewed", "issues", "flagged"],
        )

    with col3:
        # Get unique LLM models from DB
        all_queries = db.get_all_queries(limit=1000)
        llm_models = ["All"] + sorted(list(set(q["llm_model"] for q in all_queries)))
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
    for idx, query in enumerate(queries):
        with st.container():
            col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 3, 1, 1, 1, 1, 1])
            
            with col1:
                st.write(f"**{pd.to_datetime(query['timestamp']).strftime('%Y-%m-%d %H:%M')}**")
            
            with col2:
                preview = query["query_text"][:80] + "..." if len(query["query_text"]) > 80 else query["query_text"]
                st.write(preview)
            
            with col3:
                # Admin status with color coding
                status_color = {
                    "pending": "🟡",
                    "approved": "🟢", 
                    "reviewed": "🔵",
                    "issues": "🟠",
                    "flagged": "🔴"
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
        st.write(f"**Feedback:** ⬆️ {query['upvotes']} / ⬇️ {query['downvotes']} ({helpful_rate:.0%} helpful)")

    # Retrieved chunks
    st.subheader("📚 Retrieved Chunks")

    if chunks:
        for chunk in chunks:
            with st.expander(
                f"Rank {chunk['rank']}: {chunk['chunk_header'] or 'No header'} "
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
                    st.write(f"**Vector Sim:** {chunk['vector_similarity']:.3f}" if chunk['vector_similarity'] else "N/A")
                    st.write(f"**BM25:** {chunk['bm25_score']:.1f}" if chunk['bm25_score'] else "N/A")
                    st.write(f"**RRF:** {chunk['rrf_score']:.3f}" if chunk['rrf_score'] else "N/A")
                    st.write(f"**Final:** {chunk['final_score']:.3f}")

                    # Relevance buttons
                    st.write("**Relevant?**")
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        if st.button("✓", key=f"rel_yes_{chunk['id']}"):
                            db.update_chunk_relevance(chunk['id'], True)
                            st.success("Marked relevant")
                            st.rerun()
                    with col_b:
                        if st.button("✗", key=f"rel_no_{chunk['id']}"):
                            db.update_chunk_relevance(chunk['id'], False)
                            st.success("Marked not relevant")
                            st.rerun()
                    with col_c:
                        if st.button("?", key=f"rel_none_{chunk['id']}"):
                            db.update_chunk_relevance(chunk['id'], None)
                            st.success("Cleared relevance")
                            st.rerun()

                    # Show current relevance
                    if chunk['relevant'] == 1:
                        st.success("✓ Relevant")
                    elif chunk['relevant'] == 0:
                        st.error("✗ Not relevant")
                    else:
                        st.info("? Not reviewed")
    else:
        st.info("No chunks retrieved for this query.")

    # Admin controls
    st.subheader("🗒️ Admin Controls")

    col1, col2 = st.columns(2)

    with col1:
        new_status = st.selectbox(
            "Admin Status",
            ["pending", "approved", "reviewed", "issues", "flagged"],
            index=["pending", "approved", "reviewed", "issues", "flagged"].index(query["admin_status"]),
        )

    with col2:
        new_notes = st.text_area(
            "Admin Notes",
            value=query["admin_notes"] or "",
            height=100,
        )

    if st.button("💾 Save Changes"):
        db.update_query_admin_fields(
            query_id=query_id,
            admin_status=new_status,
            admin_notes=new_notes,
        )
        st.success("Changes saved!")
        st.rerun()


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
    status_data = pd.DataFrame(
        list(stats["status_counts"].items()),
        columns=["Status", "Count"]
    )
    fig = px.pie(
        status_data,
        names="Status",
        values="Count",
        title="Queries by Admin Status",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Feedback over time
    st.subheader("📉 Feedback Trends")
    queries = db.get_all_queries(limit=1000)
    if queries:
        df = pd.DataFrame(queries)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = df["timestamp"].dt.date

        daily_feedback = df.groupby("date").agg({
            "upvotes": "sum",
            "downvotes": "sum",
        }).reset_index()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=daily_feedback["date"],
            y=daily_feedback["upvotes"],
            mode="lines+markers",
            name="Upvotes",
            line=dict(color="green"),
        ))
        fig.add_trace(go.Scatter(
            x=daily_feedback["date"],
            y=daily_feedback["downvotes"],
            mode="lines+markers",
            name="Downvotes",
            line=dict(color="red"),
        ))
        fig.update_layout(
            title="Daily Feedback Trends",
            xaxis_title="Date",
            yaxis_title="Count",
        )
        st.plotly_chart(fig, use_container_width=True)

    # LLM model performance
    st.subheader("🤖 LLM Model Performance")
    if queries:
        model_stats = df.groupby("llm_model").agg({
            "query_id": "count",
            "confidence_score": "mean",
            "upvotes": "sum",
            "downvotes": "sum",
        }).reset_index()
        model_stats.columns = ["Model", "Queries", "Avg Confidence", "Upvotes", "Downvotes"]
        model_stats["Helpful Rate"] = model_stats["Upvotes"] / (model_stats["Upvotes"] + model_stats["Downvotes"])
        model_stats["Helpful Rate"] = model_stats["Helpful Rate"].fillna(0)

        fig = px.bar(
            model_stats,
            x="Model",
            y="Helpful Rate",
            title="Helpful Rate by LLM Model",
            color="Helpful Rate",
            color_continuous_scale="RdYlGn",
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(model_stats, use_container_width=True, hide_index=True)

    # Top downvoted queries
    st.subheader("🚨 Top 10 Most Downvoted Queries")
    if queries:
        top_downvoted = df.nlargest(10, "downvotes")[[
            "timestamp",
            "query_text",
            "upvotes",
            "downvotes",
            "confidence_score",
            "admin_status",
            "query_id",
        ]]
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
            import json
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

    # Check if page navigation was triggered programmatically
    if "current_page" in st.session_state:
        page = st.session_state["current_page"]
        # Clear the programmatic navigation after using it
        del st.session_state["current_page"]
    else:
        page = st.sidebar.radio(
            "Navigation",
            ["📋 Query Browser", "🔍 Query Detail", "📊 Analytics", "⚙️ Settings"],
            key="page_selector",
        )

    # Render selected page
    if page == "📋 Query Browser":
        render_query_browser(db)
    elif page == "🔍 Query Detail":
        render_query_detail(db)
    elif page == "📊 Analytics":
        render_analytics(db)
    elif page == "⚙️ Settings":
        render_settings(db)


if __name__ == "__main__":
    main()
