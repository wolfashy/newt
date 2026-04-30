import subprocess, requests, os, tempfile, wave, datetime, threading, time, json
from pathlib import Path

# ── KEYS ─────────────────────────────────────────────────
GROQ_API_KEY = "YOUR_GROQ_KEY"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
ELEVENLABS_API_KEY = "YOUR_ELEVENLABS_KEY"
ELEVENLABS_VOICE_ID = "nPczCjzI2devNBz1zQrb"
WEATHER_KEY = "YOUR_WEATHER_KEY"
NEWS_KEY = "YOUR_NEWS_KEY"
CITY = "Melbourne"
MODEL = "llama-3.3-70b-versatile"
HISTORY = []
PROJECTS_DIR = Path.home() / "Desktop" / "jarvis" / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
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
            "facts_learned": [], "conversation_count": 0}

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

def speak(text):
    clean = text.replace('`','').replace('"','').replace('#','')
    clean = ' '.join(clean.split())[:400]
    try:
        headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
        payload = {"text": clean, "model_id": "eleven_turbo_v2_5",
                  "voice_settings": {"stability": 0.4, "similarity_boost": 0.8, "style": 0.3}}
        r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
                         json=payload, headers=headers)
        if r.status_code == 200:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp.write(r.content); fname = tmp.name
            subprocess.run(["afplay", fname])
            os.unlink(fname)
        else:
            subprocess.run(["say", "-v", "Daniel", clean])
    except:
        subprocess.run(["say", "-v", "Daniel", clean])

def record_audio(seconds=6):
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

def get_input(prompt_text="What should Newt do? "):
    print(f"\n🎤 Speak now (6 sec) — or press Ctrl+C to type")
    print("🔴 Recording...", flush=True)
    try:
        frames = record_audio(seconds=6)
        text = transcribe(frames)
        if len(text) < 3:
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
            text = transcribe(frames).lower()
            if any(w in text for w in ["hey newt","hey neat","hey nude","hey new","a newt","newt",
                "noot","hey noot","nood","hey nood","nut","hey nut","nuit","hey nuit",
                "hey knight","hey mate","hey nate","nate","moot","hey moot","hey note"]):
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
    return any(w in t for w in ["weather","temperature","forecast","how hot","how cold","raining","rain today","sunny"])

def is_news_query(text):
    t = text.lower()
    return any(w in t for w in ["news","headlines","whats happening","what's happening","in the news"])

def is_wikipedia_query(text):
    t = text.lower()
    return any(w in t for w in ["who is","who was","what is","what was","tell me about","wikipedia","explain "])

# ── MAC POWERS ────────────────────────────────────────────

def open_app(app_name):
    try:
        subprocess.run(["open", "-a", app_name], check=True)
        return f"Opened {app_name}"
    except:
        return f"Couldn't find {app_name}"

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
        # Catch all spoken variations of VS Code before the single-word loop
        if any(p in t for p in ["visual studio code","visual studio","vs code","vscode",
                                  "code editor"]):
            return ("open_app", "Visual Studio Code")
        for app in ["safari","chrome","firefox","finder","terminal","code","spotify",
                    "music","mail","messages","notes","calendar","photos","slack","zoom","discord"]:
            if app in t: return ("open_app", app.title())
        words = t.replace("open","").replace("launch","").replace("start","").strip()
        if words: return ("open_app", words.title())
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
    msgs = [{"role": "system", "content": f"""You are Newt, a brilliant personal AI assistant on the user's Mac.
You have a genuine personality — confident, clever, warm, occasionally funny, always real.
You talk like a smart friend. You remember the user and reference things naturally.
You have opinions and share them when asked.
MOOD: {mood_block}
{profile_block}
{memory_block}
RULES:
- For simple questions answer directly in plain English — NO code unless asked to BUILD something
- Only write code when asked to BUILD or CREATE something
- When writing code: never use input(), use hardcoded values, add FILENAME: name.py before code
- Keep responses conversational and concise
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

# ── STARTUP ───────────────────────────────────────────────

profile = load_profile()
mem_count = memory.count()
now = datetime.datetime.now()
hour = now.hour
greeting = "Morning" if hour < 12 else "Afternoon" if hour < 17 else "Evening"
name_str = f", {profile['name']}" if profile.get('name') else ""

print("\n" + "="*50)
print("  Newt - Your AI Assistant")
print(f"  🧠 Memory: {mem_count} memories loaded")
print(f"  👤 Profile: {profile.get('name') or 'learning about you...'}")
print(f"  💬 Conversations: {profile.get('conversation_count', 0)}")
print(f"  ⚡ Groq + ElevenLabs")
print(f"  🌤️  Weather: {CITY}")
print(f"  👂 Wake word: 'Hey Newt'")
print("  Ctrl+C = type instead")
print("="*50 + "\n")

if profile.get('conversation_count', 0) == 0:
    intro = f"{greeting}! I'm Newt, your personal AI assistant. What's your name?"
else:
    intro = f"{greeting}{name_str}. Good to have you back. We've talked {profile['conversation_count']} times. What are we doing today?"

speak(intro)
print(f"Newt: {intro}\n")
mac_notification("Newt", f"{greeting}{name_str}!")

last_code = None
last_filename = None
USE_WAKE_WORD = True

# stay awake after intro
print("\n👂 Still listening...")
first = get_input()
if first and first.strip():
    USE_WAKE_WORD = False
    mood = detect_mood(first)
    if not is_goodbye(first):
        print(f"\n💬 Processing: \"{first}\" [mood: {mood}]")
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

while True:
    try:
        if USE_WAKE_WORD:
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
        print(f"\n💬 Processing: \"{user_input}\" [mood: {mood}]")

        # goodbye
        if is_goodbye(user_input):
            name2 = profile.get('name','')
            speak(f"Later {name2}. Good session today.")
            save_profile(profile)
            break

        if "wake word off" in user_input.lower():
            USE_WAKE_WORD = False; speak("Wake word off."); continue

        if "wake word on" in user_input.lower():
            USE_WAKE_WORD = True; speak("Wake word on."); continue

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
            save_memory(user_input, result)
            continue

        # news
        if is_news_query(user_input):
            print("\n📰 Getting news...")
            result = get_news()
            print(f"\nTop headlines:\n{result}")
            speak("Here are today's top headlines. " + result.split("\n")[0].replace("1.","").strip()[:200])
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
            save_memory(user_input, result)
            continue

        # time and date
        t = user_input.lower()
        if any(w in t for w in ["what time","what's the time","whats the time","what date","what day","today's date"]):
            now2 = datetime.datetime.now()
            response = f"It's {now2.strftime('%I:%M %p')} on {now2.strftime('%A, %B %d %Y')}."
            print(f"\nNewt: {response}"); speak(response)
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

        # stay awake for follow up
        print("\n👂 Still listening...")
        followup = get_input()
        if followup and followup.strip():
            if is_goodbye(followup):
                name2 = profile.get('name','')
                speak(f"Later {name2}. Good session.")
                save_profile(profile)
                break
            user_input = followup
            USE_WAKE_WORD = False
            continue
        else:
            USE_WAKE_WORD = True

    except KeyboardInterrupt:
        print("\n")
        speak("Later. Good session.")
        save_profile(profile)
        break
