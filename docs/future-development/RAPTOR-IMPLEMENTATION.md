# RAPTOR Implementation Plan for Kill Team Rules Bot

**Last updated:** 2025-01-09

## Table of Contents

- [What is RAPTOR?](#what-is-raptor)
- [Should We Implement RAPTOR?](#should-we-implement-raptor)
- [Implementation Plan](#implementation-plan)
- [Estimated Effort and Costs](#estimated-effort-and-costs)
- [Alternative: Enhance Multi-Hop First](#alternative-enhance-multi-hop-first)
- [Decision Criteria](#decision-criteria)
- [References](#references)

---

## What is RAPTOR?

**RAPTOR** (Recursive Abstractive Processing for Tree-Organized Retrieval) is an advanced RAG technique published at ICLR 2024 that creates hierarchical tree structures from documents.

### Key Concepts

1. **Hierarchical Clustering**: Groups semantically similar chunks using UMAP dimensionality reduction + Gaussian Mixture Models (GMM)
2. **Abstractive Summarization**: Uses LLMs to summarize each cluster, creating higher-level representations
3. **Recursive Tree Building**: Summaries become nodes in the next level, process repeats until convergence
4. **Multi-Level Retrieval**: At query time, retrieve from all tree levels simultaneously (both original chunks and summaries)

### How It Works

```
Original Document
    ↓
[Chunk into 100-token segments] → Leaf Nodes (Level 0)
    ↓
[Embed with SBERT/OpenAI]
    ↓
[UMAP dimensionality reduction]
    ↓
[GMM clustering with BIC optimization]
    ↓
[LLM summarizes each cluster] → Summary Nodes (Level 1)
    ↓
[Re-embed summaries]
    ↓
[Repeat clustering + summarization] → Level 2, 3, etc.
    ↓
[Stop when ≤2 clusters or max depth reached]
    ↓
Tree Structure: Root ← Summaries ← Summaries ← Leaf Chunks

Query Time:
    ↓
[Flatten all levels into single pool]
    ↓
[Vector search across all nodes]
    ↓
[Return top-k by similarity]
```

### Research Results

- **Performance**: 20% absolute accuracy improvement on QuALITY benchmark (GPT-4)
- **Use Cases**: Excels at complex multi-step reasoning over long documents
- **Retrieval**: Significant portion of final results comes from non-leaf layers (summaries)

---

## Should We Implement RAPTOR?

### ✅ Potential Benefits

1. **Natural Document Hierarchy**: Kill Team rules have clear structure
   - Core Rules → Sections (Movement, Shooting, etc.) → Subsections
   - Team Rules → Faction → Operatives → Abilities
   - Natural fit for hierarchical representation

2. **Complex Multi-Section Queries**
   - "How do Pathfinders interact with barricades and cover?" (3 rule sections)
   - "Can a concealed Eliminator use counteract against an enemy in engage order?" (multiple mechanics)
   - Current system may retrieve too narrowly

3. **Multi-Level Context**
   - High-level summaries: "Movement rules overview"
   - Mid-level: "Charge action mechanics"
   - Low-level: "Charge into engagement range calculation"
   - Provides both thematic understanding and specific details

4. **Better than Sequential Hops**
   - Current multi-hop (1 hop) adds context sequentially
   - RAPTOR provides hierarchical context natively
   - May reduce need for multiple retrieval iterations

### ⚠️ Drawbacks and Risks

1. **Implementation Complexity**
   - New dependencies: `umap-learn`, `scikit-learn`, `scipy`
   - Complex clustering logic (UMAP + GMM + BIC)
   - Tree structure management and persistence
   - More debugging surface area

2. **Ingestion Cost**
   - LLM summarization calls during tree building
   - Estimated: ~$0.30-0.65 per full ingestion (1300+ chunks → ~10-15 summary levels)
   - One-time cost, but re-runs on rule updates

3. **Ingestion Time**
   - Current: ~30 seconds
   - With RAPTOR: +2-5 minutes (clustering + summarization)
   - May impact developer workflow

4. **Storage Overhead**
   - Summaries stored alongside original chunks
   - Estimated: +30-50% vector DB size
   - ChromaDB disk usage increases

5. **Maintenance Burden**
   - More tunable hyperparameters (UMAP neighbors, GMM clusters, tree depth)
   - Harder to debug retrieval issues
   - Requires understanding of clustering algorithms
   - Summary quality depends on LLM model

6. **Diminishing Returns Risk**
   - Current system already has:
     - Multi-hop retrieval (iterative context)
     - Hybrid search (vector + BM25)
     - Header-based chunking (preserves structure)
     - Query expansion (handles terminology)
   - RAPTOR may not provide enough additional value

### 📊 Current System Strengths

Before adding RAPTOR, recognize what already works:

| Feature | Current Implementation | Coverage |
|---------|----------------------|----------|
| **Iterative Context** | Multi-hop retrieval (1 hop max) | ✅ Handles missing context |
| **Semantic + Keyword** | Hybrid search (vector + BM25) | ✅ Catches both meanings and exact terms |
| **Structure Preservation** | Header-based chunking (## and ###) | ✅ Respects document hierarchy |
| **Terminology Handling** | Query expansion + normalization | ✅ Maps user terms to official rules |
| **Metadata Filtering** | Available but unused | ⚠️ Could filter by doc_type |

### 💡 Recommendation

**✅ Implement RAPTOR if**:
- Post-deployment analytics show frequent multi-section questions
- Users complain about incomplete answers requiring thematic understanding
- Current multi-hop retrieval (1 hop) proves insufficient in quality tests
- Budget allows ~$0.50 per ingestion + ongoing storage costs
- Team has bandwidth for 2-3 weeks of implementation + tuning

**❌ Defer/Skip RAPTOR if**:
- Current retrieval quality meets user needs
- Simpler improvements (increase max hops, better prompts) can address issues
- Cost or complexity trade-off not justified
- Team prefers incremental improvements over architectural changes

**🔄 Recommended First Step**: Try simpler enhancements before RAPTOR:
1. Increase `RAG_MAX_HOPS` from 1 to 2-3
2. Improve hop evaluation prompts for better gap analysis
3. Enable metadata-based filtering (e.g., "search only core-rules for this query")
4. Implement query decomposition (break complex questions into focused sub-queries)

If these don't sufficiently improve quality, then proceed with RAPTOR.

---

## Implementation Plan

*If proceeding with RAPTOR after trying simpler alternatives...*

### Phase 1: Dependencies & Structure (1 day)

**Install dependencies**:
```bash
# Add to requirements.txt
umap-learn>=0.5.5
scikit-learn>=1.3.0
scipy>=1.11.0
```

**Create module structure**:
```
src/services/rag/raptor/
├── __init__.py
├── tree_builder.py      # UMAP + GMM clustering, tree construction
├── summarizer.py         # LLM-based cluster summarization
├── tree_retriever.py     # Hierarchical retrieval (collapsed + tree-traversal)
├── tree_store.py         # Tree persistence in ChromaDB
├── models.py             # TreeNode, TreeStructure dataclasses
└── CLAUDE.md             # RAPTOR service documentation

prompts/
└── raptor-summary-prompt.md  # Summarization prompt template

tests/unit/rag/raptor/
├── test_tree_builder.py
├── test_summarizer.py
├── test_tree_store.py
└── test_tree_retriever.py

tests/quality/
└── raptor_tests.yaml     # Quality tests for RAPTOR
```

---

### Phase 2: Tree Building (2-3 days)

**File**: `src/services/rag/raptor/tree_builder.py`

```python
"""RAPTOR tree builder using UMAP + GMM clustering."""

from typing import List, Tuple
from uuid import UUID, uuid4
from dataclasses import dataclass
import numpy as np
from umap import UMAP
from sklearn.mixture import GaussianMixture
from scipy.cluster.hierarchy import linkage, fcluster

from src.models.rag_context import DocumentChunk
from src.services.rag.raptor.models import TreeNode, TreeStructure
from src.lib.constants import (
    RAPTOR_MAX_TREE_DEPTH,
    RAPTOR_UMAP_N_NEIGHBORS,
    RAPTOR_GMM_MAX_CLUSTERS,
)
from src.lib.logging import get_logger

logger = get_logger(__name__)


class RAPTORTreeBuilder:
    """Builds hierarchical tree structure using recursive clustering and summarization."""

    def __init__(
        self,
        summarizer,  # RAPTORSummarizer instance
        embedding_service,  # EmbeddingService instance
        max_depth: int = RAPTOR_MAX_TREE_DEPTH,
        umap_neighbors: List[int] = RAPTOR_UMAP_N_NEIGHBORS,
        gmm_max_clusters: int = RAPTOR_GMM_MAX_CLUSTERS,
    ):
        self.summarizer = summarizer
        self.embedding_service = embedding_service
        self.max_depth = max_depth
        self.umap_neighbors = umap_neighbors
        self.gmm_max_clusters = gmm_max_clusters

    def build_tree(self, leaf_chunks: List[DocumentChunk]) -> TreeStructure:
        """Build RAPTOR tree from leaf chunks.

        Args:
            leaf_chunks: Original document chunks (level 0)

        Returns:
            TreeStructure with all levels
        """
        logger.info("raptor_tree_building_started", leaf_count=len(leaf_chunks))

        # Initialize tree with leaf nodes
        tree = TreeStructure(levels=[])
        current_level_nodes = [
            TreeNode(
                node_id=chunk.chunk_id,
                text=chunk.text,
                embedding=None,  # Will fetch from existing embeddings
                level=0,
                is_summary=False,
                parent_ids=[],
                metadata=chunk.metadata,
            )
            for chunk in leaf_chunks
        ]
        tree.levels.append(current_level_nodes)

        # Get embeddings for leaf nodes (already exist in vector DB)
        embeddings = self._get_embeddings_for_nodes(current_level_nodes)

        # Build tree levels recursively
        for level in range(1, self.max_depth + 1):
            logger.info(f"raptor_building_level_{level}", node_count=len(current_level_nodes))

            # Cluster current level
            clusters = self._cluster_nodes(current_level_nodes, embeddings, level)

            if len(clusters) <= 2:
                logger.info("raptor_tree_converged", final_level=level - 1)
                break

            # Summarize each cluster
            summary_nodes = []
            for cluster_id, cluster_node_ids in clusters.items():
                cluster_nodes = [n for n in current_level_nodes if n.node_id in cluster_node_ids]
                summary_text = self.summarizer.summarize_cluster([n.text for n in cluster_nodes])

                summary_node = TreeNode(
                    node_id=uuid4(),
                    text=summary_text,
                    embedding=None,  # Will generate below
                    level=level,
                    is_summary=True,
                    parent_ids=cluster_node_ids,
                    metadata={"cluster_size": len(cluster_nodes)},
                )
                summary_nodes.append(summary_node)

            # Generate embeddings for summaries
            embeddings = self.embedding_service.embed_batch([n.text for n in summary_nodes])
            for node, embedding in zip(summary_nodes, embeddings):
                node.embedding = embedding

            # Add level to tree
            tree.levels.append(summary_nodes)

            # Next iteration processes summaries
            current_level_nodes = summary_nodes

        logger.info("raptor_tree_built", total_levels=len(tree.levels), total_nodes=tree.total_nodes())
        return tree

    def _cluster_nodes(
        self, nodes: List[TreeNode], embeddings: np.ndarray, level: int
    ) -> dict[int, List[UUID]]:
        """Cluster nodes using UMAP + GMM.

        Args:
            nodes: Nodes to cluster
            embeddings: Node embeddings (N x D matrix)
            level: Current tree level (affects UMAP n_neighbors)

        Returns:
            Dict mapping cluster_id to list of node UUIDs
        """
        # UMAP dimensionality reduction (multi-scale)
        n_neighbors = self.umap_neighbors[min(level - 1, len(self.umap_neighbors) - 1)]
        reducer = UMAP(n_neighbors=n_neighbors, n_components=10, metric="cosine")
        reduced_embeddings = reducer.fit_transform(embeddings)

        # GMM clustering with BIC to select optimal cluster count
        best_gmm = None
        best_bic = float("inf")
        best_n_clusters = 2

        for n_clusters in range(2, min(self.gmm_max_clusters, len(nodes)) + 1):
            gmm = GaussianMixture(n_components=n_clusters, random_state=42)
            gmm.fit(reduced_embeddings)
            bic = gmm.bic(reduced_embeddings)

            if bic < best_bic:
                best_bic = bic
                best_gmm = gmm
                best_n_clusters = n_clusters

        # Assign nodes to clusters
        labels = best_gmm.predict(reduced_embeddings)
        clusters = {}
        for node, label in zip(nodes, labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(node.node_id)

        logger.debug(
            "raptor_clustering_complete",
            level=level,
            n_clusters=best_n_clusters,
            bic=best_bic,
        )

        return clusters

    def _get_embeddings_for_nodes(self, nodes: List[TreeNode]) -> np.ndarray:
        """Get embeddings for nodes (fetch or generate)."""
        # For leaf nodes, embeddings already exist in vector DB
        # For summary nodes, generate new embeddings
        # Implementation depends on whether we store embeddings separately
        pass
```

**File**: `src/services/rag/raptor/models.py`

```python
"""Data models for RAPTOR tree structure."""

from dataclasses import dataclass, field
from typing import List, Dict, Any
from uuid import UUID


@dataclass
class TreeNode:
    """A node in the RAPTOR tree."""

    node_id: UUID
    text: str
    embedding: List[float] | None  # Embedding vector
    level: int  # 0=leaf, 1=first summary, etc.
    is_summary: bool  # True if generated by summarization
    parent_ids: List[UUID]  # IDs of child nodes (empty for leaves)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TreeStructure:
    """Complete RAPTOR tree with all levels."""

    levels: List[List[TreeNode]]  # levels[0]=leaves, levels[1]=first summaries, etc.

    def total_nodes(self) -> int:
        """Count total nodes across all levels."""
        return sum(len(level) for level in self.levels)

    def get_all_nodes(self) -> List[TreeNode]:
        """Flatten tree to single list of all nodes."""
        return [node for level in self.levels for node in level]
```

---

### Phase 3: Summarization (1 day)

**File**: `src/services/rag/raptor/summarizer.py`

```python
"""LLM-based cluster summarization for RAPTOR."""

from typing import List
from pathlib import Path

from src.services.llm.factory import LLMProviderFactory
from src.lib.constants import (
    RAPTOR_SUMMARIZATION_MODEL,
    RAPTOR_SUMMARIZATION_PROMPT,
    RAPTOR_SUMMARY_MAX_TOKENS,
    RAPTOR_SUMMARY_TEMPERATURE,
)
from src.lib.logging import get_logger

logger = get_logger(__name__)


class RAPTORSummarizer:
    """Summarizes clusters of text chunks using LLMs."""

    def __init__(
        self,
        llm_provider_factory: LLMProviderFactory | None = None,
        model: str = RAPTOR_SUMMARIZATION_MODEL,
    ):
        self.factory = llm_provider_factory or LLMProviderFactory()
        self.model = model
        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """Load summarization prompt from file."""
        prompt_path = Path(RAPTOR_SUMMARIZATION_PROMPT)
        if not prompt_path.exists():
            logger.warning("raptor_prompt_not_found", using_default=True)
            return self._get_default_prompt()
        return prompt_path.read_text()

    def _get_default_prompt(self) -> str:
        """Default summarization prompt."""
        return """Write a concise summary of the following Kill Team rules section.

Preserve:
- Specific game mechanics and numerical values (e.g., "6\" range", "4+ to hit")
- Ability names and keywords with exact capitalization (e.g., "Accurate", "Lethal 5+")
- Rule interactions and dependencies
- Key restrictions and conditions

Rules to summarize:
{context}

Summary:"""

    def summarize_cluster(self, chunk_texts: List[str]) -> str:
        """Summarize a cluster of text chunks.

        Args:
            chunk_texts: List of text strings to summarize

        Returns:
            Summary text
        """
        # Combine chunks into single context
        combined_text = "\n\n---\n\n".join(chunk_texts)

        # Format prompt
        prompt = self.prompt_template.replace("{context}", combined_text)

        # Generate summary using LLM
        llm = self.factory.create(self.model)

        # Note: RAPTOR summarization doesn't use structured output
        # Just plain text generation
        response = llm.generate_text(
            prompt=prompt,
            max_tokens=RAPTOR_SUMMARY_MAX_TOKENS,
            temperature=RAPTOR_SUMMARY_TEMPERATURE,
        )

        logger.debug(
            "raptor_cluster_summarized",
            chunk_count=len(chunk_texts),
            input_length=len(combined_text),
            summary_length=len(response),
        )

        return response
```

**File**: `prompts/raptor-summary-prompt.md`

```markdown
Write a concise summary of the following Kill Team rules section.

Preserve:
- Specific game mechanics and numerical values (e.g., "6\" range", "4+ to hit")
- Ability names and keywords with exact capitalization (e.g., "Accurate", "Lethal 5+")
- Rule interactions and dependencies between different mechanics
- Key restrictions, conditions, and timing (e.g., "once per turning point", "at the start of each activation")
- Faction-specific mechanics and operative names

Avoid:
- Adding interpretation or examples not in the original text
- Changing numerical values or measurements
- Removing important edge cases or exceptions

Rules to summarize:
{context}

Summary:
```

---

### Phase 4: Tree Storage (1-2 days)

**File**: `src/services/rag/raptor/tree_store.py`

```python
"""Persistence layer for RAPTOR tree structure."""

from typing import List
from uuid import UUID

from src.services.rag.vector_db import VectorDBService
from src.services.rag.raptor.models import TreeNode, TreeStructure
from src.lib.logging import get_logger

logger = get_logger(__name__)


class RAPTORTreeStore:
    """Stores and retrieves RAPTOR tree nodes in ChromaDB."""

    def __init__(self, vector_db: VectorDBService | None = None):
        # Option 1: Separate collection for tree
        self.vector_db = vector_db or VectorDBService(collection_name="kill_team_rules_raptor")

        # Option 2: Same collection with tree metadata
        # self.vector_db = vector_db or VectorDBService(collection_name="kill_team_rules")

    def store_tree(self, tree: TreeStructure) -> None:
        """Store entire tree structure in vector DB.

        Args:
            tree: Complete RAPTOR tree
        """
        all_nodes = tree.get_all_nodes()

        # Prepare data for vector DB
        ids = [str(node.node_id) for node in all_nodes]
        embeddings = [node.embedding for node in all_nodes]
        documents = [node.text for node in all_nodes]
        metadatas = [
            {
                "tree_level": node.level,
                "is_summary": node.is_summary,
                "parent_ids": ",".join(str(pid) for pid in node.parent_ids),
                **node.metadata,
            }
            for node in all_nodes
        ]

        # Upsert (handles both insert and update)
        self.vector_db.upsert_embeddings(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        logger.info(
            "raptor_tree_stored",
            total_nodes=len(all_nodes),
            total_levels=len(tree.levels),
        )

    def load_tree(self) -> TreeStructure:
        """Load tree structure from vector DB.

        Returns:
            Reconstructed TreeStructure
        """
        # Get all nodes from collection
        results = self.vector_db.collection.get(include=["documents", "metadatas", "embeddings"])

        # Group by level
        levels_dict = {}
        for i, node_id_str in enumerate(results["ids"]):
            metadata = results["metadatas"][i]
            level = metadata["tree_level"]

            parent_ids_str = metadata.get("parent_ids", "")
            parent_ids = [UUID(pid) for pid in parent_ids_str.split(",") if pid]

            node = TreeNode(
                node_id=UUID(node_id_str),
                text=results["documents"][i],
                embedding=results["embeddings"][i],
                level=level,
                is_summary=metadata["is_summary"],
                parent_ids=parent_ids,
                metadata=metadata,
            )

            if level not in levels_dict:
                levels_dict[level] = []
            levels_dict[level].append(node)

        # Sort levels by level number
        sorted_levels = [levels_dict[i] for i in sorted(levels_dict.keys())]

        tree = TreeStructure(levels=sorted_levels)
        logger.info("raptor_tree_loaded", total_levels=len(tree.levels), total_nodes=tree.total_nodes())
        return tree

    def clear_tree(self) -> None:
        """Delete all tree nodes."""
        self.vector_db.reset()
        logger.info("raptor_tree_cleared")
```

---

### Phase 5: Hierarchical Retrieval (2 days)

**File**: `src/services/rag/raptor/tree_retriever.py`

```python
"""Hierarchical retrieval from RAPTOR tree."""

from typing import List, Tuple
from uuid import UUID

from src.models.rag_context import RAGContext, DocumentChunk
from src.services.rag.embeddings import EmbeddingService
from src.services.rag.raptor.tree_store import RAPTORTreeStore
from src.lib.constants import RAPTOR_RETRIEVAL_MODE, RAG_MAX_CHUNKS
from src.lib.logging import get_logger

logger = get_logger(__name__)


class RAPTORRetriever:
    """Retrieves from RAPTOR tree using collapsed or tree-traversal mode."""

    def __init__(
        self,
        tree_store: RAPTORTreeStore | None = None,
        embedding_service: EmbeddingService | None = None,
        retrieval_mode: str = RAPTOR_RETRIEVAL_MODE,
    ):
        self.tree_store = tree_store or RAPTORTreeStore()
        self.embedding_service = embedding_service or EmbeddingService()
        self.retrieval_mode = retrieval_mode

    def retrieve(
        self, query: str, max_chunks: int = RAG_MAX_CHUNKS, max_tokens: int = 2000
    ) -> Tuple[List[DocumentChunk], dict]:
        """Retrieve from RAPTOR tree.

        Args:
            query: User query
            max_chunks: Maximum chunks to return
            max_tokens: Maximum total tokens (for collapsed mode)

        Returns:
            Tuple of (chunks, metadata)
        """
        if self.retrieval_mode == "collapsed":
            return self._retrieve_collapsed(query, max_chunks, max_tokens)
        elif self.retrieval_mode == "tree-traversal":
            return self._retrieve_tree_traversal(query, max_chunks)
        else:
            raise ValueError(f"Unknown retrieval mode: {self.retrieval_mode}")

    def _retrieve_collapsed(
        self, query: str, max_chunks: int, max_tokens: int
    ) -> Tuple[List[DocumentChunk], dict]:
        """Collapsed tree retrieval: query all levels simultaneously.

        Args:
            query: User query
            max_chunks: Maximum chunks to return
            max_tokens: Maximum total tokens

        Returns:
            Tuple of (chunks, metadata)
        """
        # Generate query embedding
        query_embedding = self.embedding_service.embed_text(query)

        # Query all tree nodes (all levels)
        results = self.tree_store.vector_db.query(
            query_embeddings=[query_embedding],
            n_results=max_chunks * 2,  # Retrieve more, filter by tokens
        )

        # Convert to DocumentChunk objects
        chunks = []
        total_tokens = 0

        if results["ids"] and results["ids"][0]:
            for i, chunk_id_str in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i]
                text = results["documents"][0][i]
                distance = results["distances"][0][i]

                # Convert L2 distance to similarity
                relevance_score = max(0.0, 1.0 - (distance / 2.0))

                # Create chunk
                chunk = DocumentChunk(
                    chunk_id=UUID(chunk_id_str),
                    document_id=UUID(metadata.get("document_id", str(UUID(int=0)))),
                    text=text,
                    header=metadata.get("header", ""),
                    header_level=metadata.get("header_level", 0),
                    metadata={
                        **metadata,
                        "raptor_level": metadata["tree_level"],
                        "raptor_is_summary": metadata["is_summary"],
                    },
                    relevance_score=relevance_score,
                    position_in_doc=metadata.get("position", 0),
                )

                # Token budget check
                chunk_tokens = len(text.split())  # Rough estimate
                if total_tokens + chunk_tokens > max_tokens:
                    break

                chunks.append(chunk)
                total_tokens += chunk_tokens

                if len(chunks) >= max_chunks:
                    break

        metadata = {
            "retrieval_mode": "collapsed",
            "total_chunks": len(chunks),
            "total_tokens": total_tokens,
        }

        logger.info("raptor_retrieval_completed", mode="collapsed", chunks=len(chunks))
        return chunks, metadata

    def _retrieve_tree_traversal(
        self, query: str, max_chunks: int
    ) -> Tuple[List[DocumentChunk], dict]:
        """Tree traversal retrieval: top-down through tree layers.

        Args:
            query: User query
            max_chunks: Top-k nodes to select at each level

        Returns:
            Tuple of (chunks, metadata)
        """
        # Generate query embedding
        query_embedding = self.embedding_service.embed_text(query)

        # Load tree structure
        tree = self.tree_store.load_tree()

        # Start at root (highest level)
        selected_chunks = []
        current_level = len(tree.levels) - 1

        while current_level >= 0:
            # Query current level
            level_nodes = tree.levels[current_level]
            level_embeddings = [node.embedding for node in level_nodes]

            # Calculate similarities
            similarities = self._calculate_similarities(query_embedding, level_embeddings)

            # Select top-k nodes
            top_k_indices = sorted(
                range(len(similarities)), key=lambda i: similarities[i], reverse=True
            )[:max_chunks]

            # Add to results
            for idx in top_k_indices:
                node = level_nodes[idx]
                chunk = DocumentChunk(
                    chunk_id=node.node_id,
                    document_id=UUID(int=0),  # Tree nodes don't have document_id
                    text=node.text,
                    header="",
                    header_level=node.level,
                    metadata={
                        **node.metadata,
                        "raptor_level": node.level,
                        "raptor_is_summary": node.is_summary,
                    },
                    relevance_score=similarities[idx],
                    position_in_doc=0,
                )
                selected_chunks.append(chunk)

            # Move to next level down
            current_level -= 1

        metadata = {
            "retrieval_mode": "tree-traversal",
            "total_chunks": len(selected_chunks),
            "levels_traversed": len(tree.levels),
        }

        logger.info("raptor_retrieval_completed", mode="tree-traversal", chunks=len(selected_chunks))
        return selected_chunks, metadata

    def _calculate_similarities(self, query_embedding: List[float], node_embeddings: List[List[float]]) -> List[float]:
        """Calculate cosine similarities between query and nodes."""
        import numpy as np

        query_vec = np.array(query_embedding)
        node_vecs = np.array(node_embeddings)

        # Cosine similarity
        similarities = np.dot(node_vecs, query_vec) / (
            np.linalg.norm(node_vecs, axis=1) * np.linalg.norm(query_vec)
        )

        return similarities.tolist()
```

---

### Phase 6: Integration with RAG Pipeline (1-2 days)

**Update**: `src/lib/constants.py`

```python
# ============================================================================
# RAPTOR Tree-Organized Retrieval
# ============================================================================

# Enable/disable RAPTOR hierarchical retrieval
RAPTOR_ENABLED = False  # Set to True to use RAPTOR instead of standard retrieval

# Tree building parameters
RAPTOR_LEAF_CHUNK_SIZE = 100  # Tokens per leaf chunk (RAPTOR paper default)
RAPTOR_MAX_TREE_DEPTH = 3  # Maximum summarization layers (3-5 recommended)
RAPTOR_UMAP_N_NEIGHBORS = [10, 25, 50]  # Multi-scale clustering (varies by level)
RAPTOR_GMM_MAX_CLUSTERS = 10  # Maximum clusters to try (BIC selects optimal)

# Summarization parameters
RAPTOR_SUMMARIZATION_MODEL = "gpt-4.1-mini"  # Fast, cost-effective model
RAPTOR_SUMMARIZATION_PROMPT = "prompts/raptor-summary-prompt.md"
RAPTOR_SUMMARY_MAX_TOKENS = 500  # Maximum summary length
RAPTOR_SUMMARY_TEMPERATURE = 0.0  # Deterministic summaries

# Retrieval mode
RAPTOR_RETRIEVAL_MODE = "collapsed"  # "collapsed" (query all levels) or "tree-traversal" (top-down)

# Note: Collapsed mode is recommended per RAPTOR paper (better performance)
```

**Update**: `src/services/rag/retriever.py`

```python
from src.lib.constants import RAPTOR_ENABLED

class RAGRetriever:
    def __init__(self, ..., use_raptor: bool = RAPTOR_ENABLED):
        # Existing initialization
        ...

        # Initialize RAPTOR retriever if enabled
        self.use_raptor = use_raptor
        self.raptor_retriever = None
        if use_raptor:
            from src.services.rag.raptor.tree_retriever import RAPTORRetriever
            self.raptor_retriever = RAPTORRetriever()
            logger.info("raptor_retriever_initialized", mode=RAPTOR_RETRIEVAL_MODE)

    def retrieve(self, request: RetrieveRequest, query_id: UUID) -> tuple[RAGContext, List[Any], Dict[UUID, int]]:
        # If RAPTOR enabled, use hierarchical retrieval
        if self.use_raptor and self.raptor_retriever:
            chunks, metadata = self.raptor_retriever.retrieve(
                query=request.query,
                max_chunks=request.max_chunks,
            )

            # Create RAGContext
            context = RAGContext.from_retrieval(
                query_id=query_id,
                chunks=chunks,
                min_relevance=request.min_relevance,
            )

            logger.info("raptor_retrieval_completed", **metadata)
            return context, [], {}

        # Otherwise, use standard hybrid retrieval
        # ... existing code ...
```

---

### Phase 7: CLI Integration (1 day)

**Update**: `src/cli/ingest.py`

```python
from src.lib.constants import RAPTOR_ENABLED

@click.command()
@click.argument("directory", type=click.Path(exists=True))
@click.option("--force", is_flag=True, help="Force re-ingestion")
@click.option("--rebuild-raptor-tree", is_flag=True, help="Rebuild RAPTOR tree structure")
def ingest(directory: str, force: bool, rebuild_raptor_tree: bool):
    """Ingest rule documents from DIRECTORY into RAG system."""

    # ... existing ingestion code ...

    # Build RAPTOR tree if enabled
    if RAPTOR_ENABLED or rebuild_raptor_tree:
        click.echo("\nBuilding RAPTOR tree structure...")

        from src.services.rag.raptor.tree_builder import RAPTORTreeBuilder
        from src.services.rag.raptor.summarizer import RAPTORSummarizer
        from src.services.rag.raptor.tree_store import RAPTORTreeStore
        from src.services.rag.embeddings import EmbeddingService

        # Get all chunks from vector DB
        vector_db = VectorDBService()
        all_results = vector_db.collection.get(include=["documents", "metadatas", "embeddings"])

        # Convert to DocumentChunk objects
        chunks = [...]  # Convert results to chunks

        # Build tree
        summarizer = RAPTORSummarizer()
        embedding_service = EmbeddingService()
        tree_builder = RAPTORTreeBuilder(summarizer, embedding_service)

        tree = tree_builder.build_tree(chunks)

        # Store tree
        tree_store = RAPTORTreeStore()
        tree_store.store_tree(tree)

        click.echo(f"RAPTOR tree built: {len(tree.levels)} levels, {tree.total_nodes()} total nodes")
```

**Update**: `src/cli/query.py` (for testing)

```python
# No need for --use-raptor flag
# Use RAPTOR_ENABLED constant instead
# Users can toggle in constants.py or via environment variable
```

---

### Phase 8: Testing (2-3 days)

**Unit tests**: `tests/unit/rag/raptor/test_tree_builder.py`

```python
"""Unit tests for RAPTOR tree builder."""

import pytest
from src.services.rag.raptor.tree_builder import RAPTORTreeBuilder
from src.models.rag_context import DocumentChunk


def test_tree_builder_creates_levels():
    """Test that tree builder creates multiple levels."""
    # Mock chunks, summarizer, embeddings
    # ...

    tree = tree_builder.build_tree(leaf_chunks)

    assert len(tree.levels) >= 2  # At least leaves + one summary level
    assert tree.levels[0][0].is_summary is False  # Leaves are not summaries
    assert tree.levels[1][0].is_summary is True  # Level 1 are summaries


def test_tree_builder_stops_at_convergence():
    """Test that tree building stops when clusters converge."""
    # Test with small dataset that converges quickly
    # ...

    tree = tree_builder.build_tree(small_chunks)

    assert len(tree.levels) < tree_builder.max_depth  # Stopped early


def test_clustering_assigns_all_nodes():
    """Test that clustering assigns all nodes to clusters."""
    # ...
```

**Quality tests**: `tests/quality/raptor_tests.yaml`

```yaml
# RAPTOR-specific quality tests for multi-section queries

- id: pathfinder-barricade-cover-raptor
  query: "How do Pathfinder operatives interact with light barricades for cover?"
  tags: [multi-section, raptor, team-rules]
  expected_behavior: |
    Should retrieve:
    1. Pathfinder faction rules (team-specific)
    2. Light barricade terrain rules
    3. Cover mechanics from core rules
    RAPTOR should provide both high-level summaries and specific details
  expected_sections:
    - "Pathfinder abilities"
    - "Terrain - Barricades"
    - "Cover rules"
  min_score: 0.8

- id: eliminator-concealed-counteract-raptor
  query: "Can a concealed Eliminator use counteract against an enemy in engage order?"
  tags: [multi-section, raptor, complex-interaction]
  expected_sections:
    - "Eliminator operative"
    - "Conceal order"
    - "Engage order"
    - "Counteract ability"
  min_score: 0.8
```

**Comparison test**: `tests/quality/test_raptor_comparison.py`

```python
"""Compare RAPTOR vs standard retrieval quality."""

import pytest
from src.services.rag.retriever import RAGRetriever


@pytest.mark.parametrize("use_raptor", [False, True])
def test_raptor_vs_standard_retrieval(use_raptor, quality_test_cases):
    """Compare retrieval quality with and without RAPTOR."""
    retriever = RAGRetriever(use_raptor=use_raptor)

    results = {}
    for test_case in quality_test_cases:
        context = retriever.retrieve(test_case.query)
        score = evaluate_retrieval_quality(context, test_case)
        results[test_case.id] = score

    # Log results for comparison
    avg_score = sum(results.values()) / len(results)
    print(f"{'RAPTOR' if use_raptor else 'Standard'} avg score: {avg_score}")
```

---

### Phase 9: Documentation (1 day)

**Create**: `src/services/rag/raptor/CLAUDE.md`

```markdown
# RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval

Hierarchical retrieval system for Kill Team rules using tree-structured summaries.

## Purpose

Enables multi-level retrieval combining high-level thematic summaries with granular details.

## Architecture

- **tree_builder.py**: UMAP + GMM clustering, recursive tree construction
- **summarizer.py**: LLM-based cluster summarization
- **tree_retriever.py**: Collapsed tree and tree-traversal retrieval
- **tree_store.py**: ChromaDB persistence

## Configuration

See `src/lib/constants.py` RAPTOR section.

## Usage

Toggle via `RAPTOR_ENABLED` constant. Tree is rebuilt during ingestion.

## Testing

```bash
# Unit tests
pytest tests/unit/rag/raptor/

# Quality comparison
python -m src.cli quality-test --compare-raptor
```
```

**Update**: `src/services/rag/CLAUDE.md`

Add RAPTOR section after Multi-Hop Retrieval.

**Update**: Root `CLAUDE.md`

Add RAPTOR to architecture overview.

---

## Estimated Effort and Costs

### Development Time

| Phase | Effort | Notes |
|-------|--------|-------|
| Dependencies & Structure | 1 day | Setup, module structure |
| Tree Building | 2-3 days | UMAP, GMM, clustering logic |
| Summarization | 1 day | LLM integration, prompts |
| Tree Storage | 1-2 days | ChromaDB persistence |
| Hierarchical Retrieval | 2 days | Collapsed + tree-traversal modes |
| Integration | 1-2 days | RAGRetriever, constants |
| CLI Integration | 1 day | Ingestion command updates |
| Testing | 2-3 days | Unit + quality tests |
| Documentation | 1 day | CLAUDE.md updates |
| **Total** | **12-17 days** | **~2-3 weeks** |

### Ingestion Costs (One-Time per Run)

Assuming ~1300 chunks → tree with 3-5 levels:

| Level | Chunks | Clusters | Summarization Cost (gpt-4.1-mini) |
|-------|--------|----------|-------------------------------------|
| 0 (leaves) | 1300 | - | $0 (original chunks) |
| 1 | - | ~130 | ~$0.10 (130 summaries) |
| 2 | - | ~13 | ~$0.01 (13 summaries) |
| 3 | - | ~2 | ~$0.001 (2 summaries) |
| **Total** | **1300** | **~145** | **~$0.11-0.15** |

**Note**: Costs vary by:
- Chunk count (more chunks = more summaries)
- Clustering density (affects cluster count)
- LLM model choice (gpt-4.1-mini is cheapest, claude-haiku alternative)

### Storage Overhead

- **Summaries**: ~30-40% of original chunk count (145 summaries for 1300 chunks)
- **Embeddings**: +30-40% vector DB size
- **Metadata**: Tree structure metadata (parent_ids, tree_level)
- **Total increase**: ~40-50% disk space

### Query Costs

- **No additional cost**: Retrieval uses embeddings only (no LLM calls)
- **Latency**: Similar to standard retrieval (~200-500ms)

---

## Alternative: Enhance Multi-Hop First

Before implementing RAPTOR, consider these simpler improvements:

### 1. Increase Multi-Hop Iterations

**Current**: `RAG_MAX_HOPS = 1` (initial + 1 additional retrieval)

**Proposed**: `RAG_MAX_HOPS = 3` (initial + up to 3 additional retrievals)

**Benefits**:
- Gathers more iterative context for complex queries
- Leverages existing infrastructure
- No ingestion changes
- Easy to tune and test

**Implementation**: Change constant, test quality improvement

---

### 2. Improve Hop Evaluation Prompts

**Current**: `prompts/hop-evaluation-prompt.md`

**Improvements**:
- More specific gap analysis questions
- Better reasoning guidance
- Explicit instruction to identify missing rule sections

**Example**:
```markdown
Analyze whether you can fully answer this question:
"{query}"

With these retrieved rules:
{chunks}

Specifically check:
1. Do you have all relevant faction/team rules?
2. Do you have all relevant core game mechanics?
3. Are there rule interactions or edge cases not covered?
4. Are there FAQs or errata that might apply?

If ANY gaps exist, identify the SPECIFIC missing information needed.
```

---

### 3. Enable Metadata Filtering

**Current**: Metadata exists but not used for filtering

**Proposed**: Filter by `doc_type` based on query analysis

**Example**:
```python
# If query mentions faction name, filter to team-rules
if "Pathfinder" in query:
    results = vector_db.query(
        query_embeddings=[embedding],
        where={"doc_type": "team-rules"}
    )
```

**Benefits**:
- Reduces noise from irrelevant document types
- Focuses retrieval on likely sources
- Simple to implement

---

### 4. Query Decomposition

**Concept**: Break complex questions into focused sub-queries

**Example**:
```
Original: "Can concealed Eliminator use counteract against engaged enemy?"

Decomposed:
1. "What is the Eliminator operative's counteract ability?"
2. "How does conceal order affect ability usage?"
3. "Can abilities target enemies in engage order?"
```

**Implementation**:
- Use LLM to decompose query
- Retrieve for each sub-query
- Merge results

**Benefits**:
- Better retrieval precision
- Easier to debug
- Leverages existing retrieval

---

### Comparison: Multi-Hop Enhancements vs RAPTOR

| Factor | Multi-Hop Enhancements | RAPTOR |
|--------|----------------------|--------|
| **Complexity** | Low (config changes + prompt tuning) | High (clustering, tree building) |
| **Implementation** | 2-5 days | 2-3 weeks |
| **Ingestion Cost** | $0 | ~$0.15 per run |
| **Ingestion Time** | No change (30s) | +2-5 minutes |
| **Storage** | No change | +40% |
| **Effectiveness** | Good for iterative context | Best for hierarchical themes |
| **Risk** | Very low | Medium (new dependencies, complexity) |
| **Reversibility** | Easy (change constant) | Harder (remove code, rebuild DB) |

---

### Recommended Approach

**Phase 1** (1 week): Try multi-hop enhancements
1. Increase `RAG_MAX_HOPS` to 2-3
2. Improve hop evaluation prompts
3. Run quality tests, measure improvement

**Evaluate**:
- If quality improves significantly → stick with multi-hop
- If still insufficient → proceed to Phase 2

**Phase 2** (2-3 weeks): Implement RAPTOR
- Full implementation as outlined above
- A/B test against enhanced multi-hop
- Measure cost/quality trade-off

**Outcome**:
- **Best case**: Multi-hop enhancements sufficient, save 2-3 weeks
- **Backup plan**: RAPTOR available if needed

---

## Decision Criteria

### Use RAPTOR If...

✅ **Analytics show**:
- >30% of queries require multiple rule sections
- Users frequently ask thematic/overview questions
- Current multi-hop (even at 3 hops) misses important context

✅ **Budget allows**:
- ~$0.15 per ingestion is acceptable
- +40% storage cost is acceptable

✅ **Team capacity**:
- 2-3 weeks of development time available
- Bandwidth for ongoing RAPTOR maintenance

✅ **Use case fits**:
- Long, hierarchical documents (✓ Kill Team rules are hierarchical)
- Complex multi-step reasoning (✓ rule interactions)
- Need for both summaries and details (✓ new players + veterans)

### Stick with Enhanced Multi-Hop If...

❌ **Current quality sufficient**:
- Multi-hop improvements (2-3 hops) handle most queries
- Users satisfied with answer completeness

❌ **Cost-sensitive**:
- Cannot justify $0.15/ingestion + storage overhead
- Prefer zero-cost improvements

❌ **Complexity-averse**:
- Team prefers simpler, maintainable solutions
- Risk of RAPTOR maintenance burden too high

❌ **Time-constrained**:
- Cannot allocate 2-3 weeks for implementation
- Other priorities more urgent

---

## References

### RAPTOR Paper

- **Title**: RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval
- **Authors**: Parth Sarthi, Salman Abdullah, Aditi Tuli, Shubh Khanna, Anna Goldie, Christopher D. Manning
- **Published**: ICLR 2024
- **arXiv**: https://arxiv.org/abs/2401.18059
- **Code**: https://github.com/parthsarthi03/raptor

### Key Findings

- 20% accuracy improvement on QuALITY benchmark (complex reasoning)
- Collapsed tree retrieval outperforms tree traversal
- Significant retrieval contribution from non-leaf (summary) layers
- Effective for long documents (10K+ tokens)

### Implementation Guides

- LlamaIndex RAPTOR: https://www.educative.io/blog/mastering-rag-with-raptor
- LangChain implementation: https://github.com/langchain-ai/langchain (raptor examples)
- RAGFlow integration: https://ragflow.io/docs/dev/enable_raptor

---

**Next Steps**:

1. **Decide**: RAPTOR now or multi-hop enhancements first?
2. **If multi-hop**: Implement Phase 1 (1 week), evaluate results
3. **If RAPTOR**: Begin Phase 1 of implementation plan above

**Questions to Answer**:

- Do we have analytics showing multi-section query frequency?
- What's the budget for ingestion costs?
- Is 2-3 weeks of dev time available?
- Should we A/B test RAPTOR vs enhanced multi-hop?
