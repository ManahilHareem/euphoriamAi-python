from __future__ import annotations

import json

import re

from app.config import merge_feature_flags
from app.services.llm import chat_json, chat_text
from app.services.prompt_compose import compose_coach_system, compose_friction_system


# #region agent log
def _dbg(location, message, data, hyp):
    try:
        import urllib.request as _u
        import json as _j
        import time as _t

        _payload = {
            "sessionId": "cbefd4",
            "hypothesisId": hyp,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(_t.time() * 1000),
        }
        _r = _u.Request(
            "http://host.docker.internal:7276/ingest/a6c3c50f-2380-49c9-8118-307947533aae",
            data=_j.dumps(_payload).encode(),
            headers={"Content-Type": "application/json", "X-Debug-Session-Id": "cbefd4"},
        )
        _u.urlopen(_r, timeout=1)
    except Exception:
        pass
# #endregion

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
_EXECUTION_COMMIT_USER = re.compile(
    r"\b(let me do|i'?ll do|i will do|on it|going to do|sounds good|got it)\b",
    re.I,
)


def _token_overlap_ratio(a: str, b: str) -> float:
    ta = {w for w in re.findall(r"[a-z0-9']+", (a or "").lower()) if len(w) > 2}
    tb = {w for w in re.findall(r"[a-z0-9']+", (b or "").lower()) if len(w) > 2}
    if not ta or not tb:
        return 1.0 if (a or "").strip() == (b or "").strip() and (a or "").strip() else 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _last_assistant_content(messages: list[dict]) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "assistant" and m.get("content"):
            return str(m["content"])
    return ""


def _brief_execution_ack(user_message: str | None = None) -> str:
    if user_message and _EXECUTION_COMMIT_USER.search(user_message):
        return "Good — go do it. When you're done, come back and tell me what happened."
    return "Got it — take that step and tell me how it goes when you're done."


def _replace_duplicate_assistant_reply(
    result: dict,
    *,
    messages: list[dict],
    user_message: str | None,
    checkin: dict,
) -> dict:
    assistant = str(result.get("assistant_message") or "").strip()
    if not assistant:
        return result
    prior = _last_assistant_content(
        messages[:-1] if user_message else messages
    )
    if not prior:
        return result
    overlap = _token_overlap_ratio(assistant, prior)
    conv_sig = checkin.get("conversation_signals") or {}
    execution_commit = bool(
        conv_sig.get("user_commitment_to_act")
        or conv_sig.get("execution_confirmed")
        or checkin.get("execution_confirmed")
        or (user_message and _EXECUTION_COMMIT_USER.search(user_message))
    )
    if overlap >= 0.45 or (prior.strip() == assistant.strip()):
        if execution_commit or overlap >= 0.85:
            result = {
                **result,
                "assistant_message": _sanitize_user_facing(_brief_execution_ack(user_message)),
                "green_rep": None,
                "writeback_hints": {
                    **(result.get("writeback_hints") or {}),
                    "assign_new_green_rep": False,
                },
            }
    return result


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
    if checkin.get("state_vector_v2"):
        payload["STATE_VECTOR_V2"] = checkin["state_vector_v2"]
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
    feature_flags: dict | None = None,
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

    flags = merge_feature_flags(feature_flags or (prompts or {}).get("feature_flags"))
    prompts_with_flags = {**(prompts or {}), "feature_flags": flags}
    system = compose_coach_system(prompts_with_flags, feature_flags=flags)

    # #region agent log
    _p = prompts or {}
    _cb = _p.get("coach_brain_prompt") or ""
    _bp = _p.get("brain_prompt") or ""
    _sys_l = system.lower()
    _cs = checkin or {}
    _sig = _cs.get("conversation_signals") or {}
    _dbg(
        "coach.py:coach_reply:compose",
        "composed coach system prompt + flags + db prompts",
        {
            "cert_deep": bool(flags.get("coach_cert_deep_enabled")),
            "brain_v2": bool(flags.get("brain_prompt_v2_shadow")),
            "treatment_plan": bool(flags.get("treatment_plan_enabled")),
            "coach_brain_len": len(_cb),
            "coach_brain_head": _cb[:150],
            "brain_len": len(_bp),
            "brain_head": _bp[:150],
            "prompt_keys_present": [k for k, v in _p.items() if v and k != "feature_flags"],
            "system_len": len(system),
            "has_missing_notice": "not configured in the database" in _sys_l
            or "missing" in _sys_l and "prompt" in _sys_l,
            "system_mentions_intention": "intention" in _sys_l,
            "system_mentions_resistance": "resistance" in _sys_l,
            "session_phase": str(_cs.get("session_phase") or ""),
            "coaching_mode": str(_cs.get("coaching_mode") or ""),
            "execution_confirmed": bool(_sig.get("execution_confirmed")),
            "clarity_saturation": bool(_sig.get("clarity_saturation")),
            "repeat_complaint": bool(_sig.get("coaching_repeat_complaint")),
            "msg_count": len(messages),
        },
        "H6-H9",
    )
    # #endregion

    # When the backend has already detected that recent advice is repeating, the
    # tiny per-turn steering directive buried in the 110K system prompt is being
    # ignored by the model. Append a blunt, high-recency override at the END of
    # the user payload (the last tokens the model reads) so it CANNOT be missed.
    conv_sig = checkin.get("conversation_signals") or {}
    loop_detected = bool(
        conv_sig.get("assistant_advice_loop")
        or conv_sig.get("repeated_assistant_advice")
        or checkin.get("assistant_advice_loop")
        or checkin.get("repeated_assistant_advice")
    )
    execution_commit = bool(
        conv_sig.get("user_commitment_to_act")
        or conv_sig.get("execution_confirmed")
        or checkin.get("execution_confirmed")
        or (user_message and _EXECUTION_COMMIT_USER.search(str(user_message)))
    )
    # The member explicitly asking "how / what steps / how do I do it" is the
    # strongest signal they want a concrete action, not another generic tip. Fire
    # the override here too so we never answer a "how?" with recycled advice.
    asked_how = bool(
        conv_sig.get("user_asked_what_next") or checkin.get("user_asked_what_next")
    )
    intake_or_proof = str(checkin.get("session_phase") or "") in {
        "intention",
        "emotional_checkin",
        "resistance_probe",
        "deep_probe",
        "integration",
        "integration_deep",
    } or bool(checkin.get("awaiting_proof_log") or checkin.get("proof_integration_mode"))
    apply_override = (loop_detected or asked_how or execution_commit) and not intake_or_proof
    last_assistant = ""
    for _m in reversed(messages[:-1] if user_message else messages):
        if _m.get("role") == "assistant" and _m.get("content"):
            last_assistant = str(_m["content"])
            break

    user_payload = _build_coach_user_payload(
        domain_map,
        checkin,
        messages,
        user_message,
        active_goal_context=active_goal_context,
        user_coach_context=user_coach_context,
    )
    if apply_override:
        if execution_commit and not loop_detected and not asked_how:
            user_payload += (
                "\n\n================ CRITICAL OVERRIDE — READ LAST, OBEY FIRST ================\n"
                "The member just AGREED to execute the plan you already gave (e.g. 'let me do it').\n"
                "Reply in 1-2 sentences ONLY: brief acknowledgment + optional invite to report back.\n"
                "You are FORBIDDEN from repeating the plan, numbered steps, body-echo opening, or goal recap.\n"
                f'Plan already given (DO NOT repeat): "{last_assistant[:400]}"\n'
                "==========================================================================\n"
            )
        else:
            user_payload += (
                "\n\n================ CRITICAL OVERRIDE — READ LAST, OBEY FIRST ================\n"
                "Your recent replies repeated the SAME advice and the member is frustrated and "
                "is literally asking HOW to do it.\n"
                "This turn you are FORBIDDEN from repeating that advice or its themes: optimizing or "
                "sending proposals, increasing profile views, sharing the profile on social media / "
                "forums, or any generic 'boost visibility' tip.\n"
                "Do NOT restate the goal or milestone. Do NOT open with 'Let's focus on'. Do NOT end "
                "with 'How does that sound?'.\n"
                "You MUST do EXACTLY ONE of the following:\n"
                "  (A) Give a concrete, step-by-step micro-action they can finish in the next 10 "
                "minutes — numbered 1., 2., 3. — with real specifics (the exact words to write, the "
                "exact place to go, the exact number to send/do).\n"
                "  (B) Ask ONE sharp diagnostic question about the exact thing blocking them that you "
                "have NOT already asked.\n"
                "Keep it under 5 sentences. Be specific, human, and new.\n"
                f'Advice already given (DO NOT repeat this): "{last_assistant[:300]}"\n'
                "==========================================================================\n"
            )

    try:
        parsed = chat_json(system, user_payload)
        # #region agent log
        _dbg(
            "coach.py:coach_reply:json_path",
            "chat_json returned",
            {
                "loop_detected": loop_detected,
                "asked_how": asked_how,
                "override_applied": apply_override,
                "has_assistant_message": bool(parsed.get("assistant_message")),
                "assistant_head": str(parsed.get("assistant_message") or "")[:160],
                "has_green_rep": bool(parsed.get("green_rep")),
            },
            "H16",
        )
        # #endregion
        if parsed.get("assistant_message"):
            normalized = _normalize_coach_response(parsed, domain_map, checkin)
            return _replace_duplicate_assistant_reply(
                normalized,
                messages=messages,
                user_message=user_message,
                checkin=checkin,
            )
    except Exception as _e:
        # #region agent log
        _dbg(
            "coach.py:coach_reply:json_exception",
            "chat_json raised — using fallback text path",
            {"error": str(_e)[:200]},
            "H8",
        )
        # #endregion
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
                "assistant_message": _sanitize_user_facing(parsed["assistant_message"]),
                "green_rep": parsed.get("green_rep"),
            }
    except Exception:
        pass

    text = chat_text(
        system + "\n\n" + payload,
        [{"role": m["role"], "content": m["content"]} for m in messages],
        model=None,
    )
    return {"assistant_message": _sanitize_user_facing(text), "green_rep": None}


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
    intake_phase = session_phase in {
        "intention",
        "emotional_checkin",
        "resistance_probe",
        "deep_probe",
        "integration_deep",
    }
    insight_integration = session_phase == "insight_integration"
    awaiting_intention = bool(checkin.get("awaiting_session_intention"))
    awaiting_emotional = bool(checkin.get("awaiting_emotional_checkin"))

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

    if intake_phase or awaiting_intention or awaiting_emotional:
        green_rep = None
        hints = {k: v for k, v in hints.items() if k != "assign_new_green_rep"}
        assign_new = False

    if insight_integration and assign_green_rep_flag:
        assign_new = bool(hints.get("assign_new_green_rep")) or assign_new

    if checkin.get("session_intention") and not hints.get("session_intention"):
        hints["session_intention"] = checkin.get("session_intention")
    if checkin.get("felt_sensation") and not hints.get("felt_sensation"):
        hints["felt_sensation"] = checkin.get("felt_sensation")

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

    # Backend explicitly requested a rep this turn (e.g. member asked "how do I
    # start / what next"), but the model returned no green_rep. Fall back to the
    # backend-provided milestone rep so the member gets a concrete action card
    # instead of yet another advice paragraph — this is what breaks the loop.
    rep_suppressed = bool(
        awaiting_proof
        or proof_integration
        or intake_phase
        or awaiting_intention
        or awaiting_emotional
        or conversation_signals.get("block_rep_reassign")
        or checkin.get("suggest_session_end")
        or checkin.get("reports_stagnation")
        or conversation_signals.get("coaching_repeat_complaint")
    )
    if assign_green_rep_flag and not green_rep and not rep_suppressed:
        fallback_rep = checkin.get("suggested_milestone_rep") or conversation_signals.get(
            "suggested_green_rep"
        )
        if isinstance(fallback_rep, dict) and fallback_rep.get("name"):
            green_rep = {
                "name": fallback_rep["name"],
                "steps": fallback_rep.get("steps") or [],
                "win_condition": fallback_rep.get("win_condition") or "",
            }
            hints = {**hints, "assign_new_green_rep": True}

    # #region agent log
    _dbg(
        "coach.py:_normalize:rep_fallback",
        "green_rep resolution after normalize",
        {
            "assign_green_rep_flag": assign_green_rep_flag,
            "rep_suppressed": rep_suppressed,
            "final_has_green_rep": bool(green_rep),
            "final_rep_name": (green_rep or {}).get("name"),
            "had_suggested_milestone": bool(checkin.get("suggested_milestone_rep")),
            "session_phase": session_phase,
        },
        "H14",
    )
    # #endregion

    return {
        "assistant_message": _sanitize_user_facing(parsed.get("assistant_message", "")),
        "green_rep": green_rep,
        "detected_failure_strategy": parsed.get("detected_failure_strategy"),
        "writeback_hints": hints,
    }
