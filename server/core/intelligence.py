from __future__ import annotations
import datetime, hashlib, json, logging, re, time
from pathlib import Path
from core.config import BASE_DIR

log = logging.getLogger(__name__)

# --- Response Cache ---
_cache: dict[str, tuple[float, str]] = {}
CACHE_TTL = 300

def cache_key(text: str) -> str:
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    return hashlib.md5(normalized.encode()).hexdigest()

def get_cached(text: str) -> str | None:
    key = cache_key(text)
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return val
        del _cache[key]
    return None

def set_cached(text: str, response: str):
    _cache[cache_key(text)] = (time.time(), response)

# --- Time-Aware System Notes ---
def time_aware_note() -> str:
    now = datetime.datetime.now()
    hour = now.hour
    day = now.strftime("%A")
    date = now.strftime("%B %d, %Y")
    if hour < 6:
        period = "late night"
    elif hour < 12:
        period = "morning"
    elif hour < 17:
        period = "afternoon"
    elif hour < 21:
        period = "evening"
    else:
        period = "night"
    return f"Current time: {now.strftime('%I:%M %p')}, {day} {period} ({date})."

# --- Markdown Stripping for Voice ---
def strip_markdown(text: str) -> str:
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# --- Response Length Adaptation ---
def adapt_max_tokens(text: str, is_voice: bool = False) -> int:
    if is_voice:
        return 300
    words = len(text.split())
    if words <= 5:
        return 256
    elif words <= 15:
        return 512
    return 1024

# --- Proactive Suggestions ---
def proactive_suggestion() -> str:
    now = datetime.datetime.now()
    hour = now.hour
    day = now.weekday()
    suggestions = []
    if hour == 8 and day < 5:
        suggestions.append("Would you like your morning briefing?")
    if hour == 22:
        suggestions.append("Ready to wind down? I can set your lights to nighttime mode.")
    if hour == 12:
        suggestions.append("Lunchtime — want me to check your afternoon calendar?")
    return suggestions[0] if suggestions else ""

# --- Habit Tracking ---
HABITS_PATH = BASE_DIR / "habits.json"

def _load_habits() -> dict:
    if HABITS_PATH.exists():
        try:
            return json.loads(HABITS_PATH.read_text())
        except:
            pass
    return {"habits": {}, "streaks": {}}

def _save_habits(data: dict):
    HABITS_PATH.write_text(json.dumps(data, indent=2))

def log_habit(name: str) -> dict:
    data = _load_habits()
    today = datetime.date.today().isoformat()
    if name not in data["habits"]:
        data["habits"][name] = []
    if today not in data["habits"][name]:
        data["habits"][name].append(today)
    streak = _calc_streak(data["habits"][name])
    data["streaks"][name] = streak
    _save_habits(data)
    return {"habit": name, "streak": streak, "logged": today}

def get_habits() -> dict:
    data = _load_habits()
    result = {}
    for name, dates in data["habits"].items():
        result[name] = {"streak": _calc_streak(dates), "total": len(dates), "last": dates[-1] if dates else None}
    return result

def _calc_streak(dates: list[str]) -> int:
    if not dates:
        return 0
    sorted_dates = sorted(dates, reverse=True)
    today = datetime.date.today()
    streak = 0
    for i, d in enumerate(sorted_dates):
        expected = (today - datetime.timedelta(days=i)).isoformat()
        if d == expected:
            streak += 1
        else:
            break
    return streak

# --- Language Detection (basic) ---
def detect_language(text: str) -> str:
    common_spanish = {"hola", "que", "cómo", "está", "bien", "gracias", "por", "favor"}
    common_french = {"bonjour", "merci", "comment", "bien", "oui", "non", "je", "suis"}
    words = set(text.lower().split())
    if len(words & common_spanish) >= 2:
        return "es"
    if len(words & common_french) >= 2:
        return "fr"
    return "en"
