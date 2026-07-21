"""Green Rep selection and validation."""
from __future__ import annotations


def select_green_rep(domain_map: dict, checkin: dict | None = None) -> dict | None:
    checkin = checkin or {}
    if checkin.get("session_phase") in {
        "intention",
        "emotional_checkin",
        "resistance_probe",
        "deep_probe",
    }:
        return None
    if not checkin.get("assign_green_rep"):
        return None

    daily = domain_map.get("daily_rep")
    if isinstance(daily, dict) and daily.get("name"):
        return {
            "name": daily["name"],
            "steps": daily.get("steps") or [],
            "win_condition": daily.get("win_condition") or domain_map.get("win_condition"),
        }
    if domain_map.get("today_visible_action"):
        return {
            "name": domain_map["today_visible_action"],
            "steps": [],
            "win_condition": domain_map.get("win_condition") or "",
        }
    return None


def validate_green_rep(green_rep: dict | None) -> bool:
    if not green_rep or not isinstance(green_rep, dict):
        return False
    return bool(str(green_rep.get("name") or "").strip())
