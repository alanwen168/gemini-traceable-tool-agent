"""Phoenix / OpenTelemetry tracing.

Design choices (per FINAL_DESIGN):
- Gemini LLM spans come from the OpenInference google-genai auto-instrumentor.
- Tool execution gets EXPLICIT manual spans so judges always see tool calls even
  if auto-instrumentation drifts.
- Degrades to a no-op if Phoenix isn't configured, so the agent still runs locally
  (the smoke test runs with no Phoenix creds).
- force_flush() is called per request because Hugging Face Spaces is serverless and
  the process can be frozen between requests.
"""
from __future__ import annotations

import contextlib
import json
from typing import Any, Dict, Optional

from . import config

_tracer = None
_provider = None
_ENABLED = False


def init() -> bool:
    """Initialise tracing once. Returns True if Phoenix export is live."""
    global _tracer, _provider, _ENABLED
    if _tracer is not None:
        return _ENABLED
    if not config.phoenix_ready():
        _ENABLED = False
        return False
    try:
        from phoenix.otel import register

        # Accept either a Phoenix base URL or a full OTLP traces endpoint.
        base = config.PHOENIX_COLLECTOR_ENDPOINT
        otlp = base if base.endswith("/v1/traces") else base + "/v1/traces"
        _provider = register(
            project_name=config.PHOENIX_PROJECT_NAME,
            endpoint=otlp,
            headers={"authorization": f"Bearer {config.PHOENIX_API_KEY}"},
            auto_instrument=False,
            batch=False,
            set_global_tracer_provider=True,
        )
        try:
            from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

            GoogleGenAIInstrumentor().instrument(tracer_provider=_provider)
        except Exception as e:  # instrumentation optional; manual spans still work
            print(f"[tracing] google-genai instrumentor unavailable: {e}")
        _tracer = _provider.get_tracer("traceable-gemini-agent")
        _ENABLED = True
    except Exception as e:
        print(f"[tracing] Phoenix init failed, continuing without export: {e}")
        _ENABLED = False
    return _ENABLED


def enabled() -> bool:
    return _ENABLED


@contextlib.contextmanager
def request_span(session_id: str, request_id: str, user_input: str):
    """Top-level span for one agent request."""
    if not _ENABLED or _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span("agent.request") as span:
        span.set_attribute("openinference.span.kind", "AGENT")
        span.set_attribute("agent.session_id", session_id)
        span.set_attribute("agent.request_id", request_id)
        span.set_attribute("input.value", user_input[:1000])
        yield span


@contextlib.contextmanager
def tool_span(name: str, arguments: Dict[str, Any]):
    """Explicit span around a tool execution."""
    if not _ENABLED or _tracer is None:
        yield _NoopSpan()
        return
    with _tracer.start_as_current_span(f"tool.{name}") as span:
        span.set_attribute("openinference.span.kind", "TOOL")
        span.set_attribute("tool.name", name)
        try:
            span.set_attribute("tool.parameters", json.dumps(arguments)[:2000])
        except Exception:
            pass
        yield span


class _NoopSpan:
    def set_attribute(self, *a, **k):
        pass

    def record_exception(self, *a, **k):
        pass


def set_tool_result(span: Any, result_summary: str, status: str = "ok",
                    latency_ms: Optional[float] = None) -> None:
    if span is None:
        return
    try:
        span.set_attribute("output.value", str(result_summary)[:2000])
        span.set_attribute("tool.status", status)
        if latency_ms is not None:
            span.set_attribute("tool.latency_ms", round(latency_ms, 1))
    except Exception:
        pass


def force_flush() -> None:
    if _provider is not None:
        try:
            _provider.force_flush()
        except Exception:
            pass
