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

    Args:
        bot_response: LLM response with citations
        validation_result: Validation result for confidence display

    Returns:
        List of Discord embeds (usually 1, split if >2000 chars)
    """
    # Determine embed color based on confidence
    if bot_response.confidence_score >= 0.8:
        color = discord.Color.green()
        confidence_emoji = "🟢"
    elif bot_response.confidence_score >= 0.6:
        color = discord.Color.gold()
        confidence_emoji = "🟡"
    else:
        color = discord.Color.red()
        confidence_emoji = "🔴"
    if smalltalk:
        color = discord.Color.purple()

    # Create main embed
    embed = discord.Embed(
        title="Kill Team Rules Bot",
        description=bot_response.answer_text[:2000],  # Discord limit
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # Add disclaimer
    if not smalltalk:
        disclaimer_text = get_random_disclaimer()
        embed.add_field(
            name="Disclaimer",
            value=f"*{disclaimer_text}*",
            inline=True,
        )

    # Footer with metadata (includes response_id for feedback tracking)
    # only show confidence if not smalltalk
    footer_content = f"ID: {str(bot_response.response_id)[:8]} | Model: {bot_response.llm_model} | Latency: {bot_response.latency_ms}ms"
    if not smalltalk:
        footer_content += f" | Confidence: {confidence_emoji} {bot_response.confidence_score:.0%}"
    embed.set_footer(text=footer_content)

    return [embed]


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
