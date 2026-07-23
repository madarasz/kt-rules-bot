#!/usr/bin/env python3
"""Copy the live Chroma collection into a fresh, minimal directory.

Why this exists: `VectorDBService.reset()` drops and recreates the collection,
but the old HNSW segment directories stay on disk. After a few rebuilds the
store is mostly orphans — measured 763 MB on disk for ~63 MB of live data (113
segment directories, 2 of them referenced by the sqlite `segments` table).

Copying record-by-record into a new PersistentClient writes only what is
reachable, which is what makes the store small enough to ship to the server.

Usage:
    python3 scripts/compact_vector_db.py
    python3 scripts/compact_vector_db.py --out data/chroma_db_export --force
"""

import argparse
import shutil
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.lib.config import get_config  # noqa: E402
from src.lib.logging import get_logger  # noqa: E402
from src.services.rag.vector_db import VectorDBService  # noqa: E402

logger = get_logger(__name__)

# Chroma rejects oversized batches; well under any provider limit and plenty fast
# for the ~1.5k chunks this collection holds.
COPY_BATCH_SIZE = 500


def dir_size_mb(path: Path) -> float:
    """Total size of a directory tree, in MB."""
    if not path.exists():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / (1024 * 1024)


def compact(source_path: str, out_path: Path, collection_name: str, force: bool) -> int:
    """Copy every record from the live collection into a fresh store at out_path.

    Returns the number of records copied.
    """
    if out_path.exists():
        if not force:
            print(f"❌ {out_path} already exists (use --force to replace it)")
            sys.exit(1)
        shutil.rmtree(out_path)

    source = VectorDBService(collection_name=collection_name, db_path=source_path)
    total = source.get_count()
    if total == 0:
        print(f"❌ Source collection '{collection_name}' is empty — nothing to compact")
        sys.exit(1)

    print(f"📦 Compacting '{collection_name}': {total} records")
    print(f"   from {source_path} ({dir_size_mb(Path(source_path)):.1f} MB)")

    records = source.collection.get(include=["embeddings", "documents", "metadatas"])
    target = VectorDBService(collection_name=collection_name, db_path=str(out_path))

    ids = records["ids"]
    for start in range(0, len(ids), COPY_BATCH_SIZE):
        end = start + COPY_BATCH_SIZE
        target.add_embeddings(
            ids=ids[start:end],
            embeddings=[list(e) for e in records["embeddings"][start:end]],
            documents=records["documents"][start:end],
            metadatas=records["metadatas"][start:end],
        )
        print(f"   copied {min(end, len(ids))}/{len(ids)}", end="\r")

    copied = target.get_count()
    if copied != total:
        print(f"\n❌ Verification failed: copied {copied} of {total} records")
        sys.exit(1)

    before_mb = dir_size_mb(Path(source_path))
    after_mb = dir_size_mb(out_path)
    saved = (1 - after_mb / before_mb) * 100 if before_mb else 0.0
    print(f"\n✅ {copied} records verified")
    print(f"   {before_mb:.1f} MB → {after_mb:.1f} MB ({saved:.0f}% smaller)")
    print(f"   Output: {out_path}")
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="Compact the Chroma vector database")
    parser.add_argument(
        "--out",
        default="data/chroma_db_export",
        help="Output directory (default: data/chroma_db_export)",
    )
    parser.add_argument(
        "--collection", default="kill_team_rules", help="Collection name to copy"
    )
    parser.add_argument(
        "--force", action="store_true", help="Replace the output directory if it exists"
    )
    args = parser.parse_args()

    config = get_config()
    compact(
        source_path=config.vector_db_path,
        out_path=Path(args.out),
        collection_name=args.collection,
        force=args.force,
    )


if __name__ == "__main__":
    main()
