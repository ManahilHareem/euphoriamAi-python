"""Daily coach 4-state logic."""
from __future__ import annotations

STATE_LABELS = {
    "abducted": "Abducted by Vortex",
    "high_gravity": "High Gravity",
    "clear": "Clear + Able",
    "progress": "Progress",
}


def resolve_coach_state(checkin: dict) -> dict:
    state = str(checkin.get("current_state") or checkin.get("state") or "clear")
    gravity = checkin.get("gravity_rating")
    return {
        "current_state": state,
        "state_label": STATE_LABELS.get(state, state),
        "gravity_rating": gravity,
        "session_phase": checkin.get("session_phase"),
    }
