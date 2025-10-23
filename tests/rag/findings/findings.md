# Added multi-hop 2025.10.22
Initial hopping decision is flawed, always hopping, but adding some missing context.
| Metric | Value | Description |
|--------|-------|-------------|
| **Avg Hops Used** | 1.00 | Average number of hops performed per test |
| **Avg Ground Truth Found in Hops** | 0.37 | Average number of ground truth chunks found via hops |

# Experiment - 2025.10.20
`Granuality-v2` dataset with `text-embedding-ada-002` + chunking at header level 2 seems to be the best

![context precision](ragas_context_precision_heatmap_embedding.png)
![context recall](ragas_context_recall_heatmap_embedding.png)

---

- Adjusted `BM25_B` to 0.55, because RAG sweep tests showed better `MAP` and `Recall@5` values

| bm25_b | MAP | Recall@5 | Precision@3 | MRR | Avg Time (s) | Total Cost ($) |
|------------|-------|-----------|--------------|-------|--------------|----------------|
| 0.45 | 0.767 | 0.833 | 0.444 | 0.917 | 0.317 | $0.000003 |
| 0.5 | 0.773 | 0.833 | 0.500 | 0.917 | 0.280 | $0.000003 |
| 0.55 | 0.773 | 0.833 | 0.500 | 0.917 | 0.308 | $0.000003 |
| 0.6 | 0.773 | 0.833 | 0.500 | 0.917 | 0.428 | $0.000003 |
| 0.65 | 0.766 | 0.778 | 0.500 | 0.917 | 0.309 | $0.000003 |
| 0.7 | 0.683 | 0.778 | 0.500 | 0.833 | 0.293 | $0.000003 |

- Reduced `max chunks` to 8
- Changing `BM25_K1`, `rrf_k` does not seem to affect anything
- `text-embedding-3-small` performs better than `text-embedding-3-large`