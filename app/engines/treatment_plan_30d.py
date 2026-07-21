"""30-day structural treatment plan generator."""
from __future__ import annotations

import json

from app.engines.goal_diagnosis import build_goal_diagnosis
from app.engines.success_strategy import build_success_strategy
from app.services.llm import chat_json


def _default_plan(domain_map: dict, active_goal_context: dict | None) -> dict:
    diagnosis = build_goal_diagnosis(domain_map, active_goal_context)
    success = build_success_strategy(domain_map, active_goal_context)
    goal = (
        (active_goal_context or {}).get("specific_goal")
        or domain_map.get("goal_title")
        or "your goal"
    )
    daily_rep = (
        success.get("daily_rep")
        if isinstance(success.get("daily_rep"), str)
        else (success.get("daily_rep") or {}).get("name")
        if isinstance(success.get("daily_rep"), dict)
        else domain_map.get("today_visible_action")
    ) or "One visible action toward the goal"

    return {
        "current_week": 1,
        "current_day": 1,
        "weekly_focus": {
            "week_1": f"Stabilize execution on {goal}",
            "week_2": "Increase visible reps and proof",
            "week_3": "Catch avoidance patterns early",
            "week_4": "Consolidate milestone progress",
        },
        "days": [
            {
                "day": d,
                "focus": f"Day {d} — structural rep",
                "daily_rep": daily_rep,
                "sabotage_preempt": diagnosis.get("failure_strategy") or "Watch for delay loops",
            }
            for d in range(1, 8)
        ],
        "success_strategy_anchor": success.get("success_strategy") or "",
        "failure_strategy_watch": diagnosis.get("failure_strategy") or "",
    }


def generate_treatment_plan_30d(
    *,
    domain_map: dict,
    active_goal_context: dict | None = None,
    state_vector_v2: dict | None = None,
    prompts: dict | None = None,
) -> dict:
    """Return treatment_plan_30d JSON; uses LLM when prompt provided, else deterministic default."""
    prompt_text = (prompts or {}).get("treatment_plan_30d")
    payload = {
        "domain_map": domain_map,
        "ACTIVE_GOAL_CONTEXT": active_goal_context or {},
        "STATE_VECTOR_V2": state_vector_v2 or {},
    }

    if prompt_text:
        system = f"{prompt_text}\n\nReturn JSON only with treatment_plan_30d key."
        try:
            parsed = chat_json(system, json.dumps(payload, indent=2))
            plan = parsed.get("treatment_plan_30d") or parsed
            if isinstance(plan, dict) and plan.get("weekly_focus"):
                return plan
        except Exception:
            pass

    return _default_plan(domain_map, active_goal_context)
