"""StructuredLLMResponse.from_json parsing, including malformed-quotes tolerance."""

import json

import pytest

from src.models.structured_response import StructuredLLMResponse

QUOTES = [
    {"quote_title": "REPOSITION (1AP)", "quote_text": "An operative cannot...", "chunk_id": "a1"},
    {"quote_title": "CHARGE (1AP)", "quote_text": "An operative cannot...", "chunk_id": "b2"},
]


def _payload(quotes) -> str:
    return json.dumps({
        "smalltalk": False,
        "short_answer": "Yes.",
        "persona_short_answer": "Obviously.",
        "quotes": quotes,
        "explanation": "Because the restriction is scoped to one activation.",
        "persona_afterword": "Try to keep up.",
    })


def test_quotes_as_list():
    """The well-formed case: quotes is a plain JSON array."""
    parsed = StructuredLLMResponse.from_json(_payload(QUOTES))

    assert [q.quote_title for q in parsed.quotes] == ["REPOSITION (1AP)", "CHARGE (1AP)"]
    assert parsed.quotes[0].chunk_id == "a1"


def test_quotes_double_encoded_as_string():
    """Some models emit quotes as a JSON string wrapping the array — unwrap it."""
    parsed = StructuredLLMResponse.from_json(_payload(json.dumps(QUOTES)))

    assert [q.quote_title for q in parsed.quotes] == ["REPOSITION (1AP)", "CHARGE (1AP)"]


def test_quotes_double_encoded_with_trailing_comma():
    """Observed claude-4.6-sonnet payload: double-encoded *and* trailing comma."""
    parsed = StructuredLLMResponse.from_json(_payload(json.dumps(QUOTES) + ","))

    assert [q.quote_title for q in parsed.quotes] == ["REPOSITION (1AP)", "CHARGE (1AP)"]


def test_quotes_unparseable_string_raises():
    with pytest.raises(ValueError, match="Invalid quotes JSON"):
        StructuredLLMResponse.from_json(_payload("[{not json"))


def test_quotes_wrong_type_raises():
    with pytest.raises(ValueError, match="Expected quotes to be a list, got int"):
        StructuredLLMResponse.from_json(_payload(3))
