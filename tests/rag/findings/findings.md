# Experiment - 2025.10.17
### Original rules, chunk level=2, BM25_K1 = 1.6, BM25_B = 0.8, normalization = true, extension = true
- Total Tests: 21
- Mean MAP: 0.757
- Recall@5: 0.825 (82.5%)
- Recall@All** 0.905 (90.5%)
- Precision@3** 0.429 (42.9%)
### more-granularity rules, chunk level=2, BM25_K1 = 1.6, BM25_B = 0.8, normalization = true, extension = true
- Total Tests: 21
- Mean MAP: 0.733
- Recall@5: 0.778 (77.8%)
- Recall@All: 0.905 (90.5%)
- Precision@3: 0.397 (39.7%)
- missing chunks = 4 
### more-granularity rules, chunk level=4, BM25_K1 = 1.6, BM25_B = 0.8, normalization = true, extension = true
#### EMBEDDING_MODEL=text-embedding-3-small
- Total Tests: 21
- Mean MAP: 0.774
- Recall@5: 0.849 (84.9%)
- Recall@All: 0.905 (90.5%)
- Precision@3: 0.429 (42.9%)
- missing chunks = 4 
### granularity-v2, chunk level=4, BM25_K1 = 1.6, BM25_B = 0.8, normalization = true, extension = true
- 1282 chunks
#### EMBEDDING_MODEL=text-embedding-3-small
- Total Tests: 21
- Mean MAP: 0.7757
- Recall@5: 0.802 (80.2%)
- Recall@All: 0.881 (88.1%)
- Precision@3: 0.413 (41.3%)
- missing chunks = 5 (extra: return-to-darkness-teleport: TELEPORT PAD) 
- quality tests, gtp-4o: 53.5%
#### EMBEDDING_MODEL=text-embedding-3-large
- Total Tests: 21
- Mean MAP: 0.739
- Recall@5: 0.754 (75.4%)
- Recall@All: 0.841 (84.1%)
- Precision@3: 0.397 (39.7%)
- missing chunks = 6
- quality tests, gtp-4o: 59.7%; 69.2%; 67.3%
#### EMBEDDING_MODEL=text-embedding-ada-002
- Total Tests: 21
- Mean MAP: 0.774
- Recall@5: 0.873 (87.3%)
- Recall@All: 0.952 (95.2%)
- Precision@3: 0.460 (46%)
- missing chunks = 2
- quality tests, gtp-4o: 54.5%
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