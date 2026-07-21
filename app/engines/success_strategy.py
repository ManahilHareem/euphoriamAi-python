"""Success strategy builder from diagnosis."""
from __future__ import annotations

from app.engines.goal_diagnosis import build_goal_diagnosis


def build_success_strategy(domain_map: dict, active_goal_context: dict | None = None) -> dict:
    diagnosis = build_goal_diagnosis(domain_map, active_goal_context)
    raw = domain_map.get("success_strategy") or diagnosis.get("success_strategy") or ""
    return {
        "success_strategy": raw,
        "success_rule": domain_map.get("success_rule"),
        "opposite_belief": domain_map.get("opposite_belief"),
        "opposite_behaviour": domain_map.get("opposite_behaviour"),
        "daily_rep": domain_map.get("daily_rep"),
        "win_condition": domain_map.get("win_condition"),
    }
