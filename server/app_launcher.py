"""
Newt — app launcher + intents.

Resolves natural-language commands into structured actions for the iOS
Newt app, or executes them on the Mac directly.

Supported intents:
  * App launch      "open spotify"            -> open_url action / Mac launch
  * Shortcut run    "run my morning shortcut" -> shortcuts:// URL
  * Reminder write  "remind me to call mom at 5pm"
                                              -> create_reminder action
  * Event write     "schedule lunch with sam tomorrow at noon"
                                              -> create_event action
  * Calendar read   "what's on my calendar today" / "what's on my agenda"
                                              -> read_events action
  * Reminder read   "what are my reminders" / "what do i need to do"
                                              -> read_reminders action
"""

from __future__ import annotations

import os
import re
import subprocess
import urllib.parse
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple


# ---------------------------------------------------------------------------
# iOS URL scheme registry. Keys are lower-case; matching is case-insensitive.
# Add freely - Apple does not publish a master list, so we curate.
# ---------------------------------------------------------------------------

IOS_URL_SCHEMES: Dict[str, str] = {
    # Music & video
    "spotify":          "spotify://",
    "youtube":          "youtube://",
    "youtube music":    "youtubemusic://",
    "yt music":         "youtubemusic://",
    "apple music":      "music://",
    "music":            "music://",
    "netflix":          "nflx://",
    "disney+":          "disneyplus://",
    "disney plus":      "disneyplus://",
    "apple tv":         "videos://",
    "tv":               "videos://",
    "hbo max":          "hbomax://",
    "max":              "hbomax://",
    "twitch":           "twitch://",
    "vlc":              "vlc://",
    "plex":             "plex://",
    # Communication
    "mail":             "message://",
    "gmail":            "googlegmail://",
    "outlook":          "ms-outlook://",
    "messages":         "sms:",
    "imessage":         "sms:",
    "phone":            "tel:",
    "facetime":         "facetime://",
    "slack":            "slack://",
    "discord":          "discord://",
    "whatsapp":         "whatsapp://",
    "telegram":         "tg://",
    "signal":           "sgnl://",
    "zoom":             "zoomus://",
    "teams":            "msteams://",
    # Maps & travel
    "maps":             "maps://",
    "apple maps":       "maps://",
    "google maps":      "comgooglemaps://",
    "waze":             "waze://",
    "uber":             "uber://",
    "lyft":             "lyft://",
    # Social
    "instagram":        "instagram://",
    "ig":               "instagram://",
    "twitter":          "twitter://",
    "x":                "twitter://",
    "threads":          "barcelona://",
    "tiktok":           "snssdk1233://",
    "facebook":         "fb://",
    "fb":               "fb://",
    "reddit":           "reddit://",
    "linkedin":         "linkedin://",
    "snapchat":         "snapchat://",
    # AI assistants
    "chatgpt":          "chatgpt://",
    "gpt":              "chatgpt://",
    "claude":           "claude://",
    "perplexity":       "perplexity://",
    "gemini":           "googlegemini://",
    "copilot":          "ms-copilot://",
    # Productivity / Apple defaults
    "notes":            "mobilenotes://",
    "reminders":        "x-apple-reminderkit://",
    "calendar":         "calshow://",
    "files":            "shareddocuments://",
    "find my":          "findmy://",
    "shortcuts":        "shortcuts://",
    "settings":         "App-Prefs:",
    "weather":          "weather://",
    "calculator":       "calc://",
    "stocks":           "stocks://",
    "wallet":           "shoebox://",
    "health":           "x-apple-health://",
    "photos":           "photos-redirect://",
    "camera":           "camera://",
    "clock":            "clock-alarm://",
    "books":            "ibooks://",
    "podcasts":         "pcast://",
    "news":             "applenews://",
    # Browsers
    "safari":           "x-web-search://",
    "chrome":           "googlechrome://",
    "google":           "googlechrome://",   # alias: "open google" -> Chrome
    "google chrome":    "googlechrome://",
    "firefox":          "firefox://",
    "edge":             "microsoft-edge://",
    "duckduckgo":       "ddg://",
    "brave":            "brave://",
    "arc":              "arc://",
    # Notes / dev / misc
    "notion":           "notion://",
    "obsidian":         "obsidian://",
    "github":           "github://",
    "1password":        "onepassword://",
    "bitwarden":        "bitwarden://",
    "todoist":          "todoist://",
    "things":           "things:///show",
    "spark":            "readdle-spark://",
    # Money
    "robinhood":        "robinhood://",
    "venmo":            "venmo://",
    "cashapp":          "cashapp://",
    "paypal":           "paypal://",
}


# ---------------------------------------------------------------------------
# Mac app name aliases. Spoken name (lowercase) -> actual `open -a` arg.
# Use this when "open foo on my mac" needs a different app name on macOS.
# ---------------------------------------------------------------------------

MAC_APP_ALIASES: Dict[str, str] = {
    "google":           "Google Chrome",
    "chrome":           "Google Chrome",
    "vscode":           "Visual Studio Code",
    "vs code":          "Visual Studio Code",
    "code":             "Visual Studio Code",
    "terminal":         "Terminal",
    "iterm":            "iTerm",
    "iterm2":           "iTerm",
    "finder":           "Finder",
    "system settings":  "System Settings",
    "system preferences":"System Settings",
    "settings":         "System Settings",
    "preview":          "Preview",
    "music":            "Music",
    "apple music":      "Music",
    "tv":               "TV",
    "apple tv":         "TV",
    "messages":         "Messages",
    "imessage":         "Messages",
    "mail":             "Mail",
    "facetime":         "FaceTime",
    "photos":           "Photos",
    "notes":            "Notes",
    "reminders":        "Reminders",
    "calendar":         "Calendar",
    "maps":             "Maps",
    "weather":          "Weather",
    "calculator":       "Calculator",
    "stocks":           "Stocks",
    "books":            "Books",
    "podcasts":         "Podcasts",
    "news":             "News",
    "find my":          "Find My",
    "voice memos":      "Voice Memos",
    "shortcuts":        "Shortcuts",
    "freeform":         "Freeform",
    "spotify":          "Spotify",
    "slack":            "Slack",
    "discord":          "Discord",
    "zoom":             "zoom.us",
    "teams":            "Microsoft Teams",
    "whatsapp":         "WhatsApp",
    "telegram":         "Telegram",
    "signal":           "Signal",
    "obsidian":         "Obsidian",
    "notion":           "Notion",
    "1password":        "1Password",
    "github":           "GitHub Desktop",
    "github desktop":   "GitHub Desktop",
    "xcode":            "Xcode",
    "chatgpt":          "ChatGPT",
    "claude":           "Claude",
    "perplexity":       "Perplexity",
    "spark":            "Spark",
    "todoist":          "Todoist",
    "fantastical":      "Fantastical",
    "raycast":          "Raycast",
    "alfred":           "Alfred",
    "rectangle":        "Rectangle",
    "magnet":           "Magnet",
    "vlc":              "VLC",
    "iina":             "IINA",
    "plex":             "Plex",
    "transmission":     "Transmission",
}


# ---------------------------------------------------------------------------
# Intent parsing - regexes
# ---------------------------------------------------------------------------

OPEN_PREFIX = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:open|launch|start|fire\s+up|bring\s+up|pull\s+up)\s+",
    re.IGNORECASE,
)

MAC_TOKENS = re.compile(
    r"\b(?:on\s+(?:my\s+|the\s+)?(?:mac|imac|computer|desktop|laptop))\b",
    re.IGNORECASE,
)

IOS_TOKENS = re.compile(
    r"\b(?:on\s+(?:my\s+|the\s+)?(?:phone|iphone|mobile))\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_open_prefix(text: str) -> Optional[str]:
    m = OPEN_PREFIX.match(text)
    if not m:
        return None
    return text[m.end():].strip()


def _strip_target_tokens(text: str) -> Tuple[str, Optional[str]]:
    target: Optional[str] = None
    if MAC_TOKENS.search(text):
        target = "mac"
        text = MAC_TOKENS.sub("", text)
    elif IOS_TOKENS.search(text):
        target = "ios"
        text = IOS_TOKENS.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" \t,.!?;:")
    return text, target


def _normalize_app_name(name: str) -> str:
    name = name.strip().rstrip(" \t,.!?;:")
    name = re.sub(r"^\s*(?:the|a|an)\s+", "", name, flags=re.IGNORECASE)
    name = re.sub(
        r"\s+(?:please|pls|thanks|thank\s+you|for\s+me|now|already)\s*$",
        "", name, flags=re.IGNORECASE,
    )
    name = re.sub(r"\s+app$", "", name, flags=re.IGNORECASE).strip()
    return name


def _resolve_ios_url(name: str) -> Optional[str]:
    key = _normalize_app_name(name).lower()
    if not key:
        return None
    if key in IOS_URL_SCHEMES:
        return IOS_URL_SCHEMES[key]
    for k, v in IOS_URL_SCHEMES.items():
        if k == key or (len(k) > 3 and k in key):
            return v
    return None


def _resolve_mac_app(name: str) -> str:
    """Map a spoken name to the actual macOS app name. Falls back to title-case."""
    key = _normalize_app_name(name).lower()
    if key in MAC_APP_ALIASES:
        return MAC_APP_ALIASES[key]
    # Substring fallback ("the google app" -> google -> Google Chrome)
    for k, v in MAC_APP_ALIASES.items():
        if k == key or (len(k) > 3 and k in key):
            return v
    return _normalize_app_name(name).title()


def _open_mac_app(name: str) -> bool:
    pretty = _resolve_mac_app(name)
    if not pretty:
        return False
    try:
        result = subprocess.run(
            ["open", "-a", pretty],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _is_shortcut_request(text: str) -> Optional[str]:
    if "shortcut" not in text.lower():
        return None
    m = re.match(
        r"^\s*(?:please\s+)?(?:run|trigger|fire|execute)\s+"
        r"(?:my\s+)?(?:shortcut\s+(?:called\s+)?)?(.+?)"
        r"(?:\s+shortcut)?\s*$",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None
    return m.group(1).strip().strip(" \t,.!?;:")


# ---------------------------------------------------------------------------
# Calendar / Reminders intents
# ---------------------------------------------------------------------------

# "remind me to <something> [at|in|tomorrow|...]"
# Also accepts "remember to ..." since people use them interchangeably.
REMINDER_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:remind\s+me\s+to\s+|set\s+a?\s*reminder\s+to\s+|reminder\s+to\s+|"
    r"remember\s+to\s+)"
    r"(.+?)$",
    re.IGNORECASE,
)

# "what's on my calendar/agenda/schedule [today|tomorrow|this week]"
# Tolerates "whats" (no apostrophe) and a trailing "today"/"tomorrow"/"this week"
# anywhere in the sentence.
READ_EVENTS_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:what(?:[’']?s|\s+is)?\s+(?:on\s+)?my\s+(?:calendar|agenda|schedule)|"
    r"what\s+do\s+i\s+have\s+(?:on|today|tomorrow|this\s+week)|"
    r"my\s+(?:calendar|agenda|schedule)|"
    r"show\s+(?:me\s+)?my\s+(?:calendar|agenda|schedule))"
    r"(?:[^?.!\n]*?(today|tomorrow|this\s+week|the\s+week|week))?"
    r"[^?.!\n]*[?.!]?\s*$",
    re.IGNORECASE,
)

# "what reminders do I have", "what's on my todo list"
READ_REMINDERS_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:what\s+(?:are\s+)?(?:my\s+)?reminders|"
    r"what\s+do\s+i\s+(?:need\s+to\s+do|have\s+to\s+do)|"
    r"my\s+(?:reminders|todo\s*list|to-do\s*list)|"
    r"show\s+(?:me\s+)?(?:my\s+)?reminders)"
    r".*?\s*[?.!]?\s*$",
    re.IGNORECASE,
)

# "schedule a meeting with X tomorrow at 3pm"
EVENT_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:schedule|book|put|add|create)\s+"
    r"(?:a\s+|an\s+)?"
    r"(?:meeting|event|appointment|call|lunch|dinner|coffee)\s+"
    r"(.+?)$",
    re.IGNORECASE,
)


def _parse_natural_time(text: str, now: Optional[datetime] = None) -> Tuple[Optional[datetime], str]:
    """
    Pull a time expression out of `text`. Returns (datetime or None, text_without_time).

    Handles:
      "at 5pm", "at 5", "at 5:30", "at 17:00"
      "in 10 minutes", "in 2 hours"
      "tomorrow [at 3]", "today [at 3]"
      "next monday", "monday at 5pm"
      "tonight"
    """
    if now is None:
        now = datetime.now()

    text = text.strip()
    base_date = now.date()
    matched_a_date = False

    # ---- Date keyword ----
    date_word_re = re.compile(
        r"\b(today|tomorrow|tonight|this\s+evening|this\s+afternoon|this\s+morning|"
        r"next\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
        r"(?:on\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
        re.IGNORECASE,
    )
    m = date_word_re.search(text)
    if m:
        matched_a_date = True
        word = m.group(1).lower().strip()
        if "tomorrow" in word:
            base_date = (now + timedelta(days=1)).date()
        elif "today" in word or "tonight" in word or word.startswith("this "):
            base_date = now.date()
        else:
            # Weekday name (with or without "next" / "on")
            weekdays = ["monday", "tuesday", "wednesday", "thursday",
                        "friday", "saturday", "sunday"]
            cleaned = re.sub(r"^(?:next|on)\s+", "", word).strip()
            try:
                target = weekdays.index(cleaned)
                today_idx = now.weekday()
                delta = (target - today_idx) % 7
                if delta == 0:
                    delta = 7  # "monday" said on Monday means next Monday
                base_date = (now + timedelta(days=delta)).date()
            except ValueError:
                pass
        text = (text[:m.start()] + text[m.end():]).strip()

    # ---- Default time bucket if a date keyword used ----
    default_hour = None
    word_lower = m.group(1).lower() if m else ""
    if "tonight" in word_lower or "evening" in word_lower:
        default_hour = 19
    elif "afternoon" in word_lower:
        default_hour = 14
    elif "morning" in word_lower:
        default_hour = 9

    # ---- "at noon" / "at midnight" ----
    nm = re.search(r"\bat\s+(noon|midnight)\b", text, re.IGNORECASE)
    if nm:
        hour = 12 if nm.group(1).lower() == "noon" else 0
        text = (text[:nm.start()] + text[nm.end():]).strip()
        candidate = datetime.combine(base_date, dtime(hour=hour, minute=0))
        if not matched_a_date and candidate < now:
            candidate += timedelta(days=1)
        return candidate, text

    # ---- "in N minutes / hours" ----
    rel = re.search(
        r"\bin\s+(\d+)\s*(min(?:ute)?s?|hr?s?|hours?)\b",
        text, re.IGNORECASE,
    )
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2).lower()
        delta = timedelta(hours=n) if unit.startswith("h") else timedelta(minutes=n)
        text = (text[:rel.start()] + text[rel.end():]).strip()
        return now + delta, text

    # ---- "at H[:MM][am|pm]" / "at H" ----
    at = re.search(
        r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b",
        text, re.IGNORECASE,
    )
    if at:
        hour = int(at.group(1))
        minute = int(at.group(2)) if at.group(2) else 0
        suffix = (at.group(3) or "").lower()
        if "p" in suffix and hour < 12:
            hour += 12
        elif "a" in suffix and hour == 12:
            hour = 0
        elif not suffix:
            # No am/pm. Heuristic: if it's <8 and we have no date keyword,
            # assume PM (people say "at 5" meaning 5pm). If we have a morning
            # keyword, leave AM.
            if "morning" not in word_lower and hour < 8:
                hour += 12
        text = (text[:at.start()] + text[at.end():]).strip()
        candidate = datetime.combine(base_date, dtime(hour=hour, minute=minute))
        # If the candidate is in the past for "today", bump to tomorrow.
        if not matched_a_date and candidate < now:
            candidate += timedelta(days=1)
        return candidate, text

    # ---- Date keyword without explicit time ----
    if matched_a_date:
        hour = default_hour if default_hour is not None else 9
        return datetime.combine(base_date, dtime(hour=hour, minute=0)), text

    return None, text


def _parse_reminder(text: str) -> Optional[Dict[str, Any]]:
    """Parse 'remind me to X at 5pm' into {'title': 'X', 'due': '...'}."""
    m = REMINDER_RE.match(text)
    if not m:
        return None
    body = m.group(1).strip().rstrip(".!?")
    due, title = _parse_natural_time(body)
    title = title.strip().rstrip(".!?,;:") or body
    payload: Dict[str, Any] = {"title": title}
    if due:
        payload["due"] = due.isoformat()
    return payload


def _parse_event(text: str) -> Optional[Dict[str, Any]]:
    """Parse 'schedule a meeting with X tomorrow at 3pm' into event payload."""
    m = EVENT_RE.match(text)
    if not m:
        return None
    body = m.group(0)
    # Extract event type (meeting/lunch/...)
    type_m = re.search(
        r"\b(meeting|event|appointment|call|lunch|dinner|coffee)\b",
        body, re.IGNORECASE,
    )
    event_type = type_m.group(1).title() if type_m else "Event"

    # Strip leading verb + article + type, keep the rest as title detail
    detail = re.sub(
        r"^\s*(?:please\s+)?(?:schedule|book|put|add|create)\s+(?:a\s+|an\s+)?"
        r"(?:meeting|event|appointment|call|lunch|dinner|coffee)\s*",
        "", body, flags=re.IGNORECASE,
    ).strip()

    start, leftover = _parse_natural_time(detail)
    leftover = leftover.strip().rstrip(".!?,;:")
    leftover = re.sub(r"^\s*(?:about|for|to discuss|to)\s+", "", leftover, flags=re.IGNORECASE)

    title = f"{event_type}"
    if leftover:
        title = f"{event_type}: {leftover}" if event_type.lower() not in leftover.lower() else leftover

    payload: Dict[str, Any] = {"title": title}
    if start:
        payload["start"] = start.isoformat()
        payload["end"] = (start + timedelta(hours=1)).isoformat()
    return payload


def _read_events_intent(text: str) -> Optional[Dict[str, Any]]:
    m = READ_EVENTS_RE.match(text)
    if not m:
        return None
    range_word = (m.group(1) or "today").lower().strip()
    if "tomorrow" in range_word:
        rng = "tomorrow"
    elif "week" in range_word:
        rng = "week"
    else:
        rng = "today"
    return {"range": rng}


def _read_reminders_intent(text: str) -> bool:
    return bool(READ_REMINDERS_RE.match(text))


# ---------------------------------------------------------------------------
# Mac system control: lock, sleep, volume, mute
# ---------------------------------------------------------------------------

LOCK_RE = re.compile(
    r"^\s*(?:please\s+)?(?:lock|secure)\s+(?:my\s+|the\s+)?(?:mac|imac|computer|screen|laptop)\s*[?.!]?\s*$",
    re.IGNORECASE,
)

SLEEP_RE = re.compile(
    r"^\s*(?:please\s+)?(?:put\s+)?(?:my\s+|the\s+)?(?:mac|imac|computer|laptop)?\s*"
    r"(?:to\s+)?sleep\s*(?:my\s+|the\s+)?(?:mac|imac|computer|laptop)?\s*[?.!]?\s*$",
    re.IGNORECASE,
)

# "wake my Mac", "open my Mac", "wake up the computer", "turn on my screen"
WAKE_MAC_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:wake\s+(?:up\s+)?(?:my\s+|the\s+)?(?:mac|imac|computer|desktop|screen|display)|"
    r"open\s+(?:up\s+)?(?:my\s+|the\s+)?(?:mac|imac|computer|desktop)|"
    r"turn\s+on\s+(?:my\s+|the\s+)?(?:mac|imac|computer|screen|monitor|display)|"
    r"wake\s+up)\s*[?.!]?\s*$",
    re.IGNORECASE,
)

# "stop locking my Mac", "disable the lock screen", "don't lock my Mac"
DISABLE_AUTOLOCK_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:stop\s+locking\s+(?:my\s+|the\s+)?(?:mac|imac|computer)|"
    r"disable\s+(?:the\s+|auto\s*[-\s]?)?lock\s*(?:screen)?|"
    r"don[’']?t\s+lock\s+(?:my\s+|the\s+)?(?:mac|imac|computer)|"
    r"turn\s+off\s+(?:the\s+|auto\s*[-\s]?)?lock\s*(?:screen)?)"
    r"\s*[?.!]?\s*$",
    re.IGNORECASE,
)

# "lock my Mac forever", "enable lock screen", "start locking my Mac"
ENABLE_AUTOLOCK_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:start\s+locking\s+(?:my\s+|the\s+)?(?:mac|imac|computer)|"
    r"enable\s+(?:the\s+|auto\s*[-\s]?)?lock\s*(?:screen)?|"
    r"turn\s+on\s+(?:the\s+|auto\s*[-\s]?)?lock\s*(?:screen)?|"
    r"lock\s+(?:my\s+|the\s+)?(?:mac|imac|computer)\s+forever)"
    r"\s*[?.!]?\s*$",
    re.IGNORECASE,
)

# "set volume to 30", "volume 50", "make it louder/quieter"
VOLUME_SET_RE = re.compile(
    r"^\s*(?:please\s+)?(?:set\s+(?:the\s+)?(?:mac\s+|computer\s+)?volume\s+to\s+|"
    r"volume\s+(?:to\s+)?|"
    r"turn\s+(?:the\s+)?volume\s+(?:to|up\s+to|down\s+to)\s+)"
    r"(\d{1,3})\s*[?.!%]?\s*$",
    re.IGNORECASE,
)

VOLUME_QUERY_RE = re.compile(
    r"^\s*(?:what(?:[’']?s|\s+is)?\s+(?:the\s+|my\s+)?(?:mac\s+|computer\s+)?volume|"
    r"how\s+loud\s+is\s+(?:my\s+|the\s+)?(?:mac|computer))\s*[?.!]?\s*$",
    re.IGNORECASE,
)

MUTE_RE = re.compile(
    r"^\s*(?:please\s+)?mute\s*(?:my\s+|the\s+)?(?:mac|imac|computer)?\s*[?.!]?\s*$",
    re.IGNORECASE,
)

UNMUTE_RE = re.compile(
    r"^\s*(?:please\s+)?unmute\s*(?:my\s+|the\s+)?(?:mac|imac|computer)?\s*[?.!]?\s*$",
    re.IGNORECASE,
)

LOUDER_RE = re.compile(
    r"^\s*(?:please\s+)?(?:turn\s+(?:it\s+|the\s+volume\s+)?up|"
    r"make\s+it\s+louder|volume\s+up|increase\s+(?:the\s+)?volume)\s*[?.!]?\s*$",
    re.IGNORECASE,
)

QUIETER_RE = re.compile(
    r"^\s*(?:please\s+)?(?:turn\s+(?:it\s+|the\s+volume\s+)?down|"
    r"make\s+it\s+quieter|volume\s+down|decrease\s+(?:the\s+)?volume|lower\s+(?:the\s+)?volume)\s*[?.!]?\s*$",
    re.IGNORECASE,
)


def _run_osascript(script: str, timeout: int = 5) -> Tuple[bool, str]:
    """Run an AppleScript snippet. Returns (ok, output_or_error)."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, (result.stderr or "").strip()
    except Exception as e:
        return False, str(e)


def _get_mac_volume() -> Optional[int]:
    ok, out = _run_osascript("output volume of (get volume settings)")
    if not ok:
        return None
    try:
        return int(out)
    except ValueError:
        return None


def _set_mac_volume(n: int) -> bool:
    n = max(0, min(100, n))
    ok, _ = _run_osascript(f"set volume output volume {n}")
    return ok


def _set_mac_mute(muted: bool) -> bool:
    ok, _ = _run_osascript(f"set volume output muted {'true' if muted else 'false'}")
    return ok


def _lock_mac() -> bool:
    # Cmd+Ctrl+Q triggers screen lock on macOS.
    ok, _ = _run_osascript(
        'tell application "System Events" to keystroke "q" using {control down, command down}'
    )
    return ok


def _sleep_mac() -> bool:
    try:
        result = subprocess.run(["pmset", "sleepnow"],
                                capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def _wake_mac() -> bool:
    """Send a 'user-active' assertion via caffeinate.
    Wakes the display from sleep without unlocking it."""
    try:
        # -u = user activity assertion (this is what wakes the display)
        # -t 5 = hold the assertion for 5 seconds
        # Run in background so we return immediately
        subprocess.Popen(
            ["caffeinate", "-u", "-t", "5"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def _set_autolock(enabled: bool) -> bool:
    """
    Toggle whether macOS asks for password after display sleep / screen saver.
    Disabling means "open my Mac" lands you straight at the desktop.

    Trade-off: anyone with physical access to the Mac while you're away can
    use it. Acceptable for a home iMac, dangerous in shared spaces.
    """
    try:
        ask = "1" if enabled else "0"
        delay = "0" if enabled else "0"
        subprocess.run(
            ["defaults", "write", "com.apple.screensaver", "askForPassword", "-int", ask],
            capture_output=True, text=True, timeout=5,
        )
        subprocess.run(
            ["defaults", "write", "com.apple.screensaver", "askForPasswordDelay", "-int", delay],
            capture_output=True, text=True, timeout=5,
        )
        # Restart cfprefsd so the change takes effect immediately
        subprocess.run(
            ["killall", "cfprefsd"],
            capture_output=True, text=True, timeout=5,
        )
        return True
    except Exception:
        return False


def _autolock_status() -> Optional[bool]:
    """Returns True if auto-lock is on, False if off, None if unknown."""
    try:
        r = subprocess.run(
            ["defaults", "read", "com.apple.screensaver", "askForPassword"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0:
            return r.stdout.strip() == "1"
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# iMessage send (Mac side, via AppleScript)
# ---------------------------------------------------------------------------

# "text Mom hi", "text Mom that I'll be late", "text dad: pizza tonight"
IMESSAGE_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:text|imessage|message|sms)\s+"
    r"(?:my\s+)?([A-Za-z][A-Za-z\s'\-\.]*?)"
    r"(?:\s+(?:that|saying|telling\s+(?:him|her|them)|with)\s+|\s*:\s*|\s+)"
    r"(.+?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)

# "send Sam a message saying ...", "send mom a text that ..."
IMESSAGE_LONG_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"send\s+(?:my\s+)?([A-Za-z][A-Za-z\s'\-\.]*?)\s+"
    r"(?:a\s+|an\s+)?(?:message|text|imessage)\s+"
    r"(?:that|saying|telling\s+(?:him|her|them))\s+"
    r"(.+?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)

# "send a message to Mom saying ..." (preposition-flipped variant)
IMESSAGE_TO_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"send\s+(?:a\s+|an\s+)?(?:message|text|imessage)\s+to\s+"
    r"(?:my\s+)?([A-Za-z][A-Za-z\s'\-\.]*?)"
    r"(?:\s+(?:that|saying|telling\s+(?:him|her|them))\s+|\s*:\s*)"
    r"(.+?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)


def _send_imessage(contact: str, body: str) -> Tuple[bool, str]:
    """Send via Messages.app. Tries iMessage first, falls back to SMS."""
    contact = contact.strip()
    body = body.strip()
    # Escape double quotes for AppleScript
    safe_body = body.replace("\\", "\\\\").replace('"', '\\"')
    safe_contact = contact.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
    tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        try
            set targetBuddy to buddy "{safe_contact}" of targetService
            send "{safe_body}" to targetBuddy
            return "ok"
        on error
            -- Try by partial name match against known buddies / contacts
            set candidates to (every buddy of targetService)
            repeat with b in candidates
                if name of b contains "{safe_contact}" then
                    send "{safe_body}" to b
                    return "ok"
                end if
            end repeat
            error "no_match"
        end try
    end tell
    '''
    ok, out = _run_osascript(script, timeout=8)
    if ok and "ok" in out:
        return True, contact
    return False, out


def _parse_imessage(text: str) -> Optional[Tuple[str, str]]:
    """Returns (contact, body) or None."""
    for regex in (IMESSAGE_LONG_RE, IMESSAGE_TO_RE, IMESSAGE_RE):
        m = regex.match(text)
        if m:
            return m.group(1).strip().rstrip("."), m.group(2).strip()
    return None


# ---------------------------------------------------------------------------
# Daily briefing
# ---------------------------------------------------------------------------

BRIEFING_RE = re.compile(
    r"^\s*(?:hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:good\s+morning|morning\s+briefing|daily\s+briefing|"
    r"morning\s+routine|brief\s+me|"
    r"what(?:[’']?s|\s+is)?\s+(?:my\s+|the\s+)?day\s+(?:looking\s+)?like|"
    r"how(?:[’']?s|\s+is)\s+(?:my\s+|the\s+)?day\s+looking|"
    r"what(?:[’']?s|\s+is)?\s+(?:on\s+)?(?:for\s+)?today)"
    r"\s*[?.!]?\s*$",
    re.IGNORECASE,
)


def _fetch_weather() -> Optional[str]:
    """One-line weather from wttr.in. No API key needed. Best-effort."""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://wttr.in/?format=%C+%t",
            headers={"User-Agent": "curl/8"},
        )
        with urllib.request.urlopen(req, timeout=4) as r:
            return r.read().decode().strip()
    except Exception:
        return None


def _fetch_news_headline() -> Optional[str]:
    """Top story title from BBC News RSS. No API key needed."""
    try:
        import urllib.request
        from xml.etree import ElementTree as ET
        req = urllib.request.Request(
            "https://feeds.bbci.co.uk/news/rss.xml",
            headers={"User-Agent": "curl/8"},
        )
        with urllib.request.urlopen(req, timeout=4) as r:
            data = r.read()
        root = ET.fromstring(data)
        # First <item><title> in the channel
        for item in root.iter("item"):
            title = item.find("title")
            if title is not None and title.text:
                return title.text.strip()
    except Exception:
        return None
    return None


# Curated rotation of practical / motivating one-liners. Local — no network.
_QUOTES = [
    "“Discipline equals freedom.” — Jocko Willink",
    "“The obstacle is the way.” — Marcus Aurelius",
    "“What gets measured gets managed.” — Peter Drucker",
    "“The best time to plant a tree was 20 years ago. The second best is now.”",
    "“Comparison is the thief of joy.” — Theodore Roosevelt",
    "“Slow is smooth, smooth is fast.” — Navy SEALs",
    "“You don't rise to the level of your goals; you fall to the level of your systems.” — James Clear",
    "“Make it work, make it right, make it fast.” — Kent Beck",
    "“Energy and persistence conquer all things.” — Benjamin Franklin",
    "“What you focus on grows.” — Robin Sharma",
    "“The cave you fear to enter holds the treasure you seek.” — Joseph Campbell",
    "“Done is better than perfect.” — Sheryl Sandberg",
    "“Mood follows action.” — Rich Roll",
    "“No one is coming to save you. Get to work.”",
    "“Hard choices, easy life. Easy choices, hard life.” — Jerzy Gregorek",
]


def _quote_of_the_day() -> str:
    """Deterministic-by-day rotation through the quote list."""
    idx = datetime.now().toordinal() % len(_QUOTES)
    return _QUOTES[idx]


# ---------------------------------------------------------------------------
# Groq client (OpenAI-API compatible, free tier)
#
# We use the openai package and just point it at Groq's base URL.
# Models are picked from env or sensible defaults; override per-deployment
# by setting GROQ_CHAT_MODEL / GROQ_VISION_MODEL in .env.
# ---------------------------------------------------------------------------

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# Llama 4 Scout is more reliable than 3.3-70b at OpenAI-format tool calls.
GROQ_CHAT_MODEL   = os.environ.get("GROQ_CHAT_MODEL",   "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")


_TOOL_BADGES = {
    "web_search":           "🔍 Searching the web",
    "find_files":           "📁 Searching files",
    "list_directory":       "📂 Reading folder",
    "get_weather":          "🌤 Checking the weather",
    "read_notes":           "📝 Reading your notes",
    "save_note":            "✍️ Saving a note",
    "get_persona":          "👤 Looking up your facts",
    "read_running_apps":    "🖥 Checking what you're using",
    "get_crypto_price":     "💰 Looking up crypto",
    "get_time":             "🕒 Getting the time",
    "calculate":            "🧮 Calculating",
    "convert_currency":     "💱 Converting currency",
    "get_news_headlines":   "📰 Fetching headlines",
    "define_word":          "📖 Looking up the word",
    "now_playing":          "🎵 Checking what's playing",
    "set_reminder":         "⏰ Setting a reminder",
    "start_timer":          "⏱ Starting a timer",
    "compose_message":      "✉️ Drafting a message",
    "create_calendar_event":"📅 Adding to your calendar",
}


def _friendly_tool_badge(tool_names) -> str:
    """Map raw tool names to a single short user-facing badge string."""
    pretty = []
    for n in tool_names:
        pretty.append(_TOOL_BADGES.get(n, f"⚙️ {n}"))
    if len(pretty) == 1:
        return pretty[0] + "…"
    return " + ".join(pretty) + "…"


def _parse_llama_tool_call(text: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """Extract a Llama-native tool call from a failed_generation string.
    Format:  <function=NAME {json_args}</function>"""
    m = re.search(r"<function=([A-Za-z_][\w]*)\s+(\{.*?\})\s*</function>", text, re.DOTALL)
    if not m:
        return None, {}
    name = m.group(1)
    try:
        import json as _j
        args = _j.loads(m.group(2))
    except Exception:
        args = {}
    return name, args


def _groq_client():
    """Return an OpenAI-style client configured for Groq."""
    from openai import OpenAI
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set — add it to ~/newt/.env")
    return OpenAI(api_key=key, base_url=GROQ_BASE_URL)


# ---------------------------------------------------------------------------
# Agentic tool loop — Newt can call these to gather info or take actions
# ---------------------------------------------------------------------------

AGENT_TOOLS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the web for current information via DuckDuckGo. Returns a short summary or related topics. Use for current events, prices, definitions, factual lookups.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        },
    }},
    {"type": "function", "function": {
        "name": "find_files",
        "description": "Search for files on Ethan's Mac by filename via Spotlight. Returns matching file paths.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Filename or keyword"}},
            "required": ["query"],
        },
    }},
    {"type": "function", "function": {
        "name": "list_directory",
        "description": "List the contents of a folder on Ethan's Mac. Common names: 'Downloads', 'Desktop', 'Documents'.",
        "parameters": {
            "type": "object",
            "properties": {"folder": {"type": "string"}},
            "required": ["folder"],
        },
    }},
    {"type": "function", "function": {
        "name": "get_weather",
        "description": "Get current local weather for Ethan's location (uses public IP geolocation).",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "read_notes",
        "description": "Read recent notes Ethan has captured to ~/newt/notes.md. Useful when he asks about ideas or things he's noted before.",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "How many recent notes (default 10)"}},
        },
    }},
    {"type": "function", "function": {
        "name": "save_note",
        "description": "Append a note to Ethan's notes file. Use sparingly — only when he explicitly asks to remember something note-worthy.",
        "parameters": {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    }},
    {"type": "function", "function": {
        "name": "get_persona",
        "description": "Get Ethan's persistent facts and preferred conversation tone. Use when context about Ethan would help your answer.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "read_running_apps",
        "description": "Get the name of the app Ethan currently has in focus on his Mac.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "get_crypto_price",
        "description": "Get the current USD price for a cryptocurrency. Pass the lowercase coin id like 'bitcoin', 'ethereum', 'solana', 'dogecoin'. Use this for real-time crypto prices instead of web_search.",
        "parameters": {
            "type": "object",
            "properties": {"coin": {"type": "string", "description": "Lowercase coin id (bitcoin, ethereum, etc.)"}},
            "required": ["coin"],
        },
    }},
    {"type": "function", "function": {
        "name": "get_time",
        "description": "Return the current local date and time.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "calculate",
        "description": "Evaluate a math expression like '30% of 1500', '2.5 * 8 + 3', 'sqrt(144)'. Use this for any arithmetic instead of guessing.",
        "parameters": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    }},
    {"type": "function", "function": {
        "name": "convert_currency",
        "description": "Convert an amount between currencies. Codes are 3-letter ISO (USD, EUR, AUD, GBP, JPY, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "number"},
                "from": {"type": "string", "description": "Source ISO currency code"},
                "to":   {"type": "string", "description": "Target ISO currency code"},
            },
            "required": ["amount", "from", "to"],
        },
    }},
    {"type": "function", "function": {
        "name": "get_news_headlines",
        "description": "Top news headlines from BBC. Returns up to N recent stories.",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "How many headlines (default 5)"}},
        },
    }},
    {"type": "function", "function": {
        "name": "define_word",
        "description": "Look up the definition of an English word.",
        "parameters": {
            "type": "object",
            "properties": {"word": {"type": "string"}},
            "required": ["word"],
        },
    }},
    {"type": "function", "function": {
        "name": "now_playing",
        "description": "What music is currently playing on Ethan's Mac (Spotify or Apple Music).",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "set_reminder",
        "description": "Create a reminder on Ethan's iPhone via the Reminders app. Use this when he asks to be reminded about something.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "What to be reminded about"},
                "due_iso": {"type": "string", "description": "Due time as ISO 8601 like 2026-05-07T17:00:00. Optional."},
            },
            "required": ["title"],
        },
    }},
    {"type": "function", "function": {
        "name": "start_timer",
        "description": "Start a timer on Ethan's iPhone that fires a notification when up.",
        "parameters": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "description": "Duration in seconds"},
                "label":   {"type": "string", "description": "Human-friendly duration like '10 minutes'"},
            },
            "required": ["seconds"],
        },
    }},
    {"type": "function", "function": {
        "name": "compose_message",
        "description": "Pre-fill an iMessage / SMS on Ethan's phone for a contact. Ethan will tap Send. Use for texting people.",
        "parameters": {
            "type": "object",
            "properties": {
                "recipient": {"type": "string", "description": "Contact name (e.g. 'Mom', 'Sam')"},
                "body":      {"type": "string", "description": "What the message should say"},
            },
            "required": ["recipient", "body"],
        },
    }},
    {"type": "function", "function": {
        "name": "create_calendar_event",
        "description": "Add an event to Ethan's iPhone calendar.",
        "parameters": {
            "type": "object",
            "properties": {
                "title":  {"type": "string"},
                "start":  {"type": "string", "description": "ISO 8601 start time"},
                "end":    {"type": "string", "description": "ISO 8601 end time. Optional — defaults to 1h after start."},
                "location": {"type": "string", "description": "Optional location"},
            },
            "required": ["title", "start"],
        },
    }},
]


def _agent_web_search(query: str) -> str:
    """Call DuckDuckGo's instant-answer API. Free, no key. Limited but useful."""
    import urllib.request, json as _json
    if not query.strip():
        return "Empty query."
    try:
        url = (f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}"
               f"&format=json&no_html=1&skip_disambig=1")
        req = urllib.request.Request(url, headers={"User-Agent": "newt"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = _json.loads(r.read().decode())
        bits = []
        if data.get("Answer"):       bits.append(f"Answer: {data['Answer']}")
        if data.get("AbstractText"): bits.append(f"Summary: {data['AbstractText']}")
        if data.get("AbstractURL"):  bits.append(f"Source: {data['AbstractURL']}")
        topics = data.get("RelatedTopics") or []
        for t in topics[:4]:
            if isinstance(t, dict) and t.get("Text"):
                bits.append(f"- {t['Text']}")
        return "\n".join(bits) if bits else f"No instant answer for {query!r}. Try rephrasing."
    except Exception as e:
        return f"Search error: {e}"


def _get_crypto_price(coin: str) -> str:
    """CoinGecko free API. No key needed."""
    import urllib.request, json as _json
    coin = coin.strip().lower().replace(" ", "-")
    if not coin:
        return "Specify a coin (e.g. 'bitcoin')."
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={urllib.parse.quote(coin)}&vs_currencies=usd&include_24hr_change=true"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "newt"}), timeout=6) as r:
            data = _json.loads(r.read().decode())
        if coin not in data:
            return f"No data for {coin!r}. Try the full coin id (e.g. 'bitcoin' not 'btc')."
        info = data[coin]
        price = info.get("usd")
        change = info.get("usd_24h_change")
        out = f"{coin}: ${price:,.2f} USD"
        if change is not None:
            sign = "+" if change >= 0 else ""
            out += f" ({sign}{change:.2f}% 24h)"
        return out
    except Exception as e:
        return f"CoinGecko error: {e}"


def _convert_currency(amount: float, from_code: str, to_code: str) -> str:
    """Free FX rates from open.er-api.com (no key, daily updates)."""
    import urllib.request, json as _json
    f = (from_code or "").strip().upper()
    t = (to_code or "").strip().upper()
    if not f or not t:
        return "Need both 'from' and 'to' currency codes."
    try:
        url = f"https://open.er-api.com/v6/latest/{f}"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "newt"}), timeout=6) as r:
            data = _json.loads(r.read().decode())
        if data.get("result") != "success":
            return f"FX lookup failed: {data.get('error-type', 'unknown')}"
        rate = data["rates"].get(t)
        if rate is None:
            return f"No rate for {t!r} from {f!r}."
        converted = amount * rate
        return f"{amount:,.2f} {f} ≈ {converted:,.2f} {t} (rate {rate:.4f})"
    except Exception as e:
        return f"Currency error: {e}"


def _get_news_headlines(limit: int = 5) -> str:
    """BBC RSS — same source as the daily briefing's top headline, but more."""
    import urllib.request
    from xml.etree import ElementTree as ET
    try:
        req = urllib.request.Request(
            "https://feeds.bbci.co.uk/news/rss.xml",
            headers={"User-Agent": "curl/8"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = r.read()
        root = ET.fromstring(data)
        titles = []
        for item in root.iter("item"):
            t = item.find("title")
            if t is not None and t.text:
                titles.append(t.text.strip())
            if len(titles) >= max(1, int(limit)):
                break
        if not titles:
            return "No headlines available."
        return "\n".join(f"- {h}" for h in titles)
    except Exception as e:
        return f"News error: {e}"


def _define_word(word: str) -> str:
    """Free dictionaryapi.dev — no key needed."""
    import urllib.request, json as _json
    word = (word or "").strip().lower()
    if not word:
        return "What word should I define?"
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "newt"}), timeout=5) as r:
            data = _json.loads(r.read().decode())
        if not isinstance(data, list) or not data:
            return f"No definition found for {word!r}."
        entry = data[0]
        out_lines = [f"**{entry.get('word', word)}**"]
        for meaning in (entry.get("meanings") or [])[:3]:
            pos = meaning.get("partOfSpeech", "")
            defs = meaning.get("definitions") or []
            for d in defs[:2]:
                text = d.get("definition", "").strip()
                if text:
                    out_lines.append(f"  ({pos}) {text}")
        return "\n".join(out_lines) if len(out_lines) > 1 else f"No definition for {word!r}."
    except Exception as e:
        return f"Dictionary error: {e}"


def _now_playing_mac() -> str:
    """Ask Spotify, then Apple Music, what's playing."""
    # Spotify first
    ok, out = _run_osascript('''
        tell application "System Events"
            if exists (process "Spotify") then
                tell application "Spotify"
                    if player state is playing then
                        return (artist of current track) & " — " & (name of current track) & " (Spotify)"
                    end if
                end tell
            end if
        end tell
        return ""
    ''', timeout=4)
    if ok and out and out.strip():
        return out.strip()

    # Apple Music
    ok, out = _run_osascript('''
        tell application "System Events"
            if exists (process "Music") then
                tell application "Music"
                    if player state is playing then
                        return (artist of current track) & " — " & (name of current track) & " (Apple Music)"
                    end if
                end tell
            end if
        end tell
        return ""
    ''', timeout=4)
    if ok and out and out.strip():
        return out.strip()

    return "Nothing playing on Mac right now."


def _safe_eval_math(expr: str) -> str:
    """Tiny safe-ish math evaluator. Allows numbers, basic ops, and a few funcs."""
    import math
    expr = expr.strip()
    if not expr:
        return "Empty expression."
    # Translate human-friendly forms
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)",
                  r"(\1/100)*\2", expr, flags=re.IGNORECASE)
    expr = expr.replace("^", "**").replace("×", "*").replace("÷", "/")
    allowed_names = {"sqrt": math.sqrt, "pi": math.pi, "e": math.e,
                     "log": math.log, "ln": math.log, "sin": math.sin,
                     "cos": math.cos, "tan": math.tan, "abs": abs,
                     "round": round, "min": min, "max": max, "pow": pow}
    # Reject obvious unsafe constructs
    if re.search(r"[A-Za-z_][A-Za-z0-9_]*", expr):
        # only allow names from allowed set
        for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr):
            if name not in allowed_names:
                return f"Unknown name: {name}"
    if any(bad in expr for bad in ("import", "__", "open(", "exec", "eval", ";", "lambda")):
        return "Refused (unsafe expression)."
    try:
        result = eval(expr, {"__builtins__": {}}, allowed_names)
        return f"{expr} = {result}"
    except Exception as e:
        return f"Math error: {e}"


def _read_recent_notes(limit: int = 10) -> str:
    p = Path(NOTES_FILE)
    if not p.exists():
        return "No notes saved yet."
    try:
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        recent = lines[-max(1, int(limit)):]
        return "\n".join(recent) if recent else "No notes."
    except Exception as e:
        return f"Couldn't read notes: {e}"


def _execute_agent_tool(name: str, args: dict) -> str:
    """Run a tool and return its result as a string for the LLM to read."""
    try:
        if name == "web_search":
            return _agent_web_search(str(args.get("query", "")))
        if name == "find_files":
            return _find_files(str(args.get("query", "")))
        if name == "list_directory":
            folder = str(args.get("folder", ""))
            target = _resolve_dir_alias(folder) or _safe_path(folder)
            if target is None or not target.exists():
                return f"Folder not found: {folder!r}"
            text, _ = _list_dir(target)
            return text
        if name == "get_weather":
            return _fetch_weather() or "Weather unavailable."
        if name == "read_notes":
            return _read_recent_notes(int(args.get("limit", 10)))
        if name == "save_note":
            content = str(args.get("content", "")).strip()
            if not content:
                return "Empty note — nothing to save."
            return "Note saved." if _save_note(content) else "Failed to save note."
        if name == "get_persona":
            p = _read_persona()
            return (f"Tone: {p.get('tone', 'warm')}\n"
                    f"Facts: {p.get('facts', []) or '(none)'}")
        if name == "read_running_apps":
            return _frontmost_app() or "Couldn't read frontmost app."
        if name == "get_crypto_price":
            return _get_crypto_price(str(args.get("coin", "")))
        if name == "get_time":
            return datetime.now().strftime("%A, %B %-d, %Y at %-I:%M %p")
        if name == "calculate":
            return _safe_eval_math(str(args.get("expression", "")))
        if name == "convert_currency":
            return _convert_currency(
                float(args.get("amount", 0)),
                str(args.get("from", "")),
                str(args.get("to", "")),
            )
        if name == "get_news_headlines":
            return _get_news_headlines(int(args.get("limit", 5)))
        if name == "define_word":
            return _define_word(str(args.get("word", "")))
        if name == "now_playing":
            return _now_playing_mac()

        # ---- Action tools — return dict with both 'text' and 'action' ----
        if name == "set_reminder":
            title = str(args.get("title", "")).strip()
            due   = args.get("due_iso")
            if not title:
                return "Need a title for the reminder."
            payload = {"title": title}
            if isinstance(due, str) and due.strip():
                payload["due"] = due.strip()
            return {
                "text": f"Reminder queued: {title!r}" + (f" at {due}" if due else ""),
                "action": {"create_reminder": payload},
            }

        if name == "start_timer":
            try:
                seconds = int(args.get("seconds", 0))
            except Exception:
                seconds = 0
            label = str(args.get("label", f"{seconds} seconds")).strip()
            if seconds <= 0:
                return "Need a positive duration."
            return {
                "text": f"Timer queued for {label}.",
                "action": {"start_timer": {"seconds": seconds, "label": label}},
            }

        if name == "compose_message":
            recipient = str(args.get("recipient", "")).strip()
            body      = str(args.get("body", "")).strip()
            if not recipient or not body:
                return "Need both recipient and body."
            return {
                "text": f"Message draft to {recipient}: {body!r}",
                "action": {"compose_sms": {"recipient": recipient, "body": body}},
            }

        if name == "create_calendar_event":
            title = str(args.get("title", "")).strip()
            start = args.get("start")
            end   = args.get("end")
            location = args.get("location")
            if not title or not isinstance(start, str) or not start.strip():
                return "Need title and start time."
            payload = {"title": title, "start": start}
            if isinstance(end, str) and end.strip():       payload["end"] = end
            if isinstance(location, str) and location.strip(): payload["location"] = location
            return {
                "text": f"Event queued: {title!r} at {start}.",
                "action": {"create_event": payload},
            }
    except Exception as e:
        return f"Error executing {name}: {e}"
    return f"Unknown tool: {name}"


# ---------------------------------------------------------------------------
# Web search — returns a search URL action (opens DuckDuckGo on the phone)
# ---------------------------------------------------------------------------

WEB_SEARCH_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:search\s+(?:the\s+)?web\s+for\s+|"
    r"google\s+|"
    r"duck\s*duck\s*go\s+|"
    r"look\s+up\s+|"
    r"search\s+for\s+(?!(?:files?|documents?|my\s+files)\b)|"   # skip file searches
    r"web\s+search\s+(?:for\s+)?)"
    r"(.+?)\s*[?.!]?\s*$",
    re.IGNORECASE,
)


def _web_search_url(query: str) -> str:
    """Build a DuckDuckGo search URL for the given query."""
    return f"https://duckduckgo.com/?q={urllib.parse.quote(query.strip())}"


# ---------------------------------------------------------------------------
# Persona + "Newt remembers you"
# Stored in ~/newt/persona.json so it survives bridge restarts. The bridge
# can read this file and prepend it to system prompts on every chat call.
# ---------------------------------------------------------------------------

PERSONA_FILE = Path.home() / "newt" / "persona.json"


def _read_persona() -> Dict[str, Any]:
    """Returns the persona dict (creates a default if missing)."""
    if not PERSONA_FILE.exists():
        return {"tone": "warm", "facts": []}
    try:
        import json
        return json.loads(PERSONA_FILE.read_text())
    except Exception:
        return {"tone": "warm", "facts": []}


def _write_persona(data: Dict[str, Any]) -> bool:
    try:
        import json
        PERSONA_FILE.parent.mkdir(parents=True, exist_ok=True)
        PERSONA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return True
    except Exception as e:
        print(f"[newt] persona save failed: {e}")
        return False


def system_prompt_prefix() -> str:
    """
    Returns a string the bridge can prepend to its system prompt to give
    Newt a persistent persona + remembered facts about the user.
    """
    p = _read_persona()
    parts = []

    tone = p.get("tone", "").strip()
    if tone:
        tone_descriptions = {
            "warm":   "Speak in a warm, encouraging tone. Brief but kind.",
            "terse":  "Be very concise. Skip pleasantries. Answer in as few words as possible.",
            "witty":  "Have a dry sense of humour. Light wit, never forced. Still useful.",
            "formal": "Speak formally and precisely. No contractions, no slang.",
            "playful":"Be playful and a little cheeky. Friendly, never sarcastic.",
        }
        parts.append(tone_descriptions.get(tone, f"Tone: {tone}."))

    facts = p.get("facts", [])
    if facts:
        bullet = "\n".join(f"- {f}" for f in facts if f)
        parts.append(f"Things you know about Ethan:\n{bullet}")

    if not parts:
        return ""
    return "\n\n".join(parts) + "\n\n"


# ---------------------------------------------------------------------------
# Voice intents to manage persona + facts
# ---------------------------------------------------------------------------

# "remember that I live in Geelong" / "remember I prefer dark mode"
REMEMBER_FACT_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:remember\s+(?:that\s+)?|note\s+that\s+|keep\s+in\s+mind\s+(?:that\s+)?)"
    r"(?!to\s+)"   # skip "remember to X" — that's a reminder, not a fact
    r"(.+?)\s*[?.!]?\s*$",
    re.IGNORECASE,
)

# "what do you know about me", "what do you remember"
LIST_FACTS_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:what\s+do\s+you\s+(?:know\s+about\s+me|remember(?:\s+about\s+me)?)|"
    r"list\s+(?:my\s+)?facts|"
    r"what(?:[’']?s|\s+is)\s+in\s+your\s+memory)"
    r"\s*[?.!]?\s*$",
    re.IGNORECASE,
)

# "forget X" / "forget that I X"
FORGET_FACT_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"forget\s+(?:that\s+)?(.+?)\s*[?.!]?\s*$",
    re.IGNORECASE,
)

# "be more terse" / "be warmer" / "use a witty tone"
SET_TONE_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:be\s+(?:more\s+)?(warm|terse|witty|formal|playful)(?:\s+tone)?|"
    r"use\s+a?\s*(warm|terse|witty|formal|playful)\s+tone|"
    r"set\s+(?:your\s+)?tone\s+to\s+(warm|terse|witty|formal|playful))"
    r"\s*[?.!]?\s*$",
    re.IGNORECASE,
)


# Translation: "translate X to Y" is handled natively by the LLM, so we
# don't intercept it here.


# ---------------------------------------------------------------------------
# Mac file & screen access
# ---------------------------------------------------------------------------

import os
from pathlib import Path

HOME = Path.home()

# Friendly aliases — user says "Downloads", we know what they mean.
COMMON_DIRS: Dict[str, Path] = {
    "downloads":   HOME / "Downloads",
    "desktop":     HOME / "Desktop",
    "documents":   HOME / "Documents",
    "movies":      HOME / "Movies",
    "music":       HOME / "Music",
    "pictures":    HOME / "Pictures",
    "screenshots": HOME / "Desktop",   # macOS default is Desktop
    "applications":Path("/Applications"),
    "home":        HOME,
}


def _safe_path(p: str) -> Optional[Path]:
    """Resolve a user-supplied path. Restrict to user home + /Applications."""
    try:
        path = Path(os.path.expanduser(p)).resolve()
    except Exception:
        return None
    # Allow paths under HOME or /Applications. Reject /etc, /System, /Library, etc.
    try:
        path.relative_to(HOME)
        return path
    except ValueError:
        pass
    try:
        path.relative_to(Path("/Applications"))
        return path
    except ValueError:
        return None


def _resolve_dir_alias(name: str) -> Optional[Path]:
    """Map 'downloads' / 'my desktop' / etc. to a real Path."""
    key = name.strip().lower().rstrip("s") + "s"
    key = re.sub(r"^(?:my\s+|the\s+)", "", name.strip().lower())
    if key in COMMON_DIRS:
        return COMMON_DIRS[key]
    # Try plural/singular variants
    if key + "s" in COMMON_DIRS:
        return COMMON_DIRS[key + "s"]
    return None


def _list_dir(path: Path, limit: int = 12) -> Tuple[str, int]:
    """List human-friendly contents of a directory. Returns (text, count)."""
    if not path.exists():
        return f"{path.name} doesn't exist.", 0
    if not path.is_dir():
        return f"{path.name} isn't a folder.", 0

    try:
        entries = sorted(
            path.iterdir(),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except PermissionError:
        return f"Can't read {path.name} — permission denied.", 0

    # Skip hidden files
    entries = [e for e in entries if not e.name.startswith(".")]
    total = len(entries)

    if total == 0:
        return f"{path.name} is empty.", 0

    shown = entries[:limit]
    lines = [f"📂 {path.name} ({total} item{'s' if total != 1 else ''}):"]
    for e in shown:
        icon = "📁" if e.is_dir() else "📄"
        lines.append(f"  {icon} {e.name}")
    if total > limit:
        lines.append(f"  …and {total - limit} more")
    return "\n".join(lines), total


def _find_files(query: str, limit: int = 10) -> str:
    """Spotlight search via mdfind. Filename matches first; falls back to
    content matches. Skips system/cache dirs that are noise."""
    query = query.strip().rstrip(".!?,;:")
    if not query:
        return "What should I search for?"

    # Directories where matches are almost always noise (browser caches, etc.)
    EXCLUDE_PREFIXES = (
        str(HOME / "Library"),
        str(HOME / ".cache"),
        str(HOME / ".Trash"),
        str(HOME / ".cocoapods"),
        str(HOME / "Library/Application Support"),
    )

    def keep(path: str) -> bool:
        return not any(path.startswith(p) for p in EXCLUDE_PREFIXES)

    def run_mdfind(args):
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=8)
            return [p for p in r.stdout.splitlines() if p.strip() and keep(p)]
        except Exception:
            return []

    # 1) Filename match — highest signal
    name_hits = run_mdfind([
        "mdfind", "-onlyin", str(HOME),
        f"kMDItemDisplayName == '*{query}*'cd",
    ])

    # 2) Fall back to content if no filename hits
    paths = name_hits if name_hits else run_mdfind([
        "mdfind", "-onlyin", str(HOME), query,
    ])

    if not paths:
        return f"No files found for {query!r}."

    # Sort newest first
    def mtime(p):
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0
    paths.sort(key=mtime, reverse=True)

    where = "by name" if name_hits else "by content"
    lines = [f"🔍 {len(paths)} match{'es' if len(paths) != 1 else ''} ({where}) for {query!r}:"]
    for p in paths[:limit]:
        path_obj = Path(p)
        rel = path_obj.relative_to(HOME) if path_obj.is_relative_to(HOME) else path_obj
        icon = "📁" if path_obj.is_dir() else "📄"
        lines.append(f"  {icon} ~/{rel}")
    if len(paths) > limit:
        lines.append(f"  …and {len(paths) - limit} more")
    return "\n".join(lines)


def _take_screenshot(out_path: Path) -> bool:
    """Capture full screen. Tries:
       1. A user-created macOS Shortcut named "Newt Screenshot"
          (most reliable — Shortcuts.app has Screen Recording perm baked in)
       2. Direct `screencapture` (works only if the bridge process itself
          has Screen Recording TCC perm — often denied for launchd-launched
          processes even when toggled on)
    """
    # Path the Shortcut writes to (or that screencapture writes to)
    SHORTCUT_OUTPUT = Path.home() / "newt" / "screen.png"

    # ---- Attempt 1: macOS Shortcut --------------------------------------
    try:
        # Best-effort cleanup of stale file so we know the Shortcut produced
        # a fresh one
        if SHORTCUT_OUTPUT.exists():
            try:
                SHORTCUT_OUTPUT.unlink()
            except Exception:
                pass

        result = subprocess.run(
            ["shortcuts", "run", "Newt Screenshot"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and SHORTCUT_OUTPUT.exists() and SHORTCUT_OUTPUT.stat().st_size > 1000:
            import shutil
            shutil.copy(SHORTCUT_OUTPUT, out_path)
            return True
    except Exception as e:
        print(f"[newt] Shortcut path failed: {e}")

    # ---- Attempt 2: direct screencapture --------------------------------
    try:
        result = subprocess.run(
            ["screencapture", "-x", str(out_path)],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1000:
            return True
    except Exception as e:
        print(f"[newt] screencapture failed: {e}")

    return False


def _frontmost_app() -> Optional[str]:
    """Returns the name of the foreground app on Mac, e.g. 'Safari'."""
    ok, out = _run_osascript(
        'tell application "System Events" to name of first process whose frontmost is true'
    )
    return out if ok else None


# ---------------------------------------------------------------------------
# Intent regexes for files & screen
# ---------------------------------------------------------------------------

SCREENSHOT_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:take\s+(?:a\s+)?screenshot|screenshot|"
    r"what(?:[’']?s|\s+is)?\s+on\s+(?:my\s+|the\s+)?screen|"
    r"show\s+(?:me\s+)?(?:my\s+|the\s+)?screen|"
    r"what(?:\s+am\s+i|[’']?m\s+i)\s+(?:looking\s+at|working\s+on)|"
    r"see\s+my\s+screen|capture\s+(?:my\s+)?screen)"
    r"\s*[?.!]?\s*$",
    re.IGNORECASE,
)

LIST_DIR_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:what(?:[’']?s|\s+is)?\s+in\s+(?:my\s+|the\s+)?(.+?)|"
    r"list\s+(?:my\s+|the\s+)?(.+?)|"
    r"show\s+(?:me\s+)?(?:my\s+|the\s+)?(.+?)\s+(?:folder|files))"
    r"\s*[?.!]?\s*$",
    re.IGNORECASE,
)

FIND_FILES_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:find\s+(?:files?|documents?)\s+(?:about\s+|with\s+|named\s+|called\s+|matching\s+|for\s+)?|"
    r"search\s+(?:my\s+)?(?:files|mac|computer)\s*(?:for\s+)?|"   # explicit file context required
    r"search\s+for\s+(?:files?|documents?)\s+(?:about\s+|with\s+|named\s+|called\s+)?|"
    r"look\s+for\s+(?:files?|documents?)\s+(?:about\s+|with\s+|named\s+|called\s+)?)"
    r"(.+?)\s*[?.!]?\s*$",
    re.IGNORECASE,
)

# "send me [the] X file from desktop", "open my latest screenshot"
SEND_FILE_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:send\s+me\s+(?:the\s+|my\s+)?|"
    r"grab\s+(?:me\s+)?(?:the\s+|my\s+)?|"
    r"give\s+me\s+(?:the\s+|my\s+)?)"
    r"(.+?)\s*[?.!]?\s*$",
    re.IGNORECASE,
)


def _newt_host() -> str:
    """The base URL Newt is reachable at — used to build action open_urls."""
    # Tailscale MagicDNS by default; override with NEWT_PUBLIC_URL env.
    return os.environ.get("NEWT_PUBLIC_URL", "http://newt:8001")


# ---------------------------------------------------------------------------
# Flask route registration — call from newt_bridge.py after app = Flask(...)
# ---------------------------------------------------------------------------

def register_routes(app):
    """
    Add Newt's HTTP endpoints to the existing Flask app.
    Idempotent — safe to call multiple times during dev reloads.

    Endpoints registered:
      GET  /screenshot         — capture and return Mac screen as PNG
      GET  /file?path=...      — serve a file from user home
      POST /upload             — receive a file from phone, save to ~/newt/inbox/
      POST /vision             — describe a photo via OpenAI vision
      GET  /persona            — return the current persona JSON
      POST /persona            — overwrite the persona JSON
    """
    from flask import send_file, abort, request as _req, jsonify as _jsonify
    import tempfile, json, base64

    if "newt_screenshot" in app.view_functions:
        return  # already registered

    @app.route("/screenshot", methods=["GET"], endpoint="newt_screenshot")
    def _newt_screenshot():
        out = Path(tempfile.gettempdir()) / "newt-screen.png"
        if not _take_screenshot(out):
            abort(500, "screencapture failed — give the bridge Screen Recording permission")
        return send_file(str(out), mimetype="image/png", max_age=0)

    @app.route("/file", methods=["GET"], endpoint="newt_file")
    def _newt_file():
        p = _req.args.get("path", "")
        path = _safe_path(p)
        if not path or not path.exists() or not path.is_file():
            abort(404)
        return send_file(str(path), as_attachment=False, max_age=0)

    # --- POST /upload — phone sends a file, Mac saves it ------------------
    @app.route("/upload", methods=["POST"], endpoint="newt_upload")
    def _newt_upload():
        if "file" not in _req.files:
            return _jsonify({"error": "no file in request"}), 400
        f = _req.files["file"]
        # Sanitize filename — strip path components
        name = os.path.basename(f.filename or "upload")
        if not name:
            name = f"newt-{int(datetime.now().timestamp())}"
        inbox = Path.home() / "newt" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        # If a file with that name exists, add a suffix
        target = inbox / name
        i = 1
        while target.exists():
            stem, dot, ext = name.rpartition(".")
            if dot:
                target = inbox / f"{stem}-{i}.{ext}"
            else:
                target = inbox / f"{name}-{i}"
            i += 1
        f.save(str(target))
        return _jsonify({
            "ok": True,
            "saved_to": str(target),
            "size": target.stat().st_size,
        })

    # --- POST /vision — describe an image via Groq's vision model --------
    @app.route("/vision", methods=["POST"], endpoint="newt_vision")
    def _newt_vision():
        if "file" not in _req.files:
            return _jsonify({"error": "no file in request"}), 400
        f = _req.files["file"]
        prompt = _req.form.get("prompt") or "What's in this image? Be concise."

        # Read image bytes and base64-encode for the API
        img_bytes = f.read()
        b64 = base64.b64encode(img_bytes).decode("ascii")
        mime = f.mimetype or "image/jpeg"

        try:
            client = _groq_client()
            resp = client.chat.completions.create(
                model=GROQ_VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url",
                             "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        ],
                    },
                ],
                max_tokens=400,
            )
            answer = resp.choices[0].message.content or "(no description)"
            return _jsonify({"reply": answer.strip()})
        except Exception as e:
            return _jsonify({"error": f"vision call failed: {e}"}), 500

    # --- POST /chat/stream — Server-Sent Events streaming chat -----------
    # Routes intent matches to a single chunk; otherwise streams from OpenAI.
    @app.route("/chat/stream", methods=["POST"], endpoint="newt_chat_stream")
    def _newt_chat_stream():
        from flask import Response, stream_with_context
        import json as _json

        data = _req.get_json(silent=True) or {}
        text = (data.get("prompt") or data.get("message") or data.get("text") or "").strip()
        if not text:
            return _jsonify({"error": "no prompt"}), 400

        # If an intent matches, deliver the reply as one chunk + done.
        intent = handle_message(text)
        if intent is not None:
            def gen_intent():
                payload = _json.dumps({
                    "chunk": intent.get("reply", ""),
                    "action": intent.get("action"),
                })
                yield f"data: {payload}\n\n"
                yield "data: [DONE]\n\n"
            return Response(stream_with_context(gen_intent()),
                            mimetype="text/event-stream",
                            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})

        # Otherwise stream from Groq.
        persona = system_prompt_prefix().strip()
        sys_prompt = persona if persona else \
            "You are Newt, Ethan's voice assistant. Be concise, warm, and useful."

        # Conversation context — phone passes the last N turns so Newt can
        # answer follow-ups like "what about tomorrow" after "what's on
        # my calendar today".
        history_in = data.get("history", [])
        prior_messages = []
        if isinstance(history_in, list):
            for h in history_in[-12:]:   # keep it bounded
                if not isinstance(h, dict):
                    continue
                role = h.get("role")
                content = h.get("content")
                if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                    prior_messages.append({"role": role, "content": content})

        def gen_llm():
            """Agentic chat with Groq.
            Strategy: non-streaming tool-using turns (more reliable on Groq's
            Llama models), then chunk the final text reply for streaming-feel.
            """
            messages = [
                {"role": "system", "content": sys_prompt},
                *prior_messages,
                {"role": "user",   "content": text},
            ]
            client = _groq_client()

            def _stream_text(s):
                """Break a final text reply into ~25-char chunks so the iOS
                bubble grows visibly even though the call wasn't streamed."""
                if not s:
                    return
                step = 25
                for i in range(0, len(s), step):
                    yield f"data: {_json.dumps({'chunk': s[i:i+step]})}\n\n"

            try:
                for iteration in range(5):
                    # Non-streaming so we can reliably parse tool calls
                    kwargs = dict(
                        model=GROQ_CHAT_MODEL,
                        messages=messages,
                        max_tokens=700,
                    )
                    if iteration < 4:
                        kwargs["tools"] = AGENT_TOOLS
                        kwargs["parallel_tool_calls"] = False  # one tool at a time = more reliable

                    try:
                        response = client.chat.completions.create(**kwargs)
                        msg = response.choices[0].message
                        tool_calls = getattr(msg, "tool_calls", None) or []
                    except Exception as api_err:
                        # Groq sometimes generates Llama-native tool format that its
                        # OpenAI-shim parser rejects. We can recover the tool call
                        # from the error message and continue.
                        err_str = str(api_err)
                        if "tool_use_failed" in err_str or "failed_generation" in err_str:
                            name, args = _parse_llama_tool_call(err_str)
                            if name:
                                badge = _friendly_tool_badge([name])
                                yield f"data: {_json.dumps({'tool': badge})}\n\n"
                                result = _execute_agent_tool(name, args)

                                if isinstance(result, dict):
                                    if result.get("action"):
                                        yield f"data: {_json.dumps({'action': result['action']})}\n\n"
                                    text_result = str(result.get("text", ""))[:4000]
                                else:
                                    text_result = str(result)[:4000]

                                fake_id = f"call_recover_{iteration}"
                                messages.append({
                                    "role": "assistant",
                                    "content": "",
                                    "tool_calls": [{
                                        "id": fake_id,
                                        "type": "function",
                                        "function": {
                                            "name": name,
                                            "arguments": _json.dumps(args),
                                        },
                                    }],
                                })
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": fake_id,
                                    "content": text_result,
                                })
                                continue  # try the next iteration with the result
                        # Other errors — bubble up
                        raise

                    if not tool_calls:
                        # Final reply — chunk-stream it back to the client
                        yield from _stream_text(msg.content or "")
                        break

                    # Tools were requested — show a friendly progress badge
                    names = [tc.function.name for tc in tool_calls]
                    badge = _friendly_tool_badge(names)
                    # Send as a separate field so iOS can render it differently
                    # from regular text chunks.
                    yield f"data: {_json.dumps({'tool': badge})}\n\n"

                    # Append the assistant turn (must include tool_calls verbatim)
                    messages.append({
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments or "{}",
                                },
                            }
                            for tc in tool_calls
                        ],
                    })

                    # Execute each tool and append its result
                    for tc in tool_calls:
                        try:
                            args = _json.loads(tc.function.arguments) if tc.function.arguments else {}
                        except Exception:
                            args = {}
                        result = _execute_agent_tool(tc.function.name, args)

                        # Action-emitting tools return a dict; forward the
                        # action to iOS via the SSE stream and feed the text
                        # back to the LLM as the tool result.
                        if isinstance(result, dict):
                            if result.get("action"):
                                yield f"data: {_json.dumps({'action': result['action']})}\n\n"
                            text_result = str(result.get("text", ""))[:4000]
                        else:
                            text_result = str(result)[:4000]

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": text_result,
                        })

                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {_json.dumps({'error': str(e)})}\n\n"
                yield "data: [DONE]\n\n"

        return Response(stream_with_context(gen_llm()),
                        mimetype="text/event-stream",
                        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})

    # --- GET / POST /persona — read or update the persona JSON -----------
    @app.route("/persona", methods=["GET"], endpoint="newt_persona_get")
    def _newt_persona_get():
        return _jsonify(_read_persona())

    @app.route("/persona", methods=["POST"], endpoint="newt_persona_set")
    def _newt_persona_set():
        try:
            data = _req.get_json(silent=True) or {}
            current = _read_persona()
            # Allowed top-level keys
            if "tone" in data and isinstance(data["tone"], str):
                current["tone"] = data["tone"].strip().lower()
            if "facts" in data and isinstance(data["facts"], list):
                current["facts"] = [str(f).strip() for f in data["facts"] if str(f).strip()]
            if _write_persona(current):
                return _jsonify({"ok": True, **current})
            return _jsonify({"error": "save failed"}), 500
        except Exception as e:
            return _jsonify({"error": str(e)}), 400


# ---------------------------------------------------------------------------
# Quick capture — "note: X" or "remember X"
# ---------------------------------------------------------------------------

NOTES_FILE = subprocess.run(
    ["bash", "-lc", "echo $HOME/newt/notes.md"],
    capture_output=True, text=True,
).stdout.strip() or "/tmp/newt-notes.md"

# "note: idea X", "jot down ...", "remember the milk" (without "to" — "remember to"
# is handled by the reminder parser, since the user clearly wants a real iOS reminder).
NOTE_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:note|jot\s+(?:this\s+)?down|capture\s+(?:this)?|write\s+down|"
    r"save\s+(?:this|that)|remember(?!\s+to\s)(?:\s+that)?)"
    r"\s*[:\-,]?\s*"
    r"(.+?)\s*$",
    re.IGNORECASE,
)


def _save_note(text: str) -> bool:
    try:
        from pathlib import Path
        path = Path(NOTES_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"- [{stamp}] {text.strip()}\n")
        return True
    except Exception as e:
        print(f"[newt] note save failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Timers — "set a timer for 10 minutes"
# ---------------------------------------------------------------------------

# Kicks the iOS Clock app via Shortcuts URL scheme so a real iOS timer fires
# (audible alarm even when Newt is closed).
TIMER_RE = re.compile(
    r"^\s*(?:please\s+|hey\s+newt[,\s]+|newt[,\s]+)?"
    r"(?:set\s+(?:a|an)\s+timer\s+for|start\s+(?:a|an)\s+timer\s+for|timer\s+for)\s+"
    r"(\d+(?:\.\d+)?)\s*"
    r"(seconds?|secs?|minutes?|mins?|hours?|hrs?)\s*[?.!]?\s*$",
    re.IGNORECASE,
)


def _parse_timer(text: str) -> Optional[Tuple[int, str]]:
    """Returns (total_seconds, label) or None."""
    m = TIMER_RE.match(text)
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("h"):
        return int(n * 3600), f"{n:g} hour{'s' if n != 1 else ''}"
    if unit.startswith("m"):
        return int(n * 60), f"{n:g} minute{'s' if n != 1 else ''}"
    return int(n), f"{n:g} second{'s' if n != 1 else ''}"


# ---------------------------------------------------------------------------
# Music control — next/previous/like (iOS Music + Spotify use mediaremote
# events; we use shortcuts:// URL with built-in actions on iPhone).
# ---------------------------------------------------------------------------

MUSIC_NEXT_RE = re.compile(
    r"^\s*(?:please\s+)?(?:next|skip)\s+(?:song|track)?\s*[?.!]?\s*$",
    re.IGNORECASE,
)
MUSIC_PREV_RE = re.compile(
    r"^\s*(?:please\s+)?(?:previous|prev|last)\s+(?:song|track)\s*[?.!]?\s*$"
    r"|^\s*(?:please\s+)?go\s+back\s+(?:a\s+)?song\s*[?.!]?\s*$",
    re.IGNORECASE,
)
MUSIC_PAUSE_RE = re.compile(
    r"^\s*(?:please\s+)?(?:pause|stop)\s+(?:the\s+)?(?:music|song|playback)?\s*[?.!]?\s*$",
    re.IGNORECASE,
)
MUSIC_PLAY_RE = re.compile(
    r"^\s*(?:please\s+)?(?:resume|play|unpause)\s+(?:the\s+)?(?:music|song|playback)?\s*[?.!]?\s*$",
    re.IGNORECASE,
)
MUSIC_LIKE_RE = re.compile(
    r"^\s*(?:please\s+)?(?:like|favorite|heart|love)\s+(?:this|the)?\s*(?:song|track)?\s*[?.!]?\s*$",
    re.IGNORECASE,
)


def _music_command_mac(verb: str) -> Tuple[bool, str]:
    """
    Run a media command against whatever player is active on the Mac.
    Tries Spotify first, then Music. Returns (ok, app_name_used).
    """
    verb_map = {
        "next":     "next track",
        "previous": "previous track",
        "pause":    "pause",
        "play":     "play",
    }
    cmd = verb_map.get(verb)
    if not cmd:
        return False, ""
    for app in ("Spotify", "Music"):
        ok, _ = _run_osascript(f'tell application "{app}" to {cmd}', timeout=3)
        if ok:
            return True, app
    return False, ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def handle_message(text: str, *, default_target: str = "ios") -> Optional[Dict[str, Any]]:
    """Try to handle an app-launch / shortcut / calendar / reminders /
    Mac control / iMessage / briefing intent. Returns None if not an intent
    (let the LLM handle it), else a dict with at least 'reply' and
    optionally 'action'."""
    if not text or not isinstance(text, str):
        return None

    cleaned = text.strip()

    # --- Screen capture -----------------------------------------------------
    if SCREENSHOT_RE.match(cleaned):
        front = _frontmost_app()
        front_line = f" You're in {front}." if front else ""
        return {
            "reply": f"Here's your screen.{front_line}",
            "action": {"open_url": f"{_newt_host()}/screenshot?t={int(datetime.now().timestamp())}"},
        }

    # --- File search --------------------------------------------------------
    fm = FIND_FILES_RE.match(cleaned)
    if fm:
        query = fm.group(1).strip().rstrip(".!?,;:")
        if query and len(query) >= 2:
            return {"reply": _find_files(query)}

    # --- Directory listing --------------------------------------------------
    lm = LIST_DIR_RE.match(cleaned)
    if lm:
        # Pull the first non-None group (the folder name)
        folder = next((g for g in lm.groups() if g), "").strip()
        folder = re.sub(r"\s+folder$", "", folder, flags=re.IGNORECASE).strip()
        if folder:
            target = _resolve_dir_alias(folder)
            if target is None:
                # Try as a path under HOME
                candidate = _safe_path(str(HOME / folder))
                if candidate and candidate.is_dir():
                    target = candidate
            if target is not None:
                text, _ = _list_dir(target)
                return {"reply": text}

    # --- Send / grab a file -------------------------------------------------
    sf = SEND_FILE_RE.match(cleaned)
    if sf:
        query = sf.group(1).strip().rstrip(".!?,;:")
        # Avoid trampling app-open (which covers "send me to..." weirdness).
        # Require a file-like phrase: ends with extension, or has "file"/"latest"/"newest".
        looks_filey = bool(
            re.search(r"\.[a-zA-Z0-9]{1,6}$", query) or
            re.search(r"\b(file|files|document|pdf|image|photo|screenshot|latest|newest|recent)\b",
                      query, re.IGNORECASE)
        )
        if looks_filey:
            # Spotlight search, take newest match
            try:
                result = subprocess.run(
                    ["mdfind", "-onlyin", str(HOME), query],
                    capture_output=True, text=True, timeout=8,
                )
                paths = [p for p in result.stdout.splitlines() if p.strip()]
                paths = [p for p in paths if Path(p).is_file()]
                paths.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
                           reverse=True)
            except Exception:
                paths = []
            if paths:
                target = paths[0]
                rel = Path(target).relative_to(HOME) if Path(target).is_relative_to(HOME) else Path(target)
                url_path = urllib.parse.quote(target, safe="")
                return {
                    "reply": f"Sending ~/{rel} — opening on your phone.",
                    "action": {"open_url": f"{_newt_host()}/file?path={url_path}"},
                }
            return {"reply": f"Couldn't find a file matching {query!r}."}

    # --- Music control (Mac) -----------------------------------------------
    if MUSIC_NEXT_RE.match(cleaned):
        ok, app = _music_command_mac("next")
        return {"reply": f"Skipping ({app})." if ok else "No music player found on Mac."}
    if MUSIC_PREV_RE.match(cleaned):
        ok, app = _music_command_mac("previous")
        return {"reply": f"Going back ({app})." if ok else "No music player found on Mac."}
    if MUSIC_PAUSE_RE.match(cleaned):
        ok, app = _music_command_mac("pause")
        return {"reply": f"Paused ({app})." if ok else "Nothing playing on Mac."}
    if MUSIC_PLAY_RE.match(cleaned):
        ok, app = _music_command_mac("play")
        return {"reply": f"Playing ({app})." if ok else "Couldn't resume playback."}

    # --- Timers -------------------------------------------------------------
    timer = _parse_timer(cleaned)
    if timer:
        seconds, label = timer
        return {
            "reply": f"Timer set for {label}.",
            "action": {"start_timer": {"seconds": seconds, "label": label}},
        }

    # --- Daily briefing -----------------------------------------------------
    if BRIEFING_RE.match(cleaned):
        now = datetime.now()
        date_line = now.strftime("%A, %B %-d")

        weather = _fetch_weather()
        headline = _fetch_news_headline()
        quote = _quote_of_the_day()

        # Greeting picks up time-of-day even if user said "brief me"
        hour = now.hour
        if "morning" in cleaned.lower() or hour < 12:
            greeting = "☀️ Good morning"
        elif hour < 17:
            greeting = "👋 Good afternoon"
        else:
            greeting = "🌙 Good evening"

        lines = [f"{greeting}, Ethan. It's {date_line}."]

        if weather:
            lines.append(f"\n🌤  Outside: {weather}")
        if headline:
            lines.append(f"📰  Top story: {headline}")
        lines.append(f"\n💭  {quote}")
        lines.append("\nPulling up your agenda and reminders…")

        return {
            "reply": "\n".join(lines),
            "action": {
                "read_events": {"range": "today"},
                "read_reminders": {"list": "today"},
            },
        }

    # --- Mac: wake (display) ------------------------------------------------
    # MUST come before app-launch since "open my mac" starts with "open".
    if WAKE_MAC_RE.match(cleaned):
        if _wake_mac():
            status = _autolock_status()
            if status is False:
                return {"reply": "Waking your Mac. (Lock screen is off — you'll go straight to the desktop.)"}
            return {"reply": "Waking your Mac."}
        return {"reply": "Couldn't wake your Mac."}

    # --- Mac: toggle auto-lock ---------------------------------------------
    if DISABLE_AUTOLOCK_RE.match(cleaned):
        if _set_autolock(False):
            return {"reply": "Auto-lock off. Display sleep won't ask for a password — \"open my Mac\" goes straight to the desktop."}
        return {"reply": "Couldn't disable auto-lock."}

    if ENABLE_AUTOLOCK_RE.match(cleaned):
        if _set_autolock(True):
            return {"reply": "Auto-lock on. Display sleep will require a password to unlock."}
        return {"reply": "Couldn't enable auto-lock."}

    # --- Mac: lock / sleep --------------------------------------------------
    if LOCK_RE.match(cleaned):
        if _lock_mac():
            return {"reply": "Locking your Mac."}
        return {"reply": "Couldn't lock — try giving Newt Accessibility access in System Settings."}

    if SLEEP_RE.match(cleaned):
        if _sleep_mac():
            return {"reply": "Putting your Mac to sleep."}
        return {"reply": "Couldn't put your Mac to sleep."}

    # --- Mac: volume --------------------------------------------------------
    m = VOLUME_SET_RE.match(cleaned)
    if m:
        n = int(m.group(1))
        if _set_mac_volume(n):
            return {"reply": f"Mac volume set to {max(0, min(100, n))}."}
        return {"reply": "Couldn't change volume."}

    if VOLUME_QUERY_RE.match(cleaned):
        v = _get_mac_volume()
        if v is None:
            return {"reply": "Couldn't read volume."}
        return {"reply": f"Mac volume is at {v}."}

    if MUTE_RE.match(cleaned):
        if _set_mac_mute(True):
            return {"reply": "Muted your Mac."}
        return {"reply": "Couldn't mute."}

    if UNMUTE_RE.match(cleaned):
        if _set_mac_mute(False):
            return {"reply": "Unmuted."}
        return {"reply": "Couldn't unmute."}

    if LOUDER_RE.match(cleaned):
        cur = _get_mac_volume() or 50
        new = min(100, cur + 15)
        _set_mac_volume(new)
        return {"reply": f"Volume up to {new}."}

    if QUIETER_RE.match(cleaned):
        cur = _get_mac_volume() or 50
        new = max(0, cur - 15)
        _set_mac_volume(new)
        return {"reply": f"Volume down to {new}."}

    # --- Messaging (SMS / iMessage) ----------------------------------------
    # Default: phone composes via Messages.app (you tap Send).
    # Override: "text mom on my mac" routes through AppleScript on the iMac.
    msg = _parse_imessage(cleaned)
    if msg:
        contact, body = msg
        if contact and body and len(body) >= 2:
            # Pull off "on my mac" target hint from the body if present
            body_target_match = MAC_TOKENS.search(body)
            mac_target = bool(body_target_match)
            if mac_target:
                body = MAC_TOKENS.sub("", body).strip().rstrip(".!?,;:")

            if mac_target:
                # Send from Mac via AppleScript / Messages.app
                ok, info = _send_imessage(contact, body)
                if ok:
                    return {"reply": f"Sent to {contact} from your Mac: “{body}”"}
                if "no_match" in info:
                    return {"reply": f"Couldn't find {contact} in Messages on your Mac. Make sure you've messaged them before."}
                return {"reply": f"Couldn't send from Mac. ({info[:80]})"}

            # Default: phone-side compose (SMS or iMessage, your phone decides)
            return {
                "reply": f"Drafting a message to {contact}: “{body}”. Tap Send when ready.",
                "action": {
                    "compose_sms": {
                        "recipient": contact,
                        "body": body,
                    }
                },
            }

    # --- Read calendar ------------------------------------------------------
    ev_read = _read_events_intent(cleaned)
    if ev_read is not None:
        label = {"today": "today", "tomorrow": "tomorrow",
                 "week": "this week"}.get(ev_read["range"], "today")
        return {
            "reply": f"Pulling up your calendar for {label}…",
            "action": {"read_events": ev_read},
        }

    # --- Read reminders -----------------------------------------------------
    if _read_reminders_intent(cleaned):
        return {
            "reply": "Checking your reminders…",
            "action": {"read_reminders": {"list": "incomplete"}},
        }

    # --- Create reminder ----------------------------------------------------
    rem = _parse_reminder(cleaned)
    if rem is not None:
        when_text = ""
        if rem.get("due"):
            try:
                dt = datetime.fromisoformat(rem["due"])
                when_text = f" at {dt.strftime('%-I:%M %p').lstrip('0')}"
                if dt.date() != datetime.now().date():
                    when_text += f" on {dt.strftime('%A')}"
            except Exception:
                pass
        return {
            "reply": f"Reminding you to {rem['title']}{when_text}.",
            "action": {"create_reminder": rem},
        }

    # --- Create calendar event ---------------------------------------------
    ev = _parse_event(cleaned)
    if ev is not None and ev.get("start"):
        try:
            dt = datetime.fromisoformat(ev["start"])
            when_text = dt.strftime("%A at %-I:%M %p").replace(" 0", " ")
        except Exception:
            when_text = "the scheduled time"
        return {
            "reply": f"Scheduled \"{ev['title']}\" for {when_text}.",
            "action": {"create_event": ev},
        }

    # --- Persona / memory --------------------------------------------------
    # "remember that I live in Geelong"
    rm = REMEMBER_FACT_RE.match(cleaned)
    if rm:
        fact = rm.group(1).strip().rstrip(".,;:!?")
        if fact and len(fact) >= 2:
            persona = _read_persona()
            facts = persona.get("facts", [])
            if fact.lower() not in (f.lower() for f in facts):
                facts.append(fact)
                persona["facts"] = facts
                _write_persona(persona)
            return {"reply": f"Got it — I'll remember: {fact}"}

    # "what do you know about me"
    if LIST_FACTS_RE.match(cleaned):
        persona = _read_persona()
        facts = persona.get("facts", [])
        tone = persona.get("tone", "warm")
        if not facts:
            return {"reply": f"I don't have any facts about you yet. Tone is set to {tone}. Try \"remember that I live in Geelong\"."}
        bullet = "\n".join(f"  • {f}" for f in facts)
        return {"reply": f"Here's what I know about you:\n{bullet}\n\nTone: {tone}"}

    # "forget X"
    fm = FORGET_FACT_RE.match(cleaned)
    if fm:
        target = fm.group(1).strip().rstrip(".,;:!?").lower()
        # Don't accidentally match "forget about it" / "forget what I said"
        # for now we only delete on substring match
        if target and target not in {"about it", "it", "what i said", "that"}:
            persona = _read_persona()
            facts = persona.get("facts", [])
            kept = [f for f in facts if target not in f.lower()]
            removed = len(facts) - len(kept)
            if removed > 0:
                persona["facts"] = kept
                _write_persona(persona)
                return {"reply": f"Forgotten {removed} fact{'s' if removed != 1 else ''}."}
            return {"reply": f"I don't have anything matching {target!r} to forget."}

    # "be more terse" / "use a witty tone"
    tm = SET_TONE_RE.match(cleaned)
    if tm:
        tone = next((g for g in tm.groups() if g), "").lower()
        if tone:
            persona = _read_persona()
            persona["tone"] = tone
            _write_persona(persona)
            return {"reply": f"Tone set to {tone}."}

    # --- Web search: "google X", "search for X", "look up X" ---------------
    ws = WEB_SEARCH_RE.match(cleaned)
    if ws:
        query = ws.group(1).strip().rstrip(".,;:!?")
        if query and len(query) >= 2:
            return {
                "reply": f"Searching for {query!r}…",
                "action": {"open_url": _web_search_url(query)},
            }

    # --- Quick capture: "note: ...", "remember the milk" -------------------
    note_m = NOTE_RE.match(cleaned)
    if note_m:
        body = note_m.group(1).strip().rstrip(".,;:!?")
        if body and len(body) >= 2:
            if _save_note(body):
                return {"reply": f"Noted: “{body}”"}
            return {"reply": f"Couldn't save the note. Check ~/newt/notes.md is writable."}

    # --- Shortcut: "run my morning shortcut" -------------------------------
    sc_name = _is_shortcut_request(cleaned)
    if sc_name:
        encoded = urllib.parse.quote(sc_name)
        return {
            "reply": f"Running the {sc_name} shortcut.",
            "action": {"open_url": f"shortcuts://run-shortcut?name={encoded}"},
        }

    # --- App launch: "open <X>" --------------------------------------------
    rest = _strip_open_prefix(cleaned)
    if rest is None or not rest:
        return None

    rest, target = _strip_target_tokens(rest)
    if target is None:
        target = default_target

    if target == "mac":
        resolved = _resolve_mac_app(rest)
        if _open_mac_app(rest):
            return {"reply": f"Opening {resolved} on your Mac."}
        return {"reply": f"Couldn't find {resolved!r} on your Mac. Is it installed?"}

    url = _resolve_ios_url(rest)
    if url is None:
        return {
            "reply": (
                f"I don't have a URL scheme for {rest!r} yet. "
                f"Add it to IOS_URL_SCHEMES in app_launcher.py and reload."
            )
        }
    pretty = _normalize_app_name(rest).title()
    return {
        "reply": f"Opening {pretty}.",
        "action": {"open_url": url},
    }


if __name__ == "__main__":
    tests = [
        "open spotify",
        "open Spotify on my Mac",
        "open Google Maps",
        "launch slack on my computer",
        "start chrome on my phone",
        "fire up youtube",
        "run my morning shortcut",
        "trigger shortcut Wind Down",
        "what's the weather like",
        "open the chatgpt app please",
    ]
    for t in tests:
        print(f"> {t!r}")
        print(f"  -> {handle_message(t)}\n")
