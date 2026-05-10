import re
_RE = re.compile(r"^(?:remember|note|save)\s+(?:that\s+)?(.+)$", re.I)
def match(text):
    m = _RE.match(text.strip())
    if not m: return None
    from core.memory import load_persona, save_persona
    p = load_persona(); p.setdefault("facts", []).append(m.group(1).strip()); p["facts"] = p["facts"][-50:]
    save_persona(p)
    return {"reply": "Got it, I\'ll remember that."}
