#!/bin/bash
# Newt — migrate the bridge venv to Homebrew Python.
# The Apple-shipped CommandLineTools Python is signed but not hardened,
# so macOS TCC silently denies Screen Recording / Full Disk Access even
# when you toggle them on. Homebrew Python is properly hardened-runtime
# signed and is the standard fix.
#
# Usage:  bash ~/Desktop/NewtApp/migrate_to_homebrew_python.sh

set -uo pipefail

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;36m'; N='\033[0m'

echo ""
echo "=========================================="
echo "  Newt — Python migration to Homebrew     "
echo "=========================================="
echo ""

# ----------------------------------------------------------------------------
# 1. Homebrew check
# ----------------------------------------------------------------------------
echo "[1/6] Checking Homebrew…"

BREW=""
if command -v brew &>/dev/null; then
    BREW=$(command -v brew)
fi
# Common paths even if not in PATH
for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -z "$BREW" ] && [ -x "$p" ]; then
        BREW="$p"
    fi
done

if [ -z "$BREW" ]; then
    echo -e "  ${Y}Homebrew not installed.${N}"
    echo ""
    echo "  Install it first by running this command in Terminal:"
    echo ""
    echo "    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo ""
    echo "  It'll ask for your Mac password. Once done, run THIS script again."
    exit 1
fi
echo -e "  ${G}✓${N} Homebrew at $BREW"
echo ""

# ----------------------------------------------------------------------------
# 2. Install / verify Python
# ----------------------------------------------------------------------------
echo "[2/6] Installing Python via Homebrew (skips if already installed)…"
"$BREW" install python@3.13 2>&1 | tail -3 || true

# Find the freshly-installed python
NEW_PY=""
for p in /opt/homebrew/bin/python3.13 /usr/local/bin/python3.13 \
         /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [ -x "$p" ]; then
        NEW_PY="$p"
        break
    fi
done
if [ -z "$NEW_PY" ]; then
    echo -e "  ${R}✗ Couldn't find Homebrew Python after install.${N}"
    exit 1
fi
echo -e "  ${G}✓${N} New Python: $NEW_PY"
echo "    Code signature check…"
codesign -dv "$NEW_PY" 2>&1 | grep -E 'flags|Signature' | sed 's/^/      /'
echo ""

# ----------------------------------------------------------------------------
# 3. Save old venv's package list
# ----------------------------------------------------------------------------
OLD_VENV="$HOME/newt/venv"
REQ_FILE="$HOME/newt/requirements-snapshot.txt"

echo "[3/6] Snapshotting current bridge packages…"
if [ -d "$OLD_VENV" ] && [ -x "$OLD_VENV/bin/pip" ]; then
    "$OLD_VENV/bin/pip" freeze > "$REQ_FILE" 2>/dev/null || true
    PKG_COUNT=$(wc -l < "$REQ_FILE" | tr -d ' ')
    echo -e "  ${G}✓${N} $PKG_COUNT packages saved to $REQ_FILE"
else
    echo -e "  ${Y}!${N} No existing venv at $OLD_VENV — will install minimal deps."
    echo "flask" > "$REQ_FILE"
    echo "openai" >> "$REQ_FILE"
fi
echo ""

# ----------------------------------------------------------------------------
# 4. Stop the bridge & back up old venv
# ----------------------------------------------------------------------------
echo "[4/6] Stopping bridge & backing up old venv…"
launchctl bootout "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.ethanash.newt-bridge.plist" 2>/dev/null || true

if [ -d "$OLD_VENV" ]; then
    BACKUP="$OLD_VENV.clt-bak-$(date +%Y%m%d-%H%M%S)"
    mv "$OLD_VENV" "$BACKUP"
    echo -e "  ${G}✓${N} Backed up old venv → $BACKUP"
fi
echo ""

# ----------------------------------------------------------------------------
# 5. Create new venv & install packages
# ----------------------------------------------------------------------------
echo "[5/6] Creating new venv with Homebrew Python…"
"$NEW_PY" -m venv "$OLD_VENV"
"$OLD_VENV/bin/pip" install --upgrade pip --quiet
echo -e "  ${G}✓${N} New venv created"

echo "  Installing packages from snapshot (this can take 1-2 minutes)…"
"$OLD_VENV/bin/pip" install --quiet -r "$REQ_FILE" 2>&1 | tail -5 || {
    echo -e "  ${Y}!${N} Some packages failed; trying core deps only…"
    "$OLD_VENV/bin/pip" install --quiet flask openai distro piper-tts || true
}
echo -e "  ${G}✓${N} Packages installed"
echo ""

# ----------------------------------------------------------------------------
# 6. Restart bridge
# ----------------------------------------------------------------------------
echo "[6/6] Restarting bridge…"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.ethanash.newt-bridge.plist"
sleep 4

NEW_PROCESS=$(ps -axo command= | grep -E 'newt_bridge\.py' | grep -v grep | head -1 | awk '{print $1}')
if [ -n "$NEW_PROCESS" ]; then
    echo -e "  ${G}✓${N} Bridge running:"
    echo "      $NEW_PROCESS"
else
    echo -e "  ${R}✗ Bridge didn't start. Check ~/newt/newt-bridge.err.log${N}"
fi
echo ""

# ----------------------------------------------------------------------------
# Wrap up
# ----------------------------------------------------------------------------
echo "=========================================="
echo -e "  ${G}Migration done.${N}"
echo "=========================================="
echo ""
echo "Now you need to add the NEW Python to Screen Recording + FDA."
echo "The new path is on your clipboard:"
echo ""
echo -n "$NEW_PY" | pbcopy
echo "    $NEW_PY"
echo ""
echo "Run the fix wizard next:"
echo ""
echo "    bash ~/Desktop/NewtApp/fix_permissions.sh"
echo ""
echo "It'll auto-detect this new Python and walk you through adding it."
