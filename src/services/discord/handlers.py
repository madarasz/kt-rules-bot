"""Discord message handlers for @ mentions."""

from datetime import UTC, datetime
from uuid import uuid4

import discord

from src.lib.logging import get_logger
from src.lib.validation import sanitize_discord_message
from src.models.user_query import UserQuery

logger = get_logger(__name__)
security_logger = get_logger("security")


async def handle_message(bot, message: discord.Message, orchestrator):
    """Handle incoming Discord messages.

    Args:
        bot: Discord bot instance
        message: Discord message object
        orchestrator: Bot orchestrator for query processing
    """
    # Ignore bot's own messages
    if message.author == bot.user:
        return

    # Check if bot is mentioned
    if bot.user not in message.mentions:
        return

    # Extract query text (remove @ mention)
    query_text = message.content.replace(f"<@{bot.user.id}>", "").strip()

    # Handle empty message
    if not query_text:
        await message.channel.send("How can I help you with Kill Team rules?")
        return

    # Sanitize and validate
    sanitized_text, injection_detected = sanitize_discord_message(query_text)

    if injection_detected:
        await message.channel.send(
            "⚠️ Your message contains invalid characters. Please rephrase your question."
        )
        security_logger.warning(
            "Injection attempt detected",
            extra={
                "event_type": "injection_attempt",
                "user_id": str(message.author.id)[:16],  # Partial ID for privacy
                "message_length": len(query_text),
                "channel_id": str(message.channel.id),
            },
        )
        return

    # Create UserQuery
    user_query = UserQuery(
        query_id=uuid4(),
        user_id=UserQuery.hash_user_id(str(message.author.id)),
        channel_id=str(message.channel.id),
        message_text=query_text,
        sanitized_text=sanitized_text,
        timestamp=datetime.now(UTC),
        conversation_context_id=f"{message.channel.id}:{message.author.id}",
        pii_redacted=False,
    )

    logger.info(
        "Processing user query",
        extra={
            "correlation_id": str(user_query.query_id),
            "user_id": user_query.user_id[:16],
            "channel_id": user_query.channel_id,
            "query_length": len(sanitized_text),
        },
    )

    # Hand off to orchestrator
    await orchestrator.process_query(message, user_query)
