"""Suggested training recommendation — exactly ONE resource."""
from __future__ import annotations


def suggest_training(domain_map: dict, active_goal_context: dict | None = None) -> dict:
    resource = domain_map.get("recommended_resource")
    title = None
    if isinstance(resource, dict):
        title = resource.get("title") or resource.get("name")
    elif isinstance(resource, str) and resource.strip():
        title = resource.strip()
    return {
        "slot": "training",
        "title": title or "Suggested training",
        "why_chosen": "One resource for today's edge — complete before anything else",
        "domain": (active_goal_context or {}).get("active_domain") or domain_map.get("domain"),
        "count": 1,
    }
