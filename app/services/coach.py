from __future__ import annotations

import json

import re

from app.config import merge_feature_flags
from collections.abc import Iterator
from typing import Any

from app.services.llm import chat_json, chat_json_stream, chat_text, chat_text_stream
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
_DANGLING_NEXT_STEP_LEADIN = re.compile(
    r"(?:^|\n)\s*(?:here'?s (?:what to do|your next step)|your next step is(?: the)?|"
    r"next step is the)\s*:?\s*$",
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
_USER_REJECTS_PRESCRIPTION = re.compile(
    r"\b(don'?t want (?:an? )?(?:exercise|homework|action|step)|stop giving|stay with (?:the )?feeling|"
    r"want to understand|help me (?:figure|understand|explore)|move(?:d|s)? back to (?:another )?(?:action|exercise))\b",
    re.I,
)
_PRESCRIPTIVE_REPLY = re.compile(
    r"(?:^\s*\d+\.|try this|here'?s (?:a|your|one) (?:action|exercise|step)|write down|close your eyes|"
    r"take a deep breath|send (?:them|a message)|reach out|schedule (?:a|time)|small action|concrete step|"
    r"step-by-step|micro-action)",
    re.I | re.M,
)
_DIAGNOSIS_THEME = re.compile(
    r"\b(fear of rejection|protective mechanism|being seen as too much|fear of being (?:seen|judged|rejected)|"
    r"protect(?:ive|ing) (?:part|mechanism)|act of kindness|reach out|schedule (?:a|time to) catch up)\b",
    re.I,
)
_DISCOVERY_QUESTION_FALLBACKS = (
    "What are you experiencing right now — in your body, not your head?",
    "Tell me more about the last time that pull-away feeling showed up.",
    "Stay with that. What's the worst part of it?",
    "What happens inside you the moment closeness starts to feel real?",
    "What part of that feels most alive for you right now?",
    "If you didn't pull away, what would you be afraid might happen next?",
)


def _assistant_history(messages: list[dict], *, exclude_last_user: bool = True) -> list[str]:
    src = messages[:-1] if exclude_last_user and messages and messages[-1].get("role") == "user" else messages
    return [
        str(m.get("content") or "").strip()
        for m in src or []
        if m.get("role") == "assistant" and str(m.get("content") or "").strip()
    ]


def _max_overlap_with_prior_assistant(assistant: str, messages: list[dict]) -> float:
    prior = _assistant_history(messages)
    if not prior or not assistant.strip():
        return 0.0
    return max(_token_overlap_ratio(assistant, p) for p in prior)


def _is_prescriptive_reply(text: str) -> bool:
    return bool(_PRESCRIPTIVE_REPLY.search(text or ""))


def _repeated_diagnosis_theme(assistant: str, messages: list[dict]) -> bool:
    if not _DIAGNOSIS_THEME.search(assistant or ""):
        return False
    prior = _assistant_history(messages)
    return sum(1 for p in prior if _DIAGNOSIS_THEME.search(p)) >= 1


def _discovery_only_active(checkin: dict, user_message: str | None = None) -> bool:
    conv_sig = checkin.get("conversation_signals") or {}
    return bool(
        conv_sig.get("discovery_only_mode")
        or conv_sig.get("explore_first_mode")
        or conv_sig.get("anti_repeat_active")
        or conv_sig.get("user_rejects_prescription")
        or conv_sig.get("thematic_assistant_repeat")
        or checkin.get("discovery_only_mode")
        or checkin.get("coaching_mode") == "discovery"
        or (user_message and _USER_REJECTS_PRESCRIPTION.search(user_message))
    )


def _pick_discovery_fallback(user_message: str | None, messages: list[dict]) -> str:
    prior = _assistant_history(messages, exclude_last_user=False)
    candidates: list[str] = []

    if user_message and re.search(r"\b(body|feel|feeling|anxiety|experience)\b", user_message, re.I):
        candidates.append(_DISCOVERY_QUESTION_FALLBACKS[0])
    if user_message and re.search(r"\b(understand|why|where|come from|roots?|underneath)\b", user_message, re.I):
        candidates.append(_DISCOVERY_QUESTION_FALLBACKS[1])

    idx = len(prior) % len(_DISCOVERY_QUESTION_FALLBACKS)
    candidates.extend(_DISCOVERY_QUESTION_FALLBACKS[idx:] + _DISCOVERY_QUESTION_FALLBACKS[:idx])

    seen: set[str] = set()
    ordered: list[str] = []
    for q in candidates:
        key = q.strip().lower()
        if key not in seen:
            seen.add(key)
            ordered.append(q)

    fresh = [q for q in ordered if all(_token_overlap_ratio(q, p) < 0.38 for p in prior)]
    if fresh:
        return fresh[0]

    best = ordered[0] if ordered else _DISCOVERY_QUESTION_FALLBACKS[0]
    best_score = 1.0
    for q in ordered or _DISCOVERY_QUESTION_FALLBACKS:
        score = max((_token_overlap_ratio(q, p) for p in prior), default=0.0)
        if score < best_score:
            best_score = score
            best = q
    return best


def _strip_prescriptive_content(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        if re.match(r"^\s*\d+[\.)]\s+", line):
            continue
        if _PRESCRIPTIVE_REPLY.search(line) and len(line.split()) > 6:
            continue
        lines.append(line)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return cleaned


def _enforce_anti_repeat_reply(
    result: dict,
    *,
    messages: list[dict],
    user_message: str | None,
    checkin: dict,
) -> dict:
    assistant = str(result.get("assistant_message") or "").strip()
    if not assistant:
        return result

    conv_sig = checkin.get("conversation_signals") or {}
    discovery_only = _discovery_only_active(checkin, user_message)
    loop_detected = bool(
        conv_sig.get("assistant_advice_loop")
        or conv_sig.get("repeated_assistant_advice")
        or conv_sig.get("thematic_assistant_repeat")
        or conv_sig.get("anti_repeat_active")
        or checkin.get("assistant_advice_loop")
        or checkin.get("repeated_assistant_advice")
    )
    execution_commit = bool(
        conv_sig.get("user_commitment_to_act")
        or conv_sig.get("execution_confirmed")
        or checkin.get("execution_confirmed")
        or (user_message and _EXECUTION_COMMIT_USER.search(user_message))
    )
    prior_assistants = _assistant_history(messages)
    prior = _last_assistant_content(messages[:-1] if user_message else messages)
    overlap_last = _token_overlap_ratio(assistant, prior) if prior else 0.0
    overlap_max = _max_overlap_with_prior_assistant(assistant, messages)
    exact_dup = any(p.strip() == assistant.strip() for p in prior_assistants)
    thematic_dup = _repeated_diagnosis_theme(assistant, messages)
    prescriptive = _is_prescriptive_reply(assistant)

    must_rewrite = bool(
        exact_dup
        or overlap_max >= 0.38
        or overlap_last >= 0.38
        or thematic_dup
        or (discovery_only and prescriptive)
        or (loop_detected and (prescriptive or overlap_max >= 0.28 or thematic_dup))
    )

    if not must_rewrite:
        return result

    if execution_commit and not discovery_only and overlap_last >= 0.85:
        replacement = _brief_execution_ack(user_message)
    elif discovery_only or loop_detected or prescriptive or thematic_dup:
        replacement = _pick_discovery_fallback(user_message, messages)
        stripped = _strip_prescriptive_content(assistant)
        if stripped and not _is_prescriptive_reply(stripped) and overlap_max < 0.38:
            if "?" in stripped and len(stripped.split()) <= 45:
                replacement = stripped
    else:
        replacement = _pick_discovery_fallback(user_message, messages)

    result = {
        **result,
        "assistant_message": _sanitize_user_facing(replacement),
        "green_rep": None,
        "writeback_hints": {
            **(result.get("writeback_hints") or {}),
            "assign_new_green_rep": False,
        },
    }
    return result


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


def _sanitize_user_facing(text: str | None) -> str:
    if not text:
        return ""
    out = _REPORT_HEADERS.sub("", text)
    out = _FRAMEWORK_TERMS.sub("pattern", out)
    out = _TEMPLATE_LABEL_BLOCK.sub("", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    out = _DANGLING_NEXT_STEP_LEADIN.sub("", out).strip()
    return out

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


def _prepare_coach_turn(
    *,
    domain_map: dict,
    checkin: dict,
    messages: list[dict] | None,
    user_message: str | None,
    prompts: dict | None,
    active_goal_context: dict | None,
    user_coach_context: dict | None,
    feature_flags: dict | None,
) -> tuple[str, str, list[dict], dict, dict | None, dict | None]:
    messages = list(messages or [])
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

    # When the backend has already detected that recent advice is repeating, the
    # tiny per-turn steering directive buried in the 110K system prompt is being
    # ignored by the model. Append a blunt, high-recency override at the END of
    # the user payload (the last tokens the model reads) so it CANNOT be missed.
    conv_sig = checkin.get("conversation_signals") or {}
    discovery_only = _discovery_only_active(checkin, user_message)
    loop_detected = bool(
        conv_sig.get("assistant_advice_loop")
        or conv_sig.get("repeated_assistant_advice")
        or conv_sig.get("thematic_assistant_repeat")
        or conv_sig.get("anti_repeat_active")
        or checkin.get("assistant_advice_loop")
        or checkin.get("repeated_assistant_advice")
    )
    execution_commit = bool(
        conv_sig.get("user_commitment_to_act")
        or conv_sig.get("execution_confirmed")
        or checkin.get("execution_confirmed")
        or (user_message and _EXECUTION_COMMIT_USER.search(str(user_message)))
    )
    asked_how = bool(
        conv_sig.get("user_asked_what_next") or checkin.get("user_asked_what_next")
    ) and not discovery_only
    intake_or_proof = str(checkin.get("session_phase") or "") in {
        "intention",
        "emotional_checkin",
        "resistance_probe",
        "deep_probe",
        "integration",
        "integration_deep",
    } or bool(checkin.get("awaiting_proof_log") or checkin.get("proof_integration_mode"))
    apply_override = (
        discovery_only or loop_detected or execution_commit or asked_how
    ) and not intake_or_proof
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
        if execution_commit and not loop_detected and not asked_how and not discovery_only:
            user_payload += (
                "\n\n================ CRITICAL OVERRIDE — READ LAST, OBEY FIRST ================\n"
                "The member just AGREED to execute the plan you already gave (e.g. 'let me do it').\n"
                "Reply in 1-2 sentences ONLY: brief acknowledgment + optional invite to report back.\n"
                "You are FORBIDDEN from repeating the plan, numbered steps, body-echo opening, or goal recap.\n"
                f'Plan already given (DO NOT repeat): "{last_assistant[:400]}"\n'
                "==========================================================================\n"
            )
        elif discovery_only or loop_detected:
            user_payload += (
                "\n\n================ CRITICAL OVERRIDE — ANTI-REPEAT / DISCOVERY ONLY ================\n"
                "Zero tolerance: do NOT repeat prior advice, diagnosis labels, themes, or exercises.\n"
                "Member rejected homework OR you already repeated yourself OR they asked to stay with feeling.\n"
                "Reply in 1-3 SHORT sentences with ONE new question only.\n"
                "FORBIDDEN: numbered lists, outreach tasks, breathing/writing exercises, Green Rep, "
                "'fear of rejection', 'protective mechanism', 'Let's focus on', 'small actionable step'.\n"
                "Follow their thread. Let them discover — do not solve.\n"
                f'Prior advice themes to AVOID: "{last_assistant[:350]}"\n'
                "==========================================================================\n"
            )
        else:
            user_payload += (
                "\n\n================ CRITICAL OVERRIDE — READ LAST, OBEY FIRST ================\n"
                "Your recent replies repeated the SAME advice and the member is frustrated.\n"
                "Do NOT restate the goal or milestone. Do NOT open with 'Let's focus on'.\n"
                "Ask ONE sharp NEW question you have not asked — under 3 sentences. No numbered steps.\n"
                f'Advice already given (DO NOT repeat this): "{last_assistant[:300]}"\n'
                "==========================================================================\n"
            )

    return system, user_payload, messages, checkin, active_goal_context, user_coach_context


def _fallback_text_result(
    *,
    text: str,
    domain_map: dict,
    checkin: dict,
    messages: list[dict],
    user_message: str | None,
) -> dict:
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

    result = {
        "assistant_message": _sanitize_user_facing(text),
        "green_rep": green_rep,
        "detected_failure_strategy": None,
        "writeback_hints": {},
    }
    return _enforce_anti_repeat_reply(
        result,
        messages=messages,
        user_message=user_message,
        checkin=checkin,
    )


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
    system, user_payload, messages, checkin, active_goal_context, user_coach_context = (
        _prepare_coach_turn(
            domain_map=domain_map,
            checkin=checkin,
            messages=messages,
            user_message=user_message,
            prompts=prompts,
            active_goal_context=active_goal_context,
            user_coach_context=user_coach_context,
            feature_flags=feature_flags,
        )
    )

    try:
        parsed = chat_json(system, user_payload)
        if parsed.get("assistant_message"):
            normalized = _normalize_coach_response(parsed, domain_map, checkin)
            return _enforce_anti_repeat_reply(
                normalized,
                messages=messages,
                user_message=user_message,
                checkin=checkin,
            )
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
    return _fallback_text_result(
        text=text,
        domain_map=domain_map,
        checkin=checkin,
        messages=messages,
        user_message=user_message,
    )


def _emit_text_deltas(text: str, *, chunk_size: int = 28) -> Iterator[dict[str, Any]]:
    value = text or ""
    for i in range(0, len(value), chunk_size):
        piece = value[i : i + chunk_size]
        if piece:
            yield {"type": "delta", "text": piece}


def coach_reply_stream(
    *,
    domain_map: dict,
    checkin: dict,
    messages: list[dict] | None = None,
    user_message: str | None = None,
    prompts: dict | None = None,
    active_goal_context: dict | None = None,
    user_coach_context: dict | None = None,
    feature_flags: dict | None = None,
) -> Iterator[dict[str, Any]]:
    """Generate the full coach reply first, then stream the *committed* text.

    Live mid-generation tokens are not forwarded: anti-repeat / sanitize can rewrite
    the message after the model finishes, which previously caused a jarring UI swap.
    """
    system, user_payload, messages, checkin, active_goal_context, user_coach_context = (
        _prepare_coach_turn(
            domain_map=domain_map,
            checkin=checkin,
            messages=messages,
            user_message=user_message,
            prompts=prompts,
            active_goal_context=active_goal_context,
            user_coach_context=user_coach_context,
            feature_flags=feature_flags,
        )
    )

    yield {"type": "status", "phase": "generating"}

    result: dict | None = None
    try:
        parsed: dict | None = None
        for event in chat_json_stream(system, user_payload):
            # Intentionally do not yield mid-JSON deltas — they are not final.
            if event.get("type") == "json":
                parsed = event.get("data") if isinstance(event.get("data"), dict) else {}

        if parsed and parsed.get("assistant_message"):
            normalized = _normalize_coach_response(parsed, domain_map, checkin)
            result = _enforce_anti_repeat_reply(
                normalized,
                messages=messages,
                user_message=user_message,
                checkin=checkin,
            )
    except Exception:
        result = None

    if result is None:
        context_block = ""
        if user_coach_context:
            context_block += f"USER_COACH_CONTEXT:\n{json.dumps(user_coach_context, indent=2)}\n\n"
        if active_goal_context:
            context_block += f"ACTIVE_GOAL_CONTEXT:\n{json.dumps(active_goal_context, indent=2)}\n\n"
        fallback_system = (
            f"{system}\n\n"
            f"{context_block}"
            f"domain_map:\n{json.dumps(domain_map, indent=2)}\n\n"
            f"checkin:\n{json.dumps(checkin, indent=2)}"
        )
        llm_messages = [
            {"role": m["role"], "content": m["content"]} for m in messages if m.get("content")
        ]
        text = ""
        for event in chat_text_stream(fallback_system, llm_messages):
            if event.get("type") == "text":
                text = str(event.get("data") or "")
        result = _fallback_text_result(
            text=text,
            domain_map=domain_map,
            checkin=checkin,
            messages=messages,
            user_message=user_message,
        )

    # Stream only the committed member-facing text (post anti-repeat).
    final_text = str((result or {}).get("assistant_message") or "")
    yield from _emit_text_deltas(final_text)
    yield {"type": "result", "data": result or {"assistant_message": final_text}}



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

    return {
        "assistant_message": _sanitize_user_facing(parsed.get("assistant_message", "")),
        "green_rep": green_rep,
        "detected_failure_strategy": parsed.get("detected_failure_strategy"),
        "writeback_hints": hints,
    }
