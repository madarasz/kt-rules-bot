"""Unit tests for chunk ID attribution in prompt building."""

import pytest

from src.services.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing prompt building."""

    async def generate(self, request):
        """Not implemented - not needed for these tests."""
        pass

    async def extract_pdf(self, request):
        """Not implemented - not needed for these tests."""
        pass


class TestChunkAttribution:
    """Test chunk ID attribution in prompts."""

    @pytest.fixture
    def provider(self):
        """Create mock provider."""
        return MockLLMProvider(api_key="test", model="test-model")

    def test_build_prompt_without_chunk_ids(self, provider):
        """Test prompt building without chunk IDs (backward compatibility)."""
        user_query = "Can I shoot while concealed?"
        context = [
            "An operative can perform the Shoot action with this weapon while it has a Conceal order.",
            "Each time a friendly operative activates, select one of the following orders for it to have.",
        ]

        prompt = provider._build_prompt(user_query, context, chunk_ids=None)

        # Should use numbered context format
        assert "[Context 1]:" in prompt
        assert "[Context 2]:" in prompt
        assert "[CHUNK_" not in prompt
        assert "User Question: Can I shoot while concealed?" in prompt

    def test_build_prompt_with_chunk_ids(self, provider):
        """Test prompt building with chunk IDs."""
        user_query = "Can I shoot while concealed?"
        context = [
            "An operative can perform the Shoot action with this weapon while it has a Conceal order.",
            "Each time a friendly operative activates, select one of the following orders for it to have.",
        ]
        chunk_ids = ["12345678-90ab-cdef-1234-567890abcdef", "abcdef12-3456-7890-abcd-ef1234567890"]

        prompt = provider._build_prompt(user_query, context, chunk_ids=chunk_ids)

        # Should use CHUNK_ID format
        assert "[CHUNK_90abcdef]:" in prompt  # Last 8 chars of first UUID
        assert "[CHUNK_4567890]:" in prompt  # Last 8 chars of second UUID (corrected)
        assert "[Context 1]:" not in prompt
        assert "User Question: Can I shoot while concealed?" in prompt
        assert "reference the chunk ID in the chunk_id field" in prompt

    def test_build_prompt_with_mismatched_chunk_ids(self, provider):
        """Test prompt building when chunk_ids length doesn't match context length."""
        user_query = "Can I shoot while concealed?"
        context = [
            "An operative can perform the Shoot action with this weapon while it has a Conceal order.",
            "Each time a friendly operative activates, select one of the following orders for it to have.",
        ]
        chunk_ids = [
            "12345678-90ab-cdef-1234-567890abcdef"
            # Missing second chunk ID
        ]

        prompt = provider._build_prompt(user_query, context, chunk_ids=chunk_ids)

        # Should fall back to numbered context format
        assert "[Context 1]:" in prompt
        assert "[Context 2]:" in prompt
        assert "[CHUNK_" not in prompt

    def test_build_prompt_with_empty_chunk_ids(self, provider):
        """Test prompt building with empty chunk_ids list."""
        user_query = "Can I shoot while concealed?"
        context = [
            "An operative can perform the Shoot action with this weapon while it has a Conceal order."
        ]
        chunk_ids = []

        prompt = provider._build_prompt(user_query, context, chunk_ids=chunk_ids)

        # Should fall back to numbered context format
        assert "[Context 1]:" in prompt
        assert "[CHUNK_" not in prompt

    def test_build_prompt_chunk_id_extraction(self, provider):
        """Test that only last 8 characters of UUID are used in chunk ID."""
        user_query = "Test query"
        context = ["Test context"]
        chunk_ids = ["12345678-90ab-cdef-1234-567890abcdef"]

        prompt = provider._build_prompt(user_query, context, chunk_ids=chunk_ids)

        # Should use only last 8 chars
        assert "[CHUNK_90abcdef]:" in prompt
        assert "12345678-90ab-cdef-1234-567890abcdef" not in prompt

    def test_build_prompt_preserves_context_content(self, provider):
        """Test that context content is preserved exactly."""
        user_query = "Test query"
        context = [
            "First chunk with **bold** and special characters: $%&",
            "Second chunk with\nmultiple\nlines",
        ]
        chunk_ids = ["11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"]

        prompt = provider._build_prompt(user_query, context, chunk_ids=chunk_ids)

        # Verify context content is preserved
        assert "First chunk with **bold** and special characters: $%&" in prompt
        assert "Second chunk with\nmultiple\nlines" in prompt

    def test_build_prompt_context_ordering(self, provider):
        """Test that context chunks appear in correct order."""
        user_query = "Test query"
        context = ["Chunk A", "Chunk B", "Chunk C"]
        chunk_ids = [
            "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "cccccccc-cccc-cccc-cccc-cccccccccccc",
        ]

        prompt = provider._build_prompt(user_query, context, chunk_ids=chunk_ids)

        # Find positions
        pos_a = prompt.index("[CHUNK_aaaaaaaa]")
        pos_b = prompt.index("[CHUNK_bbbbbbbb]")
        pos_c = prompt.index("[CHUNK_cccccccc]")

        # Verify order
        assert pos_a < pos_b < pos_c
