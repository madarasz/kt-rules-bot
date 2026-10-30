"""Extract Q:/A: rules commentary entries from a two-column Kill Team PDF.

Usage:
    python extract_faqs.py <pdf> [--stop-at "HEADER TEXT"] > out.json

Output: JSON list of {"q": ..., "a": ..., "page": n}, in reading order
(page by page, left column then right column). Bullet lines in answers are
kept as "\n• ..." so the build step can turn them into markdown list items.

Why words instead of plain text extraction: the PDFs use two columns, and
pdftotext interleaves them. Full-width lines (page title, intro paragraph)
would leak into a column crop, so lines that span the centre gutter are
dropped before the columns are split.
"""

import json
import re
import sys

import pdfplumber

GUTTER_GAP = 12  # pt; a gap smaller than this across the centre = full-width line
LINE_TOL = 3  # pt; words with "top" closer than this are on one line
STOP_LINE = re.compile(
    r"^(JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\b"
    r"|^(PREVIOUS|RULES COMMENTAR|ERRATA|This section|rules interactions|In example|EXAMPLE|NOTES)"
)


def group_lines(words):
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1]["top"] - w["top"]) <= LINE_TOL:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "bottom": w["bottom"], "words": [w]})
    for ln in lines:
        ln["words"].sort(key=lambda w: w["x0"])
        ln["bottom"] = max(w["bottom"] for w in ln["words"])
    return lines


def is_full_width(line, mid):
    ws = line["words"]
    if any(w["x0"] < mid < w["x1"] for w in ws):
        return True
    left = [w for w in ws if w["x1"] <= mid]
    right = [w for w in ws if w["x0"] >= mid]
    return bool(left and right) and right[0]["x0"] - left[-1]["x1"] < GUTTER_GAP


def column_lines(page, stop_y=None):
    mid = page.width / 2
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    if stop_y is not None:
        words = [w for w in words if w["top"] < stop_y]
    lines = [ln for ln in group_lines(words) if not is_full_width(ln, mid)]
    cols = []
    for side in ("left", "right"):
        col = []
        for ln in lines:
            ws = [w for w in ln["words"] if (w["x1"] <= mid) == (side == "left")]
            if ws:
                col.append({"top": ln["top"], "bottom": ln["bottom"],
                            "text": " ".join(w["text"] for w in ws)})
        cols.append(col)
    return cols


def find_stop(page, stop_at):
    """Return the y position of the stop header on this page, or None."""
    needle = " ".join(stop_at.upper().split())
    text = " ".join((page.extract_text() or "").upper().split())
    if needle not in text:
        return None
    for ln in group_lines(page.extract_words()):
        if needle in " ".join(w["text"] for w in ln["words"]).upper():
            return ln["top"]
    return 0  # header found but split over lines: drop the whole page


def parse(pdf_path, stop_at=None):
    items, cur, mode = [], None, None
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            stop_y = find_stop(page, stop_at) if stop_at else None
            for col in column_lines(page, stop_y):
                prev_bottom = None
                for ln in col:
                    s = ln["text"].strip()
                    gap = ln["top"] - prev_bottom if prev_bottom is not None else 0
                    prev_bottom = ln["bottom"]
                    if s.startswith("Q:"):
                        cur = {"q": s[2:].strip(), "a": "", "page": pno}
                        items.append(cur)
                        mode = "q"
                    elif s.startswith("A:") and cur is not None and not cur["a"]:
                        cur["a"] = s[2:].strip()
                        mode = "a"
                    elif mode and STOP_LINE.match(s):
                        mode = None
                    elif mode == "a" and gap > 8 and not s.startswith("•"):
                        mode = None  # paragraph break ends the answer
                    elif mode and cur is not None:
                        cur[mode] += ("\n" if s.startswith("•") else " ") + s
                mode = None if mode == "a" else mode
            if stop_y is not None:
                break
    for i in items:
        i["q"] = re.sub(r" +", " ", i["q"]).strip()
        i["a"] = re.sub(r" +", " ", i["a"]).strip()
    return items


if __name__ == "__main__":
    args = sys.argv[1:]
    stop = None
    if "--stop-at" in args:
        k = args.index("--stop-at")
        stop = args[k + 1]
        del args[k : k + 2]
    print(json.dumps(parse(args[0], stop), ensure_ascii=False, indent=1))
