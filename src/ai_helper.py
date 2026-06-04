"""Auxiliary-AI router (NOT the core agent runtime — that stays Gemini).

Used for secondary AI features: LLM-as-judge evals, content review, etc.
Provider order (per project policy 2026-06-04 — save Claude/Codex quota):
  1. gemini CLI    — `gemini -p` (local if on openclaw, else `ssh alanwen@openclaw`).
     claude/codex CLIs are intentionally NOT used for sub-tasks.
  2. China APIs    — Qwen / Doubao / DeepSeek via the OpenAI-compatible Shanghai proxies
     (Tailscale-only). For Chinese copy these go FIRST.
  3. Gemini API    — last-resort fallback so the product still works where neither
     openclaw nor the Tailscale proxies are reachable (e.g. Hugging Face Spaces).

Every layer is optional & guarded; call_ai never raises for "unavailable", it falls
through and finally returns a clear message if nothing is reachable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import List, Optional

from . import config

OPENCLAW_HOST = os.getenv("OPENCLAW_HOST", "alanwen@openclaw")

# OpenAI-compatible Shanghai proxies (Tailscale 100.81.181.7). See ~/QianWen README.
# Each proxy has its OWN token; tokens come from env or ~/aipm/credentials/*.env (dev).
_CRED = os.path.expanduser("~/aipm/credentials")
CHINA_PROXIES = {
    # name: (base_url, model, token_env, cred_file, cred_var)
    "qwen": ("http://100.81.181.7:8080/v1", "qwen-plus",
             "QWEN_PROXY_TOKEN", "qianwen_dashscope.env", "PROXY_TOKEN"),
    "doubao": ("http://100.81.181.7:8081/v1", "doubao-1-5-pro-32k-250115",
               "ARK_PROXY_TOKEN", "doubao_volcengine.env", "ARK_PROXY_TOKEN"),
    "deepseek": ("http://100.81.181.7:8082/v1", "deepseek-chat",
                 "DEEPSEEK_PROXY_TOKEN", "deepseek.env", "DEEPSEEK_PROXY_TOKEN"),
}


def _proxy_token(token_env: str, cred_file: str, cred_var: str) -> str:
    if (t := os.getenv(token_env, "").strip()):
        return t
    path = os.path.join(_CRED, cred_file)
    try:
        for line in open(path):
            if line.strip().startswith(cred_var + "="):
                return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return ""


# ----------------------------------------------------------------- layer 1: CLIs
def _cli_call(cli: str, prompt: str, timeout: int = 90) -> Optional[str]:
    """Call an AI CLI either locally (on openclaw) or over ssh. Returns None on failure
    or anything that looks like a rate-limit / quota error."""
    invoke = {"claude": ["claude", "-p"], "codex": ["codex", "exec"],
              "gemini": ["gemini", "-p"]}[cli]
    try:
        if shutil.which(invoke[0]):  # on openclaw: call directly
            cmd = invoke + [prompt]
        else:  # remote
            cmd = ["ssh", "-o", "ConnectTimeout=10", OPENCLAW_HOST] + invoke + [
                _shquote(prompt)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        out = (r.stdout or "").strip()
        err = (r.stderr or "").lower()
        if r.returncode != 0 or any(k in err for k in
                                    ("rate limit", "quota", "429", "overloaded", "exhausted")):
            return None
        return out or None
    except Exception:
        return None


def _shquote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


# ----------------------------------------------------------------- layer 2: China
def _china_call(provider: str, prompt: str, timeout: int = 60) -> Optional[str]:
    cfg = CHINA_PROXIES.get(provider)
    if not cfg:
        return None
    base, model, token_env, cred_file, cred_var = cfg
    token = _proxy_token(token_env, cred_file, cred_var)
    if not token:
        return None
    try:
        import httpx

        r = httpx.post(f"{base}/chat/completions", timeout=timeout,
                       headers={"Authorization": f"Bearer {token}"},
                       json={"model": model, "messages": [{"role": "user", "content": prompt}]})
        if r.status_code == 429:
            return None
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


# ----------------------------------------------------------------- layer 3: Gemini
def _gemini_call(prompt: str, timeout: int = 60) -> Optional[str]:
    if not config.gemini_ready():
        return None
    try:
        from google import genai

        client = genai.Client(api_key=config.GEMINI_API_KEY)
        resp = client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt)
        return (resp.text or "").strip() or None
    except Exception:
        return None


def call_ai(prompt: str, kind: str = "general") -> str:
    """Route an auxiliary-AI prompt. kind: 'code' | 'writing' (Chinese) | 'general'.
    Policy: only `gemini` CLI is used among the openclaw CLIs (claude/codex are reserved);
    China proxies backfill. For 'writing' (Chinese copy) China models go FIRST for 地道中文."""
    if kind == "writing":
        # China models first for native-Chinese phrasing, then gemini CLI.
        for p in ("doubao", "qwen", "deepseek"):
            if (out := _china_call(p, prompt)):
                return out
        if (out := _cli_call("gemini", prompt)):
            return out
    else:
        # gemini CLI first (claude/codex intentionally skipped to save quota), then China.
        if (out := _cli_call("gemini", prompt)):
            return out
        order_cn = ("deepseek", "qwen", "doubao") if kind == "code" else ("qwen", "doubao", "deepseek")
        for p in order_cn:
            if (out := _china_call(p, prompt)):
                return out
    # last resort
    return _gemini_call(prompt) or "[ai_helper: no AI provider reachable]"
