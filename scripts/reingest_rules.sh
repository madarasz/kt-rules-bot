#!/bin/bash
#
# FULL rebuild of the vector database from scratch.
#
# For everyday updates you do NOT need this: `python3 -m src.cli ingest extracted-rules/`
# is incremental and only re-summarizes and re-embeds files whose content changed.
# Use this script when you want to start clean anyway (e.g. after editing the cleaning
# rules below, which rewrites every markdown file).

# Clean rules
python3 scripts/clean_rules.py
# Revert formatting-only changes of re-extracted team rules to the committed text
# (compares with git HEAD of extracted-rules; does nothing on a clean tree)
python3 scripts/stabilize_rules.py extracted-rules/team
# Re-ingest rules — --force resets the collection and rebuilds the keyword library
python3 -m src.cli ingest extracted-rules/ --force
# Generate rule structure
python3 scripts/generate_rules_structure.py --summary
# Analyse chunks
python3 scripts/analyze_chunk_stats.py
