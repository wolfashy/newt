from __future__ import annotations
import io, logging, tempfile, subprocess, shutil
import requests
from core.config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL, GROQ_API_KEY, WHISPER_MODEL

log = logging.getLogger(__name__)

def speak_elevenlabs(text: str) -> bytes | None:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    try:
        r = requests.post(url, json=payload, headers=headers, stream=True, timeout=15)
        if r.status_code == 200:
            chunks = []
            for chunk in r.iter_content(chunk_size=4096):
                if chunk:
                    chunks.append(chunk)
            return b"".join(chunks)
        log.warning(f"ElevenLabs returned {r.status_code}")
    except Exception as e:
        log.error(f"ElevenLabs error: {e}")
    return speak_piper(text)

def speak_piper(text: str) -> bytes | None:
    if not shutil.which("piper"):
        log.warning("piper not installed, TTS unavailable")
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            proc = subprocess.run(
                ["piper", "--output_file", tmp.name],
                input=text.encode(), capture_output=True, timeout=10
            )
            if proc.returncode == 0:
                with open(tmp.name, "rb") as f:
                    return f.read()
    except Exception as e:
        log.error(f"Piper fallback failed: {e}")
    return None

def transcribe(audio_data: bytes, filename: str = "audio.m4a") -> str:
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    files = {"file": (filename, io.BytesIO(audio_data), "audio/m4a")}
    data = {"model": WHISPER_MODEL, "response_format": "text"}
    try:
        r = requests.post(url, headers=headers, files=files, data=data, timeout=30)
        if r.status_code == 200:
            return r.text.strip()
        log.error(f"Whisper returned {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"Transcription error: {e}")
    return ""
