"""Active Goal Context helpers — validate and enrich onboarding output."""
from __future__ import annotations


def build_onboarding_output(active_goal_context: dict | None) -> dict:
    ctx = active_goal_context or {}
    return {
        "active_domain": ctx.get("active_domain"),
        "specific_goal": ctx.get("specific_goal") or ctx.get("goal_name"),
        "measurable_outcome": ctx.get("measurable_outcome"),
        "target_date": ctx.get("target_date"),
        "why_it_matters": ctx.get("why_it_matters"),
        "current_reality": ctx.get("current_reality"),
        "milestones": ctx.get("milestones") or {},
        "current_milestone": ctx.get("current_milestone"),
        "required_role": ctx.get("required_role"),
        "required_behaviours": ctx.get("required_behaviours") or [],
        "known_avoidance": ctx.get("known_avoidance") or [],
        "perceived_risk": ctx.get("perceived_risk"),
        "past_pattern": ctx.get("past_pattern"),
        "onboarding_complete": bool(ctx.get("specific_goal")),
    }
