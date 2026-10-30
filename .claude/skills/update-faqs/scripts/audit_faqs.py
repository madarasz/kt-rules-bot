"""Find duplicate FAQ entries across all of extracted-rules/ (team files included).

Usage (run from the repo root):
    python audit_faqs.py [--threshold 0.8]

Prints pairs of FAQ questions whose normalized text similarity is at or
above the threshold. 1.00 within one file is a definite duplicate. Pairs in
two different team files are often separate, team-specific rulings with
similar wording: read both before you call them duplicates.
"""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_faqs import RULES, read_blocks, sim  # noqa: E402


def main() -> int:
    threshold = float(sys.argv[sys.argv.index("--threshold") + 1]) if "--threshold" in sys.argv else 0.8
    entries = []
    for p in sorted(RULES.rglob("*.md")):
        lines, blocks = read_blocks(p)
        entries += [(str(p), b["start"] + 1, b["q"]) for b in blocks]
    print(f"{len(entries)} FAQ entries scanned")
    for (f1, l1, q1), (f2, l2, q2) in itertools.combinations(entries, 2):
        r = sim(q1, q2)
        if r >= threshold:
            print(f"{r:.2f}  {f1}:{l1}  <->  {f2}:{l2}\n      {q1[:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
