#!/bin/bash
# Newt cross-platform app launcher installer.
# Run from anywhere: bash ~/Desktop/NewtApp/install_launcher.sh

set -e

NEWT_DIR="$HOME/newt"
NEWTAPP_DIR="$HOME/Desktop/NewtApp"
LAUNCHER_SRC="$NEWTAPP_DIR/app_launcher.py"
BRIDGE="$NEWT_DIR/newt_bridge.py"

echo "=========================================="
echo "  Newt cross-platform launcher installer  "
echo "=========================================="
echo ""

# ---- Sanity checks --------------------------------------------------------
if [ ! -d "$NEWT_DIR" ]; then
  echo "✗ ~/newt/ doesn't exist. Bridge install missing — bail."
  exit 1
fi
if [ ! -f "$BRIDGE" ]; then
  echo "✗ $BRIDGE not found. Bail."
  exit 1
fi
if [ ! -f "$LAUNCHER_SRC" ]; then
  echo "✗ $LAUNCHER_SRC not found. Bail."
  exit 1
fi

# ---- 1. Copy app_launcher.py ---------------------------------------------
echo "[1/4] Copying app_launcher.py to ~/newt/"
cp "$LAUNCHER_SRC" "$NEWT_DIR/app_launcher.py"
echo "      ✓ done"
echo ""

# ---- 2. Backup + patch newt_bridge.py ------------------------------------
echo "[2/4] Patching newt_bridge.py"
TS=$(date +%Y%m%d-%H%M%S)
cp "$BRIDGE" "$BRIDGE.bak-$TS"
echo "      ✓ backup at $BRIDGE.bak-$TS"

# Use Python to do the patching — far more robust than sed for Python source.
"$NEWT_DIR/venv/bin/python3" - "$BRIDGE" <<'PYEOF'
import re, sys, textwrap
from pathlib import Path

bridge_path = Path(sys.argv[1])
src = bridge_path.read_text()
original = src

IMPORT_LINE = "from app_launcher import handle_message as _newt_handle_app_intent, register_routes as _newt_register_routes, system_prompt_prefix as _newt_system_prompt_prefix"

# ---- Add import (idempotent) ---------------------------------------------
# Replace any older variant of the import with the combined one.
src = re.sub(
    r"from app_launcher import [^\n]*\n",
    "",
    src,
)
if IMPORT_LINE not in src:
    lines = src.split("\n")
    last_import = -1
    for i, line in enumerate(lines):
        if re.match(r"^(import|from)\s+\S", line):
            last_import = i
    if last_import == -1:
        last_import = 0
    lines.insert(last_import + 1, IMPORT_LINE)
    src = "\n".join(lines)
    print("      ✓ added import")
else:
    print("      • import already present (skipping)")

# ---- Inject register_routes(app) call after Flask app creation ----------
REGISTER_LINE = "_newt_register_routes(app)"
if REGISTER_LINE not in src:
    flask_app_re = re.compile(
        r'(\n[ \t]*app\s*=\s*Flask\([^)]*\)[^\n]*\n)',
    )
    m = flask_app_re.search(src)
    if m:
        # Insert register call right after the app = Flask(...) line
        insert_at = m.end()
        src = src[:insert_at] + REGISTER_LINE + "\n" + src[insert_at:]
        print("      ✓ registered /screenshot + /file routes")
    else:
        print("      ⚠ couldn't find 'app = Flask(...)' line to register routes")
else:
    print("      • routes already registered (skipping)")

# ---- Helper: indent-aware block builder ----------------------------------
def reindent(block_dedented, indent):
    """Apply `indent` to the start of every non-empty line."""
    out = []
    for line in block_dedented.splitlines():
        if line.strip():
            out.append(indent + line)
        else:
            out.append("")
    return "\n".join(out) + "\n"

CHAT_BLOCK = textwrap.dedent('''\
    # Newt: cross-platform app launcher (auto-injected)
    try:
        from flask import request as _newt_req, jsonify as _newt_jsonify
        _newt_data = _newt_req.get_json(silent=True) or {}
        _newt_text = _newt_data.get("prompt") or _newt_data.get("message") or _newt_data.get("text") or ""
        _newt_intent = _newt_handle_app_intent(_newt_text)
        if _newt_intent is not None:
            return _newt_jsonify(_newt_intent)
        # Persona / memory injection — prepend tone + remembered facts so the
        # LLM downstream honors them. Mutates the cached request JSON dict.
        try:
            _newt_persona = _newt_system_prompt_prefix()
            if _newt_persona and _newt_text:
                for _k in ("prompt", "message", "text"):
                    if _k in _newt_data:
                        _newt_data[_k] = _newt_persona + _newt_text
                        break
        except Exception:
            pass
    except Exception as _newt_e:
        print(f"[newt-launcher] /chat hook error: {_newt_e}")
''')

LISTEN_BLOCK = textwrap.dedent('''\
    # Newt: cross-platform app launcher (auto-injected)
    try:
        _newt_intent_l = _newt_handle_app_intent(transcript)
        if _newt_intent_l is not None:
            from flask import jsonify as _newt_jsonify_l
            return _newt_jsonify_l({"transcript": transcript, **_newt_intent_l})
    except Exception as _newt_le:
        print(f"[newt-launcher] /listen hook error: {_newt_le}")
''')

# ---- Inject /chat hook (auto-detect indent) ------------------------------
already_chat = "_newt_handle_app_intent(_newt_text)" in src
if not already_chat:
    # Find /chat handler. Capture the indent of the FIRST non-blank line of body.
    chat_re = re.compile(
        r'(@app\.route\(\s*["\']/chat["\'][^)]*\)\s*\n\s*def\s+\w+\([^)]*\)\s*:\s*\n)'
        r'((?:[ \t]*\n)*)([ \t]+)',
        re.MULTILINE,
    )
    m = chat_re.search(src)
    if m:
        indent = m.group(3)
        block = reindent(CHAT_BLOCK, indent)
        # Insert just after the def line (and any leading blank lines)
        insert_at = m.start(3)
        src = src[:insert_at] + block + src[insert_at:]
        print(f"      ✓ injected /chat hook (indent: {len(indent)} spaces)")
    else:
        print("      ⚠ couldn't find /chat route")
else:
    print("      • /chat hook already present (skipping)")

# ---- Inject /listen hook (after transcript = ..., auto-detect indent) ----
already_listen = "_newt_intent_l" in src
if not already_listen:
    listen_match = re.search(
        r'@app\.route\(\s*["\']/listen["\'][^)]*\)\s*\n\s*def\s+(\w+)\([^)]*\)\s*:\s*\n',
        src,
    )
    if listen_match:
        body_start = listen_match.end()
        next_route = re.search(r'\n@app\.route|\nif __name__', src[body_start:])
        body_end = body_start + (next_route.start() if next_route else len(src) - body_start)
        body = src[body_start:body_end]

        # Find first `transcript = ...` and CAPTURE ITS INDENT
        tx = re.search(r'\n([ \t]+)transcript\s*=\s*[^\n]+\n', body)
        if tx:
            indent = tx.group(1)
            block = reindent(LISTEN_BLOCK, indent)
            new_body = body[:tx.end()] + block + body[tx.end():]
            src = src[:body_start] + new_body + src[body_end:]
            print(f"      ✓ injected /listen hook (indent: {len(indent)} spaces)")
        else:
            print("      ⚠ /listen has no `transcript = ` line — voice intents won't be intercepted")
    else:
        print("      ⚠ couldn't find /listen route")
else:
    print("      • /listen hook already present (skipping)")

# ---- Validate syntax before writing --------------------------------------
import ast
try:
    ast.parse(src)
except SyntaxError as e:
    print(f"      ✗ Patched file has syntax error: {e}")
    print("      ✗ NOT writing — backup is intact.")
    sys.exit(2)

# ---- Write back -----------------------------------------------------------
if src != original:
    bridge_path.write_text(src)
    print("      ✓ wrote patched newt_bridge.py")
else:
    print("      • no changes (already patched)")
PYEOF

PATCH_RC=$?
if [ $PATCH_RC -ne 0 ]; then
  echo "      ✗ Patcher exited with code $PATCH_RC. Restoring backup."
  cp "$BRIDGE.bak-$TS" "$BRIDGE"
  exit $PATCH_RC
fi

echo ""

# ---- 3. Restart launchd service ------------------------------------------
echo "[3/4] Restarting launchd service"
launchctl kickstart -k "gui/$(id -u)/com.ethanash.newt-bridge" 2>&1 || {
  echo "      ⚠ kickstart failed — service may not be loaded. Try:"
  echo "        launchctl bootout gui/\$(id -u) ~/Library/LaunchAgents/com.ethanash.newt-bridge.plist"
  echo "        launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/com.ethanash.newt-bridge.plist"
  exit 1
}
echo "      ✓ kicked"
echo ""

# ---- 4. Smoke test --------------------------------------------------------
echo "[4/4] Waiting for service, then smoke-testing..."
sleep 3

echo ""
echo "  → health check:"
curl -s --max-time 5 http://newt:8001/health | python3 -m json.tool 2>&1 | sed 's/^/    /' || echo "    (no response)"

echo ""
echo "  → 'open spotify' (should return iOS action):"
curl -s --max-time 10 -X POST http://newt:8001/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"open spotify"}' | python3 -m json.tool 2>&1 | sed 's/^/    /' || echo "    (failed)"

echo ""
echo "  → 'run my morning shortcut' (should return shortcut URL):"
curl -s --max-time 10 -X POST http://newt:8001/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"run my morning shortcut"}' | python3 -m json.tool 2>&1 | sed 's/^/    /' || echo "    (failed)"

echo ""
echo "=========================================="
echo "  ✓ Done."
echo ""
echo "  Next: rebuild the iOS app in Xcode (⌘B → ▶︎),"
echo "  then in Newt try 'open Spotify' or 'open Chrome on my Mac'."
echo ""
echo "  Backup of original bridge: $BRIDGE.bak-$TS"
echo "=========================================="
