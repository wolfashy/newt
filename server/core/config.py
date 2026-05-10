from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path.home() / "newt" / ".env")
BASE_DIR = Path.home() / "newt"

def _require(name):
    val = os.getenv(name)
    if not val: raise RuntimeError(f"Missing: {name}")
    return val

GROQ_API_KEY = _require("GROQ_API_KEY")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
ELEVENLABS_API_KEY = _require("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = _require("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-large-v3-turbo")
WEATHER_KEY = os.getenv("WEATHER_KEY", "")
NEWS_KEY = os.getenv("NEWS_KEY", "")
CITY = os.getenv("CITY", "Geelong")
PROFILE_PATH = BASE_DIR / "user_profile.json"
PERSONA_PATH = BASE_DIR / "persona.json"
NOTES_PATH = BASE_DIR / "notes.md"
MEMORY_DIR = BASE_DIR / "memory"
DB_PATH = BASE_DIR / "conversations.db"
NEWT_HOST = os.getenv("NEWT_HOST", "0.0.0.0")
NEWT_PORT = int(os.getenv("NEWT_PORT", "8001"))
NEWT_PUBLIC_URL = os.getenv("NEWT_PUBLIC_URL", "http://newt:8001")
