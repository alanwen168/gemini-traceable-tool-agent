# 🔭 Gemini Traceable Tool Agent

A **Google Gemini** agent that decides which tools to call, executes them through a
guarded dispatcher, and produces a structured report — while **every model call and
tool call is traced and evaluated in [Arize Phoenix](https://phoenix.arize.com/)** and
inspectable through the **Phoenix MCP** server.

Built for the **Google Cloud Rapid Agent Hackathon** (Arize / Phoenix partner track).

> **Live demo:** https://huggingface.co/spaces/rapidagent-demo/gemini-traceable-tool-agent
> _(access-gated to protect a capped key — judges: credentials are in our Devpost submission)_
> **Demo video:** _<VIDEO_URL — YouTube, ≤3 min>_

---

## Why it matters
Most agents are black boxes: you can't see *why* they chose a tool, *what* the tool
returned, or *whether* the answer is reliable. This project makes a Gemini agent
**traceable** (every step is a span), **evaluable** (a golden dataset + deterministic
metrics), and **inspectable** (ask Phoenix MCP to summarize the last run).

## What it does
Give it a research-to-action task. It will:
1. Let **Gemini** decide which tools to call (function calling).
2. Run them through a dispatcher that **validates args, enforces timeouts, and fails
   closed** on unsafe input.
3. Write a final markdown **report** — the report is the model's last turn, *not* a
   tool, so tool-call accuracy stays honest.
4. Emit an **OpenInference trace** (LLM + tool spans) to Arize Phoenix.

### Tools
| Tool | What it shows |
|---|---|
| `calculator` | deterministic compute (effort/cost) |
| `github_repo_inspect` | external public API tool (repo metadata) |
| `phoenix_trace_inspect` | **hero tool** — the agent inspects its *own* Phoenix traces |
| `web_fetch_allowlisted` *(stretch)* | SSRF-guarded fetch from an allowlist |

## Architecture
```
User → Gradio UI (Hugging Face Spaces, public)
 → agent loop (google-genai, gemini-2.5-flash, manual dispatcher, MAX_ITERS=5)
    ├ calculator   ├ github_repo_inspect   ├ phoenix_trace_inspect
 → final Gemini turn writes the report (not a tool)
 ↓ every LLM + tool call = an OpenInference span (force_flush per request)
Arize Phoenix Cloud  ← traces · evals over a golden dataset · Phoenix MCP inspection
```

---

## 🚀 Try it (clients / non-technical)
1. Open the **live demo** link above — no login required.
2. Click a **sample task** or type your own (e.g. *"Inspect the Arize-ai/phoenix repo,
   estimate 3+4+6 hours, and give a launch checklist"*).
3. Read the **Report**, then open the **Tool calls** and **Observability** tabs to see
   exactly what the agent did and its trace link.

The public demo runs on a capped key with daily limits. For unlimited / private use,
**self-host** with your own keys (below).

## 🛠️ Self-host / run locally
```bash
git clone https://github.com/alanwen168/gemini-traceable-tool-agent
cd gemini-traceable-tool-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill GEMINI_API_KEY (+ optional Phoenix keys)
python cli.py "Inspect Arize-ai/phoenix, estimate 3+4+6 hours, give a checklist."
python app.py                   # web UI at http://localhost:7860
```

### Environment variables
| Var | Required | Notes |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | from [Google AI Studio](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | – | default `gemini-2.5-flash` |
| `PHOENIX_API_KEY` + `PHOENIX_COLLECTOR_ENDPOINT` | for traces | from [Phoenix Cloud](https://phoenix.arize.com/) (free) |
| `PHOENIX_PROJECT_NAME` | – | default `gemini-traceable-tool-agent` |

## 🔬 Evals
```bash
python scripts/run_eval.py     # writes evidence/eval_results.json + .md
```
Deterministic metrics: `tool_call_accuracy`, `argument_validity`, `safety_refusal`,
`latency_ms`. See `data/golden_dataset.jsonl`.

## 🔌 Phoenix MCP (inspect the agent from Claude Desktop / Cursor)
Copy `mcp/phoenix-mcp-config.example.json` into your MCP client config, fill your
Phoenix base URL + API key, then ask: *"Show the latest traces in the
gemini-traceable-tool-agent project and list the tool calls."*

## 🔒 Security
- Tool args are validated before execution; `web_fetch` is allowlist-only (SSRF guard);
  `calculator` is a safe AST evaluator (no `eval`).
- Public demo: capped key, daily call limit, input-length cap, bounded concurrency,
  no raw errors leaked.
- No secrets in the repo — keys come from env / Space secrets only.

## 🧪 Tech stack
Google Gemini · Gemini function calling · Arize Phoenix · Phoenix MCP · OpenTelemetry ·
OpenInference · Python · Gradio · Hugging Face Spaces.

## Known limitations
Hackathon prototype, not a production SaaS. 3 core tools; small golden dataset; single
region. Roadmap: more tools, larger eval set, Cloud Run deployment, richer MCP feedback.

## License
MIT — see [LICENSE](LICENSE).
