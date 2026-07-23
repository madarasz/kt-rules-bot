"""Batch-item error classification + extraction + backend error-file surfacing."""

import pytest

from src.services.llm.batch.errors import (
    CLASS_PERMANENT,
    CLASS_TRANSIENT,
    classify_batch_error,
    extract_item_error,
)


@pytest.mark.parametrize(
    "text",
    [
        "rate_limit_exceeded: too many requests",
        "HTTP 429 Too Many Requests",
        "overloaded_error",
        "Error 529: overloaded",
        "503 Service Unavailable",
        "internal server_error",
        "request timed out",
        "result_type=expired",
        "insufficient_quota: add credits",
        "You have insufficient credits",
        "billing hard limit reached",
    ],
)
def test_transient_errors(text):
    cls, _reason = classify_batch_error(text)
    assert cls == CLASS_TRANSIENT


@pytest.mark.parametrize(
    "text",
    [
        "authentication_error: invalid_api_key",
        "HTTP 401 Unauthorized",
        "permission denied (403)",
        "invalid_request_error: bad schema",
        "content_policy violation",
        "response blocked by safety filter",
        "RECITATION",
        "model refusal",
        "404 not_found",
        "result_type=canceled",
    ],
)
def test_permanent_errors(text):
    cls, _reason = classify_batch_error(text)
    assert cls == CLASS_PERMANENT


def test_unknown_defaults_transient():
    cls, reason = classify_batch_error("some brand new error nobody has seen")
    assert cls == CLASS_TRANSIENT
    assert reason == "unclassified"


def test_none_defaults_transient():
    assert classify_batch_error(None)[0] == CLASS_TRANSIENT


def test_permanent_checked_before_transient():
    # "invalid_request" contains the substring "request"; a transient rule must not
    # win over the permanent invalid_request classification.
    cls, reason = classify_batch_error("invalid_request_error: your request is malformed")
    assert cls == CLASS_PERMANENT
    assert reason == "invalid_request"


def test_extract_item_error_explicit_field():
    assert extract_item_error({"error": "boom"}) == "boom"
    assert extract_item_error({"error": {"code": "x"}}) == "{'code': 'x'}"


def test_extract_item_error_openai_shape():
    # non-200 status or missing body signals a failed OpenAI-compatible item
    assert extract_item_error({"status_code": 429, "body": None}) == "status 429"
    assert extract_item_error({"status_code": 200, "body": {"ok": 1}}) is None
    # succeeded item (status None, body present) is not an error
    assert extract_item_error({"status_code": None, "body": {"ok": 1}}) is None


def test_extract_item_error_anthropic_shape():
    assert extract_item_error({"result_type": "errored"}) == "result_type=errored"
    assert extract_item_error({"result_type": "succeeded", "message": {}}) is None


def test_extract_item_error_grok_gemini_shape():
    assert extract_item_error({"response": None}) == "no response"
    assert extract_item_error({"response": {"candidates": [1]}}) is None


def test_openai_backend_fetch_reads_error_file():
    """A failed OpenAI item lives in the error file, previously never read."""
    from src.services.llm.batch.backends import OpenAICompatBatchBackend

    class _Files:
        def content(self, file_id):
            class _C:
                pass

            c = _C()
            if file_id == "out":
                c.text = (
                    '{"custom_id": "ok1", "response": {"status_code": 200, '
                    '"body": {"choices": []}}}'
                )
            else:  # error file
                c.text = (
                    '{"custom_id": "bad1", "response": {"status_code": 429}, '
                    '"error": {"code": "rate_limit_exceeded", "message": "slow down"}}'
                )
            return c

    class _Batches:
        def retrieve(self, _id):
            class B:
                output_file_id = "out"
                error_file_id = "err"

            return B()

    class _Client:
        files = _Files()
        batches = _Batches()

    b = OpenAICompatBatchBackend(api_key="k", base_url="http://x", name="openai")
    b._client = _Client()
    out = b.fetch("batch_1")

    assert set(out) == {"ok1", "bad1"}
    assert out["ok1"].get("error") is None
    assert "rate_limit_exceeded" in extract_item_error(out["bad1"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
