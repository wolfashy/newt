#!/bin/bash
# Newt — final permission fix.
# Adds the correct Python.app bundle (not the venv symlink) to Screen
# Recording and Full Disk Access.

set -u

# Detect the actual running binary (most accurate for TCC), falling back
# to readlink + .app bundle resolution if the bridge isn't running.
detect_python_app() {
    # Try running process first — this is what the kernel/TCC sees
    local running
    running=$(ps -axo command= | grep -E 'newt_bridge\.py' | grep -v grep | head -1 | awk '{print $1}')
    if [ -n "$running" ] && [ -e "$running" ]; then
        # If the binary lives inside a .app bundle, return the bundle
        if [[ "$running" == *".app/Contents/MacOS/"* ]]; then
            echo "${running%.app/Contents/MacOS/*}.app"
            return
        fi
        echo "$running"
        return
    fi

    # Fallback: resolve the venv python symlink and find .app
    for cand in "$HOME/newt/venv/bin/python3" "$HOME/newt/venv/bin/python"; do
        if [ -e "$cand" ]; then
            local real
            real=$(readlink -f "$cand" 2>/dev/null)
            if [ -n "$real" ]; then
                # Walk up to find Python.app bundle
                local dir="${real%/bin/*}"
                if [ -d "$dir/Resources/Python.app" ]; then
                    echo "$dir/Resources/Python.app"
                    return
                fi
                echo "$real"
                return
            fi
        fi
    done

    echo ""
}

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;36m'; N='\033[0m'

echo ""
echo "=========================================="
echo "  Newt — final permission fix             "
echo "=========================================="
echo ""

PY_APP=$(detect_python_app)
if [ -z "$PY_APP" ] || [ ! -e "$PY_APP" ]; then
    echo -e "${R}Could not detect Newt's Python. Is the bridge running?${N}"
    exit 1
fi

echo -e "${G}✓${N} Found the binary the bridge actually uses:"
echo "    $PY_APP"
echo ""
echo "This is what needs to be in your Screen Recording and"
echo "Full Disk Access lists — NOT the plain 'python3' you added before."
echo ""
echo -e "Press ${B}Enter${N} when you're ready to start."
read -r

# ============================================================================
# Step 1 — Screen Recording
# ============================================================================
echo ""
echo "=========================================="
echo -e "  ${Y}Step 1 of 2: Screen Recording${N}    "
echo "=========================================="
echo ""

echo -n "$PY_APP" | pbcopy
echo -e "${G}✓${N} Path copied to your clipboard."
echo ""
echo "Opening Screen Recording…"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
sleep 1

echo ""
echo "Now do this:"
echo ""
echo -e "  ${B}1.${N} You'll see your old ${R}python3${N} entry — leave it, no need to remove it"
echo -e "  ${B}2.${N} Click ${G}+${N} (bottom left of the list)"
echo -e "  ${B}3.${N} Press ${G}⇧⌘G${N}"
echo -e "  ${B}4.${N} Press ${G}⌘V${N} to paste the path"
echo -e "  ${B}5.${N} Press ${G}Enter${N}"
echo -e "  ${B}6.${N} You'll see ${G}Python.app${N} highlighted — click ${G}Open${N}"
echo -e "  ${B}7.${N} Toggle the new ${G}Python${N} entry ${G}ON${N}"
echo ""
echo -e "${Y}Then press Enter here.${N}"
read -r

# ============================================================================
# Step 2 — Full Disk Access
# ============================================================================
echo ""
echo "=========================================="
echo -e "  ${Y}Step 2 of 2: Full Disk Access${N}    "
echo "=========================================="
echo ""

echo -n "$PY_APP" | pbcopy
echo -e "${G}✓${N} Path is back on your clipboard."
echo ""
echo "Opening Full Disk Access…"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
sleep 1

echo ""
echo "Same procedure:"
echo ""
echo -e "  ${B}1.${N} Click ${G}+${N}"
echo -e "  ${B}2.${N} ${G}⇧⌘G${N}"
echo -e "  ${B}3.${N} ${G}⌘V${N}"
echo -e "  ${B}4.${N} Enter, then ${G}Open${N}"
echo -e "  ${B}5.${N} Toggle the new ${G}Python${N} entry ${G}ON${N}"
echo ""
echo -e "${Y}Press Enter when done.${N}"
read -r

# ============================================================================
# Restart bridge & test
# ============================================================================
echo ""
echo "Restarting the bridge…"
launchctl kickstart -k "gui/$(id -u)/com.ethanash.newt-bridge"
sleep 3

echo ""
echo "Testing screenshot…"
HTTP=$(curl -s -o /tmp/newt-test.png -w "%{http_code}" http://newt:8001/screenshot)
SIZE=$(stat -f%z /tmp/newt-test.png 2>/dev/null || echo 0)

if [ "$HTTP" = "200" ] && [ "$SIZE" -gt 50000 ]; then
  echo -e "  ${G}✓ Screenshot works!${N} ($SIZE bytes — opening it now…)"
  open /tmp/newt-test.png
else
  echo -e "  ${R}✗ Still failing.${N} HTTP $HTTP, $SIZE bytes."
  echo "    The toggle for Python (the new entry) needs to be ON."
fi

echo ""
echo "Testing Downloads…"
RESPONSE=$(curl -s -X POST http://newt:8001/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"whats in my downloads"}')

if echo "$RESPONSE" | grep -q "permission denied"; then
  echo -e "  ${R}✗ Still blocked.${N} Toggle in Full Disk Access needs to be ON."
elif echo "$RESPONSE" | grep -q -i "Downloads"; then
  echo -e "  ${G}✓ Downloads accessible!${N}"
else
  echo "$RESPONSE" | python3 -m json.tool 2>&1 | head -8
fi

echo ""
echo "Done. Try \"what's on my screen\" or \"what's in my Downloads\" on your phone."
