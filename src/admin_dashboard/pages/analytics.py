"""Analytics page for the admin dashboard."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.lib.database import AnalyticsDatabase

from ..components.metrics import render_cost_metrics, render_overview_metrics
from ..components.server_selector import render_server_selector
from ..utils.formatters import format_timestamp
from ..utils.icons import get_quote_validation_icon
from ..utils.session import set_selected_query


def render(db: AnalyticsDatabase) -> None:
    """Render the analytics page.

    Args:
        db: Database instance
    """
    st.title("📊 Analytics Dashboard")

    # Extract server list from all queries (same logic as query_browser.py)
    all_queries = db.get_all_queries(limit=1000)

    if not all_queries:
        st.info("No analytics data available yet.")
        return

    servers_dict: dict[tuple[str, str], str] = {}
    for q in all_queries:
        if q.get("discord_server_name") and q.get("discord_server_id"):
            server_key = (q["discord_server_id"], q["discord_server_name"])
            timestamp = q.get("timestamp", "")
            if server_key not in servers_dict or timestamp > servers_dict[server_key]:
                servers_dict[server_key] = timestamp

    # Sort servers by timestamp descending (most recent first)
    servers_list = sorted(servers_dict.keys(), key=lambda x: servers_dict[x], reverse=True)

    # Render server selector
    selected_server = render_server_selector(servers_list)
    server_filter = selected_server[0] if selected_server[0] != "All" else None

    # Get filtered stats
    stats = db.get_stats(discord_server_id=server_filter)

    if not stats:
        st.info("No analytics data available yet.")
        return

    # Overview metrics
    render_overview_metrics(stats)

    # Get filtered queries for charts
    filters = {"discord_server_id": server_filter} if server_filter else None
    queries = db.get_all_queries(filters=filters, limit=1000)

    if not queries:
        st.info("No queries available for detailed analytics.")
        return

    df = pd.DataFrame(queries)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date

    _render_admin_status_and_latency(stats, df)
    _render_feedback_trends(df)
    _render_cost_analysis(df)
    _render_llm_model_performance(df)
    _render_top_downvoted_queries(df)
    _render_quote_hallucinations(df)
    _render_top_users(df)

    # Chunk relevance stats
    #st.subheader("🎯 RAG Chunk Relevance Analysis")
    #render_chunk_relevance_metrics(stats)


def _render_admin_status_and_latency(stats: dict, df: pd.DataFrame) -> None:
    """Render admin status distribution and latency breakdown charts side by side.

    Args:
        stats: Statistics dictionary
        df: DataFrame of queries
    """
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📈 Admin Status Distribution")
        status_data = pd.DataFrame(
            list(stats["status_counts"].items()), columns=["Status", "Count"]
        )
        fig = px.pie(status_data, names="Status", values="Count", title="Queries by Admin Status")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("⏱️ Latency Breakdown")
        _render_latency_breakdown_chart(df)


def _render_latency_breakdown_chart(df: pd.DataFrame) -> None:
    """Render latency breakdown pie chart.

    Args:
        df: DataFrame of queries
    """
    # Calculate average latencies
    avg_retrieval = df["retrieval_latency_ms"].mean() if "retrieval_latency_ms" in df else 0
    avg_hop_eval = df["hop_evaluation_latency_ms"].mean() if "hop_evaluation_latency_ms" in df else 0
    avg_llm = df["latency_ms"].mean() if "latency_ms" in df else 0
    avg_total = df["total_latency_ms"].mean() if "total_latency_ms" in df else 0

    # Handle NaN values
    avg_retrieval = avg_retrieval if pd.notna(avg_retrieval) else 0
    avg_hop_eval = avg_hop_eval if pd.notna(avg_hop_eval) else 0
    avg_llm = avg_llm if pd.notna(avg_llm) else 0
    avg_total = avg_total if pd.notna(avg_total) else 0

    # Calculate "other" time if total is available
    component_sum = avg_retrieval + avg_hop_eval + avg_llm
    avg_other = max(0, avg_total - component_sum) if avg_total > 0 else 0

    # Build data for pie chart
    latency_data = []
    if avg_retrieval > 0:
        latency_data.append({"Component": "Retrieval", "Latency (ms)": avg_retrieval})
    if avg_hop_eval > 0:
        latency_data.append({"Component": "Hop Evaluation", "Latency (ms)": avg_hop_eval})
    if avg_llm > 0:
        latency_data.append({"Component": "LLM", "Latency (ms)": avg_llm})
    if avg_other > 10:  # Only show if meaningful (> 10ms)
        latency_data.append({"Component": "Other", "Latency (ms)": avg_other})

    if not latency_data:
        st.info("No latency data available.")
        return

    latency_df = pd.DataFrame(latency_data)
    fig = px.pie(
        latency_df,
        names="Component",
        values="Latency (ms)",
        title="Average Latency by Component",
    )
    # Show labels with component name, value and percentage
    fig.update_traces(
        textposition="inside",
        textinfo="label+percent",
        hovertemplate="%{label}: %{value:.0f}ms (%{percent})<extra></extra>",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Show breakdown as text for small values
    total_latency = sum(item["Latency (ms)"] for item in latency_data)
    breakdown_text = " | ".join(
        f"{item['Component']}: {item['Latency (ms)']:.0f}ms ({item['Latency (ms)']/total_latency*100:.1f}%)"
        for item in latency_data
    )
    st.caption(breakdown_text)


def _render_feedback_trends(df: pd.DataFrame) -> None:
    """Render feedback trends chart aggregated by week.

    Args:
        df: DataFrame of queries
    """
    st.subheader("📉 Feedback Trends")

    weekly_feedback = (
        df.resample("W-Mon", on="timestamp").agg({"upvotes": "sum", "downvotes": "sum"}).reset_index()
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=weekly_feedback["timestamp"],
            y=weekly_feedback["upvotes"],
            mode="lines+markers",
            name="Upvotes",
            line={"color": "green"},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=weekly_feedback["timestamp"],
            y=weekly_feedback["downvotes"],
            mode="lines+markers",
            name="Downvotes",
            line={"color": "red"},
        )
    )
    fig.update_layout(title="Weekly Feedback Trends", xaxis_title="Week", yaxis_title="Count")
    st.plotly_chart(fig, use_container_width=True)


def _render_cost_analysis(df: pd.DataFrame) -> None:
    """Render cost analysis charts aggregated by week.

    Args:
        df: DataFrame of queries
    """
    st.subheader("💰 Weekly Cost Breakdown")

    weekly_costs = df.resample("W-Mon", on="timestamp").agg({"cost": "sum"}).reset_index()

    fig = px.bar(
        weekly_costs,
        x="timestamp",
        y="cost",
        title="Weekly Query Costs (USD)",
        labels={"cost": "Total Cost (USD)", "timestamp": "Week"},
    )
    fig.update_traces(marker_color="#4CAF50")
    fig.update_layout(xaxis_title="Week", yaxis_title="Cost (USD)", yaxis_tickformat="$.5f")
    st.plotly_chart(fig, use_container_width=True)

    # Show total cost metrics
    total_cost = df["cost"].sum()
    avg_cost_per_query = df["cost"].mean()
    render_cost_metrics(total_cost, avg_cost_per_query)


def _render_llm_model_performance(df: pd.DataFrame) -> None:
    """Render LLM model performance table.

    Args:
        df: DataFrame of queries
    """
    st.subheader("🤖 LLM Model Performance")

    model_stats = (
        df.groupby("llm_model")
        .agg(
            queries=("query_id", "count"),
            avg_quote_validation=("quote_validation_score", "mean"),
            upvotes=("upvotes", "sum"),
            downvotes=("downvotes", "sum"),
            total_cost=("cost", "sum"),
            avg_cost=("cost", "mean"),
            avg_latency=("latency_ms", "mean"),
        )
        .reset_index()
    )
    model_stats.columns = [
        "Model",
        "Queries",
        "Avg Quote Validation",
        "Upvotes",
        "Downvotes",
        "Total Cost",
        "Avg Cost/Query",
        "Avg LLM Latency",
    ]
    model_stats["Helpful Rate"] = model_stats["Upvotes"] / (
        model_stats["Upvotes"] + model_stats["Downvotes"]
    )
    model_stats["Helpful Rate"] = model_stats["Helpful Rate"].fillna(0)

    # Format quote validation as percentage
    model_stats["Avg Quote Validation"] = model_stats["Avg Quote Validation"].apply(
        lambda x: f"{x:.1%}" if pd.notna(x) else "N/A"
    )

    # Format cost columns as currency
    model_stats["Total Cost"] = model_stats["Total Cost"].apply(
        lambda x: f"${x:.5f}" if pd.notna(x) else "N/A"
    )
    model_stats["Avg Cost/Query"] = model_stats["Avg Cost/Query"].apply(
        lambda x: f"${x:.5f}" if pd.notna(x) else "N/A"
    )

    # Format latency column
    model_stats["Avg LLM Latency"] = model_stats["Avg LLM Latency"].apply(
        lambda x: f"{x:.0f} ms" if pd.notna(x) else "N/A"
    )

    # Reorder columns to put Helpful Rate before Upvotes
    model_stats = model_stats[
        [
            "Model",
            "Queries",
            "Avg Quote Validation",
            "Helpful Rate",
            "Upvotes",
            "Downvotes",
            "Total Cost",
            "Avg Cost/Query",
            "Avg LLM Latency",
        ]
    ]

    st.dataframe(model_stats, use_container_width=True, hide_index=True)


def _render_top_downvoted_queries(df: pd.DataFrame) -> None:
    """Render top downvoted queries table with clickable links.

    Args:
        df: DataFrame of queries
    """
    st.subheader("🚨 Top 50 Most Downvoted Queries")

    top_downvoted = df[df["downvotes"] > 0].nlargest(50, "downvotes")[
        [
            "timestamp",
            "query_text",
            "fixed_issue",
            "admin_status",
            "upvotes",
            "downvotes",
            "query_id",
        ]
    ].copy()

    if top_downvoted.empty:
        st.info("No downvoted queries found.")
        return

    # Render header row
    col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 4, 1, 1, 1, 1, 1])
    with col1:
        st.write("**Timestamp**")
    with col2:
        st.write("**Query**")
    with col3:
        st.write("**Fixed**")
    with col4:
        st.write("**Status**")
    with col5:
        st.write("**👍**")
    with col6:
        st.write("**👎**")
    with col7:
        st.write("**View**")

    # Render each row
    for _, row in top_downvoted.iterrows():
        _render_downvoted_query_row(row)


def _render_downvoted_query_row(row: pd.Series) -> None:
    """Render a single downvoted query row.

    Args:
        row: Pandas Series representing a query row
    """
    col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 4, 1, 1, 1, 1, 1])

    with col1:
        st.write(format_timestamp(row["timestamp"]))

    with col2:
        query_preview = (
            row["query_text"][:60] + "..." if len(row["query_text"]) > 60 else row["query_text"]
        )
        st.write(query_preview)

    with col3:
        st.write("\u2705" if row["fixed_issue"] else "")

    with col4:
        st.write(row["admin_status"])

    with col5:
        st.write(str(row["upvotes"]))

    with col6:
        st.write(str(row["downvotes"]))

    with col7:
        if st.button("👁️", key=f"view_downvoted_{row['query_id']}", help="View details"):
            set_selected_query(row["query_id"])


def _render_quote_hallucinations(df: pd.DataFrame) -> None:
    """Render quote hallucinations section.

    Args:
        df: DataFrame of queries
    """
    st.subheader("⚠️ Quote Hallucinations")

    # Filter for queries with quote validation score < 1.0
    hallucination_queries = df[
        (df["quote_validation_score"].notna()) & (df["quote_validation_score"] < 1.0)
    ].copy()

    if hallucination_queries.empty:
        st.success("✅ No quote hallucinations detected!")
        return

    # Prepare display data
    hallucination_queries["validation_display"] = hallucination_queries.apply(
        lambda row: f"{get_quote_validation_icon(row['quote_validation_score'], row['quote_valid_count'], row['quote_total_count'])} "
        f"{row['quote_validation_score']:.0%} "
        f"({row['quote_valid_count']}/{row['quote_total_count']} valid)",
        axis=1,
    )

    # Sort by validation score (worst first)
    hallucination_queries = hallucination_queries.sort_values("quote_validation_score")

    # Display clickable table
    for _, row in hallucination_queries.iterrows():
        _render_hallucination_row(row)

    st.info(f"📊 Found {len(hallucination_queries)} queries with quote validation issues")


def _render_hallucination_row(row: pd.Series) -> None:
    """Render a single hallucination row.

    Args:
        row: Pandas Series representing a query row
    """
    col1, col2, col3, col4, col5 = st.columns([2, 4, 2, 2, 1])

    with col1:
        st.write(format_timestamp(row["timestamp"]))

    with col2:
        query_preview = (
            row["query_text"][:80] + "..." if len(row["query_text"]) > 80 else row["query_text"]
        )
        st.write(query_preview)

    with col3:
        st.write(row["llm_model"])

    with col4:
        st.write(row["validation_display"])

    with col5:
        if st.button("👁️", key=f"view_halluc_{row['query_id']}", help="View details"):
            set_selected_query(row["query_id"])


def _render_top_users(df: pd.DataFrame) -> None:
    """Render table of most active users by query count.

    Args:
        df: DataFrame of queries
    """
    st.subheader("👥 Top Active Users")

    if "username" not in df.columns:
        st.info("No user data available.")
        return

    user_queries = (
        df.groupby("username")
        .agg(queries=("query_id", "count"))
        .reset_index()
        .sort_values("queries", ascending=False)
    )
    user_queries.columns = ["User", "Number of Queries"]

    if user_queries.empty:
        st.info("No user data available.")
        return

    st.dataframe(user_queries, use_container_width=True, hide_index=True)
