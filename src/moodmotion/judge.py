"""Ask a model which event happened, and how big it was.

The model is given a **closed list of kinds** and asked for one label plus a 0–1
scale. It never invents magnitudes: the magnitudes live in :mod:`moodmotion.taxonomy`
where they can be reviewed. That split is what keeps the behaviour auditable.

Design notes
------------
* Transport is pluggable. Pass ``complete`` to use any model you like; otherwise the
  built-in client (OpenAI-compatible ``/chat/completions``) is used.
* Failures **never raise**. A dead model must not take the conversation down, so a
  failed call degrades to :func:`moodmotion.taxonomy.guess_fallback` and reports
  ``ok: False`` so the caller can log it. (Silently trusting a swallowed exception is
  how state quietly stops updating — the reason this flag exists.)
* Keep ``max_tokens`` small. This runs once per turn; it should cost and weigh
  nothing next to the reply itself.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Awaitable, Callable

from .taxonomy import DEFAULT_KINDS, EventKind, guess_fallback

#: Signature for a custom transport: ``async (system, user, max_tokens) -> str``.
Complete = Callable[[str, str, int], Awaitable[str]]

PROMPT_TEMPLATE = """You classify how a message affects a conversational partner's mood.

Choose exactly one category — the most dominant event, not every event:

{kinds}

Intensity:
  0.0  no event worth reacting to
  0.2  mentioned in passing
  0.5  clearly happened, moderate effect
  0.9  significant, would colour the next few hours

Reply with one line of JSON and nothing else:
{{"kind": "<category>", "scale": <0.0-1.0>}}"""


def build_prompt(kinds: list[EventKind] | None = None) -> str:
    """Render the system prompt for a given taxonomy.

    Useful if you would rather call your own model: send this as the system message
    and the raw user text as the user message, then hand the reply to
    :func:`parse_response`.
    """
    kinds = kinds or DEFAULT_KINDS
    lines = [f"- {k.name}: {k.hint or '(no description)'}" for k in kinds]
    return PROMPT_TEMPLATE.format(kinds="\n".join(lines))


def parse_response(raw: str, kinds: list[EventKind] | None = None) -> dict:
    """Parse a model reply into ``{"kind", "scale", "ok"}``.

    Tolerates code fences and stray prose around the JSON, which small models emit
    constantly. An unknown label is rejected rather than passed through.
    """
    kinds = kinds or DEFAULT_KINDS
    valid = {k.name for k in kinds}
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {"kind": "none", "scale": 0.0, "ok": False}
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return {"kind": "none", "scale": 0.0, "ok": False}
    name = str(data.get("kind", "none")).strip()
    if name not in valid:
        return {"kind": "none", "scale": 0.0, "ok": False}
    try:
        scale = float(data.get("scale", 0.0))
    except (TypeError, ValueError):
        scale = 0.0
    return {"kind": name, "scale": max(0.0, min(1.0, scale)), "ok": True}


def _openai_compatible(system: str, user: str, max_tokens: int) -> str:
    """Default transport: any OpenAI-compatible chat endpoint. Blocking."""
    base = os.environ.get("MOODMOTION_BASE_URL") or os.environ.get("OPENAI_BASE_URL") \
        or "https://api.openai.com"
    key = os.environ.get("MOODMOTION_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    model = os.environ.get("MOODMOTION_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        f"{base.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:  # noqa: S310 (fixed https scheme)
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"]["content"]


async def judge(text: str,
                kinds: list[EventKind] | None = None,
                *,
                complete: Complete | None = None,
                max_tokens: int = 60) -> dict:
    """Classify a message into one event kind plus intensity.

    Args:
        text: What the other person said.
        kinds: Taxonomy to classify against.
        complete: Optional ``async (system, user, max_tokens) -> str`` transport.
            Omit to use the built-in OpenAI-compatible client.
        max_tokens: Cap on the classification reply. Small on purpose.

    Returns:
        ``{"kind": str, "scale": float, "ok": bool}``. ``ok`` is ``False`` whenever the
        model was not reached or its reply could not be used — the caller decides what
        to do about it (the intended default is to log and move on).
    """
    kinds = kinds or DEFAULT_KINDS
    system = build_prompt(kinds)
    try:
        if complete is not None:
            raw = await complete(system, text[:400], max_tokens)
        else:
            raw = await asyncio.to_thread(_openai_compatible, system, text[:400], max_tokens)
        return parse_response(raw, kinds)
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, ValueError, TypeError):
        return {"kind": "none", "scale": 0.0, "ok": False}


def judge_blocking(text: str, kinds: list[EventKind] | None = None, *,
                   complete: Complete | None = None, max_tokens: int = 60) -> dict:
    """Synchronous convenience wrapper around :func:`judge`."""
    return asyncio.run(judge(text, kinds, complete=complete, max_tokens=max_tokens))


def apply_judged(mood, judged: dict, text: str = "",
                 kinds: list[EventKind] | None = None) -> dict:
    """Apply a judgement to a :class:`~moodmotion.engine.Mood`.

    When the judgement is unusable (``ok`` is ``False``) this falls back to
    :func:`moodmotion.taxonomy.guess_fallback`, so a model outage degrades the
    sensitivity of the state instead of freezing it.
    """
    from .taxonomy import by_name

    kinds = kinds or DEFAULT_KINDS
    kind, scale = judged.get("kind", "none"), float(judged.get("scale", 0.0))
    if not judged.get("ok"):
        kind, scale = guess_fallback(text, kinds)
    spec = by_name(kinds, kind)
    if spec is None or scale <= 0:
        return {"applied": False, "kind": kind, "scale": scale}
    dv, de = mood.apply(spec.dv * scale, spec.de * scale, note=f"{kind}({scale:.2f})")
    return {"applied": True, "kind": kind, "scale": scale, "dv": dv, "de": de}
