#!/bin/bash
# Newt — macOS permission wizard.
# Walks you through Screen Recording + Full Disk Access for the bridge,
# then restarts and tests.
#
# Run from anywhere:  bash ~/Desktop/NewtApp/grant_permissions.sh

# Auto-detect the python that newt's venv actually links to. macOS TCC
# checks the resolved binary path, not the symlink, so we need the real one.
detect_python() {
    for cand in \
        "$HOME/newt/venv/bin/python3" \
        "$HOME/newt/venv/bin/python" \
        "$HOME/newt/venv/bin/python3.13" \
        "$HOME/newt/venv/bin/python3.12" \
        "$HOME/newt/venv/bin/python3.11" \
        "$HOME/newt/venv/bin/python3.10" \
        "$HOME/newt/venv/bin/python3.9"
    do
        if [ -e "$cand" ]; then
            real=$(readlink -f "$cand" 2>/dev/null || python3 -c "import os; print(os.path.realpath('$cand'))" 2>/dev/null)
            if [ -n "$real" ] && [ -f "$real" ]; then
                echo "$real"
                return
            fi
        fi
    done
    # Common fallbacks
    for fallback in \
        "/Library/Developer/CommandLineTools/usr/bin/python3" \
        "/usr/bin/python3" \
        "/opt/homebrew/bin/python3" \
        "/usr/local/bin/python3"
    do
        if [ -f "$fallback" ]; then
            echo "$fallback"
            return
        fi
    done
}
PYTHON_PATH=$(detect_python)
if [ -z "$PYTHON_PATH" ]; then
    echo "Could not find a python binary for the bridge. Bail."
    exit 1
fi
echo "Detected the bridge Python at:"
echo "    $PYTHON_PATH"
echo ""

# Pretty colors
G='\033[0;32m'  # green
Y='\033[1;33m'  # yellow
R='\033[0;31m'  # red
B='\033[0;36m'  # blue
N='\033[0m'     # reset

echo ""
echo "=========================================="
echo "  Newt — macOS permission wizard         "
echo "=========================================="
echo ""
echo "Newt needs two macOS permissions:"
echo "  • Screen Recording  — so it can capture your screen"
echo "  • Full Disk Access  — so it can read Downloads/Desktop/Documents"
echo ""
echo "I can't toggle them for you (Apple won't allow it), BUT I'll"
echo "open the right page and put the right path on your clipboard."
echo "You just click + and paste. That's it."
echo ""
echo -e "Press ${B}Enter${N} when you're ready."
read -r

# ============================================================================
# Step 1 — Screen Recording
# ============================================================================
echo ""
echo "=========================================="
echo -e "  ${Y}Step 1 of 2: Screen Recording${N}    "
echo "=========================================="
echo ""

echo -n "$PYTHON_PATH" | pbcopy
echo -e "${G}✓${N} Path copied to your clipboard:"
echo "    $PYTHON_PATH"
echo ""
echo "Opening the Screen Recording settings pane now..."
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
sleep 1

echo ""
echo "In the window that just opened:"
echo ""
echo -e "  ${B}1.${N} Click the ${G}+${N} button at the bottom of the list"
echo -e "  ${B}2.${N} Press ${G}⇧⌘G${N} (Shift+Cmd+G)"
echo -e "  ${B}3.${N} Press ${G}⌘V${N} (Cmd+V) to paste the path"
echo -e "  ${B}4.${N} Press ${G}Enter${N}, then click ${G}Open${N}"
echo -e "  ${B}5.${N} Toggle the new ${G}python3${N} entry ${G}ON${N}"
echo ""
echo -e "${Y}When you're done, come back here and press Enter.${N}"
read -r

# ============================================================================
# Step 2 — Full Disk Access
# ============================================================================
echo ""
echo "=========================================="
echo -e "  ${Y}Step 2 of 2: Full Disk Access${N}     "
echo "=========================================="
echo ""

echo -n "$PYTHON_PATH" | pbcopy
echo -e "${G}✓${N} Path is back on your clipboard."
echo ""
echo "Opening the Full Disk Access pane..."
open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
sleep 1

echo ""
echo "Same exact procedure as before:"
echo ""
echo -e "  ${B}1.${N} Click ${G}+${N}"
echo -e "  ${B}2.${N} ${G}⇧⌘G${N}"
echo -e "  ${B}3.${N} ${G}⌘V${N} to paste"
echo -e "  ${B}4.${N} Enter, then ${G}Open${N}"
echo -e "  ${B}5.${N} Toggle the new entry ${G}ON${N}"
echo ""
echo -e "${Y}When done, press Enter.${N}"
read -r

# ============================================================================
# Restart the bridge
# ============================================================================
echo ""
echo "=========================================="
echo "  Restarting the bridge…                  "
echo "=========================================="
launchctl kickstart -k "gui/$(id -u)/com.ethanash.newt-bridge"
sleep 3

# ============================================================================
# Smoke tests
# ============================================================================
echo ""
echo "Testing screenshot…"
HTTP_CODE=$(curl -s -o /tmp/newt-test.png -w "%{http_code}" http://newt:8001/screenshot)
SIZE=$(stat -f%z /tmp/newt-test.png 2>/dev/null || echo 0)

if [ "$HTTP_CODE" = "200" ] && [ "$SIZE" -gt 50000 ]; then
  echo -e "  ${G}✓ Screenshot works!${N} ($SIZE bytes — opening it now…)"
  open /tmp/newt-test.png
else
  echo -e "  ${R}✗ Screenshot still failing.${N}"
  echo "    HTTP code: $HTTP_CODE, file size: $SIZE bytes"
  echo "    Make sure the toggle in Screen Recording is ON."
  echo "    Sometimes you have to remove the entry, re-add it, then toggle."
fi

echo ""
echo "Testing Downloads listing…"
RESPONSE=$(curl -s -X POST http://newt:8001/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"whats in my downloads"}')

if echo "$RESPONSE" | grep -q "permission denied"; then
  echo -e "  ${R}✗ Downloads still blocked.${N} Make sure Full Disk Access toggle is ON."
elif echo "$RESPONSE" | grep -q "Downloads"; then
  echo -e "  ${G}✓ Downloads accessible!${N}"
  echo "$RESPONSE" | python3 -m json.tool | head -15
else
  echo "  Response was:"
  echo "$RESPONSE" | python3 -m json.tool 2>&1 | head -10
fi

echo ""
echo "=========================================="
echo "  Done!                                   "
echo "=========================================="
echo ""
echo "If both tests passed, try on your phone:"
echo "  • \"what's on my screen\""
echo "  • \"what am I working on\""
echo "  • \"what's in my Downloads\""
echo "  • \"find files about [topic]\""
echo ""
