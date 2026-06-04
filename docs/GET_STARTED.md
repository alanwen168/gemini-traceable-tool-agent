# Get Started — for clients & evaluators

**Gemini Traceable Tool Agent** turns a Gemini model into a *transparent* agent: it
chooses tools, runs them safely, and shows you the full trace + an evaluation of every
run. Here are the two ways to use it.

## Option A — Try the hosted demo (fastest, 1 minute)
1. Go to the live demo: **https://huggingface.co/spaces/rapidagent-demo/gemini-traceable-tool-agent**
2. Log in with the demo credentials (the demo is access-gated to protect a shared key —
   evaluators receive credentials in our submission; clients can request access).
3. Click a **sample task** or type your own, e.g.
   *"Inspect the Arize-ai/phoenix repo, estimate 3+4+6 hours, and give a launch checklist."*
4. Read the **Report**, then open **Tool calls** and **Observability** to see exactly what
   the agent did and a link to its trace.

## Option B — Run your own (unlimited, private, free key)
You only need a **free Google Gemini API key** — we never ship ours; you use yours.
```bash
git clone https://github.com/alanwen168/gemini-traceable-tool-agent
cd gemini-traceable-tool-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # paste your GEMINI_API_KEY (free at aistudio.google.com/apikey)
python app.py               # open http://localhost:7860
```
Optional: add free **Arize Phoenix** keys (`phoenix.arize.com`) to `.env` to see live
traces and run the evals (`python scripts/run_eval.py`).

## What you can ask it
- Research + summarize a public GitHub project's activity.
- Estimate effort/budget with a deterministic calculator.
- Verify the agent is observable by inspecting its own Phoenix traces.
- Combine all of the above into a single grounded report.

## Why teams choose it
- **Transparent:** every model + tool call is a trace you can inspect (in-app or via the
  Phoenix MCP server from your IDE).
- **Safe by default:** tool arguments are validated, web access is allowlisted, and the
  public demo is rate-limited and login-gated.
- **Yours to run:** open source (MIT), self-host with your own keys, no lock-in.

## Need help / want full access?
Open an issue on the repo, or contact us through the submission. For production use we can
help wire your own Gemini + Phoenix project and add tools specific to your workflow.
