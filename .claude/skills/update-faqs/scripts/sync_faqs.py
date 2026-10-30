"""Rebuild the FAQ markdown files from extracted PDF entries and clean other docs.

Usage (run from the repo root):
    python sync_faqs.py <run_dir>            # dry run: report only
    python sync_faqs.py <run_dir> --write    # back up, then write changes

<run_dir> must hold sources.json (from fetch_sources.py). Each source PDF is
extracted again on every run; the result is saved to <run_dir>/<key>.json
for inspection only.

What it does:
1. Each target file is rebuilt to hold exactly the FAQs of its PDF, in PDF
   order. An existing entry whose question AND answer match the PDF
   (ignoring bold, quotes, punctuation) is kept verbatim, so its markdown
   formatting survives. Other entries use the PDF text.
2. FAQ entries in other extracted-rules docs (team/ excluded) that match a
   PDF question are deleted from those docs.
3. Writes <run_dir>/report.json and prints a summary.

Before any write, every file that will change is copied to
<run_dir>/backup/<relative path>. extracted-rules/ is a git submodule, but
do not rely on that: the backup is the safety net.
"""

import difflib
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_faqs import parse  # noqa: E402

RULES = Path("extracted-rules")
HEADER = re.compile(r"^## \[FAQ\] \*Question(?:\*:|:\*) ?(.*)$")
MATCH = 0.9  # question similarity that counts as "the same FAQ"


def norm(s: str) -> str:
    s = s.replace("**", "").replace("*", "").replace("®", "")
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"')):
        s = s.replace(a, b)
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s.lower()).split())


def sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def read_blocks(path: Path):
    """Split a markdown file into FAQ blocks with line spans.

    A block is the header line plus following lines up to the next blank line
    or next '## ' header.
    """
    lines = path.read_text().split("\n")
    blocks, i = [], 0
    while i < len(lines):
        m = HEADER.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and lines[j].strip() and not lines[j].startswith("## "):
            j += 1
        body = "\n".join(lines[i + 1 : j])
        answer = re.sub(r"^\*Answer(?:\*:|:\*) ?", "", body)
        blocks.append({"q": m.group(1), "a": answer, "raw": "\n".join(lines[i:j]),
                       "start": i, "end": j})
        i = j
    return lines, blocks


def md_answer(a: str) -> str:
    return a.replace("\n• ", "\n- ")


def main() -> int:
    run = Path(sys.argv[1])
    write = "--write" in sys.argv
    cfg = json.loads((run / "sources.json").read_text())
    targets = {Path(s["target"]) for s in cfg["sources"]}

    # Existing FAQ blocks from every non-team doc (targets included).
    docs = [p for p in sorted(RULES.rglob("*.md")) if "team" not in p.relative_to(RULES).parts[:1]]
    existing = []
    for p in docs:
        for b in read_blocks(p)[1]:
            existing.append({**b, "file": str(p)})

    report = {"targets": {}, "removed_elsewhere": [], "dropped_not_in_pdf": [], "backups": []}
    pdf_qs = []
    new_content = {}
    for src in cfg["sources"]:
        items = parse(src["pdf"], src.get("stop_at"))
        (run / f"{src['key']}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1))
        target = Path(src["target"])
        rep = {"kept": [], "new": [], "changed": []}
        out = []
        for it in items:
            q, a = it["q"], md_answer(it["a"])
            pdf_qs.append((src["key"], q))
            exact = [b for b in existing if norm(b["q"]) == norm(q) and norm(b["a"]) == norm(a)]
            if exact:
                out.append(exact[0]["raw"])
                rep["kept"].append({"q": q, "from": exact[0]["file"]})
                continue
            out.append(f"## [FAQ] *Question*: {q}\n*Answer*: {a}")
            near = max(existing, key=lambda b: sim(b["q"], q), default=None)
            if near and sim(near["q"], q) >= 0.75:
                rep["changed"].append({"q": q, "a": a, "old_q": near["q"], "old_a": near["a"],
                                       "from": near["file"]})
            else:
                rep["new"].append({"q": q, "a": a})
        front = (f'---\nsource: "{src["source_label"]}"\nlast_update_date: {src["last_updated"]}\n'
                 f"document_type: faq\nsection: faq\n---\n\n")
        new_content[target] = front + "\n\n".join(out) + "\n"
        report["targets"][str(target)] = {**rep, "count": len(items)}

    # Existing entries in target files that no PDF FAQ matches.
    for b in existing:
        if Path(b["file"]) in targets and not any(sim(b["q"], q) >= MATCH for _, q in pdf_qs):
            best = max(pdf_qs, key=lambda x: sim(b["q"], x[1]))
            report["dropped_not_in_pdf"].append(
                {"file": b["file"], "q": b["q"], "a": b["a"],
                 "closest_pdf_q": best[1], "closest_source": best[0],
                 "similarity": round(sim(b["q"], best[1]), 2)})

    # Remove matched FAQ blocks from non-target docs.
    edits = {}
    for p in docs:
        if p in targets:
            continue
        lines, blocks = read_blocks(p)
        drop = []
        for b in blocks:
            hit = max(pdf_qs, key=lambda x: sim(b["q"], x[1]))
            if sim(b["q"], hit[1]) >= MATCH:
                drop.append(b)
                report["removed_elsewhere"].append({"file": str(p), "q": b["q"], "now_in": hit[0]})
            else:
                report.setdefault("unmatched_elsewhere", []).append({"file": str(p), "q": b["q"]})
        if drop:
            keep = lines[:]
            for b in sorted(drop, key=lambda b: -b["start"]):
                end = b["end"]
                # also drop one blank line so no double blank remains
                if end < len(keep) and not keep[end].strip():
                    end += 1
                elif b["start"] > 0 and not keep[b["start"] - 1].strip():
                    b = {**b, "start": b["start"] - 1}
                del keep[b["start"] : end]
            edits[p] = "\n".join(keep).rstrip("\n") + "\n"

    changes = {p: c for p, c in {**new_content, **edits}.items()
               if not p.exists() or p.read_text() != c}
    report["files_to_change"] = sorted(str(p) for p in changes)
    if write:
        for p, c in changes.items():
            if p.exists():
                dst = run / "backup" / p
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst)
                report["backups"].append(str(dst))
            p.write_text(c)
    (run / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))

    print("WRITTEN" if write else "DRY RUN (use --write to apply)")
    for t, r in report["targets"].items():
        print(f"{t}: {r['count']} FAQs | kept {len(r['kept'])} | new {len(r['new'])} | changed {len(r['changed'])}")
    print(f"removed from other docs: {len(report['removed_elsewhere'])}")
    print(f"dropped from targets (not in any PDF): {len(report['dropped_not_in_pdf'])}")
    print(f"unmatched FAQs in other non-team docs: {len(report.get('unmatched_elsewhere', []))}")
    print("files to change:", *report["files_to_change"], sep="\n  ")
    print(f"full report: {run / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
