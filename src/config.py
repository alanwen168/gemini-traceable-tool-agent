"""Central config loaded from environment (.env in dev, Space secrets in prod)."""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv optional at runtime
    pass


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# --- Gemini runtime ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

# --- Phoenix tracing backend ---
PHOENIX_COLLECTOR_ENDPOINT = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "").strip().rstrip("/")
PHOENIX_API_KEY = os.getenv("PHOENIX_API_KEY", "").strip()
PHOENIX_PROJECT_NAME = os.getenv("PHOENIX_PROJECT_NAME", "gemini-traceable-tool-agent").strip()

# --- Agent / demo guardrails ---
AGENT_MAX_ITERS = _int("AGENT_MAX_ITERS", 5)
TOOL_TIMEOUT_SECONDS = _int("TOOL_TIMEOUT_SECONDS", 12)
DEMO_MAX_INPUT_CHARS = _int("DEMO_MAX_INPUT_CHARS", 1200)
DEMO_DAILY_CALL_LIMIT = _int("DEMO_DAILY_CALL_LIMIT", 120)

# Optional access gate for the hosted demo (so only judges with the credentials can use
# the capped key). If both are set, the Gradio app launches with basic auth. Leave empty
# for an open public demo. Credentials are shared privately in the Devpost submission.
DEMO_AUTH_USER = os.getenv("DEMO_AUTH_USER", "").strip()
DEMO_AUTH_PASSWORD = os.getenv("DEMO_AUTH_PASSWORD", "").strip()


def demo_auth():
    if DEMO_AUTH_USER and DEMO_AUTH_PASSWORD:
        return (DEMO_AUTH_USER, DEMO_AUTH_PASSWORD)
    return None

# Domains the web_fetch tool may touch (SSRF guard). Tight on purpose.
WEB_FETCH_ALLOWLIST = (
    "ai.google.dev",
    "arize.com",
    "docs.arize.com",
    "github.com",
    "raw.githubusercontent.com",
    "arxiv.org",
)


def gemini_ready() -> bool:
    return bool(GEMINI_API_KEY)


def phoenix_ready() -> bool:
    return bool(PHOENIX_COLLECTOR_ENDPOINT and PHOENIX_API_KEY)
