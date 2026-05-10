from __future__ import annotations
import json, re, time, logging
from typing import Any
from openai import OpenAI
from core.config import GROQ_API_KEY, GROQ_BASE_URL, GROQ_CHAT_MODEL, GROQ_FALLBACK_MODEL, GROQ_VISION_MODEL

log = logging.getLogger(__name__)
_client = None

def client():
    global _client
    if _client is None: _client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
    return _client

def chat(messages, *, tools=None, model=None, max_tokens=1024, temperature=0.85):
    model = model or GROQ_CHAT_MODEL
    kwargs = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    if tools: kwargs["tools"] = tools; kwargs["parallel_tool_calls"] = False
    for attempt in range(3):
        try:
            return client().chat.completions.create(**kwargs).choices[0].message
        except Exception as e:
            err = str(e)
            if attempt < 2 and ("rate_limit" in err.lower() or "429" in err):
                time.sleep(2 ** attempt); continue
            if attempt == 0 and model == GROQ_CHAT_MODEL:
                kwargs["model"] = GROQ_FALLBACK_MODEL
                kwargs.pop("tools", None); kwargs.pop("parallel_tool_calls", None); continue
            raise

def chat_text(messages, **kw):
    return (chat(messages, **kw).content or "")

def parse_llama_tool_call(text):
    m = re.search(r"<function=([A-Za-z_]\w*)\s+(\{.*?\})\s*</function>", text, re.DOTALL)
    if m:
        try: args = json.loads(m.group(2))
        except: args = {}
        return m.group(1), _flatten_args(args)
    m2 = re.search(r"failed_generation[\'\":\s]+(\[.*?\])", text, re.DOTALL)
    if m2:
        raw = m2.group(1).replace("\\n", " ").replace("\n", " ")
        try:
            calls = json.loads(raw)
            if isinstance(calls, list) and calls:
                c = calls[0]; name = c.get("name"); args = c.get("parameters") or c.get("arguments") or {}
                if name: return name, _flatten_args(args)
        except: pass
    return None, {}

def _flatten_args(args):
    flat = {}
    for k, v in args.items():
        flat[k] = v[k] if isinstance(v, dict) and k in v else v
    return flat
