# RAG Reranker Implementation Plan

## Executive Summary

This plan adds optional reranking capability to the RAG pipeline with two implementation approaches:
1. **Lightweight Score Fusion** (recommended for experimentation)
2. **Cross-Encoder Reranking** (full neural reranking)

Both approaches are toggleable via configuration flags and can be A/B tested against the current hybrid retrieval baseline.

**Key Finding**: Analysis suggests that cross-encoder reranking may NOT be necessary for this project due to:
- Small corpus size (117 chunks)
- Effective current hybrid search (vector + BM25 + RRF)
- Multi-hop retrieval already handles complex queries
- Diminishing returns for reranking 15→7 chunks

However, this plan provides a complete implementation to allow experimentation and validation.

---

## 1. Configuration Constants (constants.py)

### Proposed Additions

Add the following section after line 238 in `src/lib/constants.py`:

```python
# ============================================================================
# RAG Reranking Constants
# ============================================================================

# Enable/disable reranking (default: False to maintain current behavior)
RAG_ENABLE_RERANKER = False

# Reranker strategy: "fusion", "cross-encoder", or "listwise"
# - "fusion": Lightweight score fusion (metadata-based, no model calls)
# - "cross-encoder": BERT-based relevance scoring (adds ~100ms latency)
# - "listwise": LLM-based listwise reranking (experimental, adds ~1-2s)
RAG_RERANKER_STRATEGY: Literal["fusion", "cross-encoder", "listwise"] = "fusion"

# Number of candidate chunks to pass to reranker (retrieve top-N before reranking)
# Should be larger than RAG_MAX_CHUNKS to allow reranker to refine selection
# Recommended: 2-3x RAG_MAX_CHUNKS
RAG_RERANKER_CANDIDATES = 15

# Final top-k chunks after reranking (usually same as RAG_MAX_CHUNKS)
RAG_RERANKER_TOP_K = 7

# Cross-encoder model selection
# Options:
#   - "cross-encoder/ms-marco-TinyBERT-L-2-v2": Ultra-fast (30ms), lower quality
#   - "cross-encoder/ms-marco-MiniLM-L-6-v2": Fast (50ms), good quality (RECOMMENDED)
#   - "cross-encoder/ms-marco-MiniLM-L-12-v2": Balanced (100ms), higher quality
#   - "cross-encoder/ms-marco-electra-base": Slow (200ms), best quality
RAG_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Cross-encoder batch size for inference (affects memory usage)
RAG_RERANKER_BATCH_SIZE = 16

# Minimum reranker score threshold (0-1 for cross-encoder, may vary by model)
# Chunks below this score are filtered out even if in top-k
RAG_RERANKER_MIN_SCORE = 0.0  # No filtering by default

# Enable reranker score normalization (scale to 0-1 range)
RAG_RERANKER_NORMALIZE_SCORES = True

# Fusion reranker weights (only used when strategy="fusion")
# Combines existing RRF, vector similarity, and BM25 scores
# Must sum to 1.0
RAG_FUSION_RRF_WEIGHT = 0.5        # Weight for RRF score
RAG_FUSION_VECTOR_WEIGHT = 0.3     # Weight for vector similarity
RAG_FUSION_BM25_WEIGHT = 0.2       # Weight for BM25 score

# Listwise reranker LLM model (only used when strategy="listwise")
RAG_LISTWISE_RERANKER_MODEL = "gpt-4.1-mini"
RAG_LISTWISE_RERANKER_TIMEOUT = 10

# Enable reranking in multi-hop retrieval
# If True, rerank accumulated chunks at END of multi-hop process
# If False, only rerank during single-hop retrieval
RAG_ENABLE_MULTIHOP_RERANKING = True

# Cache reranker model in memory (reduces latency for repeated queries)
RAG_RERANKER_CACHE_MODEL = True

# Reranker timeout (seconds)
RAG_RERANKER_TIMEOUT = 5.0

# Note: Fusion reranker is recommended for initial experimentation (zero latency).
# Cross-encoder reranking adds 50-200ms latency but may improve precision.
# For this small corpus (117 chunks), simpler alternatives like increasing
# RAG_MAX_CHUNKS to 10-12 may provide better ROI than reranking.
```

### Also update the Literal type at the top:

```python
# Add after line 7
RAG_RERANKER_STRATEGY_LITERAL = Literal["fusion", "cross-encoder", "listwise"]
```

---

## 2. Reranker Service Architecture

### 2.1 Directory Structure

```
src/services/rag/
├── reranker.py                 # Base interface (BaseReranker ABC)
├── reranker_fusion.py          # Lightweight score fusion
├── reranker_cross_encoder.py   # BERT cross-encoder
└── reranker_listwise.py        # LLM listwise (experimental)
```

### 2.2 Base Interface

**File: `src/services/rag/reranker.py`**

```python
"""Base interface for RAG reranking strategies."""

from abc import ABC, abstractmethod
from typing import List
from src.models.rag_context import DocumentChunk


class BaseReranker(ABC):
    """Abstract base class for reranking strategies.

    All rerankers must implement the rerank() method which takes a query
    and list of candidate chunks and returns top-k chunks sorted by relevance.
    """

    @abstractmethod
    def rerank(
        self,
        query: str,
        chunks: List[DocumentChunk],
        top_k: int
    ) -> List[DocumentChunk]:
        """Rerank chunks based on relevance to query.

        Args:
            query: Original user query (normalized, NOT expanded)
            chunks: Candidate chunks to rerank (typically 15-30 chunks)
            top_k: Number of top chunks to return (typically 7)

        Returns:
            Top-k chunks sorted by reranker score (DESC)

        Side effects:
            - Updates chunk.relevance_score with reranker score
            - Adds chunk.metadata['reranker_score']
            - Adds chunk.metadata['reranker_strategy']
            - May add chunk.metadata['reranker_model']
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
```

### 2.3 Strategy 1: Fusion Reranker (Recommended for Start)

**File: `src/services/rag/reranker_fusion.py`**

```python
"""Lightweight metadata-based score fusion reranker.

Combines existing RRF, vector similarity, and BM25 scores using weighted average.
No model inference required - instant reranking using pre-computed scores.

Advantages:
- Zero latency (no model calls)
- Leverages all existing retrieval signals
- Easy to tune via weights
- No dependencies beyond current stack

Use case: Quick experimentation, baseline for comparison
"""

from typing import List
import logging
from src.services.rag.reranker import BaseReranker
from src.models.rag_context import DocumentChunk

logger = logging.getLogger(__name__)


class FusionReranker(BaseReranker):
    """Fuses RRF + vector + BM25 scores with configurable weights."""

    def __init__(
        self,
        rrf_weight: float = 0.5,
        vector_weight: float = 0.3,
        bm25_weight: float = 0.2,
        normalize_scores: bool = True
    ):
        """Initialize fusion reranker.

        Args:
            rrf_weight: Weight for RRF normalized score (0-1)
            vector_weight: Weight for vector similarity score (0-1)
            bm25_weight: Weight for BM25 score (0-1)
            normalize_scores: If True, normalize BM25 scores to 0-1 range

        Raises:
            AssertionError: If weights don't sum to 1.0
        """
        # Validate weights sum to 1.0 (allow small floating point error)
        total_weight = rrf_weight + vector_weight + bm25_weight
        assert abs(total_weight - 1.0) < 0.01, \
            f"Weights must sum to 1.0, got {total_weight}"

        self.rrf_weight = rrf_weight
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.normalize_scores = normalize_scores

        logger.info(
            f"Initialized FusionReranker with weights: "
            f"RRF={rrf_weight}, Vector={vector_weight}, BM25={bm25_weight}"
        )

    def rerank(
        self,
        query: str,
        chunks: List[DocumentChunk],
        top_k: int
    ) -> List[DocumentChunk]:
        """Fuse RRF + vector + BM25 scores and return top-k.

        Algorithm:
        1. Extract scores from chunk.metadata:
           - rrf_normalized (0.45-1.0)
           - vector_similarity (0-1)
           - bm25_score (raw, needs normalization)
        2. Normalize BM25 scores to 0-1 range (min-max scaling)
        3. Compute weighted fusion score
        4. Sort by fusion score DESC
        5. Return top-k

        Args:
            query: User query (unused in fusion, kept for interface consistency)
            chunks: Candidate chunks with metadata scores
            top_k: Number of chunks to return

        Returns:
            Top-k chunks sorted by fusion score
        """
        if not chunks:
            return []

        # Normalize BM25 scores across batch
        bm25_scores_normalized = self._normalize_bm25_scores(chunks)

        # Compute fusion scores
        for i, chunk in enumerate(chunks):
            rrf_score = chunk.metadata.get("rrf_normalized", 0.0)
            vector_score = chunk.metadata.get("vector_similarity", 0.0)
            bm25_score = bm25_scores_normalized[i]

            # Weighted fusion
            fusion_score = (
                self.rrf_weight * rrf_score +
                self.vector_weight * vector_score +
                self.bm25_weight * bm25_score
            )

            # Update chunk metadata
            chunk.metadata["reranker_score"] = fusion_score
            chunk.metadata["reranker_strategy"] = "fusion"
            chunk.metadata["fusion_components"] = {
                "rrf": rrf_score,
                "vector": vector_score,
                "bm25": bm25_score,
            }

            # Update primary relevance score
            chunk.relevance_score = fusion_score

        # Sort by fusion score DESC and return top-k
        ranked_chunks = sorted(
            chunks,
            key=lambda c: c.relevance_score,
            reverse=True
        )

        logger.debug(
            f"Fusion reranked {len(chunks)} chunks, "
            f"top score: {ranked_chunks[0].relevance_score:.3f}"
        )

        return ranked_chunks[:top_k]

    def _normalize_bm25_scores(self, chunks: List[DocumentChunk]) -> List[float]:
        """Normalize BM25 scores to 0-1 range using min-max scaling.

        Args:
            chunks: Chunks with metadata['bm25_score']

        Returns:
            List of normalized scores (0-1)
        """
        if not self.normalize_scores:
            return [chunk.metadata.get("bm25_score", 0.0) for chunk in chunks]

        bm25_scores = [chunk.metadata.get("bm25_score", 0.0) for chunk in chunks]

        min_score = min(bm25_scores)
        max_score = max(bm25_scores)

        # Avoid division by zero
        if max_score == min_score:
            return [0.5 for _ in bm25_scores]

        # Min-max normalization
        normalized = [
            (score - min_score) / (max_score - min_score)
            for score in bm25_scores
        ]

        return normalized

    def __repr__(self) -> str:
        return (
            f"FusionReranker(rrf={self.rrf_weight}, "
            f"vector={self.vector_weight}, bm25={self.bm25_weight})"
        )
```

### 2.4 Strategy 2: Cross-Encoder Reranker

**File: `src/services/rag/reranker_cross_encoder.py`**

```python
"""BERT-based cross-encoder relevance scoring reranker.

Uses sentence-transformers cross-encoder models to compute query-chunk
relevance scores via joint encoding (more accurate than bi-encoder).

Requires: sentence-transformers library
Model size: ~80-120MB (downloaded on first use)
Latency: +50-200ms per query depending on model and batch size

Advantages:
- Higher precision than vector similarity alone
- Trained on MS MARCO passage ranking datasets
- Handles semantic nuance better than keyword matching

Disadvantages:
- Added latency (model inference)
- Requires transformers library
- GPU recommended for batch sizes >32

Use case: Production use after validating quality gains justify latency
"""

from typing import List, Optional
import logging
import numpy as np

from src.services.rag.reranker import BaseReranker
from src.models.rag_context import DocumentChunk

logger = logging.getLogger(__name__)

# Lazy import to avoid dependency if not using cross-encoder
try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False
    logger.warning(
        "sentence-transformers not installed. "
        "Cross-encoder reranking unavailable. "
        "Install via: pip install sentence-transformers"
    )


class CrossEncoderReranker(BaseReranker):
    """BERT-based cross-encoder relevance scoring."""

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        batch_size: int = 16,
        cache_model: bool = True,
        normalize_scores: bool = True,
        min_score: float = 0.0,
        timeout: float = 5.0
    ):
        """Initialize cross-encoder reranker.

        Args:
            model_name: HuggingFace model ID (cross-encoder/ms-marco-*)
            batch_size: Batch size for inference (16 recommended)
            cache_model: If True, load model on init (else lazy load)
            normalize_scores: If True, apply sigmoid to logits → 0-1 scores
            min_score: Minimum score threshold (filter below this)
            timeout: Maximum inference time in seconds

        Raises:
            ImportError: If sentence-transformers not installed
        """
        if not CROSS_ENCODER_AVAILABLE:
            raise ImportError(
                "sentence-transformers required for cross-encoder reranking. "
                "Install via: pip install sentence-transformers"
            )

        self.model_name = model_name
        self.batch_size = batch_size
        self.normalize_scores = normalize_scores
        self.min_score = min_score
        self.timeout = timeout
        self._model: Optional[CrossEncoder] = None

        if cache_model:
            self._load_model()

        logger.info(
            f"Initialized CrossEncoderReranker with model '{model_name}', "
            f"batch_size={batch_size}"
        )

    def _load_model(self):
        """Lazy load cross-encoder model."""
        if self._model is None:
            logger.info(f"Loading cross-encoder model: {self.model_name}")
            self._model = CrossEncoder(self.model_name)
            logger.info("Cross-encoder model loaded successfully")

    def rerank(
        self,
        query: str,
        chunks: List[DocumentChunk],
        top_k: int
    ) -> List[DocumentChunk]:
        """Rerank using cross-encoder relevance scores.

        Algorithm:
        1. Prepare query-chunk pairs: [(query, chunk.text), ...]
        2. Batch predict relevance scores via cross-encoder
        3. Normalize scores to 0-1 if enabled (sigmoid)
        4. Filter by min_score threshold
        5. Sort by score DESC
        6. Return top-k

        Args:
            query: User query text
            chunks: Candidate chunks to rerank
            top_k: Number of chunks to return

        Returns:
            Top-k chunks sorted by cross-encoder score
        """
        if not chunks:
            return []

        self._load_model()

        # Prepare query-chunk pairs
        pairs = [(query, chunk.text) for chunk in chunks]

        # Predict relevance scores (batch inference)
        logger.debug(f"Predicting scores for {len(pairs)} query-chunk pairs")
        scores = self._model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False  # Disable tqdm in production
        )

        # Normalize if enabled (MS MARCO models output ~-10 to +10 logits)
        if self.normalize_scores:
            scores = self._sigmoid(scores)

        # Update chunk metadata and scores
        for chunk, score in zip(chunks, scores):
            chunk.metadata["reranker_score"] = float(score)
            chunk.metadata["reranker_strategy"] = "cross-encoder"
            chunk.metadata["reranker_model"] = self.model_name
            chunk.relevance_score = float(score)  # Update primary score

        # Filter by minimum score
        filtered_chunks = [
            c for c in chunks
            if c.relevance_score >= self.min_score
        ]

        if len(filtered_chunks) < len(chunks):
            logger.debug(
                f"Filtered {len(chunks) - len(filtered_chunks)} chunks "
                f"below min_score={self.min_score}"
            )

        # Sort by score DESC and return top-k
        ranked_chunks = sorted(
            filtered_chunks,
            key=lambda c: c.relevance_score,
            reverse=True
        )

        if ranked_chunks:
            logger.debug(
                f"Cross-encoder reranked {len(chunks)} → {len(ranked_chunks)} chunks, "
                f"top score: {ranked_chunks[0].relevance_score:.3f}"
            )

        return ranked_chunks[:top_k]

    def _sigmoid(self, scores: np.ndarray) -> np.ndarray:
        """Normalize scores to 0-1 range using sigmoid activation.

        Args:
            scores: Raw cross-encoder logits (unbounded)

        Returns:
            Normalized scores in 0-1 range
        """
        return 1 / (1 + np.exp(-scores))

    def __repr__(self) -> str:
        return f"CrossEncoderReranker(model='{self.model_name}')"
```

### 2.5 Reranker Factory

**File: `src/services/rag/reranker_factory.py`**

```python
"""Factory for creating reranker instances based on strategy."""

from typing import Optional
import logging
from src.lib import constants
from src.services.rag.reranker import BaseReranker
from src.services.rag.reranker_fusion import FusionReranker
from src.services.rag.reranker_cross_encoder import CrossEncoderReranker

logger = logging.getLogger(__name__)


def create_reranker(
    strategy: Optional[str] = None,
    **kwargs
) -> Optional[BaseReranker]:
    """Create reranker instance based on strategy.

    Args:
        strategy: Reranking strategy ("fusion", "cross-encoder", "listwise")
                  If None, uses constants.RAG_RERANKER_STRATEGY
        **kwargs: Additional arguments passed to reranker constructor

    Returns:
        Reranker instance or None if reranking disabled

    Raises:
        ValueError: If strategy is unknown
    """
    if not constants.RAG_ENABLE_RERANKER:
        logger.info("Reranking disabled (RAG_ENABLE_RERANKER=False)")
        return None

    strategy = strategy or constants.RAG_RERANKER_STRATEGY

    logger.info(f"Creating reranker with strategy: {strategy}")

    if strategy == "fusion":
        return FusionReranker(
            rrf_weight=kwargs.get("rrf_weight", constants.RAG_FUSION_RRF_WEIGHT),
            vector_weight=kwargs.get("vector_weight", constants.RAG_FUSION_VECTOR_WEIGHT),
            bm25_weight=kwargs.get("bm25_weight", constants.RAG_FUSION_BM25_WEIGHT),
            normalize_scores=kwargs.get("normalize_scores", constants.RAG_RERANKER_NORMALIZE_SCORES),
        )

    elif strategy == "cross-encoder":
        return CrossEncoderReranker(
            model_name=kwargs.get("model_name", constants.RAG_RERANKER_MODEL),
            batch_size=kwargs.get("batch_size", constants.RAG_RERANKER_BATCH_SIZE),
            cache_model=kwargs.get("cache_model", constants.RAG_RERANKER_CACHE_MODEL),
            normalize_scores=kwargs.get("normalize_scores", constants.RAG_RERANKER_NORMALIZE_SCORES),
            min_score=kwargs.get("min_score", constants.RAG_RERANKER_MIN_SCORE),
            timeout=kwargs.get("timeout", constants.RAG_RERANKER_TIMEOUT),
        )

    elif strategy == "listwise":
        # TODO: Implement listwise LLM reranker
        raise NotImplementedError("Listwise reranking not yet implemented")

    else:
        raise ValueError(
            f"Unknown reranker strategy: {strategy}. "
            f"Must be one of: fusion, cross-encoder, listwise"
        )
```

---

## 3. Integration Points

### 3.1 Update RetrievalRequest Model

**File: `src/models/user_query.py`**

Add field to `RetrievalRequest` dataclass:

```python
@dataclass
class RetrievalRequest:
    """Request for RAG retrieval."""
    query: str
    max_chunks: int = constants.RAG_MAX_CHUNKS
    min_relevance: float = constants.RAG_MIN_RELEVANCE
    use_hybrid: bool = True
    use_multi_hop: bool = False
    use_reranker: bool = constants.RAG_ENABLE_RERANKER  # <<< ADD THIS
    # ... existing fields ...
```

### 3.2 Update Retriever Service

**File: `src/services/rag/retriever.py`**

#### Import reranker factory:

```python
# Add to imports
from src.services.rag.reranker_factory import create_reranker
from src.lib import constants
```

#### Initialize reranker in `__init__`:

```python
def __init__(self, vector_db, bm25_retriever, hybrid_retriever, multi_hop_retriever):
    self.vector_db = vector_db
    self.bm25_retriever = bm25_retriever
    self.hybrid_retriever = hybrid_retriever
    self.multi_hop_retriever = multi_hop_retriever

    # Initialize reranker (None if disabled)
    self.reranker = create_reranker()  # <<< ADD THIS
    if self.reranker:
        self.logger.info(f"Reranker enabled: {self.reranker}")
```

#### Add reranking logic in `retrieve()` method:

```python
def retrieve(self, request: RetrievalRequest, query_id: Optional[UUID] = None) -> RAGContext:
    # ... existing normalization and embedding logic ...

    # Hybrid fusion
    if request.use_hybrid and self.hybrid_retriever and chunks:
        chunks = self.hybrid_retriever.retrieve_hybrid(
            query=normalized_query,
            expanded_query=expanded_query,
            max_chunks=request.max_chunks,
            query_id=query_id,
        )

    # >>> RERANKING INSERTION POINT <<<
    if request.use_reranker and self.reranker and chunks:
        self.logger.info(
            f"[{query_id}] Reranking {len(chunks)} chunks using {self.reranker}"
        )

        # Retrieve extra candidates for reranking
        candidates_count = max(len(chunks), constants.RAG_RERANKER_CANDIDATES)
        if len(chunks) < candidates_count and request.use_hybrid:
            # Re-retrieve with higher limit
            chunks = self.hybrid_retriever.retrieve_hybrid(
                query=normalized_query,
                expanded_query=expanded_query,
                max_chunks=candidates_count,
                query_id=query_id,
            )

        # Rerank
        chunks = self.reranker.rerank(
            query=normalized_query,
            chunks=chunks,
            top_k=request.max_chunks
        )

        if chunks:
            self.logger.info(
                f"[{query_id}] Reranking complete, "
                f"top score: {chunks[0].relevance_score:.3f}"
            )

    # ... rest of retrieval (filtering, context building) ...
```

### 3.3 Update Multi-Hop Retriever (Optional)

**File: `src/services/rag/multi_hop_retriever.py`**

#### Import reranker:

```python
from src.services.rag.reranker_factory import create_reranker
from src.lib import constants
```

#### Initialize in `__init__`:

```python
def __init__(self, retriever, ...):
    self.retriever = retriever
    # ... existing fields ...

    # Optional: separate reranker for multi-hop
    if constants.RAG_ENABLE_MULTIHOP_RERANKING:
        self.reranker = create_reranker()
    else:
        self.reranker = None
```

#### Add reranking at end of `retrieve_multi_hop()`:

```python
def retrieve_multi_hop(self, request: RetrievalRequest, ...) -> RAGContext:
    # ... multi-hop accumulation logic ...

    # Build final context
    final_context = RAGContext.from_retrieval(
        accumulated_chunks=accumulated_chunks,
        retrieval_metadata={"hops": hop_count, ...}
    )

    # >>> MULTI-HOP RERANKING INSERTION POINT <<<
    if self.reranker and accumulated_chunks:
        self.logger.info(
            f"[{query_id}] Reranking {len(accumulated_chunks)} "
            f"multi-hop chunks using {self.reranker}"
        )

        reranked_chunks = self.reranker.rerank(
            query=request.query,  # Original query (not hop sub-queries)
            chunks=accumulated_chunks,
            top_k=constants.RAG_MAX_CHUNKS
        )

        final_context.document_chunks = reranked_chunks

        self.logger.info(
            f"[{query_id}] Multi-hop reranking complete, "
            f"top score: {reranked_chunks[0].relevance_score:.3f}"
        )

    return final_context
```

### 3.4 Update CLI Commands

**File: `src/cli/query.py`**

Add `--reranker` and `--no-reranker` flags:

```python
@click.option(
    "--reranker/--no-reranker",
    default=None,
    help="Enable/disable reranking (overrides config default)"
)
def query(query_text: str, reranker: Optional[bool], ...):
    """Run a test query."""

    # Build request
    request = RetrievalRequest(
        query=query_text,
        use_reranker=reranker if reranker is not None else constants.RAG_ENABLE_RERANKER,
        # ... other fields ...
    )

    # ... rest of query logic ...
```

---

## 4. Testing Strategy

### 4.1 Unit Tests

**File: `tests/unit/services/rag/test_reranker_fusion.py`**

```python
"""Unit tests for fusion reranker."""

import pytest
from uuid import uuid4
from src.services.rag.reranker_fusion import FusionReranker
from src.models.rag_context import DocumentChunk


def test_fusion_weights_validation():
    """Test that weights must sum to 1.0."""
    with pytest.raises(AssertionError):
        FusionReranker(rrf_weight=0.5, vector_weight=0.5, bm25_weight=0.5)


def test_fusion_reranking():
    """Test basic fusion reranking."""
    reranker = FusionReranker(
        rrf_weight=0.5,
        vector_weight=0.3,
        bm25_weight=0.2
    )

    chunks = [
        DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="Chunk 1",
            header="Header 1",
            header_level=2,
            metadata={
                "rrf_normalized": 0.8,
                "vector_similarity": 0.6,
                "bm25_score": 5.0,
            },
            relevance_score=0.8,
            position_in_doc=0,
        ),
        DocumentChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            text="Chunk 2",
            header="Header 2",
            header_level=2,
            metadata={
                "rrf_normalized": 0.6,
                "vector_similarity": 0.9,
                "bm25_score": 10.0,
            },
            relevance_score=0.6,
            position_in_doc=1,
        ),
    ]

    reranked = reranker.rerank(query="test", chunks=chunks, top_k=2)

    # Check metadata added
    assert "reranker_score" in reranked[0].metadata
    assert reranked[0].metadata["reranker_strategy"] == "fusion"

    # Check sorting (chunk 2 should rank higher due to high vector + BM25)
    assert reranked[0].text == "Chunk 2"
```

**File: `tests/unit/services/rag/test_reranker_cross_encoder.py`**

```python
"""Unit tests for cross-encoder reranker (with mocking)."""

import pytest
from unittest.mock import Mock, patch
from uuid import uuid4
from src.services.rag.reranker_cross_encoder import CrossEncoderReranker
from src.models.rag_context import DocumentChunk


@patch("src.services.rag.reranker_cross_encoder.CrossEncoder")
def test_cross_encoder_reranking(mock_cross_encoder_class):
    """Test cross-encoder reranking with mocked model."""
    # Mock model predictions
    mock_model = Mock()
    mock_model.predict.return_value = [0.9, 0.3, 0.7]  # Scores for 3 chunks
    mock_cross_encoder_class.return_value = mock_model

    reranker = CrossEncoderReranker(
        model_name="test-model",
        normalize_scores=False
    )

    chunks = [
        DocumentChunk(chunk_id=uuid4(), text="Chunk 1", ...),
        DocumentChunk(chunk_id=uuid4(), text="Chunk 2", ...),
        DocumentChunk(chunk_id=uuid4(), text="Chunk 3", ...),
    ]

    reranked = reranker.rerank(query="test query", chunks=chunks, top_k=2)

    # Check model was called
    mock_model.predict.assert_called_once()

    # Check sorting (chunk 1 score=0.9 should be first)
    assert reranked[0].text == "Chunk 1"
    assert reranked[0].relevance_score == 0.9
    assert len(reranked) == 2
```

### 4.2 Integration Tests

**File: `tests/integration/test_retrieval_with_reranking.py`**

```python
"""Integration test for end-to-end retrieval with reranking."""

import pytest
from src.services.rag.retriever import Retriever
from src.models.user_query import RetrievalRequest
from src.lib import constants


@pytest.mark.integration
def test_retrieval_with_fusion_reranking(retriever_fixture):
    """Test full retrieval pipeline with fusion reranking."""
    request = RetrievalRequest(
        query="Can I use overwatch during a charge?",
        use_hybrid=True,
        use_reranker=True,
        max_chunks=7
    )

    # Temporarily enable fusion reranking
    original_value = constants.RAG_ENABLE_RERANKER
    original_strategy = constants.RAG_RERANKER_STRATEGY
    constants.RAG_ENABLE_RERANKER = True
    constants.RAG_RERANKER_STRATEGY = "fusion"

    try:
        context = retriever_fixture.retrieve(request)

        # Check reranker metadata present
        assert len(context.document_chunks) > 0
        chunk = context.document_chunks[0]
        assert "reranker_score" in chunk.metadata
        assert chunk.metadata["reranker_strategy"] == "fusion"

    finally:
        constants.RAG_ENABLE_RERANKER = original_value
        constants.RAG_RERANKER_STRATEGY = original_strategy
```

### 4.3 Quality Tests

Update existing quality tests to run with/without reranking:

```bash
# Baseline (no reranking)
python -m src.cli quality-test --all-tests --runs 3

# With fusion reranking
RAG_ENABLE_RERANKER=true RAG_RERANKER_STRATEGY=fusion \
  python -m src.cli quality-test --all-tests --runs 3

# With cross-encoder reranking
RAG_ENABLE_RERANKER=true RAG_RERANKER_STRATEGY=cross-encoder \
  python -m src.cli quality-test --all-tests --runs 3
```

---

## 5. Deployment Plan

### Phase 1: Fusion Reranker (Week 1)

**Goal**: Establish baseline with zero-latency fusion reranking

1. **Implementation**:
   - [ ] Add constants to `constants.py`
   - [ ] Implement `FusionReranker`
   - [ ] Integrate into `retriever.py`
   - [ ] Add unit tests

2. **Testing**:
   - [ ] Run quality tests (baseline vs fusion)
   - [ ] Compare Ragas scores (faithfulness, relevance)
   - [ ] Tune fusion weights if needed

3. **Analysis**:
   - If fusion shows **no improvement**: Stop here, increase `RAG_MAX_CHUNKS` instead
   - If fusion shows **marginal improvement** (1-2%): Proceed to Phase 2
   - If fusion shows **significant improvement** (3%+): Enable in production

### Phase 2: Cross-Encoder Validation (Week 2)

**Goal**: Validate if neural reranking justifies latency cost

1. **Implementation**:
   - [ ] Implement `CrossEncoderReranker`
   - [ ] Add sentence-transformers to requirements
   - [ ] Add latency logging
   - [ ] Test multiple models (TinyBERT, MiniLM-L-6, MiniLM-L-12)

2. **Benchmarking**:
   - [ ] Measure p50/p95/p99 latency
   - [ ] Run quality tests across models
   - [ ] Compare quality vs latency tradeoff

3. **Decision**:
   - If cross-encoder shows **<2% improvement** over fusion: Use fusion only
   - If cross-encoder shows **2-5% improvement**: A/B test in production
   - If cross-encoder shows **>5% improvement**: Enable by default

### Phase 3: Production Rollout (Week 3)

**Goal**: Gradual rollout with monitoring

1. **Staging**:
   - [ ] Deploy to staging environment
   - [ ] Enable analytics dashboard
   - [ ] Monitor for 3-5 days

2. **A/B Test** (if cross-encoder justified):
   - [ ] 50% queries with reranking, 50% without
   - [ ] Track upvote/downvote ratios
   - [ ] Monitor query latency

3. **Production**:
   - [ ] Gradual rollout: 10% → 50% → 100%
   - [ ] Monitor analytics for 2 weeks
   - [ ] Tune hyperparameters based on feedback

---

## 6. Success Metrics

### Quality Metrics (from quality tests)

- **Ragas Faithfulness**: Target >0.85 (currently ~0.8)
- **Ragas Answer Relevance**: Target >0.90 (currently ~0.85)
- **Contextual Precision**: % relevant chunks in top-7

### Performance Metrics

- **Latency p50**: <500ms (fusion) or <700ms (cross-encoder)
- **Latency p95**: <1000ms (fusion) or <1200ms (cross-encoder)
- **Throughput**: >10 queries/second

### User Metrics (from Discord analytics)

- **Upvote ratio**: >60% (currently ~55% assumed)
- **Downvote reduction**: -10% compared to baseline
- **Multi-hop query rate**: Reduced by 10-20% (better single-hop precision)

---

## 7. Alternatives to Consider

### Option 1: Increase RAG_MAX_CHUNKS (Simplest)

**Change**: `RAG_MAX_CHUNKS = 7 → 10` or `12`

**Pros**:
- Zero implementation cost
- More context for LLM
- Already tested (was 15 previously)

**Cons**:
- Higher LLM token costs
- May include more irrelevant chunks

**Recommendation**: Try this FIRST before implementing reranking

### Option 2: Metadata Filtering

**Change**: Filter chunks by `doc_type` before retrieval

**Example**:
```python
if "pathfinder" in query.lower():
    filter_metadata = {"doc_type": "team-rules"}
```

**Pros**:
- Reduces noise
- Zero latency
- Easy to implement

**Cons**:
- Requires query analysis
- May miss cross-document interactions

### Option 3: Query Decomposition

**Change**: Break complex queries into sub-queries, retrieve separately, merge

**Example**:
```
Query: "Can Eliminator shoot while concealed during counteract?"
→ Sub-queries:
  1. "Eliminator concealed shooting"
  2. "Counteract ability"
  3. "Silent weapon rules"
```

**Pros**:
- Leverages existing retrieval
- More interpretable
- May improve recall

**Cons**:
- Requires LLM call for decomposition
- Added complexity

---

## 8. Dependencies

### Python Packages

Add to `requirements.txt`:

```txt
# Reranking (optional, only if using cross-encoder)
sentence-transformers>=2.2.0  # Cross-encoder models
torch>=2.0.0                  # Required by sentence-transformers
```

### Model Downloads

Cross-encoder models are auto-downloaded on first use:

- `cross-encoder/ms-marco-TinyBERT-L-2-v2`: ~20MB
- `cross-encoder/ms-marco-MiniLM-L-6-v2`: ~80MB (recommended)
- `cross-encoder/ms-marco-MiniLM-L-12-v2`: ~120MB

Models cached in `~/.cache/huggingface/hub/` by default.

---

## 9. Documentation Updates

### Files to Update

- [ ] `CLAUDE.md`: Add reranking section
- [ ] `src/services/CLAUDE.md`: Document reranker service
- [ ] `src/services/rag/CLAUDE.md`: Detailed reranking architecture
- [ ] `src/lib/constants.py`: Inline comments for new constants

### New Documentation

- [ ] `docs/reranking-guide.md`: Tuning guide, model selection, troubleshooting
- [ ] `docs/reranking-evaluation.md`: Results of A/B testing, quality comparison

---

## 10. Summary & Recommendation

### Key Findings

1. **Small corpus** (117 chunks) may not benefit significantly from reranking
2. **Current hybrid search** (vector + BM25 + RRF) already effective
3. **Multi-hop retrieval** handles complex queries well

### Recommended Approach

**Phase 0** (Before implementing reranking):
1. Try increasing `RAG_MAX_CHUNKS` from 7 → 10-12
2. Tune `BM25_WEIGHT` via grid search (e.g., 0.3, 0.5, 0.7)
3. Enable metadata filtering by `doc_type`
4. Run quality tests and compare

**If Phase 0 insufficient**, proceed with:

**Phase 1**: Implement fusion reranker (zero latency)
**Phase 2**: Validate cross-encoder (if fusion shows promise)
**Phase 3**: Production rollout (gradual, monitored)

### Expected Outcome

- **Fusion reranking**: 0-2% quality improvement, 0ms latency
- **Cross-encoder reranking**: 2-5% quality improvement, +50-200ms latency

**Final verdict**: Implement infrastructure for experimentation, but simpler alternatives (more chunks, better fusion weights) may provide better ROI.

---

## Appendix: Cross-Encoder Model Comparison

| Model | Parameters | Latency (16 batch) | NDCG@10 | Use Case |
|-------|------------|--------------------|---------| ---------|
| `ms-marco-TinyBERT-L-2-v2` | 14M | 30ms | 0.327 | Ultra-low latency |
| `ms-marco-MiniLM-L-6-v2` | 23M | 50ms | 0.349 | **Recommended** |
| `ms-marco-MiniLM-L-12-v2` | 34M | 100ms | 0.369 | Higher quality |
| `ms-marco-electra-base` | 110M | 200ms | 0.384 | Maximum quality |

Benchmarks from sentence-transformers docs (MS MARCO Passage Ranking).

---

**End of Implementation Plan**
