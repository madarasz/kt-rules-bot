"""Chunk viewer component for displaying and marking RAG chunks."""

import streamlit as st

from src.lib.database import AnalyticsDatabase

from ..utils.icons import get_chunk_relevance_icon
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

    def render(self) -> None:
        """Render the chunk viewer."""
        # Initialize session state
        init_chunk_relevance_state(self.chunk_id, self.chunk["relevant"])

        # Get current relevance
        current_rel = get_chunk_relevance_state(self.chunk_id)

        # Render expander with status icon
        status_icon = get_chunk_relevance_icon(current_rel)
        hop_label = self._get_hop_label()

        with st.expander(
            f"{status_icon} Rank {self.chunk['rank']}: {self.chunk['chunk_header'] or 'No header'}{hop_label} "
            f"(Score: {self.chunk['final_score']:.2f})"
        ):
            col1, col2 = st.columns([3, 1])

            with col1:
                self._render_chunk_info()

            with col2:
                self._render_scores()
                self._render_relevance_controls(current_rel)

    def _get_hop_label(self) -> str:
        """Get hop number label for the chunk.

        Returns:
            Hop label string or empty string
        """
        hop_number = self.chunk.get("hop_number", 0)
        return f" [Hop {hop_number}]" if hop_number is not None else ""

    def _render_chunk_info(self) -> None:
        """Render chunk information (document, type, preview)."""
        st.write(f"**Document:** {self.chunk['document_name']}")
        st.write(f"**Type:** {self.chunk['document_type']}")
        st.text_area(
            "Preview",
            value=self.chunk["chunk_text"],
            height=150,
            disabled=True,
            key=f"chunk_{self.chunk_id}",
        )

    def _render_scores(self) -> None:
        """Render chunk scoring information."""
        # Vector similarity
        if self.chunk["vector_similarity"]:
            st.write(f"**Vector Sim:** {self.chunk['vector_similarity']:.3f}")
        else:
            st.write("**Vector Sim:** N/A")

        # BM25 score
        if self.chunk["bm25_score"]:
            st.write(f"**BM25:** {self.chunk['bm25_score']:.1f}")
        else:
            st.write("**BM25:** N/A")

        # RRF score
        if self.chunk["rrf_score"]:
            st.write(f"**RRF:** {self.chunk['rrf_score']:.3f}")
        else:
            st.write("**RRF:** N/A")

        st.write(f"**Final:** {self.chunk['final_score']:.3f}")

    def _render_relevance_controls(self, current_rel: int | None) -> None:
        """Render relevance status and marking controls.

        Args:
            current_rel: Current relevance value
        """
        # Show current status
        st.write("**Status:**")
        if current_rel == 1:
            st.success("✓ Relevant")
        elif current_rel == 0:
            st.error("✗ Not relevant")
        else:
            st.info("? Not reviewed")

        # Relevance buttons
        st.write("**Mark as:**")
        col_a, col_b, col_c = st.columns(3)

        with col_a:
            if st.button(
                "✓",
                key=f"rel_yes_{self.chunk_id}",
                help="Mark as relevant",
                type="primary" if current_rel == 1 else "secondary",
            ):
                self._update_relevance(True)

        with col_b:
            if st.button(
                "✗",
                key=f"rel_no_{self.chunk_id}",
                help="Mark as not relevant",
                type="primary" if current_rel == 0 else "secondary",
            ):
                self._update_relevance(False)

        with col_c:
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
    """Component for displaying a list of chunks."""

    def __init__(self, chunks: list[dict], db: AnalyticsDatabase):
        """Initialize chunk list viewer.

        Args:
            chunks: List of chunk data dictionaries
            db: Database instance
        """
        self.chunks = chunks
        self.db = db

    def render(self) -> None:
        """Render all chunks."""
        if not self.chunks:
            st.info("No chunks retrieved for this query.")
            return

        for chunk in self.chunks:
            viewer = ChunkViewer(chunk, self.db)
            viewer.render()
