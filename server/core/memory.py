from __future__ import annotations
import datetime, json, logging, sqlite3, threading
import chromadb
from core.config import MEMORY_DIR, DB_PATH, PROFILE_PATH, PERSONA_PATH

log = logging.getLogger(__name__)
MEMORY_DIR.mkdir(parents=True, exist_ok=True)
_mem_client = chromadb.PersistentClient(path=str(MEMORY_DIR))
collection = _mem_client.get_or_create_collection("newt_memory")

def save_memory(user_msg, response):
    doc = f"User: {user_msg}\nNewt: {response}"
    doc_id = f"mem_{datetime.datetime.now().timestamp()}"
    metadata = {"timestamp": datetime.datetime.now().isoformat(), "topic": _detect_topic(user_msg)}
    try:
        if collection.count() > 0:
            existing = collection.query(query_texts=[user_msg], n_results=1)
            if existing and existing["documents"][0]:
                if _sim(doc, existing["documents"][0][0]) > 0.85:
                    collection.update(ids=[existing["ids"][0][0]], documents=[doc], metadatas=[metadata]); return
    except: pass
    collection.add(documents=[doc], ids=[doc_id], metadatas=[metadata])

def recall_memory(query, n=5):
    try:
        count = collection.count()
        if count == 0: return ""
        results = collection.query(query_texts=[query], n_results=min(n*2, count))
        if not results or not results["documents"][0]: return ""
        docs = results["documents"][0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        now = datetime.datetime.now()
        scored = []
        for i, doc in enumerate(docs):
            d = dists[i] if i < len(dists) else 1.0
            meta = metas[i] if i < len(metas) else {}
            age = 0
            if meta and meta.get("timestamp"):
                try: age = (now - datetime.datetime.fromisoformat(meta["timestamp"])).days
                except: pass
            scored.append((d * (1 + age/60), doc))
        scored.sort(key=lambda x: x[0])
        return "\n---\n".join(doc for _, doc in scored[:n])
    except: return ""

def _detect_topic(text):
    t = text.lower()
    for topic, kws in {"work": ["meeting","project","deadline"], "health": ["exercise","sleep","gym"], "music": ["song","play","spotify"], "finance": ["price","stock","crypto"]}.items():
        if any(k in t for k in kws): return topic
    return "general"

def _sim(a, b):
    wa, wb = set(a.lower().split()), set(b.lower().split())
    return len(wa & wb) / len(wa | wb) if wa and wb else 0

def memory_count(): return collection.count()

_db_lock = threading.Lock()
_conn = None
def db():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT)")
        _conn.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT, role TEXT, content TEXT, created_at TEXT)")
        _conn.commit()
    return _conn

def save_message(conv_id, role, content):
    now = datetime.datetime.now().isoformat()
    with _db_lock:
        c = db()
        c.execute("INSERT OR IGNORE INTO conversations VALUES (?,?,?)", (conv_id, now, now))
        c.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conv_id))
        c.execute("INSERT INTO messages (conversation_id,role,content,created_at) VALUES (?,?,?,?)", (conv_id, role, content, now))
        c.commit()

def get_conversation(conv_id, limit=20):
    with _db_lock:
        rows = db().execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?", (conv_id, limit)).fetchall()
    return [{"role": r, "content": c} for r, c in reversed(rows)]

def load_profile():
    if PROFILE_PATH.exists():
        with open(PROFILE_PATH) as f: return json.load(f)
    return {"name": "Ethan", "city": "Geelong"}

def save_profile(p):
    with open(PROFILE_PATH, "w") as f: json.dump(p, f, indent=2)

def load_persona():
    if PERSONA_PATH.exists():
        try: return json.loads(PERSONA_PATH.read_text())
        except: pass
    return {"tone": "warm", "facts": []}

def save_persona(data):
    try: PERSONA_PATH.write_text(json.dumps(data, indent=2)); return True
    except: return False

def persona_system_prefix():
    p = load_persona()
    parts = []
    tone = p.get("tone", "")
    tones = {"warm": "Warm and brief.", "terse": "Very concise.", "witty": "Dry wit.", "formal": "Formal.", "playful": "Playful."}
    if tone: parts.append(tones.get(tone, f"Tone: {tone}"))
    facts = p.get("facts", [])
    if facts: parts.append("Known facts:\n" + "\n".join(f"- {f}" for f in facts))
    return "\n".join(parts) + "\n\n" if parts else ""
