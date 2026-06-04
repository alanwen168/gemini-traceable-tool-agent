"""Input validation + safety guardrails. The dispatcher never blindly trusts the
model's tool arguments — everything is validated here first."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from . import config


class GuardrailError(ValueError):
    """Raised when a tool argument fails validation (fail closed)."""


_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")


def validate_repo(repo: str) -> str:
    repo = (repo or "").strip().rstrip("/")
    # accept a full github URL too, reduce to owner/name
    if repo.startswith("http"):
        parts = urlparse(repo).path.strip("/").split("/")
        if len(parts) >= 2:
            repo = f"{parts[0]}/{parts[1]}"
    if not _REPO_RE.match(repo):
        raise GuardrailError(
            f"'{repo}' is not a valid 'owner/name' GitHub repo identifier."
        )
    owner, name = repo.split("/", 1)
    if owner in (".", "..") or name in (".", ".."):
        raise GuardrailError("Invalid repo path segment.")  # path-traversal guard
    return repo


def validate_url_allowlisted(url: str) -> str:
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise GuardrailError("Only https URLs are allowed (no http downgrade).")
    host = (parsed.hostname or "").lower()
    if host not in config.WEB_FETCH_ALLOWLIST:
        raise GuardrailError(
            f"Host '{host}' is not on the allowlist {config.WEB_FETCH_ALLOWLIST}."
        )
    return url


def validate_expression(expr: str) -> str:
    expr = (expr or "").strip()
    if not expr:
        raise GuardrailError("Empty expression.")
    if len(expr) > 200:
        raise GuardrailError("Expression too long.")
    if not re.fullmatch(r"[0-9eE+\-*/(). %]+", expr):
        raise GuardrailError("Expression may only contain numbers and + - * / ( ) . %.")
    return expr


def clamp_user_input(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise GuardrailError("Empty task.")
    if len(text) > config.DEMO_MAX_INPUT_CHARS:
        raise GuardrailError(
            f"Task too long ({len(text)} chars, max {config.DEMO_MAX_INPUT_CHARS})."
        )
    return text
