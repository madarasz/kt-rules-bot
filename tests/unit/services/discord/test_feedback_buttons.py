"""Unit tests for Discord feedback buttons.

Tests verify that feedback buttons work correctly for:
- Single user voting
- Vote changes (changing opinion)
- Multiple users with different opinions
- Multiple users with same opinion
- Same user clicking same button twice
- Multiple vote changes
"""

import pytest
from unittest.mock import AsyncMock, Mock

import discord

from src.services.discord.feedback_buttons import FeedbackView
from src.lib.database import AnalyticsDatabase


# ==================== FIXTURES ====================


@pytest.fixture
def mock_analytics_db():
    """Create mock analytics database."""
    db = Mock(spec=AnalyticsDatabase)
    db.enabled = True
    db.increment_vote = Mock()
    db.decrement_vote = Mock()
    return db


@pytest.fixture
def mock_feedback_logger(mock_analytics_db):
    """Create mock feedback logger with analytics DB."""
    from src.services.discord.feedback_logger import FeedbackLogger

    logger = FeedbackLogger(analytics_db=mock_analytics_db)
    return logger


@pytest.fixture
def create_mock_interaction():
    """Factory fixture to create mock Discord interactions for different users."""

    def _create_interaction(user_id: int):
        interaction = Mock(spec=discord.Interaction)
        interaction.user = Mock()
        interaction.user.id = user_id
        interaction.message = AsyncMock()
        interaction.message.add_reaction = AsyncMock()
        interaction.message.remove_reaction = AsyncMock()
        interaction.response = Mock()
        interaction.response.defer = AsyncMock()
        return interaction

    return _create_interaction


# ==================== BASIC OPERATIONS ====================


class TestFeedbackButtonBasicOperations:
    """Test basic feedback button operations for a single user."""

    @pytest.mark.asyncio
    async def test_single_user_helpful_vote(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test single user clicking 'Helpful' button."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # User clicks helpful button
        await view.helpful_button.callback(interaction)

        # Verify reaction added
        interaction.message.add_reaction.assert_called_once_with("👍")

        # Verify no reaction removed
        interaction.message.remove_reaction.assert_not_called()

        # Verify user tracked
        assert "111111" in view.voters
        assert view.voters["111111"] == "helpful"

        # Verify DB incremented
        mock_feedback_logger.analytics_db.increment_vote.assert_called_once_with(
            "query-123", "upvote"
        )

    @pytest.mark.asyncio
    async def test_single_user_not_helpful_vote(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test single user clicking 'Not Helpful' button."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # User clicks not helpful button
        await view.not_helpful_button.callback(interaction)

        # Verify reaction added
        interaction.message.add_reaction.assert_called_once_with("👎")

        # Verify no reaction removed
        interaction.message.remove_reaction.assert_not_called()

        # Verify user tracked
        assert "111111" in view.voters
        assert view.voters["111111"] == "not_helpful"

        # Verify DB incremented
        mock_feedback_logger.analytics_db.increment_vote.assert_called_once_with(
            "query-123", "downvote"
        )

    @pytest.mark.asyncio
    async def test_no_reply_sent_on_button_click(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test that no reply message is sent when button is clicked."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # User clicks helpful button
        await view.helpful_button.callback(interaction)

        # Verify interaction deferred (no message sent)
        interaction.response.defer.assert_called_once()

        # Verify no send methods called
        assert not hasattr(interaction.response, "send_message") or not getattr(
            interaction.response, "send_message", Mock()
        ).called

    @pytest.mark.asyncio
    async def test_reaction_added_to_message(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test that reaction is properly added to the bot's message."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # User clicks helpful button
        await view.helpful_button.callback(interaction)

        # Verify reaction added to message
        interaction.message.add_reaction.assert_called_once_with("👍")


# ==================== VOTE CHANGES ====================


class TestFeedbackButtonVoteChanges:
    """Test user changing their vote (opinion change)."""

    @pytest.mark.asyncio
    async def test_user_changes_vote_helpful_to_not_helpful(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test user changing vote from helpful to not helpful."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # First vote: helpful
        await view.helpful_button.callback(interaction)

        # Second vote: not helpful
        await view.not_helpful_button.callback(interaction)

        # Verify final state
        assert view.voters["111111"] == "not_helpful"

        # Verify reactions
        assert interaction.message.add_reaction.call_count == 2
        interaction.message.add_reaction.assert_any_call("👍")
        interaction.message.add_reaction.assert_any_call("👎")

        # Verify old reaction removed
        interaction.message.remove_reaction.assert_called_once_with("👍", interaction.user)

    @pytest.mark.asyncio
    async def test_user_changes_vote_not_helpful_to_helpful(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test user changing vote from not helpful to helpful."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # First vote: not helpful
        await view.not_helpful_button.callback(interaction)

        # Second vote: helpful
        await view.helpful_button.callback(interaction)

        # Verify final state
        assert view.voters["111111"] == "helpful"

        # Verify old reaction removed
        interaction.message.remove_reaction.assert_called_once_with("👎", interaction.user)

    @pytest.mark.asyncio
    async def test_user_multiple_vote_changes(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test user changing vote multiple times: helpful → not helpful → helpful."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # Vote 1: helpful
        await view.helpful_button.callback(interaction)

        # Vote 2: not helpful
        await view.not_helpful_button.callback(interaction)

        # Vote 3: helpful again
        await view.helpful_button.callback(interaction)

        # Verify final state
        assert view.voters["111111"] == "helpful"

        # Verify all reactions added
        assert interaction.message.add_reaction.call_count == 3
        interaction.message.add_reaction.assert_any_call("👍")
        interaction.message.add_reaction.assert_any_call("👎")

        # Verify both old reactions removed
        assert interaction.message.remove_reaction.call_count == 2
        interaction.message.remove_reaction.assert_any_call("👍", interaction.user)
        interaction.message.remove_reaction.assert_any_call("👎", interaction.user)

    @pytest.mark.asyncio
    async def test_old_reaction_removed_on_vote_change(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test that old reaction is properly removed when user changes vote."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # First vote: helpful
        await view.helpful_button.callback(interaction)

        # Change vote: not helpful
        await view.not_helpful_button.callback(interaction)

        # Verify old reaction removal was attempted
        interaction.message.remove_reaction.assert_called_once_with("👍", interaction.user)

    @pytest.mark.asyncio
    async def test_db_updated_correctly_on_vote_change(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test that database is updated correctly when user changes vote."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # First vote: helpful
        await view.helpful_button.callback(interaction)

        # Change vote: not helpful
        await view.not_helpful_button.callback(interaction)

        # Verify DB operations
        db = mock_feedback_logger.analytics_db

        # Should increment both votes (once each)
        assert db.increment_vote.call_count == 2
        db.increment_vote.assert_any_call("query-123", "upvote")
        db.increment_vote.assert_any_call("query-123", "downvote")

        # Should decrement the first vote
        db.decrement_vote.assert_called_once_with("query-123", "upvote")


# ==================== SAME VOTE CLICK ====================


class TestFeedbackButtonSameVoteClick:
    """Test user clicking the same button multiple times."""

    @pytest.mark.asyncio
    async def test_user_clicks_same_button_twice_helpful(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test user clicking 'Helpful' button twice."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # First click: helpful
        await view.helpful_button.callback(interaction)

        # Reset mocks to track second click separately
        interaction.message.add_reaction.reset_mock()
        interaction.message.remove_reaction.reset_mock()
        db = mock_feedback_logger.analytics_db
        db.increment_vote.reset_mock()
        db.decrement_vote.reset_mock()

        # Second click: helpful again
        await view.helpful_button.callback(interaction)

        # Verify no reaction removed (no vote change)
        interaction.message.remove_reaction.assert_not_called()

        # Verify reaction still added (may be redundant in Discord)
        interaction.message.add_reaction.assert_called_once_with("👍")

        # Verify voter state unchanged
        assert view.voters["111111"] == "helpful"

    @pytest.mark.asyncio
    async def test_user_clicks_same_button_twice_not_helpful(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test user clicking 'Not Helpful' button twice."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # First click: not helpful
        await view.not_helpful_button.callback(interaction)

        # Reset mocks
        interaction.message.add_reaction.reset_mock()
        interaction.message.remove_reaction.reset_mock()

        # Second click: not helpful again
        await view.not_helpful_button.callback(interaction)

        # Verify no reaction removed
        interaction.message.remove_reaction.assert_not_called()

        # Verify voter state unchanged
        assert view.voters["111111"] == "not_helpful"

    @pytest.mark.asyncio
    async def test_db_not_updated_on_duplicate_click(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test that database is not updated when user clicks same button twice."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # First click
        await view.helpful_button.callback(interaction)

        # Reset DB mocks
        db = mock_feedback_logger.analytics_db
        db.increment_vote.reset_mock()
        db.decrement_vote.reset_mock()

        # Second click (same button)
        await view.helpful_button.callback(interaction)

        # Verify no DB operations (since vote didn't change)
        db.increment_vote.assert_not_called()
        db.decrement_vote.assert_not_called()


# ==================== MULTIPLE USERS ====================


class TestFeedbackButtonMultipleUsers:
    """Test multiple users providing feedback on the same message."""

    @pytest.mark.asyncio
    async def test_two_users_same_opinion_helpful(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test two users both clicking 'Helpful'."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        # User 1 clicks helpful
        interaction1 = create_mock_interaction(user_id=111111)
        await view.helpful_button.callback(interaction1)

        # User 2 clicks helpful
        interaction2 = create_mock_interaction(user_id=222222)
        await view.helpful_button.callback(interaction2)

        # Verify both users tracked
        assert "111111" in view.voters
        assert "222222" in view.voters
        assert view.voters["111111"] == "helpful"
        assert view.voters["222222"] == "helpful"

        # Verify DB incremented twice
        db = mock_feedback_logger.analytics_db
        assert db.increment_vote.call_count == 2
        assert all(
            call[0] == ("query-123", "upvote") for call in db.increment_vote.call_args_list
        )

        # Verify both reactions added
        interaction1.message.add_reaction.assert_called_once_with("👍")
        interaction2.message.add_reaction.assert_called_once_with("👍")

    @pytest.mark.asyncio
    async def test_two_users_same_opinion_not_helpful(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test two users both clicking 'Not Helpful'."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        # User 1 clicks not helpful
        interaction1 = create_mock_interaction(user_id=111111)
        await view.not_helpful_button.callback(interaction1)

        # User 2 clicks not helpful
        interaction2 = create_mock_interaction(user_id=222222)
        await view.not_helpful_button.callback(interaction2)

        # Verify both users tracked
        assert view.voters["111111"] == "not_helpful"
        assert view.voters["222222"] == "not_helpful"

        # Verify DB incremented twice
        db = mock_feedback_logger.analytics_db
        assert db.increment_vote.call_count == 2
        assert all(
            call[0] == ("query-123", "downvote") for call in db.increment_vote.call_args_list
        )

    @pytest.mark.asyncio
    async def test_two_users_different_opinions(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test two users with different opinions."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        # User 1 clicks helpful
        interaction1 = create_mock_interaction(user_id=111111)
        await view.helpful_button.callback(interaction1)

        # User 2 clicks not helpful
        interaction2 = create_mock_interaction(user_id=222222)
        await view.not_helpful_button.callback(interaction2)

        # Verify both users tracked with different votes
        assert view.voters["111111"] == "helpful"
        assert view.voters["222222"] == "not_helpful"

        # Verify DB has both votes
        db = mock_feedback_logger.analytics_db
        assert db.increment_vote.call_count == 2
        db.increment_vote.assert_any_call("query-123", "upvote")
        db.increment_vote.assert_any_call("query-123", "downvote")

        # Verify both reactions added to message
        interaction1.message.add_reaction.assert_called_once_with("👍")
        interaction2.message.add_reaction.assert_called_once_with("👎")

    @pytest.mark.asyncio
    async def test_three_users_mixed_opinions(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test three users with mixed opinions (2 helpful, 1 not helpful)."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        # User 1: helpful
        interaction1 = create_mock_interaction(user_id=111111)
        await view.helpful_button.callback(interaction1)

        # User 2: not helpful
        interaction2 = create_mock_interaction(user_id=222222)
        await view.not_helpful_button.callback(interaction2)

        # User 3: helpful
        interaction3 = create_mock_interaction(user_id=333333)
        await view.helpful_button.callback(interaction3)

        # Verify all three users tracked
        assert len(view.voters) == 3
        assert view.voters["111111"] == "helpful"
        assert view.voters["222222"] == "not_helpful"
        assert view.voters["333333"] == "helpful"

        # Verify DB has correct counts (2 upvotes, 1 downvote)
        db = mock_feedback_logger.analytics_db
        assert db.increment_vote.call_count == 3
        upvote_calls = [
            call for call in db.increment_vote.call_args_list if call[0][1] == "upvote"
        ]
        downvote_calls = [
            call for call in db.increment_vote.call_args_list if call[0][1] == "downvote"
        ]
        assert len(upvote_calls) == 2
        assert len(downvote_calls) == 1

    @pytest.mark.asyncio
    async def test_user_vote_change_does_not_affect_other_users(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test that one user changing vote doesn't affect other users' votes."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        # User 1: helpful
        interaction1 = create_mock_interaction(user_id=111111)
        await view.helpful_button.callback(interaction1)

        # User 2: not helpful
        interaction2 = create_mock_interaction(user_id=222222)
        await view.not_helpful_button.callback(interaction2)

        # User 1 changes to not helpful
        await view.not_helpful_button.callback(interaction1)

        # Verify User 2's vote unchanged
        assert view.voters["222222"] == "not_helpful"

        # Verify User 1's vote changed
        assert view.voters["111111"] == "not_helpful"

        # Verify both users still tracked
        assert len(view.voters) == 2

    @pytest.mark.asyncio
    async def test_multiple_reactions_visible_on_message(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test that multiple reactions from different users are added to message."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        # Create 3 different interactions (same message, different users)
        interactions = [
            create_mock_interaction(user_id=111111),
            create_mock_interaction(user_id=222222),
            create_mock_interaction(user_id=333333),
        ]

        # All users click helpful
        for interaction in interactions:
            await view.helpful_button.callback(interaction)

        # Verify each user's reaction was added
        for interaction in interactions:
            interaction.message.add_reaction.assert_called_with("👍")

        # Verify no reactions removed
        for interaction in interactions:
            interaction.message.remove_reaction.assert_not_called()
