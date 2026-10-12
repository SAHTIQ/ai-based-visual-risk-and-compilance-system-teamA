"""
QUANTA — LLM Client (OpenAI-compatible chat completions)
========================================================
A thin, dependency-light transport for chat models. Talks to ANY provider that
exposes an OpenAI-compatible ``POST {base_url}/chat/completions`` endpoint:

  * Google Gemini  — https://generativelanguage.googleapis.com/v1beta/openai
  * Hugging Face   — https://router.huggingface.co/v1
  * OpenAI         — https://api.openai.com/v1
  * Ollama (local) — http://localhost:11434/v1   (drop-in, no code change)

Only ``requests`` is required (already installed). No provider SDKs.

Provider resolution (first match wins):
  base_url : LLM_BASE_URL | inferred from the key that is present
  api_key  : LLM_API_KEY | GEMINI_API_KEY | HF_TOKEN | HF_API_KEY | OPENAI_API_KEY
  model    : LLM_MODEL | GEMINI_MODEL | HF_MODEL | provider default
"""

import os
import re
import json
import requests

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
HF_BASE_URL = "https://router.huggingface.co/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"
OLLAMA_BASE_URL = "http://localhost:11434/v1"

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_HF_MODEL = "Qwen/Qwen2.5-72B-Instruct"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.IGNORECASE | re.DOTALL)
_THINK_OPEN_RE = re.compile(r"<think\b[^>]*>.*", re.IGNORECASE | re.DOTALL)


def _first_env(*names):
    """Return the first non-empty environment variable among ``names``."""
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return ""


def resolve_config():
    """Resolve the active provider configuration from the environment."""
    api_key = _first_env(
        "LLM_API_KEY", "GEMINI_API_KEY", "HF_TOKEN", "HF_API_KEY", "OPENAI_API_KEY"
    )

    base_url = _first_env("LLM_BASE_URL")
    if not base_url:
        if os.getenv("GEMINI_API_KEY"):
            base_url = GEMINI_BASE_URL
        elif os.getenv("HF_TOKEN") or os.getenv("HF_API_KEY"):
            base_url = HF_BASE_URL
        elif os.getenv("OPENAI_API_KEY"):
            base_url = OPENAI_BASE_URL
        elif os.getenv("OLLAMA_BASE_URL"):
            base_url = os.getenv("OLLAMA_BASE_URL")

    model = _first_env("LLM_MODEL", "GEMINI_MODEL", "HF_MODEL")
    if not model:
        if "generativelanguage" in base_url:
            model = DEFAULT_GEMINI_MODEL
        elif "huggingface" in base_url:
            model = DEFAULT_HF_MODEL
        elif "openai.com" in base_url:
            model = DEFAULT_OPENAI_MODEL
        else:
            model = DEFAULT_GEMINI_MODEL

    planner_model = _first_env("LLM_PLANNER_MODEL", "GEMINI_PLANNER_MODEL", "HF_PLANNER_MODEL")
    if not planner_model:
        if "huggingface" in (base_url or ""):
            planner_model = "meta-llama/Llama-3.1-8B-Instruct"
        else:
            planner_model = model

    enabled_flag = os.getenv("LLM_ENABLED", "true").lower() not in ("false", "0", "no")
    enabled = bool(enabled_flag and api_key and base_url)

    return {
        "enabled": enabled,
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
        "model": model,
        "planner_model": planner_model,
    }


def llm_enabled():
    """True when a provider + key are configured and the LLM is not disabled."""
    return resolve_config()["enabled"]


def provider_info():
    """Human-readable one-liner for boot logs (never exposes the key)."""
    cfg = resolve_config()
    if not cfg["enabled"]:
        return "DISABLED (no API key configured — running grounded template mode)"
    return f"ENABLED · provider={cfg['base_url']} · writer={cfg['model']} · router={cfg['planner_model']}"


def clean_content(text):
    """Strip reasoning-model ``<think>...</think>`` blocks and tidy whitespace."""
    if not text:
        return ""
    text = _THINK_RE.sub("", text)
    text = _THINK_OPEN_RE.sub("", text)  # strip an unterminated trailing block
    return text.strip()


def extract_json(text):
    """
    Extract and parse the first JSON object/array found in ``text``.

    Tolerates ```json fences and surrounding prose. Returns ``None`` when no
    valid JSON can be parsed.
    """
    if not text:
        return None
    cleaned = clean_content(text)
    cleaned = re.sub(r"```(?:json)?", "", cleaned).replace("```", "").strip()

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        if start == -1:
            continue
        depth = 0
        for idx in range(start, len(cleaned)):
            char = cleaned[idx]
            if char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    snippet = cleaned[start:idx + 1]
                    try:
                        return json.loads(snippet)
                    except Exception:
                        break
    return None


from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_SESSION = None

def _get_session():
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=Retry(total=1, backoff_factor=0.2)
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _SESSION = s
    return _SESSION


def chat_complete(messages, model=None, temperature=0.3, max_tokens=1200,
                  timeout=35, response_json=False):
    """
    Execute a chat completion with persistent connection pooling.
    Returns the assistant text, or None on failure.
    """
    cfg = resolve_config()
    if not cfg["enabled"]:
        return None

    payload = {
        "model": model or cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if response_json:
        payload["response_format"] = {"type": "json_object"}

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }

    try:
        session = _get_session()
        response = session.post(
            f"{cfg['base_url']}/chat/completions",
            headers=headers,
            json=payload,
            timeout=(4, timeout),
        )
    except Exception as exc:  # network / timeout / connection refused
        print(f"[LLM] request failed: {exc}")
        return None

    if response.status_code != 200:
        snippet = (response.text or "")[:200].replace("\n", " ")
        print(f"[LLM] HTTP {response.status_code}: {snippet}")
        return None

    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"[LLM] malformed response: {exc}")
        return None

    cleaned = clean_content(content)
    return cleaned or None
