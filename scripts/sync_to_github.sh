#!/bin/bash
# Newt — sync local changes to GitHub.
# Run anytime you've changed code in ~/Desktop/NewtApp or ~/newt.
#
#   bash ~/Desktop/NewtApp/sync_to_github.sh ["optional commit message"]
#
# What it does:
#   1. Pulls latest from GitHub (in case MacBook pushed something)
#   2. Mirrors ~/Desktop/NewtApp/ → ~/newt-repo/ios/
#   3. Mirrors ~/newt/        → ~/newt-repo/server/  (scrubbing secrets)
#   4. Refreshes requirements.txt from your current venv
#   5. Shows you what changed, asks to confirm
#   6. Commits + pushes

set -uo pipefail

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;36m'; N='\033[0m'

REPO="$HOME/newt-repo"
IOS_SRC="$HOME/Desktop/NewtApp"
SERVER_SRC="$HOME/newt"

echo ""
echo "=========================================="
echo "  Newt — sync to GitHub                   "
echo "=========================================="
echo ""

# ---- Sanity ----------------------------------------------------------------
if [ ! -d "$REPO/.git" ]; then
    echo -e "${R}✗ $REPO is not a git repo.${N}"
    echo "  Run upload_to_github.sh first to create it."
    exit 1
fi

# ---- 1. Pull ---------------------------------------------------------------
echo -e "${B}[1/5]${N} Pulling latest from GitHub…"
cd "$REPO"
if ! git pull --rebase --autostash 2>&1 | sed 's/^/  /'; then
    echo -e "${R}✗ Pull had conflicts.${N}"
    echo "  Open $REPO and resolve manually, then re-run."
    exit 1
fi

# ---- 2. Mirror iOS ---------------------------------------------------------
echo ""
echo -e "${B}[2/5]${N} Mirroring iOS app…"
rsync -a --delete "$IOS_SRC/" "$REPO/ios/" \
    --exclude='.DS_Store' \
    --exclude='build/' \
    --exclude='DerivedData/' \
    --exclude='xcuserdata/' \
    --exclude='*.xcuserstate' \
    --exclude='*.xcworkspace/xcuserdata/' \
    --exclude='AppIcon-1024.png' \
    --exclude='upload_to_github.sh' \
    --exclude='sync_to_github.sh' \
    --exclude='install_launcher.sh' \
    --exclude='grant_permissions.sh' \
    --exclude='fix_permissions.sh' \
    --exclude='migrate_to_homebrew_python.sh' \
    --exclude='recover_bridge.sh' \
    --exclude='keep_mac_awake.sh' \
    --exclude='app_launcher.py'
echo "  ✓"

# Refresh setup scripts in scripts/
mkdir -p "$REPO/scripts"
for s in install_launcher.sh grant_permissions.sh fix_permissions.sh \
         migrate_to_homebrew_python.sh recover_bridge.sh keep_mac_awake.sh \
         upload_to_github.sh sync_to_github.sh; do
    [ -f "$IOS_SRC/$s" ] && cp "$IOS_SRC/$s" "$REPO/scripts/"
done
[ -f "$IOS_SRC/app_launcher.py" ] && cp "$IOS_SRC/app_launcher.py" "$REPO/server/app_launcher.py"

# ---- 3. Mirror server ------------------------------------------------------
echo ""
echo -e "${B}[3/5]${N} Mirroring server (scrubbing secrets + huge files)…"
rsync -a --delete "$SERVER_SRC/" "$REPO/server/" \
    --exclude='venv' \
    --exclude='venv.*' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='.env' \
    --exclude='.env.local' \
    --exclude='persona.json' \
    --exclude='notes.md' \
    --exclude='screen.png' \
    --exclude='*.log' \
    --exclude='inbox/' \
    --exclude='chroma_db/' \
    --exclude='chroma/' \
    --exclude='.chromadb/' \
    --exclude='*.bak-*' \
    --exclude='*-snapshot.txt' \
    --exclude='requirements-snapshot.txt' \
    --exclude='voices/' \
    --exclude='*.onnx' \
    --exclude='*.pth' \
    --exclude='*.gguf' \
    --exclude='*.safetensors' \
    --exclude='*.bin' \
    --exclude='*.sqlite*' \
    --exclude='*.duckdb' \
    --exclude='*.parquet' \
    --exclude='.DS_Store'

# Make sure scripts/ in iOS folder doesn't double-up
echo "  ✓"

# ---- 4. Refresh requirements.txt ------------------------------------------
echo ""
echo -e "${B}[4/5]${N} Refreshing requirements.txt from current venv…"
if [ -x "$SERVER_SRC/venv/bin/pip" ]; then
    "$SERVER_SRC/venv/bin/pip" freeze 2>/dev/null \
        | grep -v '^-e\|@ file:' > "$REPO/server/requirements.txt"
    echo "  ✓ $(wc -l < "$REPO/server/requirements.txt" | tr -d ' ') packages"
else
    echo "  (skip — no venv)"
fi

# ---- 5. Diff, commit, push -------------------------------------------------
echo ""
echo -e "${B}[5/5]${N} Checking for changes…"
cd "$REPO"
git add -A

if git diff --cached --quiet; then
    echo -e "  ${G}Nothing changed.${N} You're already in sync with GitHub."
    exit 0
fi

# Show summary of what changed
echo ""
echo "Changes:"
git diff --cached --stat | sed 's/^/  /' | head -30
TOTAL_CHANGED=$(git diff --cached --name-only | wc -l | tr -d ' ')
echo ""
echo "  $TOTAL_CHANGED file(s) total"

# Commit message — from arg, or prompt
if [ "$#" -gt 0 ]; then
    MSG="$1"
else
    DEFAULT="Sync from iMac at $(date '+%Y-%m-%d %H:%M')"
    echo ""
    read -p "Commit message (Enter for default \"$DEFAULT\"): " MSG
    [ -z "$MSG" ] && MSG="$DEFAULT"
fi

git commit -q -m "$MSG"
echo ""
echo "Pushing to GitHub…"
if git push 2>&1 | sed 's/^/  /'; then
    echo ""
    echo -e "${G}✓ Synced.${N} Latest commit:"
    git log -1 --oneline | sed 's/^/  /'
else
    echo ""
    echo -e "${R}✗ Push failed.${N}"
    echo "  Most common cause: GitHub auth. Use a personal access token as your"
    echo "  password, or set up SSH:"
    echo "    git remote set-url origin git@github.com:wolfashy/newt.git"
fi
