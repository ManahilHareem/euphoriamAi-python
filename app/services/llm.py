from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: OpenAI | None = None

_ASSISTANT_MSG_START = re.compile(r'"assistant_message"\s*:\s*"')

COACH_MAX_COMPLETION_TOKENS = 900


def get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def resolve_coach_model(model: str | None = None) -> str:
    if model:
        return model
    return (settings.coach_openai_model or "").strip() or settings.openai_model


def chat_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_completion_tokens: int = 2000,
) -> dict:
    client = get_client()
    resolved_model = model or settings.openai_model
    t0 = time.perf_counter()
    res = client.chat.completions.create(
        model=resolved_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
        max_completion_tokens=max_completion_tokens,
    )
    openai_ms = int((time.perf_counter() - t0) * 1000)
    # print (not logger.info) so timings show under default uvicorn WARNING level
    print(
        "llm_chat_json "
        + json.dumps(
            {
                "model": resolved_model,
                "openai_ms": openai_ms,
                "system_chars": len(system or ""),
                "user_chars": len(user or ""),
                "max_completion_tokens": max_completion_tokens,
            }
        ),
        flush=True,
    )

    raw = res.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _decode_json_string_prefix(raw: str) -> tuple[str, bool]:
    """Decode characters of a JSON string value from `raw` (content after opening quote).

    Returns (decoded_text, complete) where complete means the closing quote was seen.
    """
    out: list[str] = []
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "\\":
            if i + 1 >= len(raw):
                return "".join(out), False
            nxt = raw[i + 1]
            escapes = {
                '"': '"',
                "\\": "\\",
                "/": "/",
                "b": "\b",
                "f": "\f",
                "n": "\n",
                "r": "\r",
                "t": "\t",
            }
            if nxt in escapes:
                out.append(escapes[nxt])
                i += 2
                continue
            if nxt == "u" and i + 5 < len(raw):
                try:
                    out.append(chr(int(raw[i + 2 : i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    return "".join(out), False
            return "".join(out), False
        if ch == '"':
            return "".join(out), True
        out.append(ch)
        i += 1
    return "".join(out), False


def extract_assistant_message_so_far(buf: str) -> str | None:
    match = _ASSISTANT_MSG_START.search(buf)
    if not match:
        return None
    text, _complete = _decode_json_string_prefix(buf[match.end() :])
    return text


def chat_json_stream(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_completion_tokens: int = 2000,
) -> Iterator[dict[str, Any]]:
    """Stream a JSON-object completion; yield assistant_message deltas then final parsed JSON."""
    client = get_client()
    resolved_model = model or settings.openai_model
    t0 = time.perf_counter()
    stream = client.chat.completions.create(
        model=resolved_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
        max_completion_tokens=max_completion_tokens,
        stream=True,
    )

    buf = ""
    emitted = ""
    for chunk in stream:
        delta = ""
        try:
            delta = chunk.choices[0].delta.content or ""
        except (AttributeError, IndexError):
            delta = ""
        if not delta:
            continue
        buf += delta
        so_far = extract_assistant_message_so_far(buf)
        if so_far is None:
            continue
        if len(so_far) > len(emitted):
            piece = so_far[len(emitted) :]
            emitted = so_far
            if piece:
                yield {"type": "delta", "text": piece}

    openai_ms = int((time.perf_counter() - t0) * 1000)
    print(
        "llm_chat_json_stream "
        + json.dumps(
            {
                "model": resolved_model,
                "openai_ms": openai_ms,
                "system_chars": len(system or ""),
                "user_chars": len(user or ""),
                "max_completion_tokens": max_completion_tokens,
            }
        ),
        flush=True,
    )

    try:
        parsed = json.loads(buf or "{}")
    except json.JSONDecodeError:
        parsed = {"assistant_message": emitted} if emitted else {}
    yield {"type": "json", "data": parsed if isinstance(parsed, dict) else {}}


def chat_text(system: str, messages: list[dict], *, model: str | None = None) -> str:
    client = get_client()
    res = client.chat.completions.create(
        model=model or settings.openai_model,
        messages=[{"role": "system", "content": system}, *messages],
        temperature=0.4,
        max_completion_tokens=1200,
    )
    return (res.choices[0].message.content or "").strip()


def chat_text_stream(
    system: str,
    messages: list[dict],
    *,
    model: str | None = None,
) -> Iterator[dict[str, Any]]:
    client = get_client()
    stream = client.chat.completions.create(
        model=model or settings.openai_model,
        messages=[{"role": "system", "content": system}, *messages],
        temperature=0.4,
        max_completion_tokens=1200,
        stream=True,
    )
    full = ""
    for chunk in stream:
        delta = ""
        try:
            delta = chunk.choices[0].delta.content or ""
        except (AttributeError, IndexError):
            delta = ""
        if not delta:
            continue
        full += delta
        yield {"type": "delta", "text": delta}
    yield {"type": "text", "data": full.strip()}
