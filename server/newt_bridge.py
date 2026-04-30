"""
newt_bridge.py — Flask HTTP bridge exposing Newt's brain on localhost:5001.

Your Xcode app POSTs JSON here; this file handles the Groq call,
memory lookup, and optional Mac actions, then returns clean JSON.

Run with:
    source venv/bin/activate && python newt_bridge.py

Xcode quick-start (Swift):
    let url = URL(string: "http://localhost:5001/ask")!
    var req = URLRequest(url: url)
    req.httpMethod = "POST"
    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
    req.httpBody = try? JSONSerialization.data(withJSONObject: ["message": userText])
    URLSession.shared.dataTask(with: req) { data, _, _ in
        if let d = data,
           let json = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
           let reply = json["response"] as? String { print(reply) }
    }.resume()
"""

from __future__ import annotations  # let Python 3.9 parse `str | None` etc.

import datetime
import json
import math
import os
import re
import struct
import subprocess
import tempfile
import threading
import time
from urllib.parse import quote

import chromadb
import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, stream_with_context
from app_launcher import handle_message as _newt_handle_app_intent, register_routes as _newt_register_routes, system_prompt_prefix as _newt_system_prompt_prefix

# ── ENV LOADING ───────────────────────────────────────────
# Loads ~/newt/.env regardless of cwd (matters for launchd).
load_dotenv(os.path.expanduser("~/newt/.env"))


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}. Did you create .env?")
    return val


# ── CONFIG ────────────────────────────────────────────────
GROQ_API_KEY  = _require("GROQ_API_KEY")
GROQ_URL      = "https://api.groq.com/openai/v1/chat/completions"
WEATHER_KEY   = os.getenv("WEATHER_KEY", "")
CITY          = os.getenv("CITY", "Geelong")
MODEL         = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
PROFILE_PATH  = os.path.expanduser("~/newt/user_profile.json")
HISTORY: list = []

# ── ELEVENLABS (cloned voice) ─────────────────────────────
ELEVENLABS_API_KEY  = _require("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = _require("ELEVENLABS_VOICE_ID")
ELEVENLABS_MODEL    = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2_5")

# ── WHISPER (voice-in via Groq, OpenAI-compatible) ────────
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-large-v3-turbo")
WHISPER_URL   = "https://api.groq.com/openai/v1/audio/transcriptions"

# ── MEMORY ────────────────────────────────────────────────
_mem_client = chromadb.PersistentClient(
    path=os.path.expanduser("~/newt/memory")
)
memory = _mem_client.get_or_create_collection("newt_memory")


def save_memory(user_msg: str, response: str) -> None:
    doc_id = f"mem_{datetime.datetime.now().timestamp()}"
    memory.add(documents=[f"User: {user_msg}\nNewt: {response}"], ids=[doc_id])


def recall_memory(query: str, n: int = 5) -> str:
    try:
        results = memory.query(
            query_texts=[query],
            n_results=min(n, memory.count()),
        )
        if results and results["documents"][0]:
            return "\n---\n".join(results["documents"][0])
    except Exception:
        pass
    return ""


# ── PROFILE ───────────────────────────────────────────────

def load_profile() -> dict:
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH) as f:
            return json.load(f)
    return {
        "name": None, "preferences": [], "habits": [],
        "topics_of_interest": [], "facts_learned": [],
        "conversation_count": 0, "city": None,
    }


# ── GROQ HELPERS ──────────────────────────────────────────

def _groq(messages: list, max_tokens: int = 1024, temperature: float = 0.85) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    r = requests.post(
        GROQ_URL,
        json={"model": MODEL, "messages": messages,
              "max_tokens": max_tokens, "temperature": temperature},
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ── WEATHER ───────────────────────────────────────────────

def get_weather(city: str = CITY) -> str:
    try:
        r = requests.get(
            f"http://api.openweathermap.org/data/2.5/weather"
            f"?q={city}&appid={WEATHER_KEY}&units=metric",
            timeout=8,
        )
        d = r.json()
        return (f"It's {round(d['main']['temp'])}°C in {city}, "
                f"feels like {round(d['main']['feels_like'])}°C, "
                f"{d['weather'][0]['description']}, "
                f"humidity {d['main']['humidity']}%.")
    except Exception as e:
        return f"Couldn't get weather: {e}"


# ── MAC HELPERS ───────────────────────────────────────────

def find_app_on_mac(app_name: str) -> str | None:
    """Locate a .app bundle with mdfind. Returns the path or None."""
    try:
        r = subprocess.run(
            ["mdfind",
             f"kMDItemContentType == 'com.apple.application-bundle' "
             f"&& kMDItemDisplayName == '{app_name}'"],
            capture_output=True, text=True, timeout=8,
        )
        hits = [x for x in r.stdout.strip().split("\n") if x.endswith(".app")]
        if hits:
            return hits[0]
        r2 = subprocess.run(
            ["mdfind", "-name", f"{app_name}.app"],
            capture_output=True, text=True, timeout=8,
        )
        hits2 = [x for x in r2.stdout.strip().split("\n") if x.endswith(".app")]
        if hits2:
            return hits2[0]
    except Exception:
        pass
    return None


def open_app(app_name: str) -> str:
    path = find_app_on_mac(app_name)
    if path:
        subprocess.run(["open", path])
    else:
        subprocess.run(["open", "-a", app_name])
    return f"Opened {app_name}."


def get_battery() -> str:
    r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
    return r.stdout.strip()


def set_volume(level: int) -> str:
    level = max(0, min(100, int(level)))
    subprocess.run(["osascript", "-e", f"set volume output volume {level}"])
    return f"Volume set to {level}%."


# ── CORE BRAIN ────────────────────────────────────────────

def ask_newt(prompt: str, profile: dict, context: str = "") -> str:
    past = recall_memory(prompt)
    memory_block = f"\nRELEVANT PAST MEMORY:\n{past}\n" if past else ""
    name   = profile.get("name")
    prefs  = "; ".join(profile.get("preferences", [])[:5])
    facts  = "; ".join(profile.get("facts_learned", [])[:5])
    system = f"""You are Newt, a sharp AI assistant on the user's Mac.
You are confident, direct, and genuinely clever — like a brilliant colleague.
You have real opinions and share them clearly. You remember the user.
NAME: {name or 'unknown'} | PREFERENCES: {prefs or 'none'} | FACTS: {facts or 'none'}
{memory_block}
{f'EXTRA CONTEXT: {context}' if context else ''}
RULES:
- Answer in plain English — no code unless the user asks to BUILD something
- Be concise but never robotic
- Never say you're an AI — just be Newt"""

    HISTORY.append({"role": "user", "content": prompt})
    messages = [{"role": "system", "content": system}]
    messages += [{"role": m["role"], "content": m["content"]} for m in HISTORY[-12:]]

    response = _groq(messages)
    HISTORY.append({"role": "assistant", "content": response})
    threading.Thread(target=save_memory, args=(prompt, response), daemon=True).start()
    return response


# ── INTENT ROUTING ────────────────────────────────────────
# The bridge does lightweight intent detection so the Xcode app
# doesn't need to know about individual Mac capabilities.

_WEATHER_WORDS = {"weather","temperature","forecast","hot","cold","rain","sunny"}
_BATTERY_WORDS = {"battery","charge","charging"}
_VOLUME_RE     = re.compile(r'\bvolume\b.*?(\d+)', re.I)

def route_intent(text: str, profile: dict):
    """
    Returns (intent, payload) where payload is the ready-to-send string.
    Falls through to ask_newt for anything unrecognised.
    """
    t = text.lower()

    # weather
    if any(w in t for w in _WEATHER_WORDS):
        city = profile.get("city") or CITY
        return "weather", get_weather(city)

    # battery
    if any(w in t for w in _BATTERY_WORDS):
        return "battery", get_battery()

    # volume
    m = _VOLUME_RE.search(t)
    if m:
        return "volume", set_volume(int(m.group(1)))

    # open / launch / start an app
    if any(w in t for w in ["open ", "launch ", "start "]):
        # Ask the AI to name the app
        app_prompt = (
            "Return ONLY the app name the user wants to open, nothing else.\n"
            f'User said: "{text}"\nApp name:'
        )
        try:
            app_name = _groq(
                [{"role": "user", "content": app_prompt}],
                max_tokens=20, temperature=0.1,
            ).strip().strip('"').strip("'")
            if app_name:
                return "open_app", open_app(app_name)
        except Exception:
            pass

    # general AI
    return "chat", ask_newt(text, profile)


# ── FLASK APP ─────────────────────────────────────────────

app = Flask(__name__)
_newt_register_routes(app)
_profile = load_profile()


@app.route("/health", methods=["GET"])
def health():
    """Quick liveness probe — Xcode can poll this on startup."""
    return jsonify({
        "status": "ok",
        "memory_count": memory.count(),
        "user": _profile.get("name"),
        "city": _profile.get("city") or CITY,
    })


def _read_message(data: dict) -> str:
    """Accept either {"message": ...} (bridge native) or {"prompt": ...} (iOS app)."""
    return (data.get("message") or data.get("prompt") or "").strip()


def _reply_payload(text: str, *, intent: str | None = None) -> dict:
    """Build a response that satisfies both the bridge clients and the iOS app."""
    payload = {
        "ok": True,
        "response": text,            # original bridge schema
        "reply": text,               # what NetworkManager.swift expects
        "audio_url": f"/speak?text={quote(text)}",
    }
    if intent is not None:
        payload["intent"] = intent
    return payload


@app.route("/ask", methods=["POST"])
def ask():
    """
    General-purpose endpoint with intent routing.

    Body (JSON): {"message" | "prompt": "...", "context"?: "..."}
    Returns: {"ok": true, "intent": "...", "response": "...", "reply": "...", "audio_url": "/speak?text=..."}
    """
    data = request.get_json(force=True, silent=True) or {}
    message = _read_message(data)
    if not message:
        return jsonify({"ok": False, "error": "No 'message' or 'prompt' in body."}), 400

    try:
        intent, payload = route_intent(message, _profile)
        return jsonify(_reply_payload(payload, intent=intent))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/chat", methods=["POST"])
def chat():
    # Newt: cross-platform app launcher (auto-injected)
    try:
        from flask import request as _newt_req, jsonify as _newt_jsonify
        _newt_data = _newt_req.get_json(silent=True) or {}
        _newt_text = _newt_data.get("prompt") or _newt_data.get("message") or _newt_data.get("text") or ""
        _newt_intent = _newt_handle_app_intent(_newt_text)
        if _newt_intent is not None:
            return _newt_jsonify(_newt_intent)
    except Exception as _newt_e:
        print(f"[newt-launcher] /chat hook error: {_newt_e}")
    """
    Raw chat — bypasses intent routing, always goes straight to the AI.

    Body (JSON): {"message" | "prompt": "...", "context"?: "..."}
    Returns: {"ok": true, "response": "...", "reply": "...", "audio_url": "/speak?text=..."}
    """
    data = request.get_json(force=True, silent=True) or {}
    message = _read_message(data)
    if not message:
        return jsonify({"ok": False, "error": "No 'message' or 'prompt' in body."}), 400

    context = data.get("context", "")
    try:
        response = ask_newt(message, _profile, context)
        return jsonify(_reply_payload(response))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── ELEVENLABS VOICE STREAM ───────────────────────────────

@app.route("/speak", methods=["GET", "POST"])
def speak():
    """
    Stream the cloned ElevenLabs voice for arbitrary text.

        GET  /speak?text=hello+from+newt          → audio/mpeg (handy for AVPlayer)
        POST /speak  body: {"text": "..."}        → audio/mpeg

    Optional body fields (POST): stability, similarity_boost, style, voice_id, model_id.
    """
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        text = (data.get("text") or "").strip()
    else:
        data = {}
        text = (request.args.get("text") or "").strip()

    if not text:
        return jsonify({"ok": False, "error": "text required"}), 400

    voice_id = data.get("voice_id") or ELEVENLABS_VOICE_ID
    model_id = data.get("model_id") or ELEVENLABS_MODEL
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    payload = {
        "text": text[:5000],
        "model_id": model_id,
        "voice_settings": {
            "stability":        float(data.get("stability",        0.5)),
            "similarity_boost": float(data.get("similarity_boost", 0.75)),
            "style":            float(data.get("style",            0.0)),
            "use_speaker_boost": True,
        },
    }
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    upstream = requests.post(url, headers=headers, json=payload, stream=True, timeout=60)
    if upstream.status_code != 200:
        body = upstream.text[:500]
        return (
            jsonify({"ok": False, "error": f"ElevenLabs {upstream.status_code}: {body}"}),
            upstream.status_code,
        )

    def generate():
        for chunk in upstream.iter_content(chunk_size=4096):
            if chunk:
                yield chunk

    return Response(
        stream_with_context(generate()),
        mimetype="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


# ── VOICE-IN: WHISPER → CHAT → CLONED VOICE ───────────────

@app.route("/listen", methods=["POST"])
def listen():
    """
    Push-to-talk endpoint.

    Multipart upload:
        file=<audio file>           required (m4a / wav / mp3 / webm / etc.)

    Query params:
        ?transcribe_only=1          return just the transcript, no chat round-trip

    Response:
        {
            "ok": true,
            "transcript": "what's the weather",
            "intent":     "weather",
            "reply":      "It's 18°C in Geelong ...",
            "response":   "It's 18°C in Geelong ...",
            "audio_url":  "/speak?text=It%27s+18%C2%B0C+in+Geelong..."
        }
    """
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Upload an audio 'file'."}), 400

    audio = request.files["file"]
    transcribe_only = request.args.get("transcribe_only") in ("1", "true", "yes")

    files = {
        "file": (
            audio.filename or "audio.m4a",
            audio.stream,
            audio.mimetype or "audio/m4a",
        )
    }
    data = {"model": WHISPER_MODEL, "response_format": "json"}
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}

    try:
        r = requests.post(WHISPER_URL, headers=headers, files=files, data=data, timeout=60)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Whisper request failed: {e}"}), 502

    if r.status_code != 200:
        return (
            jsonify({"ok": False, "error": f"Whisper {r.status_code}: {r.text[:300]}"}),
            r.status_code,
        )

    transcript = (r.json().get("text") or "").strip()
    # Newt: cross-platform app launcher (auto-injected)
    try:
        _newt_intent_l = _newt_handle_app_intent(transcript)
        if _newt_intent_l is not None:
            from flask import jsonify as _newt_jsonify_l
            return _newt_jsonify_l({"transcript": transcript, **_newt_intent_l})
    except Exception as _newt_le:
        print(f"[newt-launcher] /listen hook error: {_newt_le}")
    if not transcript:
        return jsonify({"ok": False, "error": "Empty transcription."}), 400

    if transcribe_only:
        return jsonify({"ok": True, "transcript": transcript})

    try:
        intent, payload = route_intent(transcript, _profile)
        out = _reply_payload(payload, intent=intent)
        out["transcript"] = transcript
        return jsonify(out)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "transcript": transcript}), 500


@app.route("/weather", methods=["GET"])
def weather():
    """GET /weather  →  { "ok": true, "response": "It's 18°C ..." }"""
    city = request.args.get("city") or _profile.get("city") or CITY
    return jsonify({"ok": True, "response": get_weather(city)})


@app.route("/memory", methods=["GET"])
def recall():
    """
    GET /memory?q=swift+concurrency
    Returns the top relevant memories for a query.
    """
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"ok": False, "error": "No query param 'q'."}), 400
    result = recall_memory(query)
    return jsonify({"ok": True, "response": result or "No relevant memories found."})


# ── ENTRY POINT ───────────────────────────────────────────

if __name__ == "__main__":
    host = os.getenv("NEWT_HOST", "0.0.0.0")     # 0.0.0.0 = reachable on the tailnet
    port = int(os.getenv("NEWT_PORT", "8001"))   # matches NetworkManager.swift
    print("=" * 50)
    print(f"  Newt Bridge — http://{host}:{port}")
    print(f"  Memory: {memory.count()} entries")
    print(f"  User:   {_profile.get('name') or 'unknown'}")
    print(f"  Voice:  ElevenLabs {ELEVENLABS_VOICE_ID} ({ELEVENLABS_MODEL})")
    print("=" * 50)
    # threaded=True so slow Groq calls don't block health-check pings
    app.run(host=host, port=port, debug=False, threaded=True)
