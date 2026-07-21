"""Goal-specific resistance diagnosis from domain map."""
from __future__ import annotations


def build_goal_diagnosis(domain_map: dict, active_goal_context: dict | None = None) -> dict:
    ctx = active_goal_context or {}
    return {
        "active_domain": ctx.get("active_domain") or domain_map.get("domain"),
        "specific_goal": ctx.get("specific_goal") or domain_map.get("goal_title"),
        "current_milestone": ctx.get("current_milestone"),
        "primary_vortex_signature": domain_map.get("signature_id"),
        "EO": domain_map.get("EO"),
        "lack_channel": domain_map.get("lack_channel"),
        "avoidance_channel": domain_map.get("avoid_type"),
        "top_avoidance_behaviours": domain_map.get("top_3_avoidance_behaviours") or [],
        "failure_strategy": domain_map.get("failure_strategy"),
        "protector_profile": domain_map.get("protector_profile"),
        "protector_rule": domain_map.get("protector_rule"),
        "core_fear": domain_map.get("core_fear") or ctx.get("core_fear"),
        "cost_to_goal": domain_map.get("cost_to_goal"),
        "success_strategy": domain_map.get("success_strategy"),
        "first_green_rep": domain_map.get("daily_rep"),
        "proof_required": domain_map.get("win_condition"),
    }
