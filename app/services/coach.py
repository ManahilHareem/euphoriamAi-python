from __future__ import annotations

import json

import re

from app.services.llm import chat_json, chat_text
from app.services.prompt_compose import compose_coach_system, compose_friction_system

_FRAMEWORK_TERMS = re.compile(
    r"\b(vortex|signature\s*id|EO\b|lack\s*channel|avoidance\s*channel|QGC|CL\s*estimate|"
    r"consciousness\s*level|gravity\s*depth|orbit\s*pattern|abducted\s*by\s*vortex)\b",
    re.I,
)
_REPORT_HEADERS = re.compile(
    r"^(current\s+goal|current\s+milestone|last\s+green\s+rep|recent\s+patterns|"
    r"last\s+session|loading)\s*:",
    re.I | re.M,
)
_TEMPLATE_LABEL_BLOCK = re.compile(
    r"\n\s*\*\*(?:Pattern|Cost|Failure\s+Strategy|Success\s+Strategy|"
    r"Today'?s?\s+Green\s+Rep|Win\s+Condition)\s*:\*\*[\s\S]*$",
    re.I,
)
_REP_REQUIRES_PERSON = re.compile(
    r"\b(someone|person|trust|send\s+it|send\s+to|reach\s+out|friend|family|tell\s+them|text\s+them)\b",
    re.I,
)


def _sanitize_user_facing(text: str | None) -> str:
    if not text:
        return ""
    out = _REPORT_HEADERS.sub("", text)
    out = _FRAMEWORK_TERMS.sub("pattern", out)
    out = _TEMPLATE_LABEL_BLOCK.sub("", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()

STATE_LABELS = {
    "abducted": "Abducted by Vortex",
    "high_gravity": "High Gravity",
    "clear": "Clear + Able",
    "progress": "Progress",
}


def _build_coach_user_payload(
    domain_map: dict,
    checkin: dict,
    messages: list[dict],
    user_message: str | None,
    *,
    active_goal_context: dict | None = None,
    user_coach_context: dict | None = None,
) -> str:
    payload: dict = {
        "domain_map": domain_map,
        "COACH_CHECKIN": checkin,
        "messages": messages,
        "user_message": user_message,
    }
    if active_goal_context:
        payload["ACTIVE_GOAL_CONTEXT"] = active_goal_context
    if user_coach_context:
        payload["USER_COACH_CONTEXT"] = user_coach_context
        if user_coach_context.get("COACH_MEMORY_CONTEXT"):
            payload["COACH_MEMORY_CONTEXT"] = user_coach_context["COACH_MEMORY_CONTEXT"]
    return json.dumps(payload, indent=2)


def coach_reply(
    *,
    domain_map: dict,
    checkin: dict,
    messages: list[dict] | None = None,
    user_message: str | None = None,
    prompts: dict | None = None,
    active_goal_context: dict | None = None,
    user_coach_context: dict | None = None,
) -> dict:
    messages = messages or []
    state = checkin.get("current_state") or checkin.get("state") or "clear"
    checkin = {
        **checkin,
        "current_state": state,
        "state_label": STATE_LABELS.get(state, state),
    }

    if user_message:
        messages = [*messages, {"role": "user", "content": user_message}]

    system = compose_coach_system(prompts)
    try:
        parsed = chat_json(
            system,
            _build_coach_user_payload(
                domain_map,
                checkin,
                messages,
                user_message,
                active_goal_context=active_goal_context,
                user_coach_context=user_coach_context,
            ),
        )
        if parsed.get("assistant_message"):
            return _normalize_coach_response(parsed, domain_map, checkin)
    except Exception:
        pass

    # Fallback: conversational path
    context_block = ""
    if user_coach_context:
        context_block += f"USER_COACH_CONTEXT:\n{json.dumps(user_coach_context, indent=2)}\n\n"
    if active_goal_context:
        context_block += f"ACTIVE_GOAL_CONTEXT:\n{json.dumps(active_goal_context, indent=2)}\n\n"
    system = (
        f"{system}\n\n"
        f"{context_block}"
        f"domain_map:\n{json.dumps(domain_map, indent=2)}\n\n"
        f"checkin:\n{json.dumps(checkin, indent=2)}"
    )
    llm_messages = [{"role": m["role"], "content": m["content"]} for m in messages if m.get("content")]
    text = chat_text(system, llm_messages)
    progress_mode = (
        str(checkin.get("current_state") or "") == "progress"
        or bool(checkin.get("user_reported_proof"))
        or str(checkin.get("session_phase") or "").startswith("proof_integration")
    )
    daily_rep = domain_map.get("daily_rep") or {}
    green_rep = None
    if not progress_mode and isinstance(daily_rep, dict) and daily_rep.get("name"):
        green_rep = {
            "name": daily_rep["name"],
            "steps": daily_rep.get("steps") or [],
            "win_condition": daily_rep.get("win_condition") or domain_map.get("win_condition"),
        }
    elif domain_map.get("today_visible_action"):
        green_rep = {
            "name": domain_map["today_visible_action"],
            "steps": [],
            "win_condition": domain_map.get("win_condition") or "",
        }

    return {
        "assistant_message": _sanitize_user_facing(text),
        "green_rep": green_rep,
        "detected_failure_strategy": None,
        "writeback_hints": {},
    }


def friction_rescue(
    *,
    domain_map: dict,
    checkin: dict,
    messages: list[dict] | None = None,
    user_message: str | None = None,
    prompts: dict | None = None,
    active_goal_context: dict | None = None,
    user_coach_context: dict | None = None,
) -> dict:
    messages = messages or []
    if user_message:
        messages = [*messages, {"role": "user", "content": user_message}]
    payload_obj: dict = {
        "domain_map": domain_map,
        "checkin": checkin,
        "messages": messages,
    }
    if active_goal_context:
        payload_obj["ACTIVE_GOAL_CONTEXT"] = active_goal_context
    if user_coach_context:
        payload_obj["USER_COACH_CONTEXT"] = user_coach_context
    payload = json.dumps(payload_obj, indent=2)
    system = compose_friction_system(prompts)
    try:
        parsed = chat_json(system, payload)
        if parsed.get("assistant_message"):
            return {
                "assistant_message": parsed["assistant_message"],
                "green_rep": parsed.get("green_rep"),
            }
    except Exception:
        pass

    text = chat_text(
        system + "\n\n" + payload,
        [{"role": m["role"], "content": m["content"]} for m in messages],
        model=None,
    )
    return {"assistant_message": text, "green_rep": None}


def _normalize_coach_response(
    parsed: dict, domain_map: dict, checkin: dict | None = None
) -> dict:
    checkin = checkin or {}
    session_phase = str(checkin.get("session_phase") or "")
    user_reported_proof = bool(checkin.get("user_reported_proof"))
    state = str(checkin.get("current_state") or "")
    coaching_mode = str(checkin.get("coaching_mode") or "")
    execute_mode = coaching_mode == "execute"
    conversation_signals = checkin.get("conversation_signals") or {}

    progress_mode = (
        state == "progress"
        or user_reported_proof
        or session_phase.startswith("proof_integration")
        or bool(checkin.get("proof_integration_mode"))
    )
    awaiting_proof = bool(checkin.get("awaiting_proof_log"))
    proof_integration = bool(checkin.get("proof_integration_mode"))
    assign_green_rep_flag = bool(checkin.get("assign_green_rep"))

    green_rep = parsed.get("green_rep")
    hints = parsed.get("writeback_hints") or {}
    if hints.get("gravity_rating") is not None:
        try:
            hints["gravity_rating"] = max(1, min(10, int(float(hints["gravity_rating"]))))
        except (TypeError, ValueError):
            hints.pop("gravity_rating", None)
    if hints.get("cl_estimate") is not None:
        try:
            hints["cl_estimate"] = max(1.0, min(5.0, float(hints["cl_estimate"])))
        except (TypeError, ValueError):
            hints.pop("cl_estimate", None)
    assign_new = bool(hints.get("assign_new_green_rep"))

    if execute_mode and not green_rep and assign_new:
        solo_rep = (
            conversation_signals.get("suggested_green_rep")
            or conversation_signals.get("suggested_solo_rep")
        )
        if isinstance(solo_rep, dict) and solo_rep.get("name") and (
            conversation_signals.get("needs_solo_rep_adaptation")
            or conversation_signals.get("user_completed_current_rep")
        ):
            green_rep = {
                "name": solo_rep["name"],
                "steps": solo_rep.get("steps") or [],
                "win_condition": solo_rep.get("win_condition") or "",
            }
            hints = {**hints, "assign_new_green_rep": True}
            assign_new = True
        else:
            daily_rep = domain_map.get("daily_rep")
            if isinstance(daily_rep, dict) and daily_rep.get("name"):
                green_rep = {
                    "name": daily_rep["name"],
                    "steps": daily_rep.get("steps") or [],
                    "win_condition": daily_rep.get("win_condition") or "",
                }
                hints = {**hints, "assign_new_green_rep": True}
                assign_new = True

    if assign_new and not conversation_signals.get("block_rep_reassign"):
        solo_rep = (
            conversation_signals.get("suggested_green_rep")
            or conversation_signals.get("suggested_solo_rep")
        )
        last_rep = str(checkin.get("last_green_rep") or "").lower()
        if isinstance(solo_rep, dict) and solo_rep.get("name"):
            next_name = str(solo_rep["name"]).lower()
            if conversation_signals.get("user_completed_current_rep") and next_name != last_rep:
                green_rep = {
                    "name": solo_rep["name"],
                    "steps": solo_rep.get("steps") or [],
                    "win_condition": solo_rep.get("win_condition") or "",
                }
            elif conversation_signals.get("needs_solo_rep_adaptation"):
                rep_text = json.dumps(green_rep or {})
                if _REP_REQUIRES_PERSON.search(rep_text) or not green_rep:
                    green_rep = {
                        "name": solo_rep["name"],
                        "steps": solo_rep.get("steps") or [],
                        "win_condition": solo_rep.get("win_condition") or "",
                    }

    if conversation_signals.get("block_rep_reassign"):
        green_rep = None
        hints = {k: v for k, v in hints.items() if k != "assign_new_green_rep"}
        assign_new = False

    if awaiting_proof or proof_integration or not assign_green_rep_flag:
        green_rep = None
        hints = {k: v for k, v in hints.items() if k != "assign_new_green_rep"}
        assign_new = False

    if bool(checkin.get("reports_stagnation")) or bool(
        (checkin.get("conversation_signals") or {}).get("coaching_repeat_complaint")
    ):
        green_rep = None
        hints = {k: v for k, v in hints.items() if k != "assign_new_green_rep"}
        assign_new = False

    if bool(checkin.get("suggest_session_end")):
        green_rep = None
        hints = {k: v for k, v in hints.items() if k != "assign_new_green_rep"}
        assign_new = False

    if bool(checkin.get("returning_member") or checkin.get("do_not_reintroduce")):
        hints = {**hints, "returning_member": True}

    if not assign_new and not green_rep:
        green_rep = None
    elif progress_mode and not assign_new and not green_rep:
        daily_rep = domain_map.get("daily_rep")
        if isinstance(daily_rep, dict) and daily_rep.get("name"):
            green_rep = {
                "name": daily_rep["name"],
                "steps": daily_rep.get("steps") or [],
                "win_condition": daily_rep.get("win_condition") or "",
            }

    return {
        "assistant_message": _sanitize_user_facing(parsed.get("assistant_message", "")),
        "green_rep": green_rep,
        "detected_failure_strategy": parsed.get("detected_failure_strategy"),
        "writeback_hints": hints,
    }
