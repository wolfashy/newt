#!/bin/bash
# Newt — bridge recovery after a broken venv migration.
# Diagnoses what the bridge needs, installs it, restarts.

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;36m'; N='\033[0m'

echo ""
echo "=========================================="
echo "  Newt — bridge recovery                  "
echo "=========================================="
echo ""

PIP="$HOME/newt/venv/bin/pip"

if [ ! -x "$PIP" ]; then
    echo -e "${R}✗ No venv at ~/newt/venv. Re-run migrate_to_homebrew_python.sh first.${N}"
    exit 1
fi

# ----------------------------------------------------------------------------
# 1. Look at the error log to see what's failing
# ----------------------------------------------------------------------------
echo -e "${B}[1/4] What's the bridge complaining about?${N}"
ERR_LOG="$HOME/newt/newt-bridge.err.log"
if [ -f "$ERR_LOG" ]; then
    tail -15 "$ERR_LOG" | sed 's/^/    /'
else
    echo "    (no err log yet)"
fi
echo ""

# ----------------------------------------------------------------------------
# 2. Discover what newt_bridge.py imports
# ----------------------------------------------------------------------------
echo -e "${B}[2/4] What does the bridge import?${N}"
BRIDGE="$HOME/newt/newt_bridge.py"
if [ -f "$BRIDGE" ]; then
    IMPORTS=$(grep -E '^[[:space:]]*(import|from)[[:space:]]+' "$BRIDGE" | head -30)
    echo "$IMPORTS" | sed 's/^/    /'
else
    echo "    (newt_bridge.py not found — that's a bigger problem)"
fi
echo ""

# ----------------------------------------------------------------------------
# 3. Install the standard Newt dependency set, plus anything we can pull
#    from any backup venv that still has packages
# ----------------------------------------------------------------------------
echo -e "${B}[3/4] Installing dependencies…${N}"
"$PIP" install --quiet --upgrade pip

# Core deps that nearly every Newt build needs
CORE_DEPS=(
    flask
    openai
    anthropic
    requests
    distro
    python-dotenv
    piper-tts
    openai-whisper
    pydub
)

echo "  Core packages:"
for pkg in "${CORE_DEPS[@]}"; do
    "$PIP" install --quiet "$pkg" 2>&1 | tail -1 | sed "s/^/    $pkg: /" || \
        echo "    $pkg: install failed (might need manual attention)"
done
echo ""

# Try to recover any extra packages from a backup
BACKUP=$(ls -dt "$HOME"/newt/venv*bak* 2>/dev/null | head -1)
if [ -n "$BACKUP" ] && [ -x "$BACKUP/bin/pip" ]; then
    echo "  Looking for extras in $BACKUP…"
    BACKUP_PKGS=$("$BACKUP/bin/pip" freeze 2>/dev/null | grep -v '^-e\|@ file:' | head -50)
    if [ -n "$BACKUP_PKGS" ]; then
        echo "$BACKUP_PKGS" > /tmp/newt-req-extras.txt
        EXTRA_COUNT=$(wc -l < /tmp/newt-req-extras.txt | tr -d ' ')
        echo "    Found $EXTRA_COUNT in backup — installing…"
        "$PIP" install --quiet -r /tmp/newt-req-extras.txt 2>&1 | tail -3 | sed 's/^/      /'
    else
        echo "    (backup venv was empty too)"
    fi
fi
echo ""

# ----------------------------------------------------------------------------
# 4. Restart the bridge & verify
# ----------------------------------------------------------------------------
echo -e "${B}[4/4] Restarting bridge…${N}"
: > "$ERR_LOG" 2>/dev/null  # clear stale errors
launchctl bootout "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.ethanash.newt-bridge.plist" 2>/dev/null
sleep 2
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.ethanash.newt-bridge.plist"
sleep 5

PROC=$(ps -axo command= | grep -E 'newt_bridge\.py' | grep -v grep | head -1)
if [ -n "$PROC" ]; then
    echo -e "  ${G}✓${N} Bridge process running:"
    echo "    $PROC"
else
    echo -e "  ${R}✗${N} Bridge didn't start. Latest err:"
    tail -10 "$ERR_LOG" 2>/dev/null | sed 's/^/    /'
    echo ""
    echo "  If you see ModuleNotFoundError, paste the missing module name back"
    echo "  and we'll install it specifically."
    exit 1
fi

echo ""
echo "  Health check…"
HEALTH=$(curl -s --max-time 5 http://newt:8001/health)
if [ -n "$HEALTH" ]; then
    echo -e "  ${G}✓${N} $HEALTH"
else
    echo -e "  ${Y}!${N} No health response yet — give it 10 more seconds and try:"
    echo "    curl -s http://newt:8001/health"
fi

echo ""
echo "=========================================="
echo -e "  ${G}Done.${N} Next: bash ~/Desktop/NewtApp/fix_permissions.sh"
echo "=========================================="
