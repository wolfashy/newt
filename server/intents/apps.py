import re, subprocess
_RE = re.compile(r"^(?:open|launch|start)\s+(.+)$", re.I)
ALIASES = {"spotify": "Spotify", "chrome": "Google Chrome", "safari": "Safari", "messages": "Messages", "mail": "Mail", "notes": "Notes", "code": "Visual Studio Code"}
def match(text):
    m = _RE.match(text.strip())
    if not m: return None
    app = m.group(1).strip().lower().rstrip(".")
    resolved = ALIASES.get(app, app.title())
    subprocess.Popen(["open", "-a", resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"reply": f"Opening {resolved}."}
