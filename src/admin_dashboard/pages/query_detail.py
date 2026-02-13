"""Query detail page for the admin dashboard."""

import textwrap

import streamlit as st

from src.lib.database import AnalyticsDatabase
from src.models.structured_response import StructuredLLMResponse

from ..services.llm_rerun import get_available_models, rerun_query

from ..components.chunk_viewer import ChunkListViewer
from ..utils.constants import ADMIN_STATUS_OPTIONS, PAGE_NAMES
from ..utils.formatters import format_helpful_rate, generate_test_id
from ..utils.icons import bool_to_icon, get_quote_validation_icon
from ..utils.session import (
    get_admin_notes_state,
    get_admin_status_state,
    get_fixed_issue_state,
    get_selected_query_id,
    init_admin_fields_state,
    navigate_to_page,
    set_admin_notes_state,
    set_admin_status_state,
    set_fixed_issue_state,
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
    _render_query_response_and_sidebar(query_id, query, db)
    _render_llm_rerun_section(query_id, query, chunks)
    _render_invalid_quotes(query_id, query, db)
    _render_hop_evaluations(query_id, query, db)
    _render_chunks(chunks, db)
    _render_rag_test_export(chunks, query)
    _render_quality_test_export(query)


def _render_query_response_and_sidebar(
    query_id: str, query: dict, db: AnalyticsDatabase
) -> None:
    """Render query text, response, admin controls, and metadata in a two-column layout.

    Args:
        query_id: Query ID
        query: Query data dictionary
        db: Database instance
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

    with col2:
        _render_admin_controls_sidebar(query_id, query, db)
        st.divider()
        _render_metadata(query)


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
    """Render query metadata.

    Args:
        query: Query data dictionary
    """
    st.subheader("📊 Metadata")
    st.write(f"**Query ID:** `{query['query_id']}`")
    st.write(f"**Timestamp:** {query['timestamp']}")
    st.write(f"**Channel:** {query['channel_name']} ({query['discord_server_name']})")
    st.write(f"**User:** @{query['username']}")
    st.write(f"**Model:** {query['llm_model']}")
    st.write(f"**RAG Score:** {query['rag_score']:.2f}")

    # Feedback
    _rate, helpful_str = format_helpful_rate(query["upvotes"], query["downvotes"])
    st.write(f"**Feedback:** {helpful_str}")

    # Multi-hop info
    _render_multi_hop_info(query)

    # Cost breakdown (display in cents)
    hop_eval_cost = query.get("hop_evaluation_cost", 0.0) * 100
    main_llm_cost = query.get("main_llm_cost", 0.0) * 100
    total_cost = query.get("cost", 0.0) * 100
    st.write(f"**Total Cost:** {total_cost:.3f}¢")
    st.write(f"  - Hop Evaluation: {hop_eval_cost:.3f}¢")
    st.write(f"  - Main LLM: {main_llm_cost:.3f}¢")

    # Latency breakdown (display in seconds)
    retrieval_s = query.get("retrieval_latency_ms", 0) / 1000
    hop_eval_s = query.get("hop_evaluation_latency_ms", 0) / 1000
    main_llm_s = query.get("latency_ms", 0) / 1000
    total_measured_s = query.get("total_latency_ms", 0) / 1000
    # Calculate "other" time (overhead not accounted for in component breakdowns)
    component_sum_s = retrieval_s + hop_eval_s + main_llm_s
    other_s = max(0, total_measured_s - component_sum_s)
    # Use measured total if available, otherwise fall back to component sum
    total_s = total_measured_s if total_measured_s > 0 else component_sum_s
    st.write(f"**Total Latency:** {total_s:.2f}s")
    st.write(f"  - Retrieval: {retrieval_s:.2f}s")
    st.write(f"  - Hop Evaluation: {hop_eval_s:.2f}s")
    st.write(f"  - Main LLM: {main_llm_s:.2f}s")
    if other_s > 0.01:  # Only show if meaningful (> 10ms)
        st.write(f"  - Other: {other_s:.2f}s")

    # Quote validation
    st.write(f"**JSON Validation:** {'✅ Passed' if query['validation_passed'] else '❌ Failed'}")
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


def _render_admin_controls_sidebar(
    query_id: str, query: dict, db: AnalyticsDatabase
) -> None:
    """Render admin controls in sidebar layout (single column).

    Args:
        query_id: Query ID
        query: Query data dictionary
        db: Database instance
    """
    st.subheader("🗒️ Admin Controls")

    # Initialize session state
    db_fixed_issue = bool(query.get("fixed_issue", 0))
    init_admin_fields_state(query_id, query["admin_status"], query["admin_notes"], db_fixed_issue)

    # Handle case where query has deprecated status that's not in options
    current_status = get_admin_status_state(query_id)
    if current_status not in ADMIN_STATUS_OPTIONS:
        # Map deprecated statuses to new ones
        if current_status == "reviewed":
            current_status = "approved"
        elif current_status == "issues":
            current_status = "flagged"
        else:
            current_status = "pending"
        set_admin_status_state(query_id, current_status)

    new_status = st.selectbox(
        "Admin Status",
        ADMIN_STATUS_OPTIONS,
        index=ADMIN_STATUS_OPTIONS.index(current_status),
        key=f"status_select_{query_id}",
    )
    set_admin_status_state(query_id, new_status)

    # Fixed issue checkbox
    new_fixed_issue = st.checkbox(
        "Fixed Issue",
        value=get_fixed_issue_state(query_id),
        key=f"fixed_issue_checkbox_{query_id}",
        help="Mark if the issue identified by this query has been fixed",
    )
    set_fixed_issue_state(query_id, new_fixed_issue)

    new_notes = st.text_area(
        "Admin Notes",
        value=get_admin_notes_state(query_id),
        height=80,
        key=f"notes_area_{query_id}",
    )
    set_admin_notes_state(query_id, new_notes)

    # Check for changes
    has_changes = (
        new_status != query["admin_status"]
        or new_notes != (query["admin_notes"] or "")
        or new_fixed_issue != db_fixed_issue
    )

    # Save button
    if st.button("💾 Save Changes", type="primary", disabled=not has_changes):
        db.update_query_admin_fields(
            query_id=query_id,
            admin_status=new_status,
            admin_notes=new_notes,
            fixed_issue=new_fixed_issue,
        )
        st.success("✅ Saved!")

    if has_changes:
        st.caption("💡 Unsaved changes")


def _render_llm_rerun_section(query_id: str, query: dict, chunks: list[dict]) -> None:
    """Render the LLM re-run comparison section.

    Allows admins to re-run the query with a different LLM model
    and compare the result side-by-side with the original.

    Args:
        query_id: Query ID
        query: Query data dictionary
        chunks: List of chunk data dictionaries from DB
    """
    with st.expander("🔄 Re-run Query with Different LLM", expanded=False):
        available_models = get_available_models()
        original_model = query.get("llm_model", "")

        # Controls row
        ctrl_col1, ctrl_col2 = st.columns([2, 1])

        with ctrl_col1:
            selected_model = st.selectbox(
                "LLM Model",
                available_models,
                index=0,
                key=f"rerun_model_{query_id}",
                help=f"Original model: {original_model}",
            )

        with ctrl_col2:
            reuse_rag = st.checkbox(
                "Reuse RAG context",
                value=False,
                key=f"rerun_reuse_rag_{query_id}",
                help=(
                    "Checked: use the same RAG chunks stored in DB (LLM-only comparison). "
                    "Unchecked: perform fresh RAG retrieval with the current vector DB."
                ),
            )

        # Run button
        if st.button("🚀 Run Query", key=f"rerun_btn_{query_id}", type="primary"):
            with st.spinner(f"Running query with {selected_model}..."):
                result = rerun_query(
                    query_text=query["query_text"],
                    chunks_from_db=chunks,
                    model_name=selected_model,
                    reuse_rag_context=reuse_rag,
                )
                st.session_state[f"rerun_result_{query_id}"] = result

        # Display result if available
        rerun_result = st.session_state.get(f"rerun_result_{query_id}")
        if rerun_result is None:
            return

        if rerun_result.error:
            st.error(rerun_result.error)
            return

        # Side-by-side comparison
        st.divider()
        col_orig, col_rerun = st.columns(2)

        with col_orig:
            st.markdown(f"**📋 Original** (`{original_model}`)")
            try:
                original_structured = StructuredLLMResponse.from_json(query["response_text"])
                _render_structured_response(original_structured)
            except ValueError:
                st.text_area(
                    "Response",
                    value=query["response_text"],
                    height=300,
                    disabled=True,
                    key=f"rerun_orig_raw_{query_id}",
                )

        with col_rerun:
            st.markdown(f"**🔄 Re-run** (`{rerun_result.model}`)")
            if rerun_result.structured_response:
                _render_structured_response(rerun_result.structured_response)
            else:
                st.text_area(
                    "Response",
                    value=rerun_result.answer_text,
                    height=300,
                    disabled=True,
                    key=f"rerun_new_raw_{query_id}",
                )

            # Metadata below the re-run response
            rag_info = rerun_result.rag_info
            rag_source = rag_info.get("source", "Unknown")
            rag_chunks = rag_info.get("chunk_count", 0)
            rag_avg = rag_info.get("avg_relevance", 0.0)
            retrieval_ms = rag_info.get("retrieval_time_ms")

            cost_cents = rerun_result.cost_usd * 100
            latency_s = rerun_result.latency_ms / 1000

            st.caption(f"⏱ Total latency: {latency_s:.1f}s | 💰 {cost_cents:.3f}¢")
            rag_line = f"📦 RAG: {rag_source} ({rag_chunks} chunks, {rag_avg:.2f} avg)"
            if retrieval_ms is not None:
                rag_line += f" | retrieval: {retrieval_ms}ms"
            st.caption(rag_line)


def _render_rag_test_export(chunks: list[dict], query: dict) -> None:
    """Render RAG test export section if relevant chunks exist.

    Args:
        chunks: List of chunk data dictionaries
        query: Query data dictionary
    """
    # Filter to only relevant chunks
    relevant_chunks = [c for c in chunks if c.get("relevant") == 1]

    if not relevant_chunks:
        return  # Don't show section if no relevant chunks

    st.subheader("📤 Export to RAG Test")

    # Generate YAML in the new format
    yaml_content = _generate_single_test_yaml(query, relevant_chunks)

    st.code(yaml_content, language="yaml")

    # Download button
    test_id = generate_test_id(query["query_text"])
    st.download_button(
        label="⬇️ Download YAML",
        data=yaml_content,
        file_name=f"{test_id}.yaml",
        mime="text/yaml",
    )


def _generate_single_test_yaml(query: dict, relevant_chunks: list[dict]) -> str:
    """Generate YAML for a single RAG test case in the new format.

    Format:
    test_id: some-id
    query: >
      Query text here...

    ground_truth_contexts:
      - "Chunk Header": "Relevant text snippet..."

    Args:
        query: Query data dictionary
        relevant_chunks: List of relevant chunk dictionaries

    Returns:
        YAML formatted string
    """
    lines = []

    # test_id
    test_id = generate_test_id(query["query_text"])
    lines.append(f"test_id: {test_id}")

    # query (multi-line format)
    lines.append("query: >")
    for line in query["query_text"].split("\n"):
        lines.append(f"  {line}")

    # ground_truth_contexts
    lines.append("")
    lines.append("ground_truth_contexts:")
    for chunk in relevant_chunks:
        header = chunk.get("chunk_header") or "No header"
        # Extract first ~150 chars of chunk text as snippet
        text_snippet = _extract_text_snippet(chunk.get("chunk_text", ""))

        # Escape quotes
        escaped_header = header.replace('"', '\\"')
        escaped_snippet = text_snippet.replace('"', '\\"')

        lines.append(f'  - "{escaped_header}": "{escaped_snippet}"')

    return "\n".join(lines)


def _extract_text_snippet(text: str, max_length: int = 150) -> str:
    """Extract a meaningful snippet from chunk text.

    Args:
        text: Full chunk text
        max_length: Maximum length of snippet

    Returns:
        Extracted text snippet (single line, no line breaks)
    """
    if not text:
        return ""

    # Normalize whitespace: replace newlines with spaces, collapse multiple spaces
    normalized = " ".join(text.split())

    # Take first meaningful portion
    snippet = normalized[:max_length]

    # Try to end at a sentence boundary if possible
    if len(normalized) > max_length:
        last_period = snippet.rfind(".")
        if last_period > max_length // 2:
            snippet = snippet[:last_period + 1]
        else:
            snippet = snippet.rstrip() + "..."

    return snippet


def _render_quality_test_export(query: dict) -> None:
    """Render Quality Test export section.

    Args:
        query: Query data dictionary
    """
    st.subheader("📤 Export to Quality Test")

    # Try to parse structured response
    try:
        structured_response = StructuredLLMResponse.from_json(query["response_text"])
    except ValueError:
        st.warning("Cannot export: response is not in structured JSON format")
        return

    # Generate YAML
    test_id = generate_test_id(query["query_text"])
    yaml_content = _generate_quality_test_yaml(query, structured_response)

    st.code(yaml_content, language="yaml")

    # CLI command for generating context file
    query_escaped = query["query_text"].replace('"', '\\"')
    query_single_line = " ".join(query_escaped.split())
    context_cmd = f'python3 -m src.cli query "{query_single_line}" --rag-only --context-output tests/quality/test_cases/{test_id}-context.json'
    st.caption("Generate context file:")
    st.code(context_cmd, language="bash")

    # Download button
    st.download_button(
        label="⬇️ Download YAML",
        data=yaml_content,
        file_name=f"{test_id}-quality.yaml",
        mime="text/yaml",
        key="quality_test_download",
    )


def _generate_quality_test_yaml(query: dict, response: StructuredLLMResponse) -> str:
    """Generate YAML for a Quality Test case.

    Args:
        query: Query data dictionary
        response: Parsed structured LLM response

    Returns:
        YAML formatted string
    """
    lines = []

    # test_id and context_file
    test_id = generate_test_id(query["query_text"])
    lines.append(f"test_id: {test_id}")
    lines.append(f"context_file: tests/quality/test_cases/{test_id}-context.json")

    # query (multi-line format)
    lines.append("query: >")
    query_normalized = " ".join(query["query_text"].split())
    for line in _wrap_text(query_normalized, width=80):
        lines.append(f"  {line}")

    # ground_truth_answers
    lines.append("")
    lines.append("ground_truth_answers:")
    short_answer_normalized = " ".join(response.short_answer.split())
    escaped_answer = short_answer_normalized.replace('"', '\\"')
    lines.append('  - key: "Final Answer"')
    lines.append(f'    text: "{escaped_answer}"')
    lines.append("    priority: critical")
    lines.append("  # ADD MORE GROUND TRUTHS HERE")

    # ground_truth_contexts (from quotes)
    lines.append("")
    lines.append("ground_truth_contexts:")
    for quote in response.quotes:
        key = quote.quote_title
        # Normalize whitespace and extract snippet
        text_normalized = " ".join(quote.quote_text.split())
        snippet = text_normalized[:150] + "..." if len(text_normalized) > 150 else text_normalized

        escaped_key = key.replace('"', '\\"')
        escaped_text = snippet.replace('"', '\\"')

        lines.append(f'  - key: "{escaped_key}"')
        lines.append(f'    text: "{escaped_text}"')
        lines.append("    priority: critical")

    # Comment explaining priority values
    lines.append("")
    lines.append("# Priority values: critical (10 points), important (5 points), supporting (3 points)")

    return "\n".join(lines)


def _wrap_text(text: str, width: int = 80) -> list[str]:
    """Wrap text to specified width for YAML formatting.

    Args:
        text: Text to wrap
        width: Maximum line width

    Returns:
        List of wrapped lines
    """
    return textwrap.wrap(text, width=width) or [""]
