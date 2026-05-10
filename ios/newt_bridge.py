"""Newt Bridge — Flask HTTP entry point.

Simple, single-file Flask server. Delegates all the heavy lifting to
app_launcher.py (intent matcher, agentic streaming, tool execution,
vision, file ops, persona, etc.).

Endpoints:
  GET  /health          — status check
  POST /chat            — non-streaming chat (intent → LLM fallback)
  POST /chat/stream     — streaming SSE chat with agentic tool loop
  POST /listen          — audio upload → Whisper → reply
  GET  /screenshot      — Mac screen capture
  GET  /file            — serve a file from user home
  POST /upload          — receive a file from phone, save to ~/newt/inbox/
  POST /vision          — describe an image
  GET  /persona         — read persona JSON
  POST /persona         — update persona JSON
"""
from __future__ import annotations

import os
import logging
import tempfile
from pathlib import Path

from flask import Flask, request, jsonify

# Load .env (OPENAI_API_KEY, GROQ_API_KEY, etc.) before importing app_launcher.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

# All the brains live in app_launcher.py.
from app_launcher import (
    handle_message,
    register_routes,
    system_prompt_prefix,
    _groq_client,
    GROQ_CHAT_MODEL,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("newt")

app = Flask(__name__)

# Register /screenshot, /file, /upload, /vision, /persona, /chat/stream
register_routes(app)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "user": os.environ.get("NEWT_USER", "Ethan"),
        "city": os.environ.get("NEWT_CITY", "Geelong"),
        "model": GROQ_CHAT_MODEL,
    })


# ---------------------------------------------------------------------------
# /chat — non-streaming chat. Intent matcher first; LLM fallback otherwise.
# ---------------------------------------------------------------------------

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    text = (data.get("prompt") or data.get("message") or data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "no prompt"}), 400

    # Try intent matcher first (open apps, calendar, etc.)
    intent = handle_message(text)
    if intent is not None:
        return jsonify(intent)

    # Fall through to the LLM
    try:
        client = _groq_client()
        persona = system_prompt_prefix().strip()
        sys_prompt = persona or "You are Newt, Ethan's voice assistant. Be concise, warm, and useful."

        resp = client.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user",   "content": text},
            ],
            max_tokens=600,
        )
        reply = (resp.choices[0].message.content or "(no reply)").strip()
        return jsonify({"reply": reply})
    except Exception as e:
        log.exception("chat LLM failure")
        return jsonify({"reply": f"Newt had a moment: {e}"}), 500


# ---------------------------------------------------------------------------
# /listen — audio upload → Whisper transcription → intent or LLM
# ---------------------------------------------------------------------------

@app.route("/listen", methods=["POST"])
def listen():
    if "file" not in request.files:
        return jsonify({"error": "no audio file in request"}), 400
    f = request.files["file"]

    tmp_path = Path(tempfile.gettempdir()) / f"newt-listen-{os.getpid()}.m4a"
    f.save(str(tmp_path))

    transcript = ""
    try:
        client = _groq_client()
        with open(tmp_path, "rb") as audio_file:
            t = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                response_format="text",
            )
        # Groq returns either a string or an object with .text depending on response_format
        transcript = (t if isinstance(t, str) else getattr(t, "text", "")).strip()
    except Exception as e:
        log.exception("transcription failed")
        return jsonify({"transcript": "", "reply": f"Couldn't transcribe: {e}"}), 200
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass

    if not transcript:
        return jsonify({"transcript": "", "reply": "I couldn't catch that — try again?"}), 200

    # Intent first
    intent = handle_message(transcript)
    if intent is not None:
        return jsonify({"transcript": transcript, **intent})

    # Otherwise LLM
    try:
        client = _groq_client()
        persona = system_prompt_prefix().strip()
        sys_prompt = persona or "You are Newt, Ethan's voice assistant. Be concise, warm, and useful."

        resp = client.chat.completions.create(
            model=GROQ_CHAT_MODEL,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user",   "content": transcript},
            ],
            max_tokens=600,
        )
        reply = (resp.choices[0].message.content or "(no reply)").strip()
    except Exception as e:
        log.exception("listen LLM failure")
        reply = f"Newt had a moment: {e}"

    return jsonify({"transcript": transcript, "reply": reply})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    host = os.environ.get("NEWT_HOST", "0.0.0.0")
    port = int(os.environ.get("NEWT_PORT", 8001))
    log.info(f"Newt bridge starting on {host}:{port} (model: {GROQ_CHAT_MODEL})")
    app.run(host=host, port=port, threaded=True)
