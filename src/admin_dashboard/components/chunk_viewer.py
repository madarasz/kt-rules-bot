"""Chunk viewer component for displaying and marking RAG chunks."""

import streamlit as st

from src.lib.database import AnalyticsDatabase

from ..utils.session import (
    get_chunk_relevance_state,
    init_chunk_relevance_state,
    set_chunk_relevance_state,
)


class ChunkViewer:
    """Component for displaying a single chunk with relevance marking."""

    def __init__(self, chunk: dict, db: AnalyticsDatabase):
        """Initialize chunk viewer.

        Args:
            chunk: Chunk data dictionary
            db: Database instance
        """
        self.chunk = chunk
        self.db = db
        self.chunk_id = chunk["id"]

    def render_table_row(self) -> None:
        """Render the chunk as a table row with inline action buttons."""
        # Initialize session state
        init_chunk_relevance_state(self.chunk_id, self.chunk["relevant"])

        # Get current relevance
        current_rel = get_chunk_relevance_state(self.chunk_id)

        # Define columns: Rank, Title, Hop, Score, Vector, BM25, RRF, Status Actions
        cols = st.columns([0.5, 3, 0.5, 0.8, 0.8, 0.8, 0.8, 1.5])

        # Rank
        with cols[0]:
            st.write(f"**{self.chunk['rank']}**")

        # Title (chunk header) with relevance indicator
        with cols[1]:
            title = self.chunk["chunk_header"] or "No header"
            prefix = "" if current_rel != 1 else "✅ "
            st.write(f"{prefix}{title}")

        # Hop number
        with cols[2]:
            hop_number = self.chunk.get("hop_number", 0)
            st.write(f"{hop_number if hop_number is not None else 0}")

        # Final Score
        with cols[3]:
            st.write(f"{self.chunk['final_score']:.3f}")

        # Vector Similarity
        with cols[4]:
            vector_sim = self.chunk["vector_similarity"]
            if vector_sim:
                st.write(f"{vector_sim:.3f}")
            else:
                st.write("0")

        # BM25 Score
        with cols[5]:
            bm25 = self.chunk["bm25_score"]
            if bm25:
                st.write(f"{bm25:.1f}")
            else:
                st.write("0")

        # RRF Score
        with cols[6]:
            rrf = self.chunk["rrf_score"]
            if rrf:
                st.write(f"{rrf:.3f}")
            else:
                st.write("0")

        # Status and Action Buttons
        with cols[7]:
            self._render_inline_relevance_controls(current_rel)

    def _render_inline_relevance_controls(self, current_rel: int | None) -> None:
        """Render inline relevance status and marking controls.

        Uses colored backgrounds to indicate current status:
        - Green: relevant (current_rel == 1)
        - Red: not relevant (current_rel == 0)
        - Blue: unknown (current_rel is None)

        Args:
            current_rel: Current relevance value
        """
        # Determine background color for the active button
        if current_rel == 1:
            active_color = "#28a745"  # Green
        elif current_rel == 0:
            active_color = "#dc3545"  # Red
        else:
            active_color = "#007bff"  # Blue

        # Inject CSS marker with unique ID to target this chunk's buttons
        marker_id = f"chunk-marker-{self.chunk_id}"
        st.markdown(
            f"""
            <style>
            #{marker_id} ~ div [data-testid="stBaseButton-primary"] button {{
                background-color: {active_color} !important;
                border-color: {active_color} !important;
            }}
            </style>
            <span id="{marker_id}" style="display:none;"></span>
            """,
            unsafe_allow_html=True,
        )

        btn_cols = st.columns(3)

        with btn_cols[0]:
            if st.button(
                "Y",
                key=f"rel_yes_{self.chunk_id}",
                help="Mark as relevant",
                type="primary" if current_rel == 1 else "secondary",
            ):
                self._update_relevance(True)

        with btn_cols[1]:
            if st.button(
                "N",
                key=f"rel_no_{self.chunk_id}",
                help="Mark as not relevant",
                type="primary" if current_rel == 0 else "secondary",
            ):
                self._update_relevance(False)

        with btn_cols[2]:
            if st.button(
                "?",
                key=f"rel_none_{self.chunk_id}",
                help="Clear relevance",
                type="primary" if current_rel is None else "secondary",
            ):
                self._update_relevance(None)

    def _update_relevance(self, value: bool | None) -> None:
        """Update chunk relevance in database and session state.

        Args:
            value: New relevance value (True, False, or None)
        """
        self.db.update_chunk_relevance(self.chunk_id, value)
        relevance_int = 1 if value is True else (0 if value is False else None)
        set_chunk_relevance_state(self.chunk_id, relevance_int)
        st.rerun()


class ChunkListViewer:
    """Component for displaying a list of chunks in a table format."""

    def __init__(self, chunks: list[dict], db: AnalyticsDatabase):
        """Initialize chunk list viewer.

        Args:
            chunks: List of chunk data dictionaries
            db: Database instance
        """
        self.chunks = chunks
        self.db = db

    def render(self) -> None:
        """Render all chunks as a table."""
        if not self.chunks:
            st.info("No chunks retrieved for this query.")
            return

        # Table header
        header_cols = st.columns([0.5, 3, 0.5, 0.8, 0.8, 0.8, 0.8, 1.5])
        with header_cols[0]:
            st.write("**#**")
        with header_cols[1]:
            st.write("**Title**")
        with header_cols[2]:
            st.write("**Hop**")
        with header_cols[3]:
            st.write("**Score**")
        with header_cols[4]:
            st.write("**Vector**")
        with header_cols[5]:
            st.write("**BM25**")
        with header_cols[6]:
            st.write("**RRF**")
        with header_cols[7]:
            st.write("**Status**")

        st.divider()

        # Table rows
        for i, chunk in enumerate(self.chunks):
            viewer = ChunkViewer(chunk, self.db)
            viewer.render_table_row()
            # Add border between rows (except after the last row)
            if i < len(self.chunks) - 1:
                st.markdown(
                    '<hr style="margin: 0.5rem 0; border: none; '
                    'border-top: 1px solid rgba(128, 128, 128, 0.3);">',
                    unsafe_allow_html=True,
                )
