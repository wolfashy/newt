import re, subprocess
def _osa(s): subprocess.run(["osascript", "-e", s], capture_output=True, timeout=5)
_VU = re.compile(r"^(?:volume\s+up|louder)$", re.I)
_VD = re.compile(r"^(?:volume\s+down|quieter)$", re.I)
_M = re.compile(r"^mute$", re.I)
_L = re.compile(r"^lock(?:\s+(?:the\s+)?(?:mac|screen))?$", re.I)
def match(text):
    t = text.strip()
    if _VU.match(t): _osa("set volume output volume ((output volume of (get volume settings)) + 15)"); return {"reply": "Volume up."}
    if _VD.match(t): _osa("set volume output volume ((output volume of (get volume settings)) - 15)"); return {"reply": "Volume down."}
    if _M.match(t): _osa("set volume with output muted"); return {"reply": "Muted."}
    if _L.match(t): _osa('tell application "System Events" to keystroke "q" using {control down, command down}'); return {"reply": "Locking."}
    return None
