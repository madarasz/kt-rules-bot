#!/usr/bin/env bash
#
# Ship the locally-ingested vector store to the deployed Debian bot, so the
# server never has to re-summarize or re-embed anything.
#
# What moves (explicit allowlist — NEVER `rsync data/`):
#   data/chroma_db/          the vector store, INCLUDING chunk summaries
#                            (they live in each chunk's Chroma metadata)
#   data/rag_keywords.json   query-normalization library, gitignored
#   data/ingestion_state.json  per-file hashes, so the server agrees with the store
#
# What must NOT move:
#   data/analytics.db        admin-dashboard stats. Dev and prod hold DIFFERENT
#                            data; copying it either way destroys real history.
#   data/rag_synonyms.json   git-tracked, arrives via `git pull`
#
# Usage:
#   scripts/sync_vector_db.sh --dry-run user@host
#   scripts/sync_vector_db.sh user@host [/path/to/remote/repo]
#
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
    shift
fi

REMOTE="${1:-}"
REMOTE_REPO="${2:-/home/killteambot/kill-team-rules-bot}"
EXPORT_DIR="data/chroma_db_export"
SERVICES="killteambot killteambot-admin"

if [[ -z "$REMOTE" ]]; then
    echo "Usage: $0 [--dry-run] user@host [remote-repo-path]" >&2
    exit 1
fi

cd "$(dirname "$0")/.."

# Use the repo venv explicitly. Bare `python3` is the system interpreter unless the
# venv happens to be activated, and there chromadb is not installed — which would
# make the version check below fail with ModuleNotFoundError instead of comparing.
PY="./venv/bin/python"
if [[ ! -x "$PY" ]]; then
    PY="python3"
    echo "⚠️  ./venv/bin/python not found — falling back to system python3"
fi

# --info=progress2 needs rsync >= 3.1. macOS ships openrsync (2.6.9-compatible),
# which aborts on it. Probe once and fall back to the universally-supported
# --progress so the upload works regardless of which rsync is in front of us.
if rsync --info=progress2 --version >/dev/null 2>&1; then
    PROGRESS_FLAG="--info=progress2"
else
    PROGRESS_FLAG="--progress"
fi

run() {
    if [[ $DRY_RUN -eq 1 ]]; then
        echo "  [dry-run] $*"
    else
        "$@"
    fi
}

echo "==> Target: $REMOTE:$REMOTE_REPO"
[[ $DRY_RUN -eq 1 ]] && echo "==> DRY RUN — no commands will be executed"

# 1. Compact: drops orphaned HNSW segments left by past resets (763MB -> ~21MB).
echo
echo "==> [1/5] Compacting vector store"
run "$PY" scripts/compact_vector_db.py --out "$EXPORT_DIR" --force

# 2. Chroma persists through a versioned sqlite schema. A server on a different
#    major version may fail to read the store we just built, so refuse to ship.
echo
echo "==> [2/5] Checking chromadb versions match"
LOCAL_VER=$("$PY" -c "import chromadb; print(chromadb.__version__)")
if [[ $DRY_RUN -eq 1 ]]; then
    echo "  [dry-run] ssh $REMOTE '<remote chromadb version check>'   (local: $LOCAL_VER)"
else
    REMOTE_VER=$(ssh "$REMOTE" "cd $REMOTE_REPO && venv/bin/python -c 'import chromadb; print(chromadb.__version__)'")
    echo "  local: $LOCAL_VER   remote: $REMOTE_VER"
    if [[ "$LOCAL_VER" != "$REMOTE_VER" ]]; then
        echo "❌ chromadb version mismatch — the server may not be able to read this store." >&2
        echo "   Align them first (requirements.txt pins the version), then re-run." >&2
        exit 1
    fi
fi

# 3. Stage next to the live data. Each source is listed individually, so --delete
#    only ever applies inside chroma_db.new/ and can never reach analytics.db.
echo
echo "==> [3/5] Uploading to staging paths"
run rsync -az --delete "$PROGRESS_FLAG" -e ssh \
    "$EXPORT_DIR/" "$REMOTE:$REMOTE_REPO/data/chroma_db.new/"
run rsync -az -e ssh \
    data/rag_keywords.json "$REMOTE:$REMOTE_REPO/data/rag_keywords.json.new"
if [[ -f data/ingestion_state.json ]]; then
    run rsync -az -e ssh \
        data/ingestion_state.json "$REMOTE:$REMOTE_REPO/data/ingestion_state.json.new"
fi

# 4. The swap stops the live bot: Chroma's sqlite + HNSW files are not consistent
#    if they are replaced under a running reader.
echo
echo "==> [4/5] Swap on the server (stops the bot briefly)"
echo "    This will: stop [$SERVICES], move the current store aside, activate the"
echo "    upload, and start the services again. analytics.db is not touched."
if [[ $DRY_RUN -eq 0 ]]; then
    read -r -p "    Proceed? [y/N] " reply
    if [[ ! "$reply" =~ ^[Yy]$ ]]; then
        echo "Aborted. Staged files remain on the server (*.new); nothing was swapped."
        exit 0
    fi
fi

# Note: the previous store is kept as chroma_db.old for rollback and is only
# removed by the NEXT sync, once this one has proven good.
#
# Every conditional below is a full if/fi, never `[ -x ] && cmd`: under `set -e` a
# false one-line test is a non-zero statement that aborts the script. Since these
# sit between `stop` and `start`, that would leave the bot DOWN — e.g. on the very
# first sync, where data/chroma_db does not exist yet.
#
# rsync ran as this ssh user (often root), so everything staged is owned by it.
# The bot runs as a different service user and Chroma opens sqlite read-WRITE even
# to read (WAL + schema migrations), so root-owned files give it 'attempt to write
# a readonly database'. Re-own the swapped-in files to whoever owns the repo (the
# service user's home), which is the account systemd runs the bot as.
run ssh "$REMOTE" "set -euo pipefail
    cd $REMOTE_REPO
    OWNER=\$(stat -c '%U:%G' .)
    sudo systemctl stop $SERVICES
    rm -rf data/chroma_db.old
    if [ -d data/chroma_db ]; then
        mv data/chroma_db data/chroma_db.old
    fi
    mv data/chroma_db.new data/chroma_db
    sudo chown -R \"\$OWNER\" data/chroma_db
    if [ -f data/rag_keywords.json.new ]; then
        mv data/rag_keywords.json.new data/rag_keywords.json
        sudo chown \"\$OWNER\" data/rag_keywords.json
    fi
    if [ -f data/ingestion_state.json.new ]; then
        mv data/ingestion_state.json.new data/ingestion_state.json
        sudo chown \"\$OWNER\" data/ingestion_state.json
    fi
    sudo systemctl start $SERVICES
    sleep 2
    systemctl is-active $SERVICES || true"

echo
echo "==> [5/5] Done"
echo "    Verify:  ssh $REMOTE 'journalctl -u killteambot -n 50 --no-pager'"
echo "    Rollback: ssh $REMOTE 'cd $REMOTE_REPO && sudo systemctl stop $SERVICES && \\"
echo "                rm -rf data/chroma_db && mv data/chroma_db.old data/chroma_db && \\"
echo "                sudo systemctl start $SERVICES'"
