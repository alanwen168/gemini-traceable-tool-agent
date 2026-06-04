#!/usr/bin/env python3
"""Day-1 command-line runner. Usage: python cli.py "your task here"
The Gradio web UI (app.py) is added on Day 3; this CLI proves the vertical slice."""
import json
import sys

from src import agent, config, tracing


def main() -> None:
    task = " ".join(sys.argv[1:]).strip() or \
        "Inspect the Arize-ai/phoenix repo, estimate 3+4+6 hours of integration work, " \
        "then inspect your own Phoenix traces. Produce a short launch checklist."
    if not config.gemini_ready():
        print("ERROR: GEMINI_API_KEY not set. Copy .env.example to .env and fill it.")
        sys.exit(1)

    print(f"== TASK ==\n{task}\n")
    res = agent.run(task)

    print("== TOOL CALLS ==")
    for i, c in enumerate(res.tool_calls, 1):
        print(f"  {i}. {c.name}({json.dumps(c.arguments)}) -> {c.status} "
              f"[{c.latency_ms:.0f} ms]")
        print(f"     {json.dumps(c.result)[:200]}")
    print(f"\n== FINAL REPORT (iterations={res.iterations}, "
          f"phoenix={'on' if res.phoenix_enabled else 'off'}) ==\n{res.final_text}")
    if res.phoenix_enabled:
        print(f"\nTraces -> {config.PHOENIX_COLLECTOR_ENDPOINT} "
              f"(project {config.PHOENIX_PROJECT_NAME})")


if __name__ == "__main__":
    main()
