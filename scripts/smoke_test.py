#!/usr/bin/env python3
"""Smoke test for the vertical slice.

Checks (no network/keys needed for the guardrail checks):
  1. Tool guardrails fail closed on bad input.
  2. calculator works deterministically.
  3. If GEMINI_API_KEY is present: a real multi-tool agent run completes with >=1
     model-selected tool call and a non-empty report.
Exit non-zero on any failure.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import agent, config, guardrails, tools  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        failures.append(name)


# 1. guardrails fail closed
try:
    guardrails.validate_repo("not-a-repo")
    check("reject bad repo", False)
except guardrails.GuardrailError:
    check("reject bad repo", True)

try:
    guardrails.validate_url_allowlisted("http://169.254.169.254/latest/meta-data")
    check("reject non-allowlisted URL (SSRF guard)", False)
except guardrails.GuardrailError:
    check("reject non-allowlisted URL (SSRF guard)", True)

try:
    guardrails.validate_expression("__import__('os').system('id')")
    check("reject code in calculator", False)
except guardrails.GuardrailError:
    check("reject code in calculator", True)

# 2. calculator deterministic
check("calculator 3+4+6 == 13", tools.calculator("3+4+6")["result"] == 13)

# 3. live agent run (only if key present)
if config.gemini_ready():
    res = agent.run("Estimate 2+4+6 hours of work, then inspect the Arize-ai/phoenix "
                    "repo. Give a one-line summary.")
    check("agent produced final text", bool(res.final_text.strip()))
    check("agent made >=1 model-selected tool call", len(res.tool_calls) >= 1)
    check("a tool call succeeded", any(c.status == "ok" for c in res.tool_calls))
    print(f"   (iterations={res.iterations}, phoenix={'on' if res.phoenix_enabled else 'off'}, "
          f"tools={[c.name for c in res.tool_calls]})")
else:
    print("SKIP - live agent run (GEMINI_API_KEY not set)")

print()
if failures:
    print(f"SMOKE TEST FAILED: {len(failures)} check(s) failed: {failures}")
    sys.exit(1)
print("SMOKE TEST PASSED")
