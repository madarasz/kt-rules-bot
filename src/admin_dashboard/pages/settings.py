"""Settings page for the admin dashboard."""

import json
from datetime import datetime

import pandas as pd
import streamlit as st

from src.lib.database import AnalyticsDatabase

from ..components.metrics import render_database_info


def render(db: AnalyticsDatabase) -> None:
    """Render the settings page.

    Args:
        db: Database instance
    """
    st.title("⚙️ Settings")

    # Database info
    st.subheader("📦 Database Information")
    stats = db.get_stats()

    render_database_info(
        db_path=db.db_path,
        total_queries=stats.get("total_queries", 0),
        retention_days=db.retention_days,
        enabled=db.enabled,
    )

    # Cleanup
    _render_cleanup_section(db)

    # Export
    _render_export_section(db)


def _render_cleanup_section(db: AnalyticsDatabase) -> None:
    """Render database cleanup section.

    Args:
        db: Database instance
    """
    st.subheader("🗑️ Database Cleanup")
    st.write(f"Delete records older than **{db.retention_days} days**")

    if st.button("🗑️ Run Cleanup Now"):
        with st.spinner("Cleaning up old records..."):
            deleted_count = db.cleanup_old_records()
        st.success(f"✅ Deleted {deleted_count} old records")


def _render_export_section(db: AnalyticsDatabase) -> None:
    """Render data export section.

    Args:
        db: Database instance
    """
    st.subheader("📦 Export Data")
    col1, col2 = st.columns(2)

    with col1:
        _render_csv_export(db)

    with col2:
        _render_json_export(db)


def _render_csv_export(db: AnalyticsDatabase) -> None:
    """Render CSV export button.

    Args:
        db: Database instance
    """
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


def _render_json_export(db: AnalyticsDatabase) -> None:
    """Render JSON export button.

    Args:
        db: Database instance
    """
    if st.button("📋 Export to JSON"):
        queries = db.get_all_queries(limit=10000)
        json_data = json.dumps(queries, indent=2, default=str)
        st.download_button(
            label="⬇️ Download JSON",
            data=json_data,
            file_name=f"queries_{datetime.utcnow().strftime('%Y%m%d')}.json",
            mime="application/json",
        )
