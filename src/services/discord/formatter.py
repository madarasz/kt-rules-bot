"""Discord response formatter with citations and feedback buttons."""

import re
from datetime import UTC, datetime

import discord

from src.lib.discord_utils import get_random_disclaimer
from src.models.bot_response import BotResponse
from src.services.discord.feedback_buttons import FeedbackView
from src.services.llm.validator import ValidationResult


def _split_field_value(text: str, max_length: int = 1024) -> list[str]:
    """Split text into chunks at sentence boundaries, respecting Discord's field limit.

    Args:
        text: Text to split
        max_length: Maximum characters per chunk (default 1024 for Discord fields)

    Returns:
        List of text chunks, each ≤ max_length
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""

    # Split on sentence boundaries (. ! ?)
    sentences = re.split(r"([.!?]+\s+)", text)

    for i in range(0, len(sentences), 2):
        sentence = sentences[i]
        delimiter = sentences[i + 1] if i + 1 < len(sentences) else ""
        sentence_with_delimiter = sentence + delimiter

        # Check if adding this sentence exceeds limit
        if len(current_chunk) + len(sentence_with_delimiter) <= max_length:
            current_chunk += sentence_with_delimiter
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence_with_delimiter

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def format_response(
    bot_response: BotResponse, _validation_result: ValidationResult, smalltalk: bool = False
) -> list[discord.Embed]:
    """Format bot response as Discord embeds with citations.

    Handles both markdown and structured JSON responses.

    Args:
        bot_response: LLM response (markdown or JSON)
        _validation_result: Validation result (currently unused)
        smalltalk: If True, use purple color and skip disclaimer

    Returns:
        List of Discord embeds (usually 1, split if >2000 chars)
    """
    # Override smalltalk flag from structured data if available
    if bot_response.structured_data and bot_response.structured_data.smalltalk:
        smalltalk = True

    # Check if structured data available
    if bot_response.structured_data:
        return _format_structured(bot_response, smalltalk)
    else:
        return _format_markdown(bot_response, smalltalk)


def _format_structured(bot_response: BotResponse, smalltalk: bool = False) -> list[discord.Embed]:
    """Format structured JSON response as Discord embeds.

    Args:
        bot_response: BotResponse with structured_data populated
        validation_result: Validation result
        smalltalk: If True, use purple color

    Returns:
        List of Discord embeds
    """
    data = bot_response.structured_data

    # Determine embed color based on confidence
    color = _get_embed_color(bot_response.confidence_score, smalltalk)

    # Main embed with short answer + persona
    description = f"**{data.short_answer}** *{data.persona_short_answer}*"

    embed = discord.Embed(
        title=None, description=description, color=color, timestamp=datetime.now(UTC)
    )

    # Add quotes as embed fields (max 25 fields per embed)
    # Discord field name limit: 256 chars
    for _i, quote in enumerate(data.quotes[:25]):
        quote_title = quote.quote_title
        quote_text = quote.quote_text

        # FAQ titles: use just "[FAQ]" as title, move rest to quote text
        if quote_title.startswith("[FAQ]"):
            remaining_title = quote_title[5:].strip()  # Remove "[FAQ]" prefix
            if remaining_title:
                quote_text = f"{remaining_title}\n{quote_text}"
            quote_title = "[FAQ]"

        field_name = f"**{quote_title}**"
        if len(field_name) > 256:
            field_name = field_name[:253] + "..."
        embed.add_field(name=field_name, value=f"> {quote_text}", inline=False)

    # Add explanation field (split if needed)
    if len(data.explanation) > 0:
        explanation_chunks = _split_field_value(data.explanation)

        for chunk_idx, chunk in enumerate(explanation_chunks):
            field_name = "Explanation" if chunk_idx == 0 else ""
            embed.add_field(name=field_name, value=chunk, inline=False)

    # Add persona afterword
    embed.add_field(name="", value=f"*{data.persona_afterword}*", inline=False)

    # Add disclaimer if not smalltalk
    if not smalltalk:
        disclaimer_text = get_random_disclaimer()
        embed.add_field(name="Disclaimer", value=f"*{disclaimer_text}*", inline=True)

    # Footer with metadatam, remove date suffix from model name
    footer_content = (
        f"ID: {str(bot_response.response_id)[:8]} | "
        f"Model: {_format_llm_model_name(bot_response.llm_model)} | "
        f"Latency: {_format_latency_ms(bot_response.latency_ms)}"
    )
    # if not smalltalk:
    #     footer_content += f" | Confidence: {confidence_emoji} {bot_response.confidence_score:.0%}"

    embed.set_footer(text=footer_content)

    return [embed]


def _format_llm_model_name(model_name: str) -> str:
    return re.sub(r"-\d{8}$", "", model_name)


def _format_latency_ms(latency_ms: int) -> str:
    return f"{latency_ms / 1000:.2f}s"


def _format_markdown(bot_response: BotResponse, smalltalk: bool = False) -> list[discord.Embed]:
    """Format markdown response as Discord embeds (existing implementation).

    This is the current implementation - kept for backwards compatibility.

    Args:
        bot_response: BotResponse with markdown answer_text
        validation_result: Validation result
        smalltalk: If True, use purple color

    Returns:
        List of Discord embeds
    """
    color = _get_embed_color(bot_response.confidence_score, smalltalk)
    confidence_emoji = _get_confidence_emoji(bot_response.confidence_score)

    embed = discord.Embed(
        title="Kill Team Rules Bot",
        description=bot_response.answer_text[:2000],
        color=color,
        timestamp=datetime.now(UTC),
    )

    if not smalltalk:
        disclaimer_text = get_random_disclaimer()
        embed.add_field(name="Disclaimer", value=f"*{disclaimer_text}*", inline=True)

    footer_content = f"ID: {str(bot_response.response_id)[:8]} | Model: {bot_response.llm_model} | Latency: {bot_response.latency_ms}ms"
    if not smalltalk:
        footer_content += f" | Confidence: {confidence_emoji} {bot_response.confidence_score:.0%}"
    embed.set_footer(text=footer_content)

    return [embed]


def _get_embed_color(confidence_score: float, smalltalk: bool) -> discord.Color:
    """Get embed color based on confidence score.

    Args:
        confidence_score: LLM confidence (0-1)
        smalltalk: If True, return purple

    Returns:
        Discord color
    """
    if smalltalk:
        return discord.Color.purple()
    elif confidence_score >= 0.8:
        return discord.Color.green()
    elif confidence_score >= 0.6:
        return discord.Color.gold()
    else:
        return discord.Color.red()


def _get_confidence_emoji(confidence_score: float) -> str:
    """Get confidence emoji based on score.

    Args:
        confidence_score: LLM confidence (0-1)

    Returns:
        Emoji string
    """
    if confidence_score >= 0.8:
        return "🟢"
    elif confidence_score >= 0.6:
        return "🟡"
    else:
        return "🔴"


def format_fallback_message(reason: str) -> str:
    """Format message when validation fails.

    Args:
        reason: Reason for validation failure

    Returns:
        Formatted fallback message
    """
    return (
        "⚠️ I couldn't provide a confident answer to your question.\n\n"
        f"**Reason**: {reason}\n\n"
        "💡 Try:\n"
        "• Rephrasing your question more specifically\n"
        "• Asking about a particular rule section\n"
        "• Providing more context about the situation"
    )


def create_feedback_view(feedback_logger, query_id: str, response_id: str) -> discord.ui.View:
    """Create Discord UI View with feedback buttons.

    Args:
        feedback_logger: FeedbackLogger instance
        query_id: Query UUID
        response_id: Response UUID

    Returns:
        Discord View with Helpful/Not Helpful buttons
    """
    return FeedbackView(
        feedback_logger=feedback_logger,
        query_id=query_id,
        response_id=response_id,
        timeout=86400,  # 24 hours
    )
