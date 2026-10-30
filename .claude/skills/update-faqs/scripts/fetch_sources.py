"""Find and download the FAQ source PDFs from the Warhammer Community downloads API.

Usage:
    python fetch_sources.py <out_dir> [--no-download]

Writes <out_dir>/sources.json: one record per configured source with title,
file name, URL, last_updated (ISO date), and local PDF path. Also lists other
Kill Team "Update Log" documents that are not configured, so they can be
checked for FAQs and reported.

Exit code 2 = the API call failed or returned no hits. Use the website
fallback in SKILL.md then.
"""

import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def main() -> int:
    out_dir = Path(sys.argv[1])
    download = "--no-download" not in sys.argv
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = json.loads((SKILL_DIR / "sources.json").read_text())

    req = urllib.request.Request(
        cfg["api"]["url"],
        data=json.dumps(cfg["api"]["payload"]).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            hits = json.load(resp).get("hits", [])
    except Exception as exc:  # noqa: BLE001
        print(f"API call failed: {exc}", file=sys.stderr)
        return 2
    if not hits:
        print("API returned no hits", file=sys.stderr)
        return 2

    by_title = {h["title"].strip(): h for h in hits}
    result = {"sources": [], "missing": [], "other_update_logs": []}
    for src in cfg["sources"]:
        hit = by_title.get(src["title"])
        if hit is None:
            result["missing"].append(src["title"])
            continue
        meta = hit["id"]
        updated = datetime.strptime(meta["last_updated"], "%d/%m/%Y").date().isoformat()
        url = cfg["api"]["asset_base"] + meta["file"]
        pdf = out_dir / f"{src['key']}.pdf"
        if download:
            urllib.request.urlretrieve(url, pdf)
        result["sources"].append(
            {**src, "file": meta["file"], "url": url, "last_updated": updated, "pdf": str(pdf)}
        )

    configured = {s["title"] for s in cfg["sources"]}
    for title, hit in sorted(by_title.items()):
        if "update log" in title.lower() and title not in configured:
            result["other_update_logs"].append(
                {"title": title, "url": cfg["api"]["asset_base"] + hit["id"]["file"],
                 "last_updated": hit["id"]["last_updated"]}
            )

    (out_dir / "sources.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 1 if result["missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
