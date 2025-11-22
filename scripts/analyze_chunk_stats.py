#!/usr/bin/env python3
"""Analyze ChromaDB chunk statistics."""

import argparse
import sys
from pathlib import Path
from statistics import mean, median, stdev

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.rag.vector_db import VectorDBService
from src.lib.tokens import count_tokens


def analyze_chunks(verbose: bool = False):
    """Analyze all chunks in ChromaDB and display statistics.

    Args:
        verbose: If True, display additional details including smallest chunks.
    """
    # Initialize vector DB
    vector_db = VectorDBService()

    # Get all chunks with documents and metadata
    all_results = vector_db.collection.get(
        include=["documents", "metadatas"]
    )

    if not all_results["ids"]:
        print("No chunks found in database")
        return

    # Collect chunk data
    chunks = []
    for i, chunk_id in enumerate(all_results["ids"]):
        text = all_results["documents"][i]
        metadata = all_results["metadatas"][i]

        # Count tokens and characters
        token_count = count_tokens(text, model="gpt-3.5-turbo")
        char_count = len(text)

        chunks.append({
            "id": chunk_id,
            "text": text,
            "header": metadata.get("header", "(no header)"),
            "source": metadata.get("source", "unknown"),
            "tokens": token_count,
            "chars": char_count,
        })

    # Calculate statistics
    total_chunks = len(chunks)
    token_counts = [c["tokens"] for c in chunks]
    char_counts = [c["chars"] for c in chunks]

    # Basic stats
    mean_tokens = mean(token_counts)
    mean_chars = mean(char_counts)
    median_tokens = median(token_counts)
    median_chars = median(char_counts)
    min_tokens = min(token_counts)
    min_chars = min(char_counts)
    max_tokens = max(token_counts)
    max_chars = max(char_counts)

    # Standard deviation (only if we have more than 1 chunk)
    if total_chunks > 1:
        stdev_tokens = stdev(token_counts)
        stdev_chars = stdev(char_counts)
    else:
        stdev_tokens = 0
        stdev_chars = 0

    # Percentiles
    sorted_tokens = sorted(token_counts)
    sorted_chars = sorted(char_counts)

    def percentile(data, p):
        """Calculate percentile."""
        n = len(data)
        k = (n - 1) * p / 100
        f = int(k)
        c = k - f
        if f + 1 < n:
            return data[f] + c * (data[f + 1] - data[f])
        else:
            return data[f]

    p25_tokens = percentile(sorted_tokens, 25)
    p50_tokens = percentile(sorted_tokens, 50)
    p75_tokens = percentile(sorted_tokens, 75)
    p95_tokens = percentile(sorted_tokens, 95)

    p25_chars = percentile(sorted_chars, 25)
    p50_chars = percentile(sorted_chars, 50)
    p75_chars = percentile(sorted_chars, 75)
    p95_chars = percentile(sorted_chars, 95)

    # Sort chunks by size
    chunks_by_tokens = sorted(chunks, key=lambda c: c["tokens"], reverse=True)
    chunks_by_tokens_asc = sorted(chunks, key=lambda c: c["tokens"])

    # Print results
    print("=" * 80)
    print("CHROMADB CHUNK STATISTICS")
    print("=" * 80)
    print()

    print(f"Total chunks: {total_chunks}")
    print()

    print("-" * 80)
    print("SIZE STATISTICS")
    print("-" * 80)
    print()
    print(f"{'Metric':<20} {'Tokens':>15} {'Characters':>15}")
    print(f"{'-' * 20} {'-' * 15} {'-' * 15}")
    print(f"{'Mean':<20} {mean_tokens:>15.1f} {mean_chars:>15.1f}")
    print(f"{'Median':<20} {median_tokens:>15.1f} {median_chars:>15.1f}")
    print(f"{'Min':<20} {min_tokens:>15} {min_chars:>15}")
    print(f"{'Max':<20} {max_tokens:>15} {max_chars:>15}")
    print(f"{'Std Dev':<20} {stdev_tokens:>15.1f} {stdev_chars:>15.1f}")
    print()

    print("-" * 80)
    print("PERCENTILES")
    print("-" * 80)
    print()
    print(f"{'Percentile':<20} {'Tokens':>15} {'Characters':>15}")
    print(f"{'-' * 20} {'-' * 15} {'-' * 15}")
    print(f"{'25th':<20} {p25_tokens:>15.1f} {p25_chars:>15.1f}")
    print(f"{'50th (Median)':<20} {p50_tokens:>15.1f} {p50_chars:>15.1f}")
    print(f"{'75th':<20} {p75_tokens:>15.1f} {p75_chars:>15.1f}")
    print(f"{'95th':<20} {p95_tokens:>15.1f} {p95_chars:>15.1f}")
    print()

    print("-" * 80)
    print("TOP 10 LARGEST CHUNKS")
    print("-" * 80)
    print()
    for i, chunk in enumerate(chunks_by_tokens[:10], 1):
        print(f"{i}. {chunk['header']}")
        print(f"   Tokens: {chunk['tokens']:,} | Characters: {chunk['chars']:,}")
        print(f"   Source: {chunk['source']}")
        print()

    if verbose:
        print("-" * 80)
        print("TOP 10 SMALLEST CHUNKS")
        print("-" * 80)
        print()
        for i, chunk in enumerate(chunks_by_tokens_asc[:10], 1):
            print(f"{i}. {chunk['header']}")
            print(f"   Tokens: {chunk['tokens']:,} | Characters: {chunk['chars']:,}")
            print(f"   Source: {chunk['source']}")
            print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze ChromaDB chunk statistics")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show additional details including smallest chunks"
    )
    args = parser.parse_args()

    analyze_chunks(verbose=args.verbose)
