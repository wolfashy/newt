import re, subprocess
def _osa(s): subprocess.run(["osascript", "-e", s], capture_output=True, timeout=5)
_P = [(re.compile(r"^(?:next|skip)(?:\s+(?:song|track))?$", re.I), "next"), (re.compile(r"^(?:pause|stop)(?:\s+(?:music|spotify))?$", re.I), "pause"), (re.compile(r"^(?:play|resume)(?:\s+(?:music|spotify))?$", re.I), "play")]
def match(text):
    for p, a in _P:
        if p.match(text.strip()):
            if a == "next": _osa('tell application "Spotify" to next track'); return {"reply": "Next track."}
            if a == "pause": _osa('tell application "Spotify" to pause'); return {"reply": "Paused."}
            if a == "play": _osa('tell application "Spotify" to play'); return {"reply": "Playing."}
    return None
