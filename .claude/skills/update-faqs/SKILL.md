---
name: update-faqs
description: Sync the official Kill Team FAQ entries (the "Q:/A:" rules commentary in the Warhammer Community update-log PDFs) into the extracted-rules/faq-*.md files of this repo. Gets the latest PDFs from the Warhammer Community downloads API, extracts the FAQs, rebuilds faq-core-rules.md, faq-approved-ops.md, faq-universal-equipment.md and faq-tomb-world.md, removes FAQ copies from other rule docs, checks for duplicates, and reports. Use this skill whenever the user asks to update, refresh, sync, reorganize or check the FAQs, rules commentaries or update logs, says a new Core Rules / Approved Ops / Universal Equipment / Tomb World update log is out, or asks whether the FAQ markdown matches the official PDFs — even if they do not say "skill" or name the files.
---

# Update FAQs

Keep the FAQ markdown in `extracted-rules/` equal to the official Kill Team
update-log PDFs. Each target file holds exactly the FAQs of one PDF, in PDF
order. FAQ entries in team files stay where they are.

| PDF title (downloads API) | Target file |
|---|---|
| Core Rules: Update Log | `extracted-rules/faq-core-rules.md` |
| Approved Ops: Update Log (not the "APPROVED OPS CARD PACK 2024" section) | `extracted-rules/faq-approved-ops.md` |
| Universal Equipment | `extracted-rules/faq-universal-equipment.md` |
| Killzone: Tomb World Update Log | `extracted-rules/faq-tomb-world.md` |

The mapping lives in `sources.json` next to this file. To add a new source
(for example a new killzone update log), add an entry there.

## Things to know before you start

- `extracted-rules/` is a **git submodule**. In the parent repo, `git status`
  shows only ` m extracted-rules`, and `git checkout <file>` from the parent
  fails. Use `git -C extracted-rules ...` to see diffs or restore files.
- Never overwrite a target file before its entries are read correctly. Run
  `sync_faqs.py` without `--write` first and read the summary. With
  `--write` it backs up each changed file to `<run_dir>/backup/` first.
- FAQ headers have two forms. Non-team docs use
  `## [FAQ] *Question*: ...` + `*Answer*: ...`. Team docs often use
  `## [FAQ] *Question:* ...` + `*Answer:* ...`. The scripts read both. New
  entries use the first form.
- The PDFs have two columns. Plain `pdftotext` mixes the columns, and a
  column crop picks up parts of full-width title lines (for example
  "No. EQUIPMENT: G and interact more smoothly..."). `extract_faqs.py`
  handles this. Do not extract FAQs by hand from `pdftotext` output.
- A PDF has a "RULES COMMENTARY" section (newest) and a "PREVIOUS RULES
  COMMENTARIES" section. Both are FAQs. Include both.
- Use the project venv (`source venv/bin/activate`); it has `pdfplumber`.
  Run all scripts from the repo root. Put downloads in the session
  scratchpad, not in the repo.

## Workflow

Set `SKILL=.claude/skills/update-faqs` and `RUN=<scratchpad>/faq-run`.

### 1. Get the latest PDFs

```bash
python -I $SKILL/scripts/fetch_sources.py $RUN
```

This POSTs to `https://www.warhammer-community.com/api/search/downloads/`
with `{"index": "downloads_v2", "searchTerm": "", "gameSystem": "kill-team",
"language": "english"}`, finds each configured title, downloads the PDF from
`https://assets.warhammer-community.com/<file>`, and writes
`$RUN/sources.json`. `last_updated` (from the API, `DD/MM/YYYY`) becomes the
`last_update_date` in the target file front matter.

- Exit code 1: a configured title is missing from the API result. Look at
  the titles in the API result for a renamed document, then fix
  `sources.json` or ask the user.
- Exit code 2: the API failed. Use the **website fallback** below.
- `other_update_logs` lists Kill Team update logs that are not configured
  (for example "Mission Packs Update Log"). Check each one for `Q:` entries
  (`pdftotext <pdf> - | grep -c 'Q:'`) and tell the user. Do not add them
  to the repo unless the user asks.

**Website fallback.** Open
`https://www.warhammer-community.com/en-gb/downloads/kill-team/` in the
built-in browser. Read the page text and find the download links to
`assets.warhammer-community.com` for the four titles and their update
dates. Download each PDF to `$RUN/<key>.pdf` (keys are in `sources.json`)
and write `$RUN/sources.json` by hand in the same shape that
`fetch_sources.py` writes (`sources` list: the config entry plus `url`,
`last_updated` as `YYYY-MM-DD`, `pdf`).

### 2. Dry run

```bash
python -I $SKILL/scripts/sync_faqs.py $RUN
```

Sanity check the counts: for each PDF, `pdftotext <pdf> - | grep -o 'Q:' | wc -l`
must equal the FAQ count of its target. The exception is Approved Ops,
where the raw count also includes the 2024 card pack FAQs that are left out.
If a count is wrong, look at `$RUN/<key>.json` before you continue.

Read `$RUN/report.json`:

- `kept`: entry text equals the PDF. The existing markdown is kept as it
  is, so its bold formatting stays.
- `new`: in the PDF, not in the repo.
- `changed`: a similar entry exists, but the text is different. The PDF text
  is used. `old_q`/`old_a` show the earlier text. This fixes extraction
  errors (for example, merged team names) and takes in official rewording.
- `dropped_not_in_pdf`: an entry in a target file that no PDF has. It is
  removed. Look at each one: it can be an older wording of a current FAQ
  (`similarity` 0.6–0.9), or errata text that was wrongly made into a FAQ.
  Report each one with its reason. Do not add it back.
- `removed_elsewhere`: FAQ entries in non-FAQ, non-team docs (for example
  `killzone/*.md`) that a PDF has. They are removed from those docs.
- `unmatched_elsewhere`: FAQ entries in non-team docs that no PDF has. They
  stay. Report them to the user, because the user wants to know about FAQs
  that are not in one of the target files.

### 3. Write

```bash
python -I $SKILL/scripts/sync_faqs.py $RUN --write
```

### 4. Restore formatting on `new` and `changed` entries

The PDF text has no markdown. Make these entries look like the kept
entries around them. Bold:
- faction and operative keywords (the ALL CAPS names, for example
  `**PLAGUE MARINES**`, `**HERNKYN YAEGIR**`),
- named team rules after a keyword (`**Lumbering Death**`),
- core game terms that other entries also bold (`**Guard**`, `**Shoot**`,
  `**counteract**`, `**incapacitated**`, `**Vantage**`, `**Accessible**`,
  `**Blast**`, tac op names such as `**Dominate**`).

Change only the formatting. Keep every word as the PDF has it. When a
`changed` entry had bold text before, copy that bolding (`old_q`/`old_a`).

### 5. Leave generated files alone

`extracted-rules/rules-structure.yml` and `teams-structure.yml` can still
list `'[FAQ] Question: ...'` headers of removed entries. Do not edit them
and do not run `scripts/generate_rules_structure.py`. The user re-ingests
the rules and regenerates these files. Tell the user in the report which
removed entries the YAML still lists.

### 6. Duplicate check

```bash
python -I $SKILL/scripts/audit_faqs.py
```

- Similarity 1.00 in one file: a real duplicate. Delete the later copy,
  also in team files (this keeps the team FAQs in their file). Report it.
- Pairs in two different team files: usually separate rulings for each
  team with similar wording. Read both. Report only real duplicates.
- Pairs that differ in one key word (for example "activated" and
  "incapacitated") are not duplicates.

Run the dry run again at the end. Expect `new 0 | changed 0`, all entries
`kept`, and an empty "files to change" list. The comparison ignores bold,
so the edits from step 4 do not show as changes.

### 7. Report

Do not commit unless the user asks. Give the user:

1. A table of each target file: FAQ count before and after, date, kept /
   new / changed.
2. Entries moved between files (from which file, to which file).
3. Entries removed and not in any PDF, each with its reason.
4. Text changes taken from the PDF (short before and after).
5. FAQs in non-team docs that are not in a target file (`unmatched_elsewhere`).
6. Duplicates removed, and near-duplicates left in place.
7. Unconfigured update logs that have FAQs.
8. Next step for the user: re-ingest and regenerate the structure YAML
   files. Do not run these yourself.
