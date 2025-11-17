"""Query detail page for the admin dashboard."""

import streamlit as st

from src.lib.database import AnalyticsDatabase
from src.models.structured_response import StructuredLLMResponse

from ..components.chunk_viewer import ChunkListViewer
from ..utils.constants import ADMIN_STATUS_OPTIONS, PAGE_NAMES
from ..utils.formatters import format_helpful_rate
from ..utils.icons import bool_to_icon, get_quote_validation_icon
from ..utils.session import (
    get_admin_notes_state,
    get_admin_status_state,
    get_selected_query_id,
    init_admin_fields_state,
    navigate_to_page,
    set_admin_notes_state,
    set_admin_status_state,
)


def render(db: AnalyticsDatabase) -> None:
    """Render the query detail page.

    Args:
        db: Database instance
    """
    st.title("🔍 Query Detail")

    # Back button
    if st.button("⬅️ Back to Query Browser"):
        navigate_to_page(PAGE_NAMES["QUERY_BROWSER"])

    # Get query ID
    query_id = get_selected_query_id()
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

    # Render sections
    _render_query_and_response(query)
    _render_metadata(query)
    _render_invalid_quotes(query_id, query, db)
    _render_hop_evaluations(query_id, query, db)
    _render_chunks(chunks, db)
    _render_admin_controls(query_id, query, db)


def _render_query_and_response(query: dict) -> None:
    """Render query text and response.

    Args:
        query: Query data dictionary
    """
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📝 Query Text")
        st.text_area("Query", value=query["query_text"], height=100, disabled=True)

        st.subheader("🤖 Response Text")
        try:
            structured_response = StructuredLLMResponse.from_json(query["response_text"])
            _render_structured_response(structured_response)
        except ValueError:
            st.text_area("Response", value=query["response_text"], height=200, disabled=True)


def _render_structured_response(response: StructuredLLMResponse) -> None:
    """Render structured LLM response.

    Args:
        response: Structured response object
    """
    st.write(f"**smalltalk:** {bool_to_icon(response.smalltalk)}")
    st.write(f"**short answer:** {response.short_answer}")
    st.write(f"**persona short answer:** *{response.persona_short_answer}*")

    for quote in response.quotes:
        st.write(f"> **{quote.quote_title}**\n> {quote.quote_text}")

    st.write(f"**explanation:** {response.explanation}")
    st.write(f"**persona afterword:** *{response.persona_afterword}*")


def _render_metadata(query: dict) -> None:
    """Render query metadata in sidebar.

    Args:
        query: Query data dictionary
    """
    col1, col2 = st.columns([2, 1])

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
        _rate, helpful_str = format_helpful_rate(query["upvotes"], query["downvotes"])
        st.write(f"**Feedback:** {helpful_str}")

        # Multi-hop info
        _render_multi_hop_info(query)

        # Cost
        cost = query.get("cost", 0.0)
        st.write(f"**Cost:** ${cost:.5f}")

        # Quote validation
        _render_quote_validation_metadata(query)


def _render_multi_hop_info(query: dict) -> None:
    """Render multi-hop information.

    Args:
        query: Query data dictionary
    """
    multi_hop_enabled = query.get("multi_hop_enabled", 0)
    hops_used = query.get("hops_used", 0)

    if multi_hop_enabled:
        st.write(f"**Multi-Hop:** 🔄 {hops_used} hops")
    else:
        st.write("**Multi-Hop:** Disabled")


def _render_quote_validation_metadata(query: dict) -> None:
    """Render quote validation metadata.

    Args:
        query: Query data dictionary
    """
    quote_validation_score = query.get("quote_validation_score")

    if quote_validation_score is not None:
        quote_total = query.get("quote_total_count", 0)
        quote_valid = query.get("quote_valid_count", 0)
        score_icon = get_quote_validation_icon(quote_validation_score, quote_valid, quote_total)

        st.write(
            f"**Quote Validation:** {score_icon} {quote_validation_score:.1%} ({quote_valid}/{quote_total} valid)"
        )
    else:
        st.write("**Quote Validation:** N/A")


def _render_invalid_quotes(query_id: str, query: dict, db: AnalyticsDatabase) -> None:
    """Render invalid quotes section if present.

    Args:
        query_id: Query ID
        query: Query data dictionary
        db: Database instance
    """
    quote_invalid_count = query.get("quote_invalid_count", 0)

    if quote_invalid_count == 0:
        return

    st.subheader("⚠️ Invalid Quotes Detected")
    invalid_quotes = db.get_invalid_quotes_for_query(query_id)

    if not invalid_quotes:
        st.info("Invalid quotes count is non-zero but no invalid quotes found in database.")
        return

    for i, invalid_quote in enumerate(invalid_quotes, 1):
        with st.expander(f"❌ Invalid Quote {i}: {invalid_quote.get('quote_title', 'No title')}"):
            st.write(f"**Title:** {invalid_quote.get('quote_title', 'N/A')}")
            st.text_area(
                "Quote Text",
                value=invalid_quote.get("quote_text", ""),
                height=100,
                disabled=True,
                key=f"invalid_quote_{i}",
            )
            st.write(f"**Claimed Chunk ID:** {invalid_quote.get('claimed_chunk_id', 'N/A')}")
            st.write(f"**Reason:** {invalid_quote.get('reason', 'N/A')}")


def _render_hop_evaluations(query_id: str, query: dict, db: AnalyticsDatabase) -> None:
    """Render hop evaluations section if multi-hop was used.

    Args:
        query_id: Query ID
        query: Query data dictionary
        db: Database instance
    """
    if query.get("hops_used", 0) == 0:
        return

    st.subheader("🔄 Multi-Hop Evaluations")
    hop_evaluations = db.get_hop_evaluations_for_query(query_id)

    if not hop_evaluations:
        st.info("No hop evaluations recorded (may be an older query)")
        return

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


def _render_chunks(chunks: list[dict], db: AnalyticsDatabase) -> None:
    """Render retrieved chunks section.

    Args:
        chunks: List of chunk data dictionaries
        db: Database instance
    """
    st.subheader("📚 Retrieved Chunks")
    chunk_viewer = ChunkListViewer(chunks, db)
    chunk_viewer.render()


def _render_admin_controls(query_id: str, query: dict, db: AnalyticsDatabase) -> None:
    """Render admin controls section.

    Args:
        query_id: Query ID
        query: Query data dictionary
        db: Database instance
    """
    st.subheader("🗒️ Admin Controls")

    # Initialize session state
    init_admin_fields_state(query_id, query["admin_status"], query["admin_notes"])

    col1, col2 = st.columns(2)

    with col1:
        new_status = st.selectbox(
            "Admin Status",
            ADMIN_STATUS_OPTIONS,
            index=ADMIN_STATUS_OPTIONS.index(get_admin_status_state(query_id)),
            key=f"status_select_{query_id}",
        )
        set_admin_status_state(query_id, new_status)

    with col2:
        new_notes = st.text_area(
            "Admin Notes",
            value=get_admin_notes_state(query_id),
            height=100,
            key=f"notes_area_{query_id}",
        )
        set_admin_notes_state(query_id, new_notes)

    # Check for changes
    has_changes = new_status != query["admin_status"] or new_notes != (query["admin_notes"] or "")

    # Save button
    col_save, _col_reset = st.columns([1, 4])
    with col_save:
        if st.button("💾 Save Changes", type="primary", disabled=not has_changes):
            db.update_query_admin_fields(query_id=query_id, admin_status=new_status, admin_notes=new_notes)
            st.success("✅ Changes saved successfully!")

    if has_changes:
        st.info("💡 You have unsaved changes. Click 'Save Changes' to persist them.")
