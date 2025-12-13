"""Unit tests for Discord feedback buttons.

Tests verify that feedback buttons work correctly for:
- Single user voting (button labels update with counts)
- Vote changes (changing opinion)
- Multiple users with different opinions
- Multiple users with same opinion
- Same user clicking same button twice (silently ignored)
- Multiple vote changes
"""

from unittest.mock import AsyncMock, Mock

import discord
import pytest

from src.lib.database import AnalyticsDatabase
from src.services.discord.feedback_buttons import FeedbackView

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
        interaction.response = Mock()
        interaction.response.defer = AsyncMock()
        interaction.response.edit_message = AsyncMock()
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

        # Verify message edited with updated view
        interaction.response.edit_message.assert_called_once_with(view=view)

        # Verify user tracked
        assert "111111" in view.voters
        assert view.voters["111111"] == "helpful"

        # Verify vote count incremented
        assert view.helpful_count == 1
        assert view.not_helpful_count == 0

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

        # Verify message edited with updated view
        interaction.response.edit_message.assert_called_once_with(view=view)

        # Verify user tracked
        assert "111111" in view.voters
        assert view.voters["111111"] == "not_helpful"

        # Verify vote count incremented
        assert view.helpful_count == 0
        assert view.not_helpful_count == 1

        # Verify DB incremented
        mock_feedback_logger.analytics_db.increment_vote.assert_called_once_with(
            "query-123", "downvote"
        )

    @pytest.mark.asyncio
    async def test_button_label_updated_with_count(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test that button labels are updated with vote counts."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # User clicks helpful button
        await view.helpful_button.callback(interaction)

        # Find the helpful button and verify label
        helpful_button = None
        for child in view.children:
            if child.custom_id == "helpful":
                helpful_button = child
                break

        assert helpful_button is not None
        assert helpful_button.label == "Helpful 👍 [1]"

    @pytest.mark.asyncio
    async def test_button_label_no_count_when_zero(
        self, mock_feedback_logger
    ):
        """Test that button labels don't show (0) count."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        # Find buttons before any votes
        helpful_button = None
        not_helpful_button = None
        for child in view.children:
            if child.custom_id == "helpful":
                helpful_button = child
            elif child.custom_id == "not_helpful":
                not_helpful_button = child

        # Initial labels should not have count
        assert helpful_button.label == "Helpful 👍"
        assert not_helpful_button.label == "Not Helpful 👎"


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

        # Verify counts updated correctly
        assert view.helpful_count == 0
        assert view.not_helpful_count == 1

        # Verify message edited twice
        assert interaction.response.edit_message.call_count == 2

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

        # Verify counts updated correctly
        assert view.helpful_count == 1
        assert view.not_helpful_count == 0

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
        assert view.helpful_count == 1
        assert view.not_helpful_count == 0

        # Vote 2: not helpful
        await view.not_helpful_button.callback(interaction)
        assert view.helpful_count == 0
        assert view.not_helpful_count == 1

        # Vote 3: helpful again
        await view.helpful_button.callback(interaction)
        assert view.helpful_count == 1
        assert view.not_helpful_count == 0

        # Verify final state
        assert view.voters["111111"] == "helpful"

        # Verify message edited 3 times
        assert interaction.response.edit_message.call_count == 3

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
        """Test user clicking 'Helpful' button twice - second click ignored."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # First click: helpful
        await view.helpful_button.callback(interaction)

        # Reset mocks to track second click separately
        interaction.response.edit_message.reset_mock()
        interaction.response.defer.reset_mock()
        db = mock_feedback_logger.analytics_db
        db.increment_vote.reset_mock()
        db.decrement_vote.reset_mock()

        # Second click: helpful again
        await view.helpful_button.callback(interaction)

        # Verify interaction deferred (no edit, no visible change)
        interaction.response.defer.assert_called_once()
        interaction.response.edit_message.assert_not_called()

        # Verify voter state unchanged
        assert view.voters["111111"] == "helpful"

        # Verify count unchanged
        assert view.helpful_count == 1

    @pytest.mark.asyncio
    async def test_user_clicks_same_button_twice_not_helpful(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test user clicking 'Not Helpful' button twice - second click ignored."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        interaction = create_mock_interaction(user_id=111111)

        # First click: not helpful
        await view.not_helpful_button.callback(interaction)

        # Reset mocks
        interaction.response.edit_message.reset_mock()
        interaction.response.defer.reset_mock()

        # Second click: not helpful again
        await view.not_helpful_button.callback(interaction)

        # Verify deferred (no edit)
        interaction.response.defer.assert_called_once()
        interaction.response.edit_message.assert_not_called()

        # Verify voter state unchanged
        assert view.voters["111111"] == "not_helpful"

        # Verify count unchanged
        assert view.not_helpful_count == 1

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

        # Verify count reflects both votes
        assert view.helpful_count == 2
        assert view.not_helpful_count == 0

        # Verify DB incremented twice
        db = mock_feedback_logger.analytics_db
        assert db.increment_vote.call_count == 2
        assert all(
            call[0] == ("query-123", "upvote") for call in db.increment_vote.call_args_list
        )

        # Verify both messages edited
        interaction1.response.edit_message.assert_called_once_with(view=view)
        interaction2.response.edit_message.assert_called_once_with(view=view)

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

        # Verify count reflects both votes
        assert view.helpful_count == 0
        assert view.not_helpful_count == 2

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

        # Verify counts
        assert view.helpful_count == 1
        assert view.not_helpful_count == 1

        # Verify DB has both votes
        db = mock_feedback_logger.analytics_db
        assert db.increment_vote.call_count == 2
        db.increment_vote.assert_any_call("query-123", "upvote")
        db.increment_vote.assert_any_call("query-123", "downvote")

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

        # Verify counts
        assert view.helpful_count == 2
        assert view.not_helpful_count == 1

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

        # Verify counts
        assert view.helpful_count == 0
        assert view.not_helpful_count == 2

    @pytest.mark.asyncio
    async def test_button_labels_reflect_multiple_users(
        self, mock_feedback_logger, create_mock_interaction
    ):
        """Test that button labels show accurate count from multiple users."""
        view = FeedbackView(
            feedback_logger=mock_feedback_logger,
            query_id="query-123",
            response_id="response-456",
        )

        # 3 users click helpful
        for user_id in [111111, 222222, 333333]:
            interaction = create_mock_interaction(user_id=user_id)
            await view.helpful_button.callback(interaction)

        # Find the helpful button and verify label
        helpful_button = None
        for child in view.children:
            if child.custom_id == "helpful":
                helpful_button = child
                break

        assert helpful_button is not None
        assert helpful_button.label == "Helpful 👍 [3]"
