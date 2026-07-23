"""Provider Batch API support: backends, error classification, and id helpers.

Shared by the quality-test runner (tests/quality/test_runner.py) and RAG
ingestion (src/services/rag/summarizer_batch.py). Provider-specific request
building and result parsing stay in the LLM adapters; this package only covers
submission, polling, result retrieval, and the cross-cutting helpers around them.
"""
