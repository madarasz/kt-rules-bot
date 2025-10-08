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

    # Create main embed
    embed = discord.Embed(
        title="Kill Team Rules Assistant",
        description=bot_response.answer_text[:2000],  # Discord limit
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # Add confidence field
    embed.add_field(
        name="Confidence",
        value=f"{confidence_emoji} {bot_response.confidence_score:.0%}",
        inline=True,
    )

    # Add RAG score field
    # embed.add_field(
    #     name="RAG Score",
    #     value=f"{bot_response.rag_score:.0%}",
    #     inline=True,
    # )

    # Add citations
    # if bot_response.citations:
    #     citations_text = "\n".join(
    #         [
    #             f"{i+1}. **{c.document_name}** - {c.section}"
    #             for i, c in enumerate(bot_response.citations[:5])  # Limit to 5 citations
    #         ]
    #     )
    #     embed.add_field(
    #         name="Sources",
    #         value=citations_text,
    #         inline=False,
    #     )

    # Add disclaimer
    disclaimer_text = get_random_disclaimer()
    embed.add_field(
        name="Disclaimer",
        value=f"*{disclaimer_text}*",
        inline=True,
    )

    # Footer with metadata (includes response_id for feedback tracking)
    embed.set_footer(
        text=f"ID: {str(bot_response.response_id)[:8]} | "
        f"Model: {bot_response.llm_model} | "
        f"Tokens: {bot_response.token_count} | "
        f"Latency: {bot_response.latency_ms}ms"
    )

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
