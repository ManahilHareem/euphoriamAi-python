"""In-memory prompt bundle cache — Node sends prompts_cache_key after first upload.

Ephemeral per-turn fields (e.g. brain_prompt_rag_chunks) may be sent as a thin
overlay without invalidating the cached static bundle.
"""
from __future__ import annotations

import time
from threading import Lock

_TTL_SECONDS = 6 * 60 * 60
_cache: dict[str, tuple[dict, float]] = {}
_lock = Lock()

_EPHEMERAL_KEYS = frozenset({"brain_prompt_rag_chunks"})


def _has_static_prompts(prompts: dict | None) -> bool:
    if not prompts:
        return False
    return any(
        key not in _EPHEMERAL_KEYS and prompts.get(key)
        for key in prompts
    )


def _apply_overlay(static: dict, overlay: dict | None) -> dict:
    result = dict(static)
    if not overlay:
        return result
    rag = overlay.get("brain_prompt_rag_chunks")
    if rag is not None:
        result["brain_prompt_rag_chunks"] = rag
        # Prefer RAG for composition; truncated brain stays in cache for misses.
        if not rag:
            result.pop("brain_prompt_rag_chunks", None)
    return result


def resolve_prompts(
    prompts: dict | None,
    cache_key: str | None,
) -> dict | None:
    """Return prompts from body or cache. None means cache miss when key was provided."""
    overlay = prompts if isinstance(prompts, dict) else None

    if _has_static_prompts(overlay):
        static = {k: v for k, v in overlay.items() if k not in _EPHEMERAL_KEYS}
        if cache_key:
            with _lock:
                _cache[cache_key] = (dict(static), time.time())
        return _apply_overlay(static, overlay)

    if not cache_key:
        return overlay

    with _lock:
        entry = _cache.get(cache_key)
        if not entry:
            return None
        bundle, stored_at = entry
        if time.time() - stored_at > _TTL_SECONDS:
            _cache.pop(cache_key, None)
            return None
        cached = dict(bundle)

    return _apply_overlay(cached, overlay)
