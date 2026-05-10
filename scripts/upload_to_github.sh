#!/bin/bash
# Newt — bundle iOS app + bridge into a single git repo and push to GitHub.
#
# Run:  bash ~/Desktop/NewtApp/upload_to_github.sh
#
# What it does:
#   1. Creates ~/newt-repo/ with ios/ and server/ folders
#   2. Copies sources, scrubbing secrets (.env, persona.json, venv, logs, etc.)
#   3. Writes .gitignore, README, .env.example
#   4. Initializes git, makes initial commit
#   5. Walks you through creating a GitHub repo, then pushes

set -uo pipefail

G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;36m'; N='\033[0m'

REPO="$HOME/newt-repo"
IOS_SRC="$HOME/Desktop/NewtApp"
SERVER_SRC="$HOME/newt"
PLIST="$HOME/Library/LaunchAgents/com.ethanash.newt-bridge.plist"

echo ""
echo "=========================================="
echo "  Newt — bundle for GitHub                "
echo "=========================================="
echo ""

# ---- Sanity ----------------------------------------------------------------
command -v git >/dev/null || { echo -e "${R}git not installed${N}"; exit 1; }
command -v rsync >/dev/null || { echo -e "${R}rsync not installed${N}"; exit 1; }

if [ -d "$REPO" ]; then
    echo -e "${Y}!${N} $REPO already exists. Reset it? (y/N)"
    read -r ans
    if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then
        echo "Aborted. (Edit/move $REPO yourself if you want to keep it.)"
        exit 0
    fi
    rm -rf "$REPO"
fi

# Make sure git knows who you are. If not, prompt for it.
if [ -z "$(git config --global user.name 2>/dev/null)" ]; then
    echo "Git needs your name + email for commits."
    read -p "  Your name: " GNAME
    read -p "  Your email: " GEMAIL
    git config --global user.name  "$GNAME"
    git config --global user.email "$GEMAIL"
fi

mkdir -p "$REPO"/{ios,server,launchd,scripts}
echo -e "${G}✓${N} Created $REPO"

# ---- Copy iOS app ----------------------------------------------------------
echo ""
echo -e "${B}[1/6]${N} Copying iOS app…"
rsync -a "$IOS_SRC/" "$REPO/ios/" \
    --exclude='.DS_Store' \
    --exclude='build/' \
    --exclude='DerivedData/' \
    --exclude='xcuserdata/' \
    --exclude='*.xcuserstate' \
    --exclude='*.xcworkspace/xcuserdata/' \
    --exclude='AppIcon-1024.png' \
    --exclude='upload_to_github.sh' \
    --exclude='install_launcher.sh' \
    --exclude='grant_permissions.sh' \
    --exclude='fix_permissions.sh' \
    --exclude='migrate_to_homebrew_python.sh' \
    --exclude='recover_bridge.sh' \
    --exclude='keep_mac_awake.sh' \
    --exclude='app_launcher.py'
echo "  $(find "$REPO/ios" -type f | wc -l | tr -d ' ') files copied to ios/"

# Move setup scripts to scripts/ folder (they're useful but not iOS app code)
echo ""
echo -e "${B}[2/6]${N} Copying setup scripts…"
for script in install_launcher.sh grant_permissions.sh fix_permissions.sh \
              migrate_to_homebrew_python.sh recover_bridge.sh keep_mac_awake.sh; do
    [ -f "$IOS_SRC/$script" ] && cp "$IOS_SRC/$script" "$REPO/scripts/"
done
[ -f "$IOS_SRC/app_launcher.py" ] && cp "$IOS_SRC/app_launcher.py" "$REPO/server/app_launcher.py"
echo "  $(find "$REPO/scripts" -type f | wc -l | tr -d ' ') scripts copied"

# ---- Copy server -----------------------------------------------------------
echo ""
echo -e "${B}[3/6]${N} Copying server (excluding secrets, venv, logs)…"
rsync -a "$SERVER_SRC/" "$REPO/server/" \
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
    --exclude='.DS_Store'
echo "  $(find "$REPO/server" -type f | wc -l | tr -d ' ') files copied to server/"

# Generate a real requirements.txt so anyone can `pip install -r`
if command -v "$SERVER_SRC/venv/bin/pip" >/dev/null 2>&1; then
    "$SERVER_SRC/venv/bin/pip" freeze 2>/dev/null \
        | grep -v '^-e\|@ file:' > "$REPO/server/requirements.txt"
    echo "  + generated requirements.txt ($(wc -l < "$REPO/server/requirements.txt" | tr -d ' ') packages)"
fi

# ---- Copy LaunchAgent plist -----------------------------------------------
echo ""
echo -e "${B}[4/6]${N} Copying LaunchAgent plist…"
if [ -f "$PLIST" ]; then
    # Replace user-specific paths with placeholders for portability
    sed "s|$HOME|\$HOME|g" "$PLIST" > "$REPO/launchd/com.ethanash.newt-bridge.plist"
    echo "  ✓ Sanitized + copied (replaced $HOME with \$HOME placeholder)"
else
    echo "  (skip — no plist at $PLIST)"
fi

# ---- Write .gitignore + .env.example + README -----------------------------
echo ""
echo -e "${B}[5/6]${N} Writing .gitignore, README, .env.example…"

cat > "$REPO/.gitignore" <<'EOF'
# --- Secrets / private data ---
.env
.env.local
.env.*.local
**/persona.json
**/notes.md
**/screen.png

# --- Python ---
__pycache__/
*.pyc
*.pyo
*.egg-info/
venv/
venv.*/
.venv/
.python-version

# --- Logs / runtime ---
*.log
**/inbox/
**/chroma_db/
**/chroma/
**/.chromadb/
**/*.bak-*
**/*-snapshot.txt

# --- macOS ---
.DS_Store
**/.DS_Store

# --- Xcode ---
build/
DerivedData/
**/xcuserdata/
*.xcuserstate
**/*.xcworkspace/xcuserdata/
*.swp
*.swo
.swiftpm/

# --- Misc ---
AppIcon-1024.png
EOF

cat > "$REPO/server/.env.example" <<'EOF'
# Newt bridge — copy this file to `.env` and fill in your real keys.
# `cp .env.example .env` then edit.

# OpenAI: powers chat + Whisper transcription + vision (image description)
OPENAI_API_KEY=sk-replace-me

# Optional: Anthropic Claude (only if your bridge calls Claude directly)
# ANTHROPIC_API_KEY=sk-ant-replace-me

# Optional: Piper TTS — path to a downloaded ONNX voice model for the cloned voice
# PIPER_VOICE_PATH=/Users/you/voices/en_US-amy-medium.onnx
EOF

cat > "$REPO/README.md" <<'EOF'
# Newt

Personal voice assistant. iPhone listens, Mac does things.

## What's in here

- `ios/` — SwiftUI iOS app (push-to-talk chat with cloned-voice replies)
- `server/` — Flask bridge that runs on a Mac, parses intents, calls LLMs
- `launchd/` — macOS LaunchAgent plist for keeping the bridge running 24/7
- `scripts/` — one-off setup wizards (permissions, Homebrew migration, etc.)

## What Newt can do

- **Voice + text chat** with cloned-voice replies
- **Open apps** on iPhone or Mac ("open Spotify", "open Chrome on my Mac")
- **Calendar + Reminders** ("what's on my calendar today", "remind me to call mom at 5pm")
- **iMessage** ("text Mom I'm running late") — pre-fills Messages on the phone
- **Mac control** — lock, sleep, wake, volume, music skip/pause, auto-lock toggle
- **File ops** — list / search / send-from-Mac / upload-to-Mac
- **Vision** — point camera at thing, get description
- **Web search** — "google lakers score"
- **Daily briefing** — weather + agenda + reminders + news + quote
- **Quick capture** — "note: idea X" → appends to ~/newt/notes.md
- **Timers** — "set a timer for 10 minutes" (local notification)
- **Persistent memory** — "remember that I live in Geelong"
- **Persona tone** — "be more terse" / "use a witty tone"

## Setup on a fresh Mac

### 1. Clone

```bash
git clone https://github.com/<you>/newt.git ~/newt-repo
```

### 2. Server side

```bash
# Use Homebrew Python (the bridge needs a hardened-runtime Python for TCC)
brew install python@3.13

cd ~/newt-repo/server
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Secrets
cp .env.example .env
# Edit .env to add OPENAI_API_KEY etc.

# Symlink to ~/newt (where the launchd plist expects it)
ln -s ~/newt-repo/server ~/newt

# LaunchAgent
mkdir -p ~/Library/LaunchAgents
cp ~/newt-repo/launchd/com.ethanash.newt-bridge.plist ~/Library/LaunchAgents/
# Edit the plist if your home dir differs — replace $HOME placeholder with /Users/yourname
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ethanash.newt-bridge.plist

# Verify
curl http://localhost:8001/health
```

### 3. macOS permissions (one-time, interactive)

```bash
bash ~/newt-repo/scripts/fix_permissions.sh
```

This walks you through granting Screen Recording + Full Disk Access to the bridge's Python.

### 4. iOS app

```bash
cd ~/newt-repo/ios
open NewtApp.xcodeproj
```

In Xcode → Signing & Capabilities → set your Apple Developer team. Build & run on your iPhone.

## Architecture

```
   iPhone (SwiftUI app)
      │  HTTP POST /chat or /listen (audio)
      ▼
  Tailscale (newt:8001)
      │
      ▼
   Mac bridge (Flask, ~/newt/newt_bridge.py)
      ├── app_launcher.py  ← intent parser (open apps, calendar, etc.)
      ├── chromadb         ← long-term memory
      ├── openai           ← chat / transcription / vision
      └── piper-tts        ← voice cloning
```

## Privacy notes

- All secrets (`.env`, `persona.json`, etc.) are gitignored.
- ChromaDB memory + iOS chat history live locally — never uploaded.
- Your personal Tailscale config isn't here either.

## License

Personal project. Use at your own risk. Not affiliated with Anthropic.
EOF
echo "  ✓ done"

# ---- Initialize git + commit -----------------------------------------------
echo ""
echo -e "${B}[6/6]${N} Initializing git…"
cd "$REPO"
git init -q -b main
git add .
git commit -q -m "Initial commit: Newt voice assistant (iOS + bridge)"
echo "  ✓ Initial commit made"

# Print a summary of what's in the repo
echo ""
echo "Repo summary:"
echo "  $(git ls-files | wc -l | tr -d ' ') files tracked"
echo "  $(du -sh "$REPO" | awk '{print $1}') total size"

# ---- Push to GitHub --------------------------------------------------------
echo ""
echo "=========================================="
echo "  Local repo ready at $REPO"
echo "=========================================="
echo ""
echo "Now create the GitHub repo:"
echo ""
echo "  1. Opening https://github.com/new in your browser…"
echo "  2. Name it:  newt"
echo "  3. Set to:   ${Y}Private${N} (recommended for personal stuff)"
echo "  4. ${R}Don't${N} tick 'Add README/.gitignore/license' boxes"
echo "  5. Click Create"
echo "  6. Copy the URL it shows (looks like https://github.com/yourname/newt.git)"
echo ""

# Open GitHub in browser
open "https://github.com/new" 2>/dev/null || true

read -p "Paste the URL here, then press Enter: " GH_URL
GH_URL=$(echo "$GH_URL" | tr -d ' ')
if [ -z "$GH_URL" ]; then
    echo ""
    echo "No URL given. To finish later:"
    echo "  cd $REPO"
    echo "  git remote add origin <your-url>"
    echo "  git push -u origin main"
    exit 0
fi

git remote add origin "$GH_URL"

echo ""
echo "Pushing to $GH_URL …"
if git push -u origin main; then
    echo ""
    echo -e "${G}✓ Done. Newt is on GitHub.${N}"
    echo ""
    echo "On your MacBook, you can now clone with:"
    echo ""
    echo "  git clone $GH_URL ~/newt-repo"
    echo ""
    echo "Then follow the setup steps in $REPO/README.md"
else
    echo ""
    echo -e "${R}✗ Push failed.${N} Most likely cause: GitHub auth."
    echo ""
    echo "If you got prompted for a password and didn't have one ready:"
    echo "  1. Generate a personal access token at https://github.com/settings/tokens"
    echo "  2. Use the token as your password when git asks"
    echo ""
    echo "Or set up SSH and try:"
    echo "  cd $REPO"
    echo "  git remote set-url origin git@github.com:<you>/newt.git"
    echo "  git push -u origin main"
fi
