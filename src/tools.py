"""Tool implementations + their Gemini FunctionDeclaration schemas.

Tools (Day-1 vertical slice keeps the first three):
  - calculator            deterministic, no network
  - github_repo_inspect   public GitHub REST, demonstrates an external API tool
  - phoenix_trace_inspect HERO tool — queries Arize Phoenix for the latest trace and
                          summarizes its tool calls (this is the partner-MCP story
                          made part of the product, not just an after-the-fact demo)
  - web_fetch_allowlisted [stretch] tight SSRF-guarded fetch
The final report is NOT a tool: it is the model's last turn, so tool-call accuracy
evals stay honest.
"""
from __future__ import annotations

import ast
import operator
import time
from typing import Any, Callable, Dict, List

import httpx

from . import config, guardrails

# ---------------------------------------------------------------- calculator

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e6):
            raise guardrails.GuardrailError("Exponent/base too large.")  # DoS guard
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _safe_eval(node.operand)
        return v if isinstance(node.op, ast.UAdd) else -v
    raise guardrails.GuardrailError("Unsupported arithmetic expression.")


def calculator(expression: str) -> Dict[str, Any]:
    expr = guardrails.validate_expression(expression)
    value = _safe_eval(ast.parse(expr, mode="eval"))
    return {"expression": expr, "result": value}


# ---------------------------------------------------------------- github_repo_inspect

def github_repo_inspect(repo: str) -> Dict[str, Any]:
    repo = guardrails.validate_repo(repo)
    with httpx.Client(timeout=config.TOOL_TIMEOUT_SECONDS) as c:
        r = c.get(
            f"https://api.github.com/repos/{repo}",
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": "traceable-gemini-agent"},
        )
    if r.status_code == 404:
        raise guardrails.GuardrailError(f"Repo '{repo}' not found.")
    r.raise_for_status()
    d = r.json()
    return {
        "repo": d.get("full_name"),
        "description": d.get("description"),
        "stars": d.get("stargazers_count"),
        "forks": d.get("forks_count"),
        "open_issues": d.get("open_issues_count"),
        "language": d.get("language"),
        "topics": d.get("topics", [])[:8],
        "updated_at": d.get("updated_at"),
        "homepage": d.get("homepage"),
    }


# ---------------------------------------------------------------- phoenix_trace_inspect

def phoenix_trace_inspect(limit: int = 1) -> Dict[str, Any]:
    """Query Arize Phoenix for recent spans in this project and summarize tool calls.
    Honest degradation: if Phoenix isn't configured, say so clearly."""
    limit = max(1, min(int(limit or 1), 10))
    if not config.phoenix_ready():
        return {"status": "phoenix_not_configured",
                "note": "Set PHOENIX_API_KEY + PHOENIX_COLLECTOR_ENDPOINT to inspect traces."}
    # Try the official phoenix client first (most stable across versions)
    try:
        from phoenix.client import Client  # type: ignore

        px = Client(base_url=config.PHOENIX_COLLECTOR_ENDPOINT,
                    api_key=config.PHOENIX_API_KEY)
        df = px.spans.get_spans_dataframe(project_name=config.PHOENIX_PROJECT_NAME,
                                          limit=200)
        if df is None or len(df) == 0:
            return {"status": "no_spans_yet",
                    "note": "No spans recorded in this project yet. Run a task first."}
        tool_rows = df[df["span_kind"].astype(str).str.upper() == "TOOL"] \
            if "span_kind" in df else df
        source = tool_rows if len(tool_rows) else df
        names: List[str] = []
        for col in ("attributes.tool.name", "name"):
            if col in source:
                names = [str(x) for x in source[col].dropna().tolist()][:20]
                break
        return {"status": "ok", "spans_seen": int(len(df)),
                "tool_spans_seen": int(len(tool_rows)),
                "recent_tool_names": names[:10],
                "project": config.PHOENIX_PROJECT_NAME}
    except Exception as e:
        # REST fallback — list spans via the v1 API
        try:
            url = f"{config.PHOENIX_COLLECTOR_ENDPOINT}/v1/projects/{config.PHOENIX_PROJECT_NAME}/spans"
            with httpx.Client(timeout=config.TOOL_TIMEOUT_SECONDS) as c:
                r = c.get(url, params={"limit": 50},
                          headers={"authorization": f"Bearer {config.PHOENIX_API_KEY}"})
            if r.status_code == 200:
                data = r.json()
                items = data.get("data", data if isinstance(data, list) else [])
                names = [it.get("name") for it in items if isinstance(it, dict)][:10]
                return {"status": "ok", "spans_seen": len(items),
                        "recent_span_names": names, "project": config.PHOENIX_PROJECT_NAME}
            return {"status": "query_failed", "http_status": r.status_code,
                    "note": "Could not read spans via REST; client path error: " + str(e)[:200]}
        except Exception as e2:
            return {"status": "query_failed", "note": f"{str(e)[:150]} / {str(e2)[:150]}"}


# ---------------------------------------------------------------- web_fetch_allowlisted (stretch)

def web_fetch_allowlisted(url: str) -> Dict[str, Any]:
    url = guardrails.validate_url_allowlisted(url)
    # follow_redirects=False: a 30x to an internal host would bypass the allowlist (SSRF).
    with httpx.Client(timeout=config.TOOL_TIMEOUT_SECONDS, follow_redirects=False) as c:
        r = c.get(url, headers={"User-Agent": "traceable-gemini-agent"})
    if r.is_redirect:
        raise guardrails.GuardrailError(
            "Refusing to follow a redirect (SSRF guard). Provide a direct allowlisted URL.")
    r.raise_for_status()
    text = r.text
    return {"url": url, "status": r.status_code, "length": len(text),
            "preview": text[:1500]}


# ---------------------------------------------------------------- registry

REGISTRY: Dict[str, Callable[..., Dict[str, Any]]] = {
    "calculator": lambda **kw: calculator(kw.get("expression", "")),
    "github_repo_inspect": lambda **kw: github_repo_inspect(kw.get("repo", "")),
    "phoenix_trace_inspect": lambda **kw: phoenix_trace_inspect(kw.get("limit", 1)),
    "web_fetch_allowlisted": lambda **kw: web_fetch_allowlisted(kw.get("url", "")),
}

# Day-1 vertical slice ships these three; web_fetch is stretch (Day-2+).
ACTIVE_TOOLS = ("calculator", "github_repo_inspect", "phoenix_trace_inspect")


def gemini_tool_declarations(active=ACTIVE_TOOLS):
    """Return google-genai types.Tool list for the active tools."""
    from google.genai import types

    decls = []
    if "calculator" in active:
        decls.append(types.FunctionDeclaration(
            name="calculator",
            description="Evaluate a basic arithmetic expression (estimate hours, costs, totals).",
            parameters={"type": "object",
                        "properties": {"expression": {"type": "string",
                                       "description": "e.g. '2+4+6' or '40*1.25'"}},
                        "required": ["expression"]}))
    if "github_repo_inspect" in active:
        decls.append(types.FunctionDeclaration(
            name="github_repo_inspect",
            description="Inspect a PUBLIC GitHub repo's metadata: stars, language, "
                        "description, topics, last update. Input is 'owner/name'.",
            parameters={"type": "object",
                        "properties": {"repo": {"type": "string",
                                       "description": "e.g. 'Arize-ai/phoenix'"}},
                        "required": ["repo"]}))
    if "phoenix_trace_inspect" in active:
        decls.append(types.FunctionDeclaration(
            name="phoenix_trace_inspect",
            description="Inspect the agent's OWN recent observability traces in Arize "
                        "Phoenix and summarize how many spans/tool calls were recorded.",
            parameters={"type": "object",
                        "properties": {"limit": {"type": "integer",
                                       "description": "How many recent traces to look at (1-10)."}}}))
    if "web_fetch_allowlisted" in active:
        decls.append(types.FunctionDeclaration(
            name="web_fetch_allowlisted",
            description="Fetch text from an ALLOWLISTED docs URL (Google AI, Arize, "
                        "GitHub, arXiv only). Use for grounding facts.",
            parameters={"type": "object",
                        "properties": {"url": {"type": "string"}},
                        "required": ["url"]}))
    return [types.Tool(function_declarations=decls)]
