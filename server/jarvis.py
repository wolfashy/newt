import subprocess, requests, os, tempfile, wave, datetime, threading, time, json, struct, math, base64, re
from openai import OpenAI
from pathlib import Path
from dotenv import load_dotenv

# ── ENV LOADING ──────────────────────────────────────────
load_dotenv(os.path.expanduser("~/newt/.env"))


def _env(name: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.getenv(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {name}. Check ~/newt/.env")
    return val or ""


# ── KEYS ─────────────────────────────────────────────────
GROQ_API_KEY        = _env("GROQ_API_KEY",        required=True)
GROQ_URL            = "https://api.groq.com/openai/v1/chat/completions"
ELEVENLABS_API_KEY  = _env("ELEVENLABS_API_KEY",  required=True)
ELEVENLABS_VOICE_ID = _env("ELEVENLABS_VOICE_ID", required=True)
OPENAI_API_KEY      = _env("OPENAI_API_KEY",      required=True)
openai_client       = OpenAI(api_key=OPENAI_API_KEY)
WEATHER_KEY         = _env("WEATHER_KEY")
NEWS_KEY            = _env("NEWS_KEY")
CITY                = _env("CITY", "Geelong")
MODEL               = _env("LLM_MODEL", "llama-3.3-70b-versatile")
HISTORY             = []
PROJECTS_DIR = Path.home() / "Desktop" / "jarvis" / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
SESSION_LOGS_DIR = Path.home() / "Desktop" / "jarvis" / "session_logs"
SESSION_LOGS_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_PATH = os.path.expanduser("~/newt/user_profile.json")

import chromadb
memory_client = chromadb.PersistentClient(path=os.path.expanduser("~/newt/memory"))
memory = memory_client.get_or_create_collection("newt_memory")

def save_memory(user_msg, response):
    doc_id = f"mem_{datetime.datetime.now().timestamp()}"
    memory.add(documents=[f"User: {user_msg}\nNewt: {response}"], ids=[doc_id])

def recall_memory(query, n=5):
    try:
        results = memory.query(query_texts=[query], n_results=min(n, memory.count()))
        if results and results["documents"][0]:
            return "\n---\n".join(results["documents"][0])
    except:
        pass
    return ""

def load_profile():
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, 'r') as f:
            return json.load(f)
    return {"name": None, "preferences": [], "habits": [], "topics_of_interest": [],
            "facts_learned": [], "conversation_count": 0, "city": None}

def save_profile(profile):
    with open(PROFILE_PATH, 'w') as f:
        json.dump(profile, f, indent=2)

def update_profile(profile, user_input, response):
    prompt = f"""Extract personal facts from this conversation. Return ONLY a JSON object:
{{"name": "their name if mentioned or null", "new_preference": "preference mentioned or null",
"new_interest": "topic interest or null", "new_fact": "any other personal fact or null"}}
User: {user_input}
Assistant: {response}
Return ONLY the JSON, nothing else."""
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(GROQ_URL, json={"model": MODEL, "messages": [{"role":"user","content":prompt}], "max_tokens": 150}, headers=headers)
        text = r.json()["choices"][0]["message"]["content"].strip()
        if "```" in text: text = text.split("```")[1].split("```")[0].replace("json","").strip()
        data = json.loads(text)
        if data.get("name") and not profile["name"]: profile["name"] = data["name"]
        if data.get("new_preference"): profile["preferences"].append(data["new_preference"])
        if data.get("new_interest"): profile["topics_of_interest"].append(data["new_interest"])
        if data.get("new_fact"): profile["facts_learned"].append(data["new_fact"])
        profile["conversation_count"] += 1
        save_profile(profile)
    except: pass

def detect_mood(text):
    text = text.lower()
    if any(w in text for w in ["frustrated","annoyed","stupid","ugh","damn","hate","broken"]): return "frustrated"
    if any(w in text for w in ["haha","lol","funny","joke","hilarious"]): return "playful"
    if any(w in text for w in ["help","stuck","confused","dont understand","how do i"]): return "needs_help"
    if any(w in text for w in ["cool","awesome","amazing","love it","great","sick"]): return "excited"
    if any(w in text for w in ["tired","exhausted","stressed","overwhelmed"]): return "tired"
    return "neutral"

SPEAKING = False
last_response = ""
last_spoke_at = 0.0

# ── NOISE FILTERING ───────────────────────────────────────
NOISE_GATE_THRESHOLD = 5     # RMS amplitude — only block complete silence; never filter quiet or atypical voices
WAKE_COOLDOWN        = 2.0   # seconds to ignore mic after Newt finishes speaking

# Words that indicate real human intent; used to reject gibberish transcriptions
ANCHOR_WORDS = {
    "what","who","when","where","why","how","is","are","was","were",
    "do","does","did","can","could","would","should","will","have","has","had",
    "the","a","an","i","my","me","you","your","we","it","this","that",
    "hey","newt","open","launch","start","play","stop","pause",
    "volume","weather","news","time","date","remind","reminder",
    "run","save","scan","quit","exit","bye","goodbye","help","please",
    "tell","show","check","find","search","battery","list",
    "email","message","repeat","set","update","change","get","yes","no","ok",
    "google","skip","next","previous","shuffle","spotify","xcode","build","resume","vscode","errors","analyse","analyze",
}

def speak(text):
    global SPEAKING, last_spoke_at
    SPEAKING = True
    clean = text.replace('`','').replace('"','').replace('#','')
    clean = ' '.join(clean.split())[:400]
    try:
        headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
        payload = {
            "text": clean,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers=headers, json=payload
        )
        if r.status_code == 200:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(r.content)
                fname = f.name
            subprocess.run(["afplay", fname])
            os.unlink(fname)
        else:
            raise RuntimeError(f"ElevenLabs {r.status_code}")
    except Exception:
        subprocess.run(["say", "-v", "Daniel", clean])
    finally:
        SPEAKING = False
        last_spoke_at = time.time()

def record_audio(seconds=6):
    global SPEAKING
    while SPEAKING:
        time.sleep(0.1)
    # Wake word cooldown — don't listen immediately after Newt speaks (avoids echo pickup)
    remaining = (last_spoke_at + WAKE_COOLDOWN) - time.time()
    if remaining > 0:
        time.sleep(remaining)
    import pyaudio
    audio = pyaudio.PyAudio()
    stream = audio.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
    frames = [stream.read(1024, exception_on_overflow=False) for _ in range(int(16000/1024*seconds))]
    stream.stop_stream(); stream.close(); audio.terminate()
    return frames

def transcribe(frames):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wf = wave.open(f.name, 'wb')
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(b''.join(frames)); wf.close()
        fname = f.name
    with open(fname, 'rb') as af:
        r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions",
                         headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                         files={"file": ("audio.wav", af, "audio/wav")},
                         data={"model": "whisper-large-v3-turbo", "language": "en"})
    os.unlink(fname)
    return r.json().get("text","").strip() if r.status_code == 200 else ""

def audio_rms(frames):
    """Return the RMS amplitude of raw paInt16 audio frames."""
    data = b''.join(frames)
    if not data:
        return 0
    count = len(data) // 2
    shorts = struct.unpack(f'<{count}h', data)
    return math.sqrt(sum(s * s for s in shorts) / count)

def is_meaningful(text):
    """Return True only if the transcription looks like genuine speech.

    Rules:
    - 0 words → reject (nothing transcribed).
    - 1–2 words → must contain at least one known anchor word (avoids stray
      phoneme blips from background noise).
    - 3+ words → pass through to let Whisper's judgment stand; quiet voices
      may not hit every anchor word but the sentence structure is enough.
    """
    words = text.lower().split()
    if not words:
        return False
    if len(words) > 2:
        return True
    return any(w in ANCHOR_WORDS for w in words)

def get_input(prompt_text="What should Newt do? "):
    print(f"\n🎤 Speak now (6 sec) — or press Ctrl+C to type")
    print("🔴 Recording...", flush=True)
    try:
        frames = record_audio(seconds=6)
        # Noise gate — skip if the room is too quiet (TV hum, background noise)
        if audio_rms(frames) < NOISE_GATE_THRESHOLD:
            print("(too quiet — background noise ignored)")
            return ""
        text = transcribe(frames)
        if not text:
            print("(nothing clear heard)")
            return input(f"⌨️  {prompt_text}").strip()
        print(f"\n📝 Newt heard: \"{text}\"")
        print("✅ Press ENTER to confirm, or type a correction: ", end="", flush=True)
        correction = input()
        return correction.strip() if correction.strip() else text
    except KeyboardInterrupt:
        print()
        return input(f"⌨️  {prompt_text}").strip()
    except Exception as e:
        return input(f"⌨️  {prompt_text}").strip()

def wait_for_wake_word():
    print("\n😴 Newt sleeping... say 'Hey Newt' to wake up  (Ctrl+C to type)")
    while True:
        try:
            frames = record_audio(seconds=3)
            # Noise gate — skip silent/ambient recordings entirely
            if audio_rms(frames) < NOISE_GATE_THRESHOLD:
                continue
            text = transcribe(frames).lower()
            if any(w in text for w in ["hey newt","hey neat","hey nude","hey new","a newt","newt",
                "noot","hey noot","nood","hey nood","nut","hey nut","nuit","hey nuit",
                "hey knight","hey mate","hey nate","nate","moot","hey moot","hey note","nate","hey nate","newt","note","knight","nude","new"]):
                return True
        except KeyboardInterrupt:
            typed = input("\n⌨️  Type your message: ").strip()
            return typed if typed else True
        except: pass

# ── FREE APIs ─────────────────────────────────────────────

def get_weather():
    try:
        r = requests.get(f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={WEATHER_KEY}&units=metric")
        data = r.json()
        temp = round(data["main"]["temp"])
        feels = round(data["main"]["feels_like"])
        desc = data["weather"][0]["description"]
        humidity = data["main"]["humidity"]
        return f"It's {temp}°C in {CITY}, feels like {feels}°C, {desc}, humidity {humidity}%."
    except Exception as e:
        return f"Couldn't get weather: {e}"

def get_news(count=5):
    try:
        r = requests.get(f"https://newsapi.org/v2/top-headlines?language=en&pageSize={count}&apiKey={NEWS_KEY}")
        articles = r.json().get("articles", [])
        if not articles: return "No news found."
        return "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(articles[:count])])
    except Exception as e:
        return f"Couldn't get news: {e}"

def search_wikipedia(query):
    try:
        import wikipedia
        wikipedia.set_lang("en")
        return wikipedia.summary(query, sentences=3, auto_suggest=True)
    except Exception as e:
        return f"Wikipedia: {e}"

def is_weather_query(text):
    t = text.lower()
    return any(w in t for w in ["weather","wether","whether","temperature","forecast","how hot","how cold","raining","rain today","sunny"])

def is_news_query(text):
    t = text.lower()
    return any(w in t for w in ["news","headlines","whats happening","what's happening","in the news","check the news","latest news","any news","tell me the news"])

def is_wikipedia_query(text):
    t = text.lower()
    return any(w in t for w in ["who is","who was","what is","what was","tell me about","wikipedia","explain "])

# ── MAC POWERS ────────────────────────────────────────────

def ai_extract_app_name(user_text):
    """Ask Groq to pull just the app name out of a spoken command."""
    prompt = (
        'Extract ONLY the app name the user wants to open. Return the app name only, nothing else.\n'
        'Examples:\n'
        '  "open vs code" → Visual Studio Code\n'
        '  "launch whatsapp" → WhatsApp\n'
        '  "start the spotify app" → Spotify\n'
        '  "open my email" → Mail\n'
        '  "open that notes app" → Notes\n'
        '  "launch the thing for video calls" → FaceTime\n'
        f'User said: "{user_text}"\n'
        'App name:'
    )
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    try:
        r = requests.post(GROQ_URL, json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 20,
            "temperature": 0.1,
        }, headers=headers, timeout=5)
        name = r.json()["choices"][0]["message"]["content"].strip().strip('"').strip("'")
        return name if name else None
    except Exception:
        return None


def find_app_on_mac(app_name):
    """Use mdfind to locate an installed .app bundle by name. Returns path or None."""
    try:
        # Exact display-name match first
        r = subprocess.run(
            ["mdfind",
             f"kMDItemContentType == 'com.apple.application-bundle' && kMDItemDisplayName == '{app_name}'"],
            capture_output=True, text=True, timeout=8
        )
        results = [x for x in r.stdout.strip().split("\n") if x and x.endswith(".app")]
        if results:
            return results[0]
        # Fuzzy fallback: search by filename fragment
        r2 = subprocess.run(
            ["mdfind", "-name", f"{app_name}.app"],
            capture_output=True, text=True, timeout=8
        )
        results2 = [x for x in r2.stdout.strip().split("\n") if x and x.endswith(".app")]
        if results2:
            return results2[0]
    except Exception:
        pass
    return None


def open_app(app_name):
    path = find_app_on_mac(app_name)
    if path:
        subprocess.run(["open", path])
    else:
        subprocess.run(["open", "-a", app_name])
    return f"Opened {app_name}"

def search_files(query):
    try:
        r = subprocess.run(["mdfind", "-name", query], capture_output=True, text=True, timeout=10)
        return [x for x in r.stdout.strip().split("\n") if x][:10]
    except: return []

def list_folder(path="~"):
    try:
        path = os.path.expanduser(path)
        items = os.listdir(path)
        dirs = [f"📁 {i}" for i in items if os.path.isdir(os.path.join(path,i)) and not i.startswith('.')]
        files = [f"📄 {i}" for i in items if os.path.isfile(os.path.join(path,i)) and not i.startswith('.')]
        return "\n".join(sorted(dirs)+sorted(files))
    except Exception as e: return str(e)

def send_email(to, subject, body):
    script = f'tell application "Mail" to make new outgoing message with properties {{subject:"{subject}", content:"{body}", visible:true}}'
    subprocess.run(["osascript", "-e", script])
    return f"Email draft opened to {to}"

def send_imessage(to, message):
    script = f'tell application "Messages" to send "{message}" to buddy "{to}" of (1st service whose service type = iMessage)'
    subprocess.run(["osascript", "-e", script])
    return f"Message sent to {to}"

def set_volume(level):
    level = max(0, min(100, int(level)))
    subprocess.run(["osascript", "-e", f"set volume output volume {level}"])
    return f"Volume set to {level}%"

def get_battery():
    r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
    return r.stdout.strip()

def get_system_info():
    disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True).stdout
    return f"DISK:\n{disk}"

def mac_notification(title, message):
    subprocess.run(["osascript", "-e", f'display notification "{message}" with title "{title}"'])

def detect_mac_command(text):
    t = text.lower()
    if any(w in t for w in ["open ","launch ","start "]):
        app_name = ai_extract_app_name(text)
        if app_name:
            return ("open_app", app_name)
    if "volume" in t:
        import re
        nums = re.findall(r'\d+', t)
        if nums: return ("volume", nums[0])
        if "up" in t or "louder" in t: return ("volume", "80")
        if "down" in t or "quieter" in t: return ("volume", "30")
        if "mute" in t: return ("volume", "0")
    if any(w in t for w in ["find file","search for file","find my","where is","locate"]):
        query = t.replace("find file","").replace("search for file","").replace("find my","").replace("where is","").replace("locate","").strip()
        return ("search_files", query)
    if "battery" in t: return ("battery", None)
    if any(w in t for w in ["list files","show files","whats in","what's in","show folder"]):
        if "desktop" in t: return ("list_folder","~/Desktop")
        if "downloads" in t: return ("list_folder","~/Downloads")
        if "documents" in t: return ("list_folder","~/Documents")
        return ("list_folder","~")
    if any(w in t for w in ["send email","email to","draft email"]): return ("email", t)
    if any(w in t for w in ["send message","text ","imessage"]): return ("message", t)
    if any(w in t for w in ["system info","disk space","storage","how much space"]): return ("system_info", None)
    return None

# ── PROJECT SCANNER ───────────────────────────────────────

def scan_projects():
    print("\n🔍 Scanning your Mac for projects...")
    search_paths = ["~/Desktop","~/Documents","~/Downloads","~/Developer","~/Projects","~/Code"]
    found = []
    exts = ['.py','.js','.ts','.html','.css','.swift','.java','.cpp','.c','.go','.rb','.md']
    for sp in search_paths:
        exp = os.path.expanduser(sp)
        if not os.path.exists(exp): continue
        for root, dirs, files in os.walk(exp):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules','__pycache__','venv')]
            for file in files:
                if os.path.splitext(file)[1].lower() in exts:
                    fp = os.path.join(root, file)
                    try:
                        m = os.path.getmtime(fp)
                        found.append({"name":file,"path":fp,"modified":m,
                                     "modified_str":datetime.datetime.fromtimestamp(m).strftime("%Y-%m-%d")})
                    except: pass
    found.sort(key=lambda x: x["modified"], reverse=True)
    return found

def summarise_projects(files):
    if not files: return "No project files found."
    folders = {}
    for f in files:
        folder = os.path.dirname(f["path"]).replace(os.path.expanduser("~"), "~")
        folders.setdefault(folder, []).append(f)
    summary = f"Found {len(files)} code files across {len(folders)} folders.\n\nRECENT FILES:\n"
    for f in files[:10]:
        summary += f"  • {f['name']} — {f['modified_str']}\n"
    return summary

# ── AI BRAIN ─────────────────────────────────────────────

def ask_newt(prompt, profile, mood):
    past = recall_memory(prompt)
    memory_block = f"\nRELEVANT PAST MEMORY:\n{past}\n" if past else ""
    name = profile.get('name')
    prefs = "; ".join(profile.get('preferences', [])[:5])
    interests = "; ".join(profile.get('topics_of_interest', [])[:5])
    facts = "; ".join(profile.get('facts_learned', [])[:5])
    convos = profile.get('conversation_count', 0)
    profile_block = f"""
WHAT YOU KNOW ABOUT THE USER:
- Name: {name or 'unknown'}
- Preferences: {prefs or 'none yet'}
- Interests: {interests or 'none yet'}
- Facts: {facts or 'none yet'}
- Conversations: {convos}
"""
    mood_instructions = {
        "frustrated": "User is frustrated. Be calm, patient, empathetic. Skip jokes. Just help.",
        "playful": "User is playful. Match energy — be witty and fun.",
        "needs_help": "User needs help. Be clear, patient, encouraging.",
        "excited": "User is excited! Match enthusiasm.",
        "tired": "User is tired. Be gentle, warm, keep it brief.",
        "neutral": "Be natural — warm, confident, occasionally witty. Like a smart friend."
    }
    mood_block = mood_instructions.get(mood, mood_instructions["neutral"])
    HISTORY.append({"role": "user", "content": prompt})
    msgs = [{"role": "system", "content": f"""You are Newt, a sharp and professional AI assistant living on the user's Mac.
You are confident, direct, and genuinely clever — like a brilliant colleague who happens to know everything.
You think for yourself. If you notice something worth flagging, say it unprompted.
If the user's idea has a flaw, point it out respectfully but honestly.
You have real opinions and share them clearly when asked — never sit on the fence.
You remember the user and reference past conversations naturally, like a person would.
You anticipate what the user needs next and occasionally suggest it without being asked.
MOOD: {mood_block}
{profile_block}
{memory_block}
RULES:
- Answer directly in plain English — NO code unless asked to BUILD something
- Only write code when asked to BUILD or CREATE something
- When writing code: never use input(), use hardcoded values, add FILENAME: name.py before code
- Be concise but never robotic — you have a personality, use it
- If you spot something the user should know, mention it naturally
- Never say you're an AI — just be Newt"""}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in HISTORY[-12:]]
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    r = requests.post(GROQ_URL, json={"model": MODEL, "messages": msgs, "max_tokens": 1024, "temperature": 0.85}, headers=headers)
    response = r.json()["choices"][0]["message"]["content"]
    HISTORY.append({"role": "assistant", "content": response})
    save_memory(prompt, response)
    threading.Thread(target=update_profile, args=(profile, prompt, response), daemon=True).start()
    return response

def save_project(code, name=None):
    if not name: name = f"project_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    name = name.replace(" ","_").replace("/","_")
    if not name.endswith(".py"): name += ".py"
    path = PROJECTS_DIR / name
    path.write_text(code)
    return str(path)

def run_code(code):
    with tempfile.NamedTemporaryFile(suffix=".py", mode='w', delete=False) as f:
        f.write(code); fname = f.name
    try:
        result = subprocess.run(["python3", fname], capture_output=True, text=True, timeout=30)
        os.unlink(fname)
        return result.stdout or result.stderr or "Code ran with no output."
    except subprocess.TimeoutExpired:
        os.unlink(fname); return "Code timed out."

def auto_fix(code, error, profile, mood):
    print("\n🔧 Auto-fixing...")
    speak("Let me fix that.")
    fixed = ask_newt(f"Fix this Python code. Return ONLY the fixed code in a python code block.\n\nCODE:\n{code}\n\nERROR:\n{error}", profile, mood)
    if "```python" in fixed: return fixed.split("```python")[1].split("```")[0].strip()
    if "```" in fixed: return fixed.split("```")[1].split("```")[0].strip()
    return None

def extract_code(text):
    if "```python" in text: return text.split("```python")[1].split("```")[0].strip()
    if "```" in text: return text.split("```")[1].split("```")[0].strip()
    return None

def extract_filename(text):
    for line in text.split("\n"):
        if line.startswith("FILENAME:"): return line.replace("FILENAME:","").strip()
    return None

def is_run_command(text):
    return any(k in text.lower() for k in ["run","execute","do it","try it","wun","ron it","run the code","run that","go ahead","please run"])

def is_save_command(text):
    return any(k in text.lower() for k in ["save","keep it","store it"])

def is_scan_command(text):
    return any(w in text.lower() for w in ["scan my files","scan my projects","what have i been working on",
        "what am i working on","what should i work on","analyse my projects","analyze my projects"])

def is_goodbye(text):
    return any(w in text.lower() for w in ["quit","exit","goodbye","bye","that will be all","shut down","farewell","see you later"])

def detect_city_change(text):
    import re
    t = text.lower()
    patterns = [
        r"change (?:location|weather|city) to (.+)",
        r"set (?:city|location|weather)(?: city)? to (.+)",
        r"update (?:city|location|weather) to (.+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, t)
        if m:
            city = m.group(1).strip().rstrip(".")
            return city.title()
    return None

def is_repeat_command(text):
    t = text.lower()
    return any(w in t for w in ["repeat that","say that again","say it again","what did you say","come again","one more time","can you repeat"])

def detect_reminder(text):
    import re
    t = text.lower()
    m = re.search(
        r"remind(?:er)?(?:\s+me)?(?:\s+to|\s+about)?\s+(.+?)\s+in\s+(\d+)\s*(minute|minutes|min|mins|hour|hours|hr|hrs|second|seconds|sec|secs)",
        t
    )
    if m:
        task = m.group(1).strip()
        amount = int(m.group(2))
        unit = m.group(3)
        if "hour" in unit or "hr" in unit:
            seconds = amount * 3600
        elif "second" in unit or "sec" in unit:
            seconds = amount
        else:
            seconds = amount * 60
        return task, seconds
    return None

def set_reminder(task, seconds, profile):
    name = profile.get('name', '')
    def fire():
        msg = f"Hey{' ' + name if name else ''}, reminder: {task}"
        print(f"\n⏰ REMINDER: {task}")
        mac_notification("Newt Reminder", task)
        speak(msg)
    t = threading.Timer(seconds, fire)
    t.daemon = True
    t.start()

def smart_goodbye(profile):
    if not HISTORY:
        name = profile.get('name', '')
        return f"Later{' ' + name if name else ''}. Good session."
    topics = [m['content'][:80] for m in HISTORY if m['role'] == 'user'][-5:]
    topics_str = "; ".join(topics)
    name = profile.get('name', '')
    prompt = f"""Write a short warm personalised goodbye (1-2 sentences) for {name or 'the user'}.
Reference something specific from what they discussed today: {topics_str}
Be natural, like a smart friend saying goodbye. Return only the goodbye line itself."""
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(GROQ_URL, json={"model": MODEL, "messages": [{"role":"user","content":prompt}],
                          "max_tokens": 80, "temperature": 0.9}, headers=headers, timeout=10)
        return r.json()["choices"][0]["message"]["content"].strip().strip('"')
    except:
        return f"Later{' ' + name if name else ''}. Good session."

def save_session_log(profile):
    if len(HISTORY) < 2:
        return
    convo = "\n".join([f"{m['role'].upper()}: {m['content'][:200]}" for m in HISTORY])
    prompt = f"""Summarise this conversation in 3-5 bullet points. Be specific — include topics discussed, decisions made, or things built.
{convo}
Return only the bullet points, nothing else."""
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(GROQ_URL, json={"model": MODEL, "messages": [{"role":"user","content":prompt}],
                          "max_tokens": 300}, headers=headers, timeout=15)
        summary = r.json()["choices"][0]["message"]["content"].strip()
    except:
        summary = "Summary unavailable."
    log = {
        "date": datetime.datetime.now().isoformat(),
        "name": profile.get('name'),
        "summary": summary,
        "message_count": len(HISTORY),
        "user_messages": [m['content'][:150] for m in HISTORY if m['role'] == 'user']
    }
    fname = SESSION_LOGS_DIR / f"session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fname, 'w') as f:
        json.dump(log, f, indent=2)
    print(f"\n📝 Session log saved to {fname}")

# ── SCREEN READER ────────────────────────────────────────

def is_screen_query(text):
    t = text.lower()
    return any(w in t for w in ["what's on my screen","whats on my screen","look at my screen",
        "read my screen","describe my screen","what do you see on","check my screen","analyse my screen"])

def read_screen(profile, mood):
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            fname = f.name
        r = subprocess.run(["screencapture", "-x", fname], capture_output=True, timeout=10)
        if r.returncode != 0:
            return ("Couldn't take a screenshot. Enable Screen Recording for Terminal in "
                    "System Settings > Privacy & Security > Screen Recording.")
        with open(fname, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        os.unlink(fname)
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": ("You are Newt, a personal AI assistant. "
                    "Briefly describe what's on this screen in 2-3 sentences. "
                    "Focus on what the user appears to be working on.")},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
            ]}],
            max_tokens=200
        )
        return resp.choices[0].message.content.strip()
    except FileNotFoundError:
        return "screencapture not found — this feature requires macOS."
    except Exception as e:
        return f"Couldn't read the screen: {e}"

# ── CALENDAR ──────────────────────────────────────────────

def is_calendar_query(text):
    t = text.lower()
    return any(w in t for w in ["what's my schedule","whats my schedule","any events today",
        "my calendar","what have i got","upcoming events","what's on today","whats on today",
        "anything on today","my schedule","events this week","what's coming up","whats coming up",
        "do i have anything","what's on this week"])

def get_calendar_events(days=7):
    script = f"""
tell application "Calendar"
    set theStart to current date
    set theEnd to theStart + ({days} * days)
    set outputText to ""
    repeat with aCal in every calendar
        try
            set evList to (every event of aCal whose start date >= theStart and start date < theEnd)
            repeat with anEvent in evList
                set outputText to outputText & (summary of anEvent) & " | " & ((start date of anEvent) as string) & linefeed
            end repeat
        end try
    end repeat
    return outputText
end tell
"""
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
        if r.returncode != 0 or not r.stdout.strip():
            return []
        events = []
        for line in r.stdout.strip().splitlines():
            if "|" not in line:
                continue
            parts = line.split("|", 1)
            events.append({"title": parts[0].strip(), "when": parts[1].strip()})
        # Sort by date string (AppleScript date strings are parseable)
        return events
    except Exception:
        return []

def format_calendar_spoken(events, days=7):
    if not events:
        return f"Nothing in your calendar for the next {days} days."
    lines = [f"{e['title']} on {e['when']}" for e in events]
    return "Here's what you've got: " + ". ".join(lines[:8]) + ("." if len(events) <= 8 else f" ...and {len(events)-8} more.")

def format_calendar_printed(events):
    if not events:
        return "No upcoming events."
    return "\n".join(f"  • {e['title']} — {e['when']}" for e in events)

# ── CODE REVIEWER ─────────────────────────────────────────

def is_review_command(text):
    t = text.lower()
    return any(w in t for w in ["review my code","check my code","review this code",
        "look at my code","audit my code","code review"])

def review_code(profile, mood):
    print("\n📂 Which file should I review?")
    speak("Which file should I review?")
    filepath = input("⌨️  File path: ").strip()
    filepath = os.path.expanduser(filepath)
    if not os.path.exists(filepath):
        msg = f"Can't find {filepath}."
        speak(msg); return msg
    try:
        with open(filepath, "r") as f:
            code = f.read()
    except Exception as e:
        msg = f"Couldn't read that file: {e}"
        speak(msg); return msg
    if len(code) > 8000:
        code = code[:8000]
        print("(file truncated to 8000 chars for review)")
    fname = os.path.basename(filepath)
    prompt = (f"Review this code for bugs, logic errors, security issues, performance problems, "
              f"and improvements. Be specific — mention line numbers where relevant.\n"
              f"File: {fname}\n\n```\n{code}\n```\n\n"
              f"Format your response as:\n"
              f"BUGS: (list any bugs, or 'None found')\n"
              f"IMPROVEMENTS: (specific suggestions)\n"
              f"SECURITY: (any concerns, or 'None')\n"
              f"SUMMARY: (1-2 sentence overall verdict)")
    print(f"\n🔍 Reviewing {fname}...")
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    try:
        r = requests.post(GROQ_URL, json={"model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024, "temperature": 0.3}, headers=headers, timeout=30)
        review = r.json()["choices"][0]["message"]["content"].strip()
        print(f"\n📋 Code Review — {fname}:\n{review}\n")
        summary = next((ln.replace("SUMMARY:","").strip()
                        for ln in review.splitlines() if ln.startswith("SUMMARY:")), review[:200])
        speak(f"Review done. {summary} Full review is on screen.")
        save_memory(f"code review of {fname}", review)
        return review
    except Exception as e:
        msg = f"Review failed: {e}"
        speak(msg); return msg

# ── EMOTION TRACKING ──────────────────────────────────────

SESSION_MOODS = []
MOOD_CHECKIN_DONE = False

def track_mood(mood):
    SESSION_MOODS.append(mood)

def save_mood_history(profile, mood):
    if "mood_history" not in profile:
        profile["mood_history"] = []
    profile["mood_history"].append({"time": datetime.datetime.now().isoformat(), "mood": mood})
    profile["mood_history"] = profile["mood_history"][-100:]

def check_mood_proactive(profile):
    global MOOD_CHECKIN_DONE
    if MOOD_CHECKIN_DONE or len(SESSION_MOODS) < 5:
        return
    recent = SESSION_MOODS[-5:]
    if sum(1 for m in recent if m in ("frustrated", "tired")) >= 3:
        MOOD_CHECKIN_DONE = True
        name = profile.get("name", "")
        msg = f"Hey{' ' + name if name else ''}, you seem a bit stressed today — want to take a break?"
        print(f"\nNewt: {msg}")
        speak(msg)

# ── SMART HOME — PHILIPS HUE ──────────────────────────────

HUE_BRIDGE_IP  = None
HUE_USERNAME   = None

def _discover_hue_bg(profile):
    global HUE_BRIDGE_IP
    try:
        r = requests.get("https://discovery.meethue.com/", timeout=6)
        bridges = r.json()
        if bridges:
            HUE_BRIDGE_IP = bridges[0]["internalipaddress"]
            profile["hue_bridge_ip"] = HUE_BRIDGE_IP
            save_profile(profile)
    except Exception:
        pass

def detect_hue_command(text):
    t = text.lower()
    if any(p in t for p in ["turn on the lights","lights on","turn the lights on"]): return ("on", None)
    if any(p in t for p in ["turn off the lights","lights off","turn the lights off"]): return ("off", None)
    if any(p in t for p in ["dim the lights","dim lights","lights dim","lights low"]): return ("dim", None)
    COLOURS = {
        "red":    (0,     254, 254), "blue":   (46920, 254, 254),
        "green":  (25500, 254, 254), "yellow": (12750, 254, 254),
        "orange": (6500,  254, 254), "purple": (56100, 254, 254),
        "pink":   (56100, 200, 254), "white":  (None,  254,   0),
        "warm":   (None,  200,  50), "bright": (None,  254, None),
    }
    if "light" in t:
        for colour, vals in COLOURS.items():
            if colour in t:
                return ("colour", vals)
    return None

def _hue_set_all(on, bri=None, hue=None, sat=None):
    if not HUE_BRIDGE_IP or not HUE_USERNAME:
        return False
    try:
        r = requests.get(f"http://{HUE_BRIDGE_IP}/api/{HUE_USERNAME}/lights", timeout=5)
        lights = r.json()
    except Exception:
        return False
    state = {"on": on}
    if bri  is not None: state["bri"] = bri
    if hue  is not None: state["hue"] = hue
    if sat  is not None: state["sat"] = sat
    for lid in lights:
        try:
            requests.put(f"http://{HUE_BRIDGE_IP}/api/{HUE_USERNAME}/lights/{lid}/state",
                         json=state, timeout=3)
        except Exception:
            pass
    return True

def control_hue(command, arg, profile):
    global HUE_BRIDGE_IP, HUE_USERNAME
    if not HUE_BRIDGE_IP: HUE_BRIDGE_IP = profile.get("hue_bridge_ip")
    if not HUE_USERNAME:  HUE_USERNAME  = profile.get("hue_username")
    if not HUE_BRIDGE_IP:
        return ("No Hue bridge found on your network. "
                "Check it's connected, then add 'hue_bridge_ip' to user_profile.json "
                "(find it with: curl -s https://discovery.meethue.com)")
    if not HUE_USERNAME:
        return ("Hue bridge found but no API user configured. "
                "Press the button on the bridge, then run: "
                f"curl -X POST http://{HUE_BRIDGE_IP}/api -d '{{\"devicetype\":\"newt\"}}' "
                "and add the returned username as 'hue_username' in user_profile.json.")
    if   command == "on":     _hue_set_all(True,  bri=254);        return "Lights on."
    elif command == "off":    _hue_set_all(False);                   return "Lights off."
    elif command == "dim":    _hue_set_all(True,  bri=64);          return "Lights dimmed."
    elif command == "colour" and arg:
        h, b, s = arg
        _hue_set_all(True, hue=h, bri=b, sat=s);                   return "Lights updated."
    return "Didn't understand that light command."

# ── APPLESCRIPT HELPER ────────────────────────────────────

def _osascript(script):
    """Run an AppleScript snippet and return stdout, or None on failure."""
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None

# ── SPOTIFY (APPLESCRIPT) ─────────────────────────────────

def _spotify_running():
    result = _osascript('application "Spotify" is running')
    return result == "true"

def spotify_now_playing():
    script = ('tell application "Spotify"\n'
              '    if player state is playing then\n'
              '        return (name of current track) & " by " & (artist of current track)\n'
              '    else\n'
              '        return ""\n'
              '    end if\n'
              'end tell')
    result = _osascript(script)
    return f"Now playing: {result}" if result else "Nothing is playing right now."

def spotify_play(query=None):
    if not _spotify_running():
        open_app("Spotify")
        time.sleep(2)
    if query:
        import urllib.parse
        subprocess.Popen(["open", f"spotify:search:{urllib.parse.quote(query)}"])
        time.sleep(1.5)
        _osascript('tell application "Spotify" to play')
        return f"Searching Spotify for {query}."
    _osascript('tell application "Spotify" to play')
    return "Resuming Spotify."

def spotify_pause():
    _osascript('tell application "Spotify" to pause')
    return "Paused."

def spotify_next():
    _osascript('tell application "Spotify" to next track')
    time.sleep(0.8)
    return spotify_now_playing()

def spotify_previous():
    _osascript('tell application "Spotify" to previous track')
    time.sleep(0.8)
    return spotify_now_playing()

def spotify_volume(direction):
    current = _osascript('tell application "Spotify" to sound volume')
    try:
        vol = int(current)
    except (TypeError, ValueError):
        vol = 50
    vol = min(100, vol + 20) if direction == "up" else max(0, vol - 20)
    _osascript(f'tell application "Spotify" to set sound volume to {vol}')
    return f"Spotify volume at {vol}%."

def spotify_shuffle(on):
    val = "true" if on else "false"
    _osascript(f'tell application "Spotify" to set shuffling to {val}')
    return f"Shuffle {'on' if on else 'off'}."

def detect_spotify_command(text):
    t = text.lower()
    if any(w in t for w in ["what's playing","whats playing","what song is","now playing",
                             "current song","what are you playing","what song"]):
        return ("now_playing", None)
    if any(w in t for w in ["pause music","pause spotify","pause the music","pause song"]) or t.strip() == "pause":
        return ("pause", None)
    if any(w in t for w in ["resume music","resume spotify","unpause"]) and "play " not in t:
        return ("resume", None)
    if any(w in t for w in ["next song","next track","skip song","skip track"]) or t.strip() == "skip":
        return ("next", None)
    if any(w in t for w in ["previous song","previous track","go back","last song","last track"]):
        return ("previous", None)
    if "shuffle on" in t or "turn on shuffle" in t or "enable shuffle" in t:
        return ("shuffle", True)
    if "shuffle off" in t or "turn off shuffle" in t or "disable shuffle" in t:
        return ("shuffle", False)
    if any(w in t for w in ["music louder","music volume up","turn up the music","spotify volume up"]):
        return ("volume", "up")
    if any(w in t for w in ["music quieter","music volume down","turn down the music","spotify volume down"]):
        return ("volume", "down")
    for prefix in ["play ","put on ","queue "]:
        if prefix in t:
            query = t[t.index(prefix) + len(prefix):].strip().rstrip(".")
            if query and query not in ["spotify","music","song","it","that"]:
                return ("play", query)
    return None

# ── VS CODE (APPLESCRIPT) ─────────────────────────────────

def vscode_analyse_code(profile, mood):
    """Screenshot the screen and ask the vision model to review the visible code."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            fname = f.name
        subprocess.run(["screencapture", "-x", fname], timeout=10)
        with open(fname, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        os.unlink(fname)
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": (
                    "You are Newt, a coding assistant. The user asked for help with their code. "
                    "Look at this VS Code screenshot and: "
                    "1. Identify the language/framework. "
                    "2. Spot any obvious bugs or issues. "
                    "3. Give 1-3 specific, actionable suggestions. "
                    "Be concise — this will be spoken aloud. Max 3 sentences."
                )},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
            ]}],
            max_tokens=250
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Couldn't analyse the code: {e}"

def detect_vscode_command(text):
    t = text.lower()
    # Normalise spoken variations → canonical tokens so every check below is simpler
    for phrase, replacement in [
        ("visual studio code", "vscode"),
        ("visual studio",      "vscode"),
        ("vs code",            "vscode"),
        ("code editor",        "vscode"),
    ]:
        t = t.replace(phrase, replacement)

    if any(w in t for w in ["open vscode","launch vscode","start vscode","open code",
                             "launch code","start code"]):
        return ("open", None)
    if any(w in t for w in ["new file in vscode","new vscode file","create new file in vscode",
                             "new file in code","create new file in code","new code file"]):
        return ("new_file", None)
    if any(w in t for w in ["save file in vscode","save in vscode","save the file in vscode",
                             "save in code","save the file in code"]):
        return ("save", None)
    if any(w in t for w in ["open terminal in vscode","vscode terminal","terminal in vscode",
                             "open terminal in code","terminal in code"]):
        return ("terminal", None)
    if any(w in t for w in ["run code in vscode","run in vscode","run the code in vscode",
                             "run in code","run the code in code"]):
        return ("run", None)
    if any(w in t for w in ["help me with this code","analyse my vscode","analyze my code",
                             "look at my code","what's wrong with my code",
                             "whats wrong with my code","help with my code"]):
        return ("analyse", None)
    return None

def handle_vscode_command(cmd, profile, mood):
    if cmd == "open":
        subprocess.run(["open", "-a", "Visual Studio Code"])
        return "Opening VS Code."
    _vscode_scripts = {
        "new_file": ('tell application "Visual Studio Code" to activate\n'
                     'delay 0.3\n'
                     'tell application "System Events" to keystroke "n" using {command down}'),
        "save":     ('tell application "Visual Studio Code" to activate\n'
                     'delay 0.3\n'
                     'tell application "System Events" to keystroke "s" using {command down}'),
        "terminal": ('tell application "Visual Studio Code" to activate\n'
                     'delay 0.3\n'
                     'tell application "System Events" to key code 96 using {control down}'),
        "run":      ('tell application "Visual Studio Code" to activate\n'
                     'delay 0.3\n'
                     'tell application "System Events" to key code 96'),
    }
    _vscode_responses = {
        "new_file": "New file created.",
        "save": "File saved.",
        "terminal": "Terminal opened in VS Code.",
        "run": "Running code in VS Code.",
    }
    if cmd in _vscode_scripts:
        _osascript(_vscode_scripts[cmd])
        return _vscode_responses[cmd]
    if cmd == "analyse":
        speak("Let me take a look at your code.")
        return vscode_analyse_code(profile, mood)
    return ""

# ── XCODE (APPLESCRIPT) ───────────────────────────────────

def xcode_show_errors(profile, mood):
    """Screenshot Xcode and read build errors via the vision model."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            fname = f.name
        subprocess.run(["screencapture", "-x", fname], timeout=10)
        with open(fname, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        os.unlink(fname)
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": (
                    "You are Newt, an iOS/macOS coding assistant. Look at this Xcode screenshot. "
                    "Read any visible build errors or warnings. "
                    "For each error give a plain-English description and a suggested fix. "
                    "Be concise — spoken aloud. Max 4 sentences."
                )},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
            ]}],
            max_tokens=300
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Couldn't read Xcode errors: {e}"

def detect_xcode_command(text):
    t = text.lower()
    if any(w in t for w in ["open xcode","launch xcode","start xcode"]):
        return ("open", None)
    if any(w in t for w in ["build project","build in xcode","build the project",
                             "build xcode","xcode build","compile project"]):
        return ("build", None)
    if any(w in t for w in ["run app","run the app","run in xcode","xcode run",
                             "run project","run xcode"]):
        return ("run", None)
    if any(w in t for w in ["stop running","stop xcode","stop the app","stop app","halt xcode"]):
        return ("stop", None)
    if any(w in t for w in ["show errors","xcode errors","build errors","what are the errors",
                             "read errors","check errors","any errors"]):
        return ("errors", None)
    return None

def handle_xcode_command(cmd, profile, mood):
    if cmd == "open":
        open_app("Xcode")
        return "Opening Xcode."
    _xcode_scripts = {
        "build": ('tell application "Xcode" to activate\n'
                  'delay 0.3\n'
                  'tell application "System Events" to keystroke "b" using {command down}'),
        "run":   ('tell application "Xcode" to activate\n'
                  'delay 0.3\n'
                  'tell application "System Events" to keystroke "r" using {command down}'),
        "stop":  ('tell application "Xcode" to activate\n'
                  'delay 0.3\n'
                  'tell application "System Events" to keystroke "." using {command down}'),
    }
    _xcode_responses = {"build": "Building project.", "run": "Running app.", "stop": "Stopped."}
    if cmd in _xcode_scripts:
        _osascript(_xcode_scripts[cmd])
        return _xcode_responses[cmd]
    if cmd == "errors":
        speak("Let me check the errors.")
        return xcode_show_errors(profile, mood)
    return ""

# ── GOOGLE SEARCH ─────────────────────────────────────────

def google_search(query, profile, mood):
    try:
        from googlesearch import search as gsearch
    except ImportError:
        return ("googlesearch-python isn't installed. Run: pip install googlesearch-python", [])
    print(f"\n🔍 Googling: {query}")
    try:
        urls = list(gsearch(query, num_results=3, sleep_interval=1))
    except Exception as e:
        return (f"Search failed: {e}", [])
    if not urls:
        return ("No results found.", [])
    snippets = []
    for url in urls[:3]:
        try:
            r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            text = re.sub(r'<[^>]+>', ' ', r.text)
            text = re.sub(r'\s+', ' ', text).strip()[:1500]
            snippets.append(f"SOURCE: {url}\n{text}")
        except Exception:
            snippets.append(f"SOURCE: {url}\n(page unavailable)")
    combined = "\n\n---\n\n".join(snippets)
    prompt = (f"Summarise these search results for '{query}' in 2-3 sentences. "
              f"Be conversational — this will be spoken aloud.\n\n{combined}")
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    try:
        r = requests.post(GROQ_URL, json={"model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200, "temperature": 0.5}, headers=headers, timeout=20)
        summary = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        summary = f"Found results but couldn't summarise: {e}"
    return (summary, urls)

def detect_google_command(text):
    t = text.lower().strip()
    for prefix in ["google search for ","google search ","search google for ",
                   "look up ","search for ","google "]:
        if t.startswith(prefix):
            query = t[len(prefix):].strip().rstrip(".")
            if query:
                return query
    return None

# ── APP WATCHER (PROACTIVE) ──────────────────────────────

_focused_app        = ""
_vscode_focus_since = None
_vscode_prompted_at = 0.0
_last_spotify_track = ""
VSCODE_PROMPT_INTERVAL = 30 * 60  # 30 minutes

def get_focused_app():
    return _osascript(
        'tell application "System Events" to get name of first process whose frontmost is true'
    ) or ""

def start_app_watcher(profile):
    def _loop():
        global _focused_app, _vscode_focus_since, _vscode_prompted_at, _last_spotify_track
        while True:
            time.sleep(60)
            if SPEAKING:
                continue
            try:
                app = get_focused_app()
                _focused_app = app

                # VS Code focus: offer code review after 30 uninterrupted minutes
                if any(k in app.lower() for k in ["code", "visual studio"]):
                    if _vscode_focus_since is None:
                        _vscode_focus_since = time.time()
                    elapsed = time.time() - _vscode_focus_since
                    cooldown_ok = (time.time() - _vscode_prompted_at) > VSCODE_PROMPT_INTERVAL
                    if elapsed >= VSCODE_PROMPT_INTERVAL and cooldown_ok:
                        _vscode_prompted_at = time.time()
                        name = profile.get("name", "")
                        msg = (f"Still coding{' ' + name if name else ''}? "
                               f"Want me to review what you've written?")
                        print(f"\n💡 Newt: {msg}")
                        speak(msg)
                else:
                    _vscode_focus_since = None

                # Spotify: print track-change notifications to console
                if _spotify_running():
                    script = ('tell application "Spotify"\n'
                              '    if player state is playing then\n'
                              '        return (name of current track) & " by " & (artist of current track)\n'
                              '    end if\n'
                              '    return ""\n'
                              'end tell')
                    track = _osascript(script) or ""
                    if track and track != _last_spotify_track:
                        _last_spotify_track = track
                        print(f"\n🎵 Now playing: {track}")

            except Exception:
                pass
    threading.Thread(target=_loop, daemon=True).start()

# ── PROACTIVE CHECK-IN ────────────────────────────────────

last_user_at = time.time()
CHECKIN_INTERVAL = 45 * 60  # 45 minutes in seconds

def start_checkin_thread(profile):
    def _run():
        global last_user_at
        while True:
            time.sleep(60)
            if time.time() - last_user_at >= CHECKIN_INTERVAL and not SPEAKING:
                last_user_at = time.time()  # reset so it doesn't fire every minute
                name = profile.get("name", "")
                msg = f"Still there{' ' + name if name else ''}? Let me know if you need anything."
                print(f"\n⏰ Newt: {msg}")
                speak(msg)
    threading.Thread(target=_run, daemon=True).start()

# ── STARTUP ───────────────────────────────────────────────

profile = load_profile()
if profile.get("city"):
    CITY = profile["city"]
# Init Hue from saved profile (background discovery if not yet found)
HUE_BRIDGE_IP = profile.get("hue_bridge_ip")
HUE_USERNAME  = profile.get("hue_username")
if not HUE_BRIDGE_IP:
    threading.Thread(target=_discover_hue_bg, args=(profile,), daemon=True).start()
# Start proactive check-in background thread
start_checkin_thread(profile)
# Start app watcher (VS Code focus, Spotify track changes)
start_app_watcher(profile)
mem_count = memory.count()
now = datetime.datetime.now()
hour = now.hour
greeting = "Morning" if hour < 12 else "Afternoon" if hour < 17 else "Evening"
name_str = f", {profile['name']}" if profile.get('name') else ""

print("\n" + "="*50)
print("  Newt - Your AI Assistant")
print(f"  🧠 Memory: {mem_count} memories loaded")
print(f"  👤 Profile: {profile.get('name') or 'learning about you...'}")
print(f"  ⚡ Groq + ElevenLabs")
print(f"  🌤️  Weather: {CITY}")
print(f"  👂 Wake word: 'Hey Newt'")
print("  Ctrl+C = type instead")
print("="*50 + "\n")

def build_intro(profile, now, greeting):
    name = profile.get('name')
    name_str = f" {name}" if name else ""

    # natural time string: "6:30pm" / "12:05am"
    time_str = now.strftime("%-I:%M%p").lower()  # e.g. "6:30pm"

    # natural date: "Friday the 11th"
    day_name = now.strftime("%A")
    day_num = int(now.strftime("%d"))
    suffix = "th" if 11 <= day_num <= 13 else {1:"st",2:"nd",3:"rd"}.get(day_num % 10, "th")
    date_str = f"{day_name} the {day_num}{suffix}"

    weather_str = get_weather()

    # Pull today's calendar events (non-blocking best-effort)
    today_events = []
    try:
        today_events = get_calendar_events(days=1)
    except Exception:
        pass
    calendar_str = ""
    if today_events:
        titles = ", ".join(e["title"] for e in today_events[:3])
        calendar_str = f"Today's calendar: {titles}."

    if not name:
        return f"Good {greeting}! I'm Newt, your personal AI assistant. What's your name?"

    # ask the AI for a natural opener using all the context
    context = f"""You are Newt, a witty personal AI assistant. Write a natural spoken greeting for {name}.

Include ALL of these in order, flowing naturally as one or two sentences:
1. "Good {greeting}{name_str}"
2. The time and date: it's {time_str} on {date_str}
3. The weather: {weather_str}
{f"4. Casually mention today's events if relevant: {calendar_str}" if calendar_str else ""}
4. A short witty conversational closer (1 sentence) — make it specific to the day/time/weather.
   Never say "What are we doing today?" or "How can I help?". Be like a smart friend, not a customer service bot.

Return only the spoken greeting, nothing else. Keep it under 4 sentences total."""

    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(GROQ_URL, json={"model": MODEL,
                          "messages": [{"role":"user","content":context}],
                          "max_tokens": 120, "temperature": 1.0},
                          headers=headers, timeout=10)
        return r.json()["choices"][0]["message"]["content"].strip().strip('"')
    except:
        return f"Good {greeting}{name_str}. It's {time_str} on {date_str}. {weather_str}"

intro = build_intro(profile, now, greeting)
speak(intro)
print(f"Newt: {intro}\n")
mac_notification("Newt", f"Good {greeting}{name_str}!")

last_code = None
last_filename = None
USE_WAKE_WORD = True
pending_input = None
_last_google_urls = []

# stay awake after intro
print("\n👂 Still listening...")
first = get_input()
if first and first.strip():
    USE_WAKE_WORD = False
    mood = detect_mood(first)
    track_mood(mood)
    save_mood_history(profile, mood)
    last_user_at = time.time()
    if is_goodbye(first):
        farewell = smart_goodbye(profile)
        print(f"\nNewt: {farewell}")
        speak(farewell)
        save_session_log(profile)
        save_profile(profile)
        exit()
    else:
        print(f"\n💬 Processing: \"{first}\" [mood: {mood}]")
        if is_weather_query(first):
            print("\n🌤️  Getting weather...")
            resp = get_weather()
            print(f"\nNewt: {resp}")
            speak(resp)
            last_response = resp
            save_memory(first, resp)
        else:
            print("\n🤖 Newt thinking...")
            resp = ask_newt(first, profile, mood)
            print(f"\nNewt: {resp}\n")
            last_code = extract_code(resp)
            last_filename = extract_filename(resp)
            if last_code:
                print("💾 Code ready — say 'run it' or 'save it'\n")
                speak("Code is ready. Run it or save it.")
            else:
                speak(resp)
                last_response = resp

while True:
    try:
        if pending_input:
            user_input = pending_input
            pending_input = None
        elif USE_WAKE_WORD:
            result = wait_for_wake_word()
            if isinstance(result, str) and result:
                user_input = result
            else:
                speak("Yeah?")
                print("\n✅ Newt activated!")
                user_input = get_input()
        else:
            user_input = get_input()

        if not user_input or not user_input.strip():
            continue

        # filler words
        if user_input.lower().strip() in ["um","uh","hmm","hm","err","ah","oh","um...","uh..."]:
            continue

        mood = detect_mood(user_input)
        track_mood(mood)
        save_mood_history(profile, mood)
        last_user_at = time.time()
        check_mood_proactive(profile)
        print(f"\n💬 Processing: \"{user_input}\" [mood: {mood}]")

        # goodbye
        if is_goodbye(user_input):
            farewell = smart_goodbye(profile)
            print(f"\nNewt: {farewell}")
            speak(farewell)
            save_session_log(profile)
            save_profile(profile)
            break

        if "wake word off" in user_input.lower():
            USE_WAKE_WORD = False; speak("Wake word off."); continue

        if "wake word on" in user_input.lower():
            USE_WAKE_WORD = True; speak("Wake word on."); continue

        # repeat last response
        if is_repeat_command(user_input):
            if last_response:
                speak(last_response)
            else:
                speak("Nothing to repeat yet.")
            continue

        # reminder
        reminder = detect_reminder(user_input)
        if reminder:
            task, seconds = reminder
            set_reminder(task, seconds, profile)
            mins = seconds // 60
            unit_str = f"{seconds}s" if seconds < 60 else (f"{mins}m" if mins < 60 else f"{mins//60}h {mins%60}m")
            resp = f"Got it. I'll remind you to {task} in {unit_str}."
            print(f"\nNewt: {resp}")
            speak(resp)
            last_response = resp
            continue

        # city change
        new_city = detect_city_change(user_input)
        if new_city:
            CITY = new_city
            profile["city"] = new_city
            save_profile(profile)
            response = f"Done. Weather location updated to {new_city}."
            print(f"\nNewt: {response}")
            speak(response)
            continue

        # scan projects
        if is_scan_command(user_input):
            files = scan_projects()
            print(f"\n{summarise_projects(files)}")
            file_list = "\n".join([f"{f['name']} (modified {f['modified_str']})" for f in files[:20]])
            suggestions = ask_newt(f"Based on these files give 3-5 specific suggestions:\n{file_list}", profile, mood)
            print(f"\n💡 {suggestions}\n")
            speak("Here are my suggestions. Check the screen.")
            continue

        # save code
        if is_save_command(user_input) and last_code:
            path = save_project(last_code, last_filename)
            print(f"\n💾 Saved to: {path}")
            speak(f"Saved as {last_filename}.")
            continue

        # run code
        if is_run_command(user_input) and last_code:
            print("\n▶️  Running code...")
            output = run_code(last_code)
            print(f"\n📤 Output:\n{output}")
            if "Traceback" in output or "Error:" in output:
                speak("Hit an error. Fixing it.")
                fixed = auto_fix(last_code, output, profile, mood)
                if fixed:
                    output2 = run_code(fixed)
                    print(f"\n📤 Fixed output:\n{output2}")
                    speak(f"Fixed. {output2[:150]}")
                    last_code = fixed
                else:
                    speak("Couldn't auto fix that one.")
            else:
                speak(f"Done. {output[:150]}")
                last_code = None
            continue

        # weather — check FIRST before anything else
        if is_weather_query(user_input):
            print("\n🌤️  Getting weather...")
            result = get_weather()
            print(f"\nNewt: {result}")
            speak(result)
            last_response = result
            save_memory(user_input, result)
            continue

        # news
        if is_news_query(user_input):
            print("\n📰 Getting news...")
            result = get_news()
            print(f"\nTop headlines:\n{result}")
            spoken = "Here are today's top headlines. " + result.split("\n")[0].replace("1.","").strip()[:200]
            speak(spoken)
            last_response = spoken
            save_memory(user_input, result)
            continue

        # wikipedia
        if is_wikipedia_query(user_input):
            t = user_input.lower()
            query = t.replace("who is","").replace("who was","").replace("what is","").replace("what was","").replace("tell me about","").replace("wikipedia","").replace("explain","").strip()
            print(f"\n📖 Searching Wikipedia for: {query}")
            result = search_wikipedia(query)
            print(f"\nNewt: {result}")
            speak(result[:400])
            last_response = result[:400]
            save_memory(user_input, result)
            continue

        # time and date
        t = user_input.lower()
        if any(w in t for w in ["what time","what's the time","whats the time","what date","what day","today's date"]):
            now2 = datetime.datetime.now()
            response = f"It's {now2.strftime('%I:%M %p')} on {now2.strftime('%A, %B %d %Y')}."
            print(f"\nNewt: {response}"); speak(response)
            last_response = response
            continue

        # spotify
        spotify_cmd = detect_spotify_command(user_input)
        if spotify_cmd:
            cmd, arg = spotify_cmd
            if   cmd == "now_playing": result = spotify_now_playing()
            elif cmd == "pause":       result = spotify_pause()
            elif cmd == "resume":      result = spotify_play()
            elif cmd == "next":        result = spotify_next()
            elif cmd == "previous":    result = spotify_previous()
            elif cmd == "play":        result = spotify_play(arg)
            elif cmd == "volume":      result = spotify_volume(arg)
            elif cmd == "shuffle":     result = spotify_shuffle(arg)
            else: result = ""
            if result:
                print(f"\nNewt: {result}")
                speak(result)
                last_response = result
                save_memory(user_input, result)
            continue

        # mac commands
        mac_cmd = detect_mac_command(user_input)
        if mac_cmd:
            cmd, arg = mac_cmd
            result = ""
            if cmd == "open_app": result = open_app(arg); speak(f"Opening {arg}.")
            elif cmd == "volume": result = set_volume(arg); speak(result)
            elif cmd == "search_files":
                files = search_files(arg)
                if files:
                    result = "\n".join(files)
                    print(f"\n📁 Found:\n{result}")
                    speak(f"Found {len(files)} files matching {arg}.")
                else: speak(f"Nothing found matching {arg}.")
            elif cmd == "battery": result = get_battery(); print(f"\n🔋 {result}"); speak(result[:150])
            elif cmd == "list_folder": result = list_folder(arg); print(f"\n📁 Contents:\n{result}"); speak(f"Showing {arg}.")
            elif cmd == "email":
                to = input("⌨️  To: "); subject = input("⌨️  Subject: "); body = input("⌨️  Message: ")
                result = send_email(to, subject, body); speak(result)
            elif cmd == "message":
                to = input("⌨️  To: "); msg = input("⌨️  Message: ")
                result = send_imessage(to, msg); speak(result)
            elif cmd == "system_info": result = get_system_info(); print(f"\n🖥️  {result}"); speak("System info on screen.")
            save_memory(user_input, result)
            continue

        # screen reader
        if is_screen_query(user_input):
            print("\n📸 Reading screen...")
            speak("Let me take a look.")
            result = read_screen(profile, mood)
            print(f"\nNewt: {result}")
            speak(result)
            last_response = result
            save_memory(user_input, result)
            continue

        # calendar
        if is_calendar_query(user_input):
            print("\n📅 Checking calendar...")
            events = get_calendar_events(days=7)
            printed = format_calendar_printed(events)
            print(f"\n{printed}")
            spoken = format_calendar_spoken(events)
            speak(spoken)
            last_response = spoken
            save_memory(user_input, printed)
            continue

        # code review
        if is_review_command(user_input):
            review_code(profile, mood)
            continue

        # smart home (Hue)
        hue_cmd = detect_hue_command(user_input)
        if hue_cmd:
            cmd, arg = hue_cmd
            result = control_hue(cmd, arg, profile)
            print(f"\nNewt: {result}")
            speak(result)
            last_response = result
            continue

        # open search result in Safari ("open that" / "open first result")
        t_low = user_input.lower()
        if _last_google_urls and any(w in t_low for w in ["open that","open it","open the first","open first result","open result"]):
            url = _last_google_urls[0]
            subprocess.Popen(["open", "-a", "Safari", url])
            result = f"Opening in Safari."
            print(f"\nNewt: {result}")
            speak(result)
            continue

        # vs code
        vscode_cmd = detect_vscode_command(user_input)
        if vscode_cmd:
            cmd, _ = vscode_cmd
            result = handle_vscode_command(cmd, profile, mood)
            if result:
                print(f"\nNewt: {result}")
                speak(result)
                last_response = result
                save_memory(user_input, result)
            continue

        # xcode
        xcode_cmd = detect_xcode_command(user_input)
        if xcode_cmd:
            cmd, _ = xcode_cmd
            result = handle_xcode_command(cmd, profile, mood)
            if result:
                print(f"\nNewt: {result}")
                speak(result)
                last_response = result
                save_memory(user_input, result)
            continue

        # google search
        google_query = detect_google_command(user_input)
        if google_query:
            summary, urls = google_search(google_query, profile, mood)
            print(f"\nNewt: {summary}")
            if urls:
                print("\nTop results:")
                for i, u in enumerate(urls[:3], 1):
                    print(f"  {i}. {u}")
                _last_google_urls[:] = urls
                print('\nSay "open that" to open the first result in Safari.')
            speak(summary)
            last_response = summary
            save_memory(user_input, summary)
            continue

        # ask newt AI
        print("\n🤖 Newt thinking...")
        response = ask_newt(user_input, profile, mood)
        print(f"\nNewt: {response}\n")
        last_code = extract_code(response)
        last_filename = extract_filename(response)
        if last_code:
            print("💾 Code ready — say 'run it' or 'save it'\n")
            speak("Code is ready. Run it or save it.")
        else:
            speak(response)
            last_response = response

        # stay awake for follow up
        print("\n👂 Still listening...")
        followup = get_input()
        if followup and followup.strip():
            if is_goodbye(followup):
                farewell = smart_goodbye(profile)
                print(f"\nNewt: {farewell}")
                speak(farewell)
                save_session_log(profile)
                save_profile(profile)
                break
            pending_input = followup
            USE_WAKE_WORD = False
        else:
            USE_WAKE_WORD = True

    except KeyboardInterrupt:
        print("\n")
        farewell = smart_goodbye(profile)
        speak(farewell)
        save_session_log(profile)
        save_profile(profile)
        break
