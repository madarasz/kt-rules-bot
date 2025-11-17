# Replace Reactions with Discord UI Buttons for Feedback

**Status**: Planned
**Created**: 2025-11-15
**Author**: Planning Document

## Problem Statement

Currently, the bot uses `add_reaction()` to add 👍/👎 reactions to bot response messages for user feedback. This approach has a significant UX issue: when the bot adds these reactions, it appears as if someone has already voted on the message, which is misleading to users.

**Current Implementation**:
- File: [src/services/discord/formatter.py](../src/services/discord/formatter.py:262-269)
- Method: `add_feedback_reactions(message: discord.Message)`
- Behavior: Adds 👍 and 👎 reactions to the bot's own message
- Called from: [src/services/discord/bot.py](../src/services/discord/bot.py:330)

## Proposed Solution

Replace reaction-based feedback with **Discord UI Buttons** using `discord.ui.View`. This provides:

✅ **Better UX**: No misleading pre-existing reactions
✅ **Clearer Intent**: Labeled buttons like "Helpful 👍" and "Not Helpful 👎"
✅ **Accessibility**: Screen readers can announce buttons properly
✅ **Professional Appearance**: Buttons look more polished than reactions
✅ **Backward Compatibility**: Old reactions on existing messages still tracked

## Implementation Plan

### 1. Create Button View Component

**New File**: `src/services/discord/feedback_buttons.py`

```python
"""Discord UI components for user feedback."""

import discord
from src.lib.logging import get_logger

logger = get_logger(__name__)


class FeedbackView(discord.ui.View):
    """Discord UI View with feedback buttons (Helpful/Not Helpful)."""

    def __init__(self, feedback_logger, query_id: str, response_id: str, timeout: int = 86400):
        """Initialize feedback view.

        Args:
            feedback_logger: FeedbackLogger instance for tracking feedback
            query_id: Query UUID for database tracking
            response_id: Response UUID for database tracking
            timeout: Button timeout in seconds (default 24 hours)
        """
        super().__init__(timeout=timeout)
        self.feedback_logger = feedback_logger
        self.query_id = query_id
        self.response_id = response_id
        self.voters = set()  # Track who voted to prevent duplicates

    @discord.ui.button(label="Helpful 👍", style=discord.ButtonStyle.success, custom_id="helpful")
    async def helpful_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle 'Helpful' button click."""
        await self._handle_feedback(interaction, "helpful", "👍")

    @discord.ui.button(label="Not Helpful 👎", style=discord.ButtonStyle.danger, custom_id="not_helpful")
    async def not_helpful_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle 'Not Helpful' button click."""
        await self._handle_feedback(interaction, "not_helpful", "👎")

    async def _handle_feedback(self, interaction: discord.Interaction, feedback_type: str, emoji: str):
        """Process feedback from button interaction.

        Args:
            interaction: Discord interaction from button click
            feedback_type: 'helpful' or 'not_helpful'
            emoji: Emoji for user confirmation
        """
        user_id = str(interaction.user.id)

        # Prevent duplicate votes from same user
        if user_id in self.voters:
            await interaction.response.send_message(
                "You've already provided feedback on this response!",
                ephemeral=True
            )
            return

        # Record vote
        self.voters.add(user_id)

        # Log to feedback logger
        if self.feedback_logger:
            await self.feedback_logger.record_button_feedback(
                query_id=self.query_id,
                response_id=self.response_id,
                user_id=user_id,
                feedback_type=feedback_type
            )

        # Send ephemeral acknowledgement
        await interaction.response.send_message(
            f"Thanks for your feedback! {emoji}",
            ephemeral=True
        )

        logger.info(
            f"Feedback button clicked: {feedback_type}",
            extra={
                "query_id": self.query_id,
                "response_id": self.response_id,
                "feedback_type": feedback_type,
                "user_id": user_id[:16]  # Partial for privacy
            }
        )

    async def on_timeout(self):
        """Disable buttons when view times out."""
        for item in self.children:
            item.disabled = True

        logger.debug(
            "Feedback view timed out",
            extra={"response_id": self.response_id}
        )
```

**Key Features**:
- Inherits from `discord.ui.View`
- Two buttons: "Helpful 👍" (green) and "Not Helpful 👎" (red)
- Prevents duplicate votes from same user
- Sends ephemeral acknowledgement (only voter sees it)
- 24-hour timeout (buttons auto-disable after that)
- Integrates with existing `FeedbackLogger`

---

### 2. Update Formatter

**File**: [src/services/discord/formatter.py](../src/services/discord/formatter.py)

**Changes**:

1. **Remove** `add_feedback_reactions()` function (lines 262-269):

```python
# DELETE THIS FUNCTION
async def add_feedback_reactions(message: discord.Message) -> None:
    """Add helpful/not helpful reaction buttons to bot response."""
    await message.add_reaction("👍")
    await message.add_reaction("👎")
```

2. **Add** new function to create button view:

```python
def create_feedback_view(feedback_logger, query_id: str, response_id: str) -> discord.ui.View:
    """Create Discord UI View with feedback buttons.

    Args:
        feedback_logger: FeedbackLogger instance
        query_id: Query UUID
        response_id: Response UUID

    Returns:
        Discord View with Helpful/Not Helpful buttons
    """
    from src.services.discord.feedback_buttons import FeedbackView
    return FeedbackView(
        feedback_logger=feedback_logger,
        query_id=query_id,
        response_id=response_id,
        timeout=86400  # 24 hours
    )
```

**Rationale**: Keeping view creation in formatter maintains separation of concerns (formatter handles all Discord UI element creation).

---

### 3. Update Bot Orchestrator

**File**: [src/services/discord/bot.py](../src/services/discord/bot.py)

**Changes** (around lines 317-330):

**Before**:
```python
# Step 7: Format response
embeds = formatter.format_response(bot_response, validation_result, smalltalk=smalltalk)

# Step 8: Send to Discord
sent_message = await message.channel.send(embeds=embeds)

# Step 9: Register response for feedback tracking
if self.feedback_logger:
    self.feedback_logger.register_response(
        str(user_query.query_id),
        str(bot_response.response_id)
    )

# Step 9b: Add feedback reaction buttons (👍👎)
await formatter.add_feedback_reactions(sent_message)
```

**After**:
```python
# Step 7: Format response
embeds = formatter.format_response(bot_response, validation_result, smalltalk=smalltalk)

# Step 8: Create feedback button view
feedback_view = None
if self.feedback_logger:
    feedback_view = formatter.create_feedback_view(
        feedback_logger=self.feedback_logger,
        query_id=str(user_query.query_id),
        response_id=str(bot_response.response_id)
    )

# Step 9: Send to Discord with feedback buttons
sent_message = await message.channel.send(embeds=embeds, view=feedback_view)

# Note: No need to register_response() anymore - view handles tracking directly
```

**Key Changes**:
- Create `FeedbackView` **before** sending message
- Pass `view=feedback_view` to `channel.send()`
- Remove call to `add_feedback_reactions()`
- Remove call to `register_response()` (view handles tracking directly)

---

### 4. Update Feedback Logger

**File**: [src/services/discord/feedback_logger.py](../src/services/discord/feedback_logger.py)

**Changes**:

1. **Keep** existing `on_reaction_add()` for backward compatibility (existing reactions on old messages)

2. **Add** new method for button feedback:

```python
async def record_button_feedback(
    self,
    query_id: str,
    response_id: str,
    user_id: str,
    feedback_type: str,
) -> None:
    """Record feedback from Discord UI button interaction.

    Args:
        query_id: Query UUID (from UserQuery)
        response_id: Response UUID (from BotResponse)
        user_id: Discord user ID (raw, will be hashed)
        feedback_type: 'helpful' or 'not_helpful'
    """
    from datetime import datetime, timezone
    from uuid import uuid4
    from src.models.user_query import UserQuery

    feedback_id = uuid4()
    hashed_user_id = UserQuery.hash_user_id(user_id)

    # Update database vote count (if enabled)
    if self.analytics_db.enabled:
        try:
            vote_type = "upvote" if feedback_type == "helpful" else "downvote"
            self.analytics_db.increment_vote(query_id, vote_type)
            logger.debug(
                f"Button vote incremented in analytics DB",
                extra={"query_id": query_id, "vote_type": vote_type}
            )
        except Exception as e:
            logger.error(f"Failed to increment vote in DB: {e}", exc_info=True)

    # Log to structured logs
    logger.info(
        "Button feedback received",
        extra={
            "event_type": "button_feedback",
            "feedback_id": str(feedback_id),
            "response_id": response_id,
            "query_id": query_id,
            "user_id": hashed_user_id[:16],  # Partial hash for privacy
            "feedback_type": feedback_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    # Optional: Store in feedback_cache for deduplication
    cache_key = f"{response_id}:{hashed_user_id}"
    self.feedback_cache[cache_key] = {
        "feedback_id": feedback_id,
        "feedback_type": feedback_type,
        "timestamp": datetime.now(timezone.utc),
    }
```

3. **Optional cleanup**: Remove `response_to_query_map` and `register_response()` method (no longer needed since buttons pass IDs directly)

**Rationale**: Buttons provide query_id/response_id directly, eliminating need for mapping registry.

---

### 5. Update Tests

**File**: [tests/unit/test_discord_services.py](../tests/unit/test_discord_services.py)

**Changes**:

1. **Remove** old reaction test (around line 135-144):

```python
# DELETE THIS TEST
@pytest.mark.asyncio
async def test_add_feedback_reactions():
    """Test feedback reactions are added to message."""
    message = Mock(spec=discord.Message)
    message.add_reaction = AsyncMock()

    await add_feedback_reactions(message)

    assert message.add_reaction.call_count == 2
    message.add_reaction.assert_any_call("👍")
    message.add_reaction.assert_any_call("👎")
```

2. **Add** new button view tests:

```python
# ==================== FEEDBACK BUTTON TESTS ====================

@pytest.mark.asyncio
async def test_feedback_view_helpful_button():
    """Test 'Helpful' button click records feedback."""
    from src.services.discord.feedback_buttons import FeedbackView
    from unittest.mock import MagicMock

    # Setup
    feedback_logger = Mock()
    feedback_logger.record_button_feedback = AsyncMock()

    view = FeedbackView(
        feedback_logger=feedback_logger,
        query_id="query-123",
        response_id="response-456",
        timeout=60
    )

    # Mock interaction
    interaction = Mock(spec=discord.Interaction)
    interaction.user = Mock()
    interaction.user.id = 123456789
    interaction.response = Mock()
    interaction.response.send_message = AsyncMock()

    # Trigger button click
    button = Mock(spec=discord.ui.Button)
    await view.helpful_button(interaction, button)

    # Verify feedback logged
    feedback_logger.record_button_feedback.assert_called_once_with(
        query_id="query-123",
        response_id="response-456",
        user_id="123456789",
        feedback_type="helpful"
    )

    # Verify ephemeral response sent
    interaction.response.send_message.assert_called_once()
    assert "Thanks for your feedback!" in interaction.response.send_message.call_args[0][0]


@pytest.mark.asyncio
async def test_feedback_view_not_helpful_button():
    """Test 'Not Helpful' button click records feedback."""
    from src.services.discord.feedback_buttons import FeedbackView

    # Setup
    feedback_logger = Mock()
    feedback_logger.record_button_feedback = AsyncMock()

    view = FeedbackView(
        feedback_logger=feedback_logger,
        query_id="query-123",
        response_id="response-456",
        timeout=60
    )

    # Mock interaction
    interaction = Mock(spec=discord.Interaction)
    interaction.user = Mock()
    interaction.user.id = 123456789
    interaction.response = Mock()
    interaction.response.send_message = AsyncMock()

    # Trigger button click
    button = Mock(spec=discord.ui.Button)
    await view.not_helpful_button(interaction, button)

    # Verify feedback logged
    feedback_logger.record_button_feedback.assert_called_once_with(
        query_id="query-123",
        response_id="response-456",
        user_id="123456789",
        feedback_type="not_helpful"
    )


@pytest.mark.asyncio
async def test_feedback_view_prevents_duplicate_votes():
    """Test that users can't vote twice on same response."""
    from src.services.discord.feedback_buttons import FeedbackView

    # Setup
    feedback_logger = Mock()
    feedback_logger.record_button_feedback = AsyncMock()

    view = FeedbackView(
        feedback_logger=feedback_logger,
        query_id="query-123",
        response_id="response-456",
        timeout=60
    )

    # Mock interaction (same user)
    interaction = Mock(spec=discord.Interaction)
    interaction.user = Mock()
    interaction.user.id = 123456789
    interaction.response = Mock()
    interaction.response.send_message = AsyncMock()

    # First vote
    button = Mock(spec=discord.ui.Button)
    await view.helpful_button(interaction, button)

    # Second vote (should be rejected)
    await view.helpful_button(interaction, button)

    # Verify only logged once
    assert feedback_logger.record_button_feedback.call_count == 1

    # Verify second interaction got rejection message
    assert interaction.response.send_message.call_count == 2
    assert "already provided feedback" in interaction.response.send_message.call_args[0][0]


@pytest.mark.asyncio
async def test_feedback_logger_record_button_feedback():
    """Test FeedbackLogger.record_button_feedback() method."""
    from src.services.discord.feedback_logger import FeedbackLogger

    # Setup
    analytics_db = Mock()
    analytics_db.enabled = True
    analytics_db.increment_vote = Mock()

    logger = FeedbackLogger(analytics_db=analytics_db)

    # Record button feedback
    await logger.record_button_feedback(
        query_id="query-123",
        response_id="response-456",
        user_id="123456789",
        feedback_type="helpful"
    )

    # Verify DB incremented
    analytics_db.increment_vote.assert_called_once_with("query-123", "upvote")

    # Verify cache updated
    assert len(logger.feedback_cache) == 1
    cache_key = list(logger.feedback_cache.keys())[0]
    assert logger.feedback_cache[cache_key]["feedback_type"] == "helpful"
```

3. **Update** formatter tests to use new `create_feedback_view()`:

```python
def test_create_feedback_view():
    """Test creating feedback button view."""
    from src.services.discord.formatter import create_feedback_view
    from src.services.discord.feedback_buttons import FeedbackView

    feedback_logger = Mock()

    view = create_feedback_view(
        feedback_logger=feedback_logger,
        query_id="query-123",
        response_id="response-456"
    )

    assert isinstance(view, FeedbackView)
    assert view.query_id == "query-123"
    assert view.response_id == "response-456"
    assert view.feedback_logger == feedback_logger
```

---

## Migration Strategy

### Phase 1: Deploy New Button System
1. Deploy all code changes above
2. New bot responses will have buttons instead of reactions
3. Old messages with reactions will still work (backward compatibility)

### Phase 2: Monitor
1. Check logs for `event_type: button_feedback` events
2. Verify analytics DB vote increments working
3. Monitor user engagement (button clicks vs reaction clicks)

### Phase 3: Cleanup (Optional, after 30 days)
1. Remove `on_reaction_add()` handler if no longer needed
2. Remove `response_to_query_map` and `register_response()` from FeedbackLogger
3. Archive this document

---

## Files to Modify

| File | Action | Lines | Description |
|------|--------|-------|-------------|
| `src/services/discord/feedback_buttons.py` | **CREATE** | N/A | New file with `FeedbackView` class |
| `src/services/discord/formatter.py` | **EDIT** | 262-269 | Remove `add_feedback_reactions()`, add `create_feedback_view()` |
| `src/services/discord/bot.py` | **EDIT** | 317-330 | Create view before sending message, pass to `send()` |
| `src/services/discord/feedback_logger.py` | **EDIT** | N/A | Add `record_button_feedback()` method |
| `tests/unit/test_discord_services.py` | **EDIT** | Various | Remove old test, add button view tests |

---

## Benefits Summary

| Aspect | Before (Reactions) | After (Buttons) |
|--------|-------------------|-----------------|
| **UX** | Misleading (looks like someone voted) | Clear (no pre-existing votes) |
| **Accessibility** | Screen readers struggle with reactions | Buttons properly announced |
| **Clarity** | Just emojis (👍👎) | Labeled buttons ("Helpful 👍") |
| **Duplicate Prevention** | Manual tracking needed | Built-in via view state |
| **Feedback to User** | None | Ephemeral "Thanks!" message |
| **Professional Look** | Informal | Polished, modern UI |

---

## Related Documentation

- Discord.py UI Components: https://discordpy.readthedocs.io/en/stable/interactions/api.html#discord.ui.View
- Discord.py Buttons Guide: https://guide.pycord.dev/interactions/ui-components/buttons
- [src/services/discord/CLAUDE.md](../src/services/discord/CLAUDE.md) - Discord service architecture
- [src/services/discord/feedback_logger.py](../src/services/discord/feedback_logger.py) - Current feedback implementation

---

## Notes

- **Backward Compatibility**: Keep `on_reaction_add()` handler for 30 days to support reactions on old messages
- **Button Timeout**: 24 hours is Discord's recommended timeout for persistent UI components
- **Ephemeral Messages**: User feedback acknowledgements are ephemeral (only visible to voter) to avoid channel clutter
- **Duplicate Prevention**: Handled in-memory by `FeedbackView.voters` set (resets when bot restarts, but that's acceptable)
- **Bot Restarts**: Button interactions will fail if bot restarts before 24-hour timeout (Discord limitation). Users will see "This interaction failed" - this is expected behavior.

---

**Ready to implement?** Follow the steps above sequentially for a smooth migration from reactions to buttons.
