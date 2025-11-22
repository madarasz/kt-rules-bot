#!/bin/bash

# Clean rules
python3 scripts/clean_rules.py
# Reset DB
python3 scripts/reset_rag_db.py --confirm
# Re-ingest rules
python3 -m src.cli ingest extracted-rules/
# Generate rule structure
python3 scripts/generate_rules_structure.py
# Analyse chunks
python3 scripts/analyze_chunk_stats.py 