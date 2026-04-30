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
