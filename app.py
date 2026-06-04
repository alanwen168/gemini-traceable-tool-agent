#!/usr/bin/env python3
"""Gemini Traceable Tool Agent — public Gradio demo (Hugging Face Spaces entrypoint).

Four panels: the agent's Report, the Tool-Calls timeline, the Observability summary
(session/trace + Phoenix link), and live status. Abuse controls protect the exposed
Gemini key on a public, no-login Space.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import date

import gradio as gr

from src import agent, config, guardrails, tracing

# ----------------------------------------------------------------- abuse controls
# Concurrency is bounded by Gradio's queue + per-event concurrency_limit (see build_ui).
_DAY = {"date": str(date.today()), "count": 0}
_DAY_LOCK = threading.Lock()


def _quota_remaining() -> bool:
    with _DAY_LOCK:
        today = str(date.today())
        if _DAY["date"] != today:
            _DAY["date"], _DAY["count"] = today, 0
        return _DAY["count"] < config.DEMO_DAILY_CALL_LIMIT


def _quota_consume() -> None:
    with _DAY_LOCK:
        _DAY["count"] += 1


SAMPLES = [
    "Inspect the Arize-ai/phoenix repo, estimate 3+4+6 hours of integration work, then "
    "inspect your own Phoenix traces and produce a short launch checklist.",
    "Compare google-gemini/generative-ai-python and Arize-ai/openinference by stars and "
    "activity, then summarize which is more active.",
    "Estimate a monthly budget of 1500/12 and inspect your recent Phoenix traces to "
    "confirm the agent is observable.",
]

INTRO = """
# 🔭 Gemini Traceable Tool Agent
A **Google Gemini** agent that decides which tools to call, runs them through a guarded
dispatcher, and writes a structured report — while every model call and tool call is
**traced and evaluable in Arize Phoenix**. The agent can inspect its own traces in-app,
and the same project is queryable from your IDE via the **Phoenix MCP server**
(config in the repo's `mcp/` folder).

*Built for the Google Cloud Rapid Agent Hackathon. Public demo — no login. Try a sample
below or describe a research-to-action task.*
"""


def _render_tools(res: "agent.AgentResult") -> str:
    if not res.tool_calls:
        return "_No tools were called — the model answered directly._"
    lines = ["| # | Tool | Arguments | Status | Latency |", "|---|---|---|---|---|"]
    for i, c in enumerate(res.tool_calls, 1):
        args = json.dumps(c.arguments)[:60]
        lines.append(f"| {i} | `{c.name}` | `{args}` | {c.status} | {c.latency_ms:.0f} ms |")
    return "\n".join(lines)


def _render_obs(res: "agent.AgentResult") -> str:
    rows = [
        f"- **Session:** `{res.session_id}`  ·  **Request:** `{res.request_id}`",
        f"- **Iterations:** {res.iterations}  ·  **Tool calls:** {len(res.tool_calls)}",
        f"- **Phoenix tracing:** {'🟢 on' if res.phoenix_enabled else '⚪ off (no key)'}",
    ]
    if res.phoenix_enabled and config.PHOENIX_COLLECTOR_ENDPOINT:
        rows.append(f"- **Traces:** [open Phoenix project]({config.PHOENIX_COLLECTOR_ENDPOINT}) "
                    f"(`{config.PHOENIX_PROJECT_NAME}`)")
    return "\n".join(rows)


def run_agent(task: str):
    if not config.gemini_ready():
        return ("⚠️ The demo is not configured (no Gemini key).", "", "", "Not ready.")
    try:
        task = guardrails.clamp_user_input(task)
    except guardrails.GuardrailError as e:
        return (f"⚠️ {e}", "", "", "Rejected input.")
    if not _quota_remaining():
        return ("⚠️ Daily demo limit reached. This is a public demo with a capped key — "
                "please try again tomorrow or self-host with your own keys.", "", "",
                "Quota reached.")
    try:
        res = agent.run(task)
        _quota_consume()  # only count successful runs against the daily cap
        status = (f"✅ Done — {res.iterations} step(s), {len(res.tool_calls)} tool call(s), "
                  f"Phoenix {'on' if res.phoenix_enabled else 'off'}.")
        return (res.final_text, _render_tools(res), _render_obs(res), status)
    except Exception as e:  # never leak raw stack/keys
        return (f"⚠️ The agent hit an error: {type(e).__name__}. Please try a simpler task.",
                "", "", "Error.")


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="Gemini Traceable Tool Agent") as demo:
        gr.Markdown(INTRO)
        with gr.Row():
            task = gr.Textbox(label="Your task", lines=3,
                              placeholder="e.g. Inspect a GitHub repo, estimate effort, "
                                          "and produce a checklist…")
        with gr.Row():
            run_btn = gr.Button("Run agent", variant="primary")
        gr.Examples(examples=[[s] for s in SAMPLES], inputs=[task], label="Try a sample")
        with gr.Tab("📋 Report"):
            out_report = gr.Markdown()
        with gr.Tab("🛠️ Tool calls"):
            out_tools = gr.Markdown()
        with gr.Tab("🔭 Observability"):
            out_obs = gr.Markdown()
        status = gr.Markdown()
        run_btn.click(run_agent, inputs=[task],
                      outputs=[out_report, out_tools, out_obs, status],
                      concurrency_limit=2)
    return demo


if __name__ == "__main__":
    # init tracing eagerly so the first request is fast
    tracing.init()
    # On Hugging Face Spaces, let gradio auto-detect host/port (binds 0.0.0.0:7860).
    # Locally, set GRADIO_SERVER_PORT if you need a specific port.
    build_ui().queue(max_size=16).launch(
        ssr_mode=False,  # disable gradio-5 node SSR (its health check fails in HF sandbox)
        auth=config.demo_auth(),  # judge-only gate when DEMO_AUTH_* are set
        auth_message="Demo access is limited. Judges: use the credentials in our Devpost "
                     "submission.")
