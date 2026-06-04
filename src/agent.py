"""The agent loop: a MANUAL Gemini function-calling dispatcher.

We disable the SDK's automatic function calling so the application layer owns tool
execution — that gives us (a) per-tool validation/timeout and (b) honest, observable
tool spans for Phoenix. The final markdown report is the model's last plain-text turn,
not a tool, so tool-call accuracy stays meaningful.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

from . import config, guardrails, tools, tracing

SYSTEM_PROMPT = (
    "You are Gemini Traceable Tool Agent, a research-to-action assistant for the "
    "Google Cloud Rapid Agent Hackathon. You decide which tools to call, then write a "
    "concise structured markdown report.\n"
    "Rules:\n"
    "- Use tools to GROUND facts; never invent repo stats, numbers, or trace data.\n"
    "- Use calculator for any arithmetic (effort/cost estimates).\n"
    "- Use github_repo_inspect for repo facts (input 'owner/name').\n"
    "- Use phoenix_trace_inspect to report on your own observability traces.\n"
    "- Prefer 1-3 well-chosen tool calls. When you have enough, STOP calling tools and "
    "write the final report with a short 'Tools used' line.\n"
)


@dataclass
class ToolCall:
    name: str
    arguments: Dict[str, Any]
    status: str = "ok"
    result: Any = None
    latency_ms: float = 0.0


@dataclass
class AgentResult:
    final_text: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    session_id: str = ""
    request_id: str = ""
    iterations: int = 0
    phoenix_enabled: bool = False


def _dispatch(name: str, args: Dict[str, Any]) -> ToolCall:
    """Execute one tool with validation, timing, and a Phoenix span."""
    call = ToolCall(name=name, arguments=args)
    t0 = time.time()
    with tracing.tool_span(name, args) as span:
        try:
            if name not in tools.REGISTRY:
                raise guardrails.GuardrailError(f"Unknown tool '{name}'.")
            result = tools.REGISTRY[name](**args)
            call.result = result
            call.status = "ok"
        except guardrails.GuardrailError as e:
            call.status = "rejected"
            call.result = {"error": str(e)}
        except Exception as e:  # tool failure shouldn't crash the agent
            call.status = "error"
            call.result = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        call.latency_ms = (time.time() - t0) * 1000.0
        tracing.set_tool_result(span, str(call.result)[:500], call.status, call.latency_ms)
    return call


def run(task: str, session_id: str | None = None) -> AgentResult:
    from google import genai
    from google.genai import types

    task = guardrails.clamp_user_input(task)
    session_id = session_id or uuid.uuid4().hex[:12]
    request_id = uuid.uuid4().hex[:12]
    phoenix_on = tracing.init()

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    gen_config = types.GenerateContentConfig(
        tools=tools.gemini_tool_declarations(),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
        system_instruction=SYSTEM_PROMPT,
    )

    contents: List[Any] = [types.Content(role="user", parts=[types.Part(text=task)])]
    result = AgentResult(final_text="", session_id=session_id,
                         request_id=request_id, phoenix_enabled=phoenix_on)

    with tracing.request_span(session_id, request_id, task) as req_span:
        for step in range(config.AGENT_MAX_ITERS):
            result.iterations = step + 1
            resp = client.models.generate_content(
                model=config.GEMINI_MODEL, contents=contents, config=gen_config)
            if not resp.candidates:
                fb = getattr(resp, "prompt_feedback", None)
                result.final_text = (
                    "Gemini returned no candidates; the request may have been blocked."
                    + (f" ({fb})" if fb else ""))
                break
            cand = resp.candidates[0]
            if not cand.content or not cand.content.parts:
                result.final_text = (resp.text or "").strip() or "(empty Gemini response)"
                break
            contents.append(cand.content)

            fcs = [p.function_call for p in cand.content.parts if getattr(p, "function_call", None)]
            if not fcs:
                result.final_text = (resp.text or "").strip() or "(no text returned)"
                break

            response_parts = []
            for fc in fcs:
                args = dict(fc.args) if fc.args else {}
                call = _dispatch(fc.name, args)
                result.tool_calls.append(call)
                payload = call.result if isinstance(call.result, dict) else {"result": call.result}
                kwargs = {"name": fc.name, "response": payload}
                fc_id = getattr(fc, "id", None)
                if fc_id:  # Gemini 2.x links responses to calls by id when present
                    kwargs["id"] = fc_id
                try:
                    response_parts.append(types.Part.from_function_response(**kwargs))
                except TypeError:
                    kwargs.pop("id", None)
                    response_parts.append(types.Part.from_function_response(**kwargs))
            contents.append(types.Content(role="user", parts=response_parts))
        else:
            # ran out of iterations without a final text turn
            result.final_text = (
                "Reached the maximum number of tool iterations. Partial findings:\n"
                + "\n".join(f"- {c.name}: {c.status}" for c in result.tool_calls))
        if req_span is not None:
            try:
                req_span.set_attribute("output.value", result.final_text[:2000])
                req_span.set_attribute("agent.tool_calls", len(result.tool_calls))
            except Exception:
                pass

    tracing.force_flush()
    return result
