from unittest.mock import MagicMock


class TestClaudeCacheTokenExtraction:
    def test_extracts_cache_read_tokens(self):
        mock_usage = MagicMock()
        mock_usage.input_tokens = 500
        mock_usage.output_tokens = 100
        mock_usage.cache_read_input_tokens = 300
        mock_usage.cache_creation_input_tokens = 0

        cache_read = getattr(mock_usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(mock_usage, "cache_creation_input_tokens", 0) or 0
        assert cache_read == 300
        assert cache_creation == 0

    def test_extracts_cache_creation_tokens(self):
        mock_usage = MagicMock()
        mock_usage.cache_read_input_tokens = 0
        mock_usage.cache_creation_input_tokens = 400

        cache_read = getattr(mock_usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(mock_usage, "cache_creation_input_tokens", 0) or 0
        assert cache_read == 0
        assert cache_creation == 400

    def test_missing_cache_fields_default_to_zero(self):
        mock_usage = MagicMock(spec=["input_tokens", "output_tokens"])
        mock_usage.input_tokens = 500
        mock_usage.output_tokens = 100

        cache_read = getattr(mock_usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(mock_usage, "cache_creation_input_tokens", 0) or 0
        assert cache_read == 0
        assert cache_creation == 0


class TestOpenAICacheTokenExtraction:
    def test_extracts_cached_tokens_from_prompt_details(self):
        mock_details = MagicMock()
        mock_details.cached_tokens = 400

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 1000
        mock_usage.prompt_tokens_details = mock_details

        prompt_details = getattr(mock_usage, "prompt_tokens_details", None)
        cache_read = getattr(prompt_details, "cached_tokens", 0) or 0
        assert cache_read == 400

    def test_no_cache_details_defaults_to_zero(self):
        mock_usage = MagicMock(spec=["prompt_tokens", "completion_tokens", "total_tokens"])
        mock_usage.prompt_tokens = 1000

        prompt_details = getattr(mock_usage, "prompt_tokens_details", None)
        cache_read = 0
        if prompt_details is not None:
            cache_read = getattr(prompt_details, "cached_tokens", 0) or 0
        assert cache_read == 0


class TestGrokCacheTokenExtraction:
    def test_extracts_cached_tokens_from_usage_dict(self):
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "total_tokens": 1200,
            "prompt_tokens_details": {"cached_tokens": 500},
        }
        prompt_details = usage.get("prompt_tokens_details", {})
        cache_read = prompt_details.get("cached_tokens", 0) if prompt_details else 0
        assert cache_read == 500

    def test_missing_prompt_details_defaults_to_zero(self):
        usage = {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200}
        prompt_details = usage.get("prompt_tokens_details", {})
        cache_read = prompt_details.get("cached_tokens", 0) if prompt_details else 0
        assert cache_read == 0
