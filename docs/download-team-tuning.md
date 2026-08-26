# download-team output tuning

Goal: `download-team` + `clean_rules.py` should reproduce a hand-curated team file with
zero manual editing.

## Verification loop

```bash
git -C extracted-rules checkout -- team/raveners.md
python -m src.cli download-team https://assets.warhammer-community.com/eng_raveners_online_rules-8vfeyxgbks-nf6lxfcbfw.pdf
python3 scripts/clean_rules.py extracted-rules/team/raveners.md
python3 scripts/paragraph_diff.py            # -v to see the differing paragraphs
```

Always pass the file to `clean_rules.py`. Without an argument it rewrites every rules
file, and the other teams have rules updates that have not been processed yet.

Two teams are used as references:

| team | PDF |
|---|---|
| `team/raveners.md` | `eng_raveners_online_rules-8vfeyxgbks-nf6lxfcbfw.pdf` |
| `team/angels_of_death.md` | `eng_26-08_killteam_angels_of_death_online_rules-1rwlnicmkz-qjtykwlybg.pdf` |

`scripts/paragraph_diff.py` counts paragraphs that differ between the committed and the
working copy of a rules file. Paragraphs are compared unordered - section order varies
between runs and carries no meaning - so only added, removed or reworded paragraphs count.

`extracted-rules` is a git submodule, so the reference version lives in that repo's HEAD.

## Changes made

**src/cli/download_team.py**
- `extract_team_name` strips a trailing `_kill_team`, so the file lands at `raveners.md`
  with `section: raveners` instead of `raveners_kill_team.md`

**prompts/team-extraction-prompt.md**
- Flavor text (rule 6): recognition test ("does the sentence carry a game instruction?")
  plus a before/after example. This was the single biggest source of manual cleanup
- Footnote-derived weapon rules (`Crush*`) become their own `###` section, placed before
  the operative's other abilities, with the leading `*` dropped
- Composition card: flat bullet list, never invent a lead-in sentence. The old example
  (`"consists of 6 operatives selected from the follows:"`) was itself being hallucinated
  into the output
- Verbatim: never add clarifying words, never invent list items
- Operative headers drop a trailing "KILL TEAM" from the team-name prefix
- Faction rules stay in printed order
- Bold tac op names, and named rules referenced in FAQ entries
- `**cover**` stays plain in the phrase "cover save"
- "activation" is bolded only in the pair `**activation**/**counteraction**`
- Designer's Notes are kept, as `> **Designer's Note:** ...` blockquotes
- Faction rules named after a keyword several teams share (`ASTARTES`) take the team name:
  `## ANGELS OF DEATH - ASTARTES - Faction Rule`. Names that merely contain it
  (`VETERAN ASTARTES`, `HUNTING ASTARTES`) do not
- Faction rule variants repeat the rule name (`### CHAPTER TACTICS - 1. AGGRESSIVE`)
- Fixed composition wording (`Your kill team consists of 1 **X** operative ...`), weapon
  options as indented sub-bullets, one archetype per bullet
- An action's restriction sentence becomes another bullet of the action's own list

**scripts/clean_rules.py** - new deterministic normalizers, so bolding no longer depends
on what the model felt like doing:
- `strip_stray_leading_asterisk` - leftover footnote marker on the first line of a `###`
  section (markers inside selection lists are left alone)
- `bold_distance_expressions` - also bolds bare "wholly within" and pulls a distance
  inside an existing bold (`**wholly within** 5"` -> `**wholly within 5"**`)
- `normalize_heading_case` - `RAVENERS KILL Team` -> `RAVENERS KILL TEAM`
- `bold_rule_text_keywords` - `counteract`/`counteracting`/`counteraction`,
  `incapacitated`, `shoot`/`fight` before "against", `Light`/`Heavy` before "terrain",
  and both halves of `activation/counteraction` (standalone "activation" is unbolded)
- `bold_ploy_references` - bolds a ploy name in rule text when this same file has a header
  for that ploy ("the **Combat Doctrine** strategy ploy"); designer notes are left alone
- `format_designer_notes` - `Designer's Note: ...` -> `> **Designer's Note:** ...`
- `prefix_shared_faction_rules` - adds the team name (taken from the `section` front
  matter field) to the faction rules listed in `SHARED_FACTION_RULES`

**Baseline**: `extracted-rules/team/raveners.md` and `team/angels_of_death.md` were
normalized in a series of submodule commits
(section frontmatter, footnote asterisk, `wholly within` bolding, FAQ rule/tac op names,
`Light` terrain, `shoot`/`fight`, `activation`/`counteraction` bolding, designer note
blockquote, action restrictions as bullets). No other team file was touched - other teams have
rules updates that have not been processed yet, so `clean_rules.py` was run per-file:
`python3 scripts/clean_rules.py extracted-rules/team/raveners.md`.

## Prompt iterations (gemini-2.5-pro)

| step | differing paragraphs |
|---|---|
| starting point | 11 |
| flavor text + footnote sections + asterisk cleaner | 5 |
| composition, verbatim, heading case cleaner | 0 (but 7-10 on repeat runs) |
| counteract / shoot / fight / Light terrain cleaners | 3 |
| FAQ rule-name bolding | 2 |
| incapacitated cleaner + operative header prefix | **0** (4 of 5 runs, worst case 3) |

Then, validated against `angels_of_death`:

| step | differing paragraphs |
|---|---|
| starting point | 24 |
| activation/counteraction pair + unbold standalone, `counteracting`, faction rule variant headers, option sub-bullets | 8 |
| fixed composition wording, one archetype per bullet, restriction bullets | 3 |
| `counteraction` cleaner + restriction-bullet example | 4 (ploy names lost their bold) |
| `bold_ploy_references` cleaner | **0** |

Reverted along the way: a prompt rule bolding lowercase `shoot`/`fight` - the model applied
it too widely. It is handled deterministically in `clean_rules.py` instead.

## Model comparison

Same prompt and cleaners, one run each, raveners PDF:

| model | differing paragraphs | time | cost |
|---|---|---|---|
| **gemini-2.5-pro** (default) | **0** (4/5 runs, worst 3) | ~60s | $0.043-0.049 |
| gemini-3.5-flash | 16 | 74s | $0.053 |
| gemini-3.1-pro-preview | 33 | 105s | $0.071 |
| gemini-2.5-flash | 38 | 40s | $0.012 |
| grok-4.3 | 43 | 27s | $0.023 |
| claude-4.5-sonnet | 89 | 234s | $0.126 |

`grok-4.3` is the fastest and second cheapest, but the Grok adapter extracts the PDF as
plain text instead of sending it as a document, so the card layout is lost. Nothing beat
`gemini-2.5-pro` on fidelity, so the default is unchanged.
