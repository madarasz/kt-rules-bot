#!/usr/bin/env python3
"""
Undo formatting-only changes in re-extracted rules files.

Team rules are extracted from PDFs by an LLM, so each re-extraction changes the
formatting (bold, bullets, section order) even where the rule text did not change.
This script compares each file with its committed version (git HEAD) and keeps the
committed text wherever the two differ only in formatting, so the diff shows only
real rule changes.

For each file:
- Both versions are cleaned with `clean_rules.clean_content` first.
- The files are split into sections at `##`/`###` headers, and the sections are
  matched by their canonical header.
- A matched section whose canonical text is equal keeps the committed text. Otherwise
  each line whose canonical text is equal keeps the committed line.
- Matched sections keep the committed order; new sections follow the section they
  follow in the new file. Front matter comes from the new file.

Canonical text ignores bold/italic markers, bullet markers, indentation, letter case,
"&" vs "and", quote styles and whitespace.

Usage:
    python3 scripts/stabilize_rules.py extracted-rules/team
    python3 scripts/stabilize_rules.py extracted-rules/team/blooded.md --dry-run
"""

import argparse
import difflib
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from clean_rules import clean_content  # noqa: E402

HEADER_PATTERN = re.compile(r"^#{2,3} ")

# Minimum similarity of canonical bodies to pair sections whose headers do not match
SIMILAR_BODY_RATIO = 0.8


@dataclass
class Section:
    """One `##`/`###` section: the header line and its body lines."""
    header: str
    body: list[str]

    def text(self) -> str:
        lines = [self.header, *self.body] if self.header else self.body
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        return "\n".join(lines)

    def body_text(self) -> str:
        return "\n".join(self.body)


@dataclass
class StabilizeReport:
    """Section counts for one file."""
    unchanged: int = 0
    changed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def canonical(text: str) -> str:
    """Return the text with all formatting differences removed."""
    text = re.sub(r"^\s*(?:[-*•]\s+|#+\s+)", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("*", "").replace("`", "")
    text = text.replace("&", "and")
    text = re.sub(r"[″“”]", '"', text).replace("’", "'")
    return re.sub(r"\s+", " ", text).strip().casefold()


def header_suffix(header: str) -> str:
    """Return the canonical header without its first " - " part (if it has more than one)."""
    parts = canonical(header).split(" - ", 1)
    return parts[-1]


def split_sections(content: str) -> tuple[str, list[Section]]:
    """Split content into the preamble (front matter) and its sections."""
    preamble: list[str] = []
    sections: list[Section] = []
    for line in content.split("\n"):
        if HEADER_PATTERN.match(line):
            sections.append(Section(line, []))
        elif sections:
            sections[-1].body.append(line)
        else:
            preamble.append(line)
    return "\n".join(preamble).rstrip("\n"), sections


def stabilize_lines(old: list[str], new: list[str]) -> list[str]:
    """Return the new lines, using the old line wherever the canonical lines match."""
    matcher = difflib.SequenceMatcher(
        a=[canonical(line) for line in old], b=[canonical(line) for line in new], autojunk=False
    )
    result: list[str] = []
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        result.extend(old[old_start:old_end] if tag == "equal" else new[new_start:new_end])
    return result


def stabilize_content(old_content: str, new_content: str) -> tuple[str, StabilizeReport]:
    """Return the new content with formatting-only changes reverted to the old content."""
    report = StabilizeReport()
    _, old_sections = split_sections(clean_content(old_content)[0])
    new_preamble, new_sections = split_sections(clean_content(new_content)[0])

    # Old sections by canonical header; duplicate headers are matched in order
    old_by_header: dict[str, list[int]] = {}
    for index, section in enumerate(old_sections):
        old_by_header.setdefault(canonical(section.header), []).append(index)

    # Index of the matched old section for each new section (or None)
    old_indexes: list[int | None] = []
    for section in new_sections:
        candidates = old_by_header.get(canonical(section.header))
        old_indexes.append(candidates.pop(0) if candidates else None)

    # Second pass for renamed prefixes ("RATLING - X" -> "RATLINGS - X",
    # "1. Fleet" -> "ACCURSED GIFTS - 1. Fleet"): match the remaining sections on the
    # header without its first part, where that is unique on both sides
    unmatched_old = sorted(index for indexes in old_by_header.values() for index in indexes)
    old_by_suffix: dict[str, list[int]] = {}
    for index in unmatched_old:
        old_by_suffix.setdefault(header_suffix(old_sections[index].header), []).append(index)
    new_by_suffix: dict[str, list[int]] = {}
    for position, section in enumerate(new_sections):
        if old_indexes[position] is None:
            new_by_suffix.setdefault(header_suffix(section.header), []).append(position)
    for suffix, positions in new_by_suffix.items():
        if len(positions) == 1 and len(old_by_suffix.get(suffix, [])) == 1:
            old_indexes[positions[0]] = old_by_suffix[suffix][0]
            unmatched_old.remove(old_by_suffix[suffix][0])

    # Third pass for renamed sections ("KABALITE ARCHSYBARITE" -> "ARCHSYBARITE"):
    # pair the remaining sections whose canonical bodies are most similar
    pairs = []
    for position, section in enumerate(new_sections):
        if old_indexes[position] is not None:
            continue
        for index in unmatched_old:
            ratio = difflib.SequenceMatcher(
                a=canonical(old_sections[index].body_text()), b=canonical(section.body_text()), autojunk=False
            ).ratio()
            if ratio >= SIMILAR_BODY_RATIO:
                pairs.append((ratio, position, index))
    for _, position, index in sorted(pairs, reverse=True):
        if old_indexes[position] is None and index in unmatched_old:
            old_indexes[position] = index
            unmatched_old.remove(index)
    report.removed = [old_sections[index].header for index in unmatched_old]

    # Each new section with its matched old section index (or None)
    matched: list[tuple[Section, int | None]] = []
    for section, old_index in zip(new_sections, old_indexes, strict=True):
        if old_index is None:
            matched.append((section, None))
            report.added.append(section.header)
            continue

        # The header is kept from the new file, so a renamed prefix shows in the diff
        old = old_sections[old_index]
        if canonical(old.text()) == canonical(section.text()):
            matched.append((old, old_index))
            report.unchanged += 1
        elif canonical(old.body_text()) == canonical(section.body_text()):
            matched.append((Section(section.header, old.body), old_index))
            report.changed.append(section.header)
        else:
            body = stabilize_lines(old.body, section.body)
            matched.append((Section(section.header, body), old_index))
            report.changed.append(section.header)

    # Matched sections in old order; each added section stays after the section it
    # follows in the new file
    groups: list[tuple[float, list[Section]]] = []
    for section, old_index in matched:
        if old_index is None and groups:
            groups[-1][1].append(section)
        else:
            groups.append((-1 if old_index is None else old_index, [section]))
    groups.sort(key=lambda group: group[0])

    parts = [new_preamble] + [section.text() for _, group in groups for section in group]
    ending = "\n" if new_content.endswith("\n") else ""
    # Clean again: a kept old body can sit under a new header that changes its format
    # (e.g. "SPOT 1AP" -> "SPOT [1AP]" makes it an action, whose body is bulleted)
    return clean_content("\n\n".join(part for part in parts if part) + ending)[0], report


def read_committed(file_path: Path) -> str | None:
    """Return the file content at git HEAD, or None if the file is not committed."""
    repo_root = subprocess.run(
        ["git", "-C", str(file_path.parent), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    if not repo_root:
        return None
    relative = file_path.resolve().relative_to(Path(repo_root).resolve())
    result = subprocess.run(
        ["git", "-C", repo_root, "show", f"HEAD:{relative.as_posix()}"],
        capture_output=True, text=True, check=False,
    )
    return result.stdout if result.returncode == 0 else None


def stabilize_file(file_path: Path, dry_run: bool) -> StabilizeReport | None:
    """Stabilize one file in place. Return None if it has no committed version."""
    old_content = read_committed(file_path)
    if old_content is None:
        return None
    new_content = file_path.read_text(encoding="utf-8")
    if new_content == old_content:
        return StabilizeReport()
    stabilized, report = stabilize_content(old_content, new_content)
    if not dry_run and stabilized != new_content:
        file_path.write_text(stabilized, encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Undo formatting-only changes in re-extracted rules files.")
    parser.add_argument("paths", nargs="+", type=Path, help="Markdown files or directories")
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not write files")
    parser.add_argument("--verbose", "-v", action="store_true", help="List the changed, added and removed headers")
    args = parser.parse_args()

    files = sorted(
        file for path in args.paths for file in (path.rglob("*.md") if path.is_dir() else [path])
    )
    for file_path in files:
        report = stabilize_file(file_path, args.dry_run)
        if report is None:
            print(f"{file_path}: not committed, skipped")
            continue
        if not (report.changed or report.added or report.removed):
            continue
        print(
            f"{file_path}: {report.unchanged} unchanged, {len(report.changed)} changed, "
            f"{len(report.added)} added, {len(report.removed)} removed"
        )
        if args.verbose:
            for label, headers in (("~", report.changed), ("+", report.added), ("-", report.removed)):
                for header in headers:
                    print(f"    {label} {header}")


if __name__ == "__main__":
    main()
