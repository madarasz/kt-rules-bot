"""RAG tests page for the admin dashboard."""

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from src.lib.database import AnalyticsDatabase

from ..utils.formatters import generate_test_id


def render(db: AnalyticsDatabase) -> None:
    """Render the RAG tests page.

    Args:
        db: Database instance
    """
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

    # Generate and display YAML
    yaml_content = _generate_yaml(queries_with_chunks)
    _render_yaml_preview(yaml_content)
    _render_download_button(yaml_content)

    # Display table of test cases
    _render_test_cases_table(queries_with_chunks)


def _generate_yaml(queries_data: list[dict[str, Any]]) -> str:
    """Generate YAML content for test cases.

    Args:
        queries_data: List of query data with relevant chunks

    Returns:
        YAML formatted string
    """
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


def _render_yaml_preview(yaml_content: str) -> None:
    """Render YAML preview section.

    Args:
        yaml_content: YAML content string
    """
    st.subheader("📄 Generated YAML")
    st.code(yaml_content, language="yaml")


def _render_download_button(yaml_content: str) -> None:
    """Render download button for YAML file.

    Args:
        yaml_content: YAML content string
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label="⬇️ Download YAML file",
        data=yaml_content,
        file_name=f"rag_test_cases_{timestamp}.yaml",
        mime="text/yaml",
    )


def _render_test_cases_table(queries_with_chunks: list[dict[str, Any]]) -> None:
    """Render test cases preview table.

    Args:
        queries_with_chunks: List of query data with relevant chunks
    """
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
