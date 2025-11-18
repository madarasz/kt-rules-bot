"""Analytics page for the admin dashboard."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.lib.database import AnalyticsDatabase

from ..components.metrics import (
    render_chunk_relevance_metrics,
    render_cost_metrics,
    render_overview_metrics,
)
from ..utils.formatters import format_timestamp
from ..utils.icons import get_quote_validation_icon
from ..utils.session import set_selected_query


def render(db: AnalyticsDatabase) -> None:
    """Render the analytics page.

    Args:
        db: Database instance
    """
    st.title("📊 Analytics Dashboard")

    # Get stats
    stats = db.get_stats()

    if not stats:
        st.info("No analytics data available yet.")
        return

    # Overview metrics
    render_overview_metrics(stats)

    # Charts and detailed analytics
    queries = db.get_all_queries(limit=1000)

    if not queries:
        st.info("No queries available for detailed analytics.")
        return

    df = pd.DataFrame(queries)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date

    _render_admin_status_distribution(stats)
    _render_feedback_trends(df)
    _render_cost_analysis(df)
    _render_llm_model_performance(df)
    _render_top_downvoted_queries(df)
    _render_quote_hallucinations(df, db)

    # Chunk relevance stats
    st.subheader("🎯 RAG Chunk Relevance Analysis")
    render_chunk_relevance_metrics(stats)


def _render_admin_status_distribution(stats: dict) -> None:
    """Render admin status distribution chart.

    Args:
        stats: Statistics dictionary
    """
    st.subheader("📈 Admin Status Distribution")
    status_data = pd.DataFrame(list(stats["status_counts"].items()), columns=["Status", "Count"])
    fig = px.pie(status_data, names="Status", values="Count", title="Queries by Admin Status")
    st.plotly_chart(fig, use_container_width=True)


def _render_feedback_trends(df: pd.DataFrame) -> None:
    """Render feedback trends chart.

    Args:
        df: DataFrame of queries
    """
    st.subheader("📉 Feedback Trends")

    daily_feedback = df.groupby("date").agg({"upvotes": "sum", "downvotes": "sum"}).reset_index()

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


def _render_cost_analysis(df: pd.DataFrame) -> None:
    """Render cost analysis charts.

    Args:
        df: DataFrame of queries
    """
    st.subheader("💰 Daily Cost Breakdown")

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
            {
                "query_id": "count",
                "quote_validation_score": "mean",
                "upvotes": "sum",
                "downvotes": "sum",
            }
        )
        .reset_index()
    )
    model_stats.columns = ["Model", "Queries", "Avg Quote Validation", "Upvotes", "Downvotes"]
    model_stats["Helpful Rate"] = model_stats["Upvotes"] / (
        model_stats["Upvotes"] + model_stats["Downvotes"]
    )
    model_stats["Helpful Rate"] = model_stats["Helpful Rate"].fillna(0)

    # Format quote validation as percentage
    model_stats["Avg Quote Validation"] = model_stats["Avg Quote Validation"].apply(
        lambda x: f"{x:.1%}" if pd.notna(x) else "N/A"
    )

    st.dataframe(model_stats, use_container_width=True, hide_index=True)


def _render_top_downvoted_queries(df: pd.DataFrame) -> None:
    """Render top downvoted queries table.

    Args:
        df: DataFrame of queries
    """
    st.subheader("🚨 Top 10 Most Downvoted Queries")

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


def _render_quote_hallucinations(df: pd.DataFrame, db: AnalyticsDatabase) -> None:
    """Render quote hallucinations section.

    Args:
        df: DataFrame of queries
        db: Database instance
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
