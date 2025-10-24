"""Discord response formatter with citations and feedback buttons."""

from datetime import datetime, timezone
from typing import List

import discord

from src.lib.discord_utils import get_random_disclaimer
from src.models.bot_response import BotResponse
from src.services.llm.validator import ValidationResult


def format_response(
    bot_response: BotResponse,
    validation_result: ValidationResult,
    smalltalk: bool = False,
) -> List[discord.Embed]:
    """Format bot response as Discord embeds with citations.

    Handles both markdown and structured JSON responses.

    Args:
        bot_response: LLM response (markdown or JSON)
        validation_result: Validation result for confidence display
        smalltalk: If True, use purple color and skip disclaimer

    Returns:
        List of Discord embeds (usually 1, split if >2000 chars)
    """
    # Override smalltalk flag from structured data if available
    if bot_response.structured_data and bot_response.structured_data.smalltalk:
        smalltalk = True

    # Check if structured data available
    if bot_response.structured_data:
        return _format_structured(bot_response, validation_result, smalltalk)
    else:
        return _format_markdown(bot_response, validation_result, smalltalk)


def _format_structured(
    bot_response: BotResponse,
    validation_result: ValidationResult,
    smalltalk: bool = False,
) -> List[discord.Embed]:
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
    confidence_emoji = _get_confidence_emoji(bot_response.confidence_score)

    # Main embed with short answer + persona
    description = f"**{data.short_answer}** {data.persona_short_answer}"

    embed = discord.Embed(
        title="Kill Team Rules Bot",
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # Add quotes as embed fields (max 25 fields per embed)
    for i, quote in enumerate(data.quotes[:25]):
        embed.add_field(
            name=f"**{quote.quote_title}**",
            value=f"> {quote.quote_text}",
            inline=False
        )

    # Add explanation field
    embed.add_field(
        name="Explanation",
        value=data.explanation,
        inline=False
    )

    # Add persona afterword
    embed.add_field(
        name="",
        value=f"*{data.persona_afterword}*",
        inline=False
    )

    # Add disclaimer if not smalltalk
    if not smalltalk:
        disclaimer_text = get_random_disclaimer()
        embed.add_field(
            name="Disclaimer",
            value=f"*{disclaimer_text}*",
            inline=True,
        )

    # Footer with metadata
    footer_content = (
        f"ID: {str(bot_response.response_id)[:8]} | "
        f"Model: {bot_response.llm_model} | "
        f"Latency: {bot_response.latency_ms}ms"
    )
    if not smalltalk:
        footer_content += f" | Confidence: {confidence_emoji} {bot_response.confidence_score:.0%}"

    embed.set_footer(text=footer_content)

    return [embed]


def _format_markdown(
    bot_response: BotResponse,
    validation_result: ValidationResult,
    smalltalk: bool = False,
) -> List[discord.Embed]:
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
        timestamp=datetime.now(timezone.utc),
    )

    if not smalltalk:
        disclaimer_text = get_random_disclaimer()
        embed.add_field(
            name="Disclaimer",
            value=f"*{disclaimer_text}*",
            inline=True,
        )

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


async def add_feedback_reactions(message: discord.Message) -> None:
    """Add helpful/not helpful reaction buttons to bot response.

    Args:
        message: Discord message to add reactions to
    """
    await message.add_reaction("👍")
    await message.add_reaction("👎")
