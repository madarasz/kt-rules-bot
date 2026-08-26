#!/usr/bin/env python3
"""
Count paragraphs that differ between the committed and the working copy of a rules file.

Used to check that `download-team` + `clean_rules.py` reproduce a hand-curated file.
Paragraphs are compared as an unordered collection: extraction runs place sections in
different orders, which carries no meaning, so only added, removed or reworded
paragraphs are counted.

Usage:
    python3 scripts/paragraph_diff.py [team/raveners.md] [-v]
"""

import difflib
import subprocess
import sys


def paragraphs(text: str) -> list[str]:
    return sorted(p.strip() for p in text.split("\n\n") if p.strip())


def count_differences(old: str, new: str, verbose: bool = False) -> int:
    a, b = paragraphs(old), paragraphs(new)

    total = 0
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        total += max(i2 - i1, j2 - j1)
        if verbose:
            for p in a[i1:i2]:
                print("--- ", p[:400].replace("\n", "\\n"))
            for p in b[j1:j2]:
                print("+++ ", p[:400].replace("\n", "\\n"))
            print()
    return total


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "-v"]
    relative_path = args[0] if args else "team/raveners.md"
    verbose = "-v" in sys.argv

    old = subprocess.run(
        ["git", "-C", "extracted-rules", "show", f"HEAD:{relative_path}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    with open(f"extracted-rules/{relative_path}", encoding="utf-8") as f:
        new = f.read()

    count = count_differences(old, new, verbose)
    print(f"DIFFERING PARAGRAPHS: {count}")
    return 0 if count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
