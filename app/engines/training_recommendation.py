"""Suggested training recommendation (Stage 2 stub)."""
from __future__ import annotations


def suggest_training(domain_map: dict, active_goal_context: dict | None = None) -> dict:
    resource = domain_map.get("recommended_resource")
    return {
        "slot": "training",
        "title": resource or "Suggested training",
        "why_chosen": "Aligned to active goal and failure strategy",
        "domain": (active_goal_context or {}).get("active_domain") or domain_map.get("domain"),
    }
