"""In-memory prompt bundle cache — Node sends prompts_cache_key after first upload."""
from __future__ import annotations

import time
from threading import Lock

_TTL_SECONDS = 6 * 60 * 60
_cache: dict[str, tuple[dict, float]] = {}
_lock = Lock()


def resolve_prompts(
    prompts: dict | None,
    cache_key: str | None,
) -> dict | None:
    """Return prompts from body or cache. None means cache miss when key was provided."""
    if prompts:
        if cache_key:
            with _lock:
                _cache[cache_key] = (prompts, time.time())
        return prompts

    if not cache_key:
        return None

    with _lock:
        entry = _cache.get(cache_key)
        if not entry:
            return None
        bundle, stored_at = entry
        if time.time() - stored_at > _TTL_SECONDS:
            _cache.pop(cache_key, None)
            return None
        return bundle
