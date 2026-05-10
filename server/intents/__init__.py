from intents import apps, media, system, notes
_MODULES = [system, media, apps, notes]
def match(text):
    for m in _MODULES:
        r = m.match(text)
        if r is not None: return r
    return None
