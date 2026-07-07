from __future__ import annotations

import json
import re

from app.services.llm import chat_json, chat_text
from app.services.prompt_compose import compose_map_resistance_turn_system
from app.services.prompts import MAP_RESISTANCE_EXTRACT_RULES

WELCOME_TEMPLATE = """Hi {name}, we're mapping the resistance structure for your **{label}** goal — not a generic life diagnostic.

**Your goal:** {goal}
**90-day outcome:** {outcome}

About {target_count} questions — your goal and milestones are already set, so we isolate resistance around this outcome only.

One question at a time. Every question stays anchored to this goal.

**Q1 — Resistance when pursuing this goal**
When you move toward "{goal}", what do you usually do instead, avoid, or tell yourself first that slows you down?"""

# Internal framework codes must never reach the member — expand to full words if the model leaks them.
_CODE_FULL_FORMS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bEO\b"), "core belief pattern"),
    (re.compile(r"\bNE\b"), "Not Enough"),
    (re.compile(r"\bNC\b"), "Not Capable"),
    (re.compile(r"\bNS\b"), "Not Safe"),
    (re.compile(r"\bPL\b"), "Powerless"),
    (re.compile(r"\bCD\b"), "Can't Depend"),
    (re.compile(r"\bNON\b"), "Needs Not OK"),
    (re.compile(r"\bNOV\b"), "Vulnerable Not OK"),
    (re.compile(r"\bNOH\b"), "Happy/Comfort Not OK"),
]


def _expand_framework_codes(text: str) -> str:
    """Replace leaked uppercase framework codes (EO, NE, PL, …) with full human words."""
    if not text:
        return text
    out = text
    for pattern, full in _CODE_FULL_FORMS:
        out = pattern.sub(full, out)
    return out


_FALLBACK_TOPICS: list[tuple[str, str]] = [
    ("Body and breath", 'When you imagine taking the next visible step on "{goal}", what do you notice first in your body, breath, or energy?'),
    ("Protector voice", 'What inner voice or story shows up to talk you out of moving on "{goal}"?'),
    ("Fear if you act", 'If you actually moved forward on "{goal}" today, what are you afraid would happen?'),
    ("Cost to the goal", 'How does your usual avoidance limit the measurable outcome you want from "{goal}"?'),
    ("Past pattern", 'When you tried something similar to "{goal}" before, what happened — and what made you stop?'),
    ("Hidden rule", 'What unspoken rule are you obeying that says you cannot fully go for "{goal}" yet?'),
    ("Avoidance behaviours", 'Name 2–3 specific things you do instead of the next step on "{goal}".'),
    ("Identity risk", 'Who would you have to become to complete "{goal}" — and what feels unsafe about that?'),
    ("Visibility or judgement", 'On "{goal}", do you avoid being seen, judged, wrong, or needy — which hits hardest and how?'),
    ("Smallest disobedience", 'What is the smallest action on "{goal}" that would disobey your usual avoidance?'),
    ("Proof in 7 days", 'What proof would you accept from yourself in the next 7 days that you are serious about "{goal}"?'),
    ("Recovery after action", 'After you take a small step on "{goal}", what makes you collapse, overthink, or pull back?'),
    ("Resistance belief", 'What do you believe about yourself when you avoid working on "{goal}" — even if you never say it out loud?'),
    ("Shame hook", 'What would feel shameful or exposing if someone saw you struggling with "{goal}"?'),
    ("Permission structure", 'What conditions do you wait for before you allow yourself to act on "{goal}" (energy, mood, time, approval)?'),
    ("All-or-nothing", 'Where does all-or-nothing thinking show up around "{goal}" — and how does it justify stopping?'),
    ("Comparison trap", 'Who do you compare yourself to around "{goal}", and how does that comparison become a reason to delay?'),
    ("Energy story", 'What story do you tell yourself about your energy or capacity when "{goal}" comes up?'),
    ("Commitment meaning", 'What does fully committing to "{goal}" mean you can no longer pretend or postpone?'),
    ("Self-trust", 'When you think about past attempts at "{goal}", what breaks your trust in yourself — and how does that show up now?'),
    ("Withdrawal pattern", 'After a good day on "{goal}", what pulls you back into old habits — reward, relief, or collapse?'),
    ("Success cost", 'If you actually succeeded at "{goal}", what uncomfortable change would you have to live with?'),
    ("Integration", 'What would need to shift in daily life so "{goal}" feels normal rather than a battle every time?'),
]


def _is_obvious_gibberish(text: str) -> bool:
    """Fast local check for keyboard mash / nonsense (backup to Node LLM validation)."""
    t = (text or "").strip()
    if len(t) < 2:
        return True
    letters = re.sub(r"[^a-zA-Z]", "", t)
    if len(letters) < 2:
        return True
    if len(letters) >= 5 and not re.search(r"[aeiouAEIOU]", letters):
        return True
    words = re.findall(r"[a-zA-Z]{3,}", t)
    if words:
        vowelless = sum(1 for w in words if not re.search(r"[aeiouAEIOU]", w))
        if vowelless >= max(1, len(words) // 2):
            return True
    return False


def _count_answered(transcript: list[dict], *, last_answer_valid: bool = True) -> int:
    """Count completed questions — tracks Q progression, not raw user messages."""
    highest = 0
    pending_q = 0
    seen_user = False
    for m in transcript:
        if m.get("role") == "assistant":
            match = re.search(r"\*\*Q(\d+)", m.get("content") or "", re.I)
            if match:
                q = int(match.group(1))
                if seen_user and pending_q > 0:
                    highest = max(highest, pending_q)
                pending_q = q
                seen_user = False
        elif m.get("role") == "user":
            seen_user = True
    if seen_user and pending_q > 0:
        highest = max(highest, pending_q)
    if not last_answer_valid and transcript and transcript[-1].get("role") == "user":
        last_q = _last_q_number(transcript)
        if last_q > 0:
            highest = min(highest, max(0, last_q - 1))
    return highest


def _last_q_number(transcript: list[dict]) -> int:
    n = 0
    for m in transcript:
        if m.get("role") != "assistant":
            continue
        match = re.search(r"\*\*Q(\d+)", m.get("content") or "", re.I)
        if match:
            n = max(n, int(match.group(1)))
    return n


def _build_completion_message(target_count: int, goal: str) -> str:
    return (
        f'Great work — you\'ve answered all {target_count} questions about "{goal}".\n\n'
        "When you're ready, click **Complete mapping** below to extract your resistance "
        "structure and continue."
    )


def _next_question_number(
    transcript: list[dict],
    target_count: int,
    *,
    last_answer_valid: bool = True,
) -> int:
    last = _last_q_number(transcript)
    if not last_answer_valid:
        return max(1, last) if last > 0 else 1
    answered = _count_answered(transcript, last_answer_valid=True)
    if last <= 1 and answered >= 1:
        return min(target_count, 2)
    return min(target_count, max(last + 1, 1))


def _extract_assistant_message(parsed: dict) -> str:
    if not parsed:
        return ""
    for key in ("assistant_message", "message", "question", "reply", "content"):
        val = parsed.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _fallback_question(
    q_num: int,
    goal: str,
    *,
    reask: bool = False,
    last_user: str = "",
    prompts: dict | None = None,
) -> str:
    topics = _FALLBACK_TOPICS
    idx = max(0, min(q_num - 2, len(topics) - 1))
    title, template = topics[idx]
    body = template.format(goal=goal)
    if reask:
        preview = last_user[:60].strip() if last_user else ""
        if preview:
            lead = (
                f'Hmm, that doesn\'t look like a response I can work with ("{preview}") — '
                "no worries, let me rephrase."
            )
        else:
            lead = "That didn't come through clearly — no worries, let me rephrase."
        return f"{lead}\n\n**Q{q_num} — {title}**\n{body}"
    return f"Got it — thanks for sharing that.\n\n**Q{q_num} — {title}**\n{body}"


def _find_last_assistant_question(transcript: list[dict]) -> str:
    for m in reversed(transcript):
        if m.get("role") == "assistant" and re.search(r"Q\d+", m.get("content") or "", re.I):
            return (m.get("content") or "").strip()
    return ""


def _build_reask_from_previous(
    q_num: int,
    last_user: str,
    previous_content: str,
    goal: str,
    *,
    prompts: dict | None = None,
) -> str:
    preview = (last_user or "").strip()[:80]
    if preview:
        lead = (
            f'Hmm, that doesn\'t look like a response I can work with ("{preview}") — '
            "no worries, let me rephrase."
        )
    else:
        lead = "That didn't come through clearly — no worries, let me rephrase."

    title_match = re.search(r"\*\*Q\d+\s*[—–-]\s*([^*\n]+)", previous_content, re.I)
    title = (title_match.group(1).replace("**", "").strip() if title_match else "This question")
    body_match = re.search(r"\*\*Q\d+[^*\n]*\*\*\s*\n?([\s\S]*)$", previous_content, re.I)
    body = body_match.group(1).strip() if body_match else ""
    if not body:
        return _fallback_question(q_num, goal, reask=True, last_user=last_user, prompts=prompts)
    return f"{lead}\n\n**Q{q_num} — {title}**\n{body}"


def _build_turn_user_payload(
    *,
    active_goal_context: dict,
    transcript: list[dict],
    target_count: int,
    last_answer_valid: bool = True,
    stay_on_question: int | None = None,
) -> str:
    goal = (
        active_goal_context.get("specific_goal")
        or active_goal_context.get("goal_name")
        or "your goal"
    )
    label = active_goal_context.get("domain_label") or active_goal_context.get("active_domain") or "this domain"
    answered = _count_answered(transcript, last_answer_valid=last_answer_valid)
    next_q = _next_question_number(
        transcript,
        target_count,
        last_answer_valid=last_answer_valid,
    )
    if stay_on_question and stay_on_question > 0 and not last_answer_valid:
        next_q = stay_on_question

    last_user = ""
    for m in reversed(transcript):
        if m.get("role") == "user":
            last_user = (m.get("content") or "").strip()
            break

    if not last_answer_valid and last_user:
        instruction = (
            f'The user\'s last reply was invalid, unclear, or gibberish ("{last_user[:80]}"). '
            f'Output: (1) A brief warm response — e.g. "Hmm, that doesn\'t look like a response I can work with — no worries." '
            f'or "I\'m not sure that answers the question — let me rephrase." '
            f'(2) Then re-ask **Q{next_q} — [topic]** in completely different words with one short example. '
            f"Do NOT advance to Q{next_q + 1}. Do NOT count their last message as an answer."
        )
    elif len(last_user) < 3:
        instruction = (
            f"The user's last reply was too short. "
            f'Output: (1) Brief warm note that you need a bit more (e.g. "Could you say a little more?"). '
            f"(2) Re-ask **Q{next_q}** in simpler words with one example. Do not advance question number."
        )
    elif answered >= target_count:
        instruction = (
            f"User has answered all {target_count} questions. "
            "Acknowledge completion warmly in one short paragraph. "
            "Do not ask another intake question. Set finalize_ready true."
        )
    else:
        instruction = (
            f'The user gave a valid answer to the previous question ("{last_user[:120]}"). '
            f'Output: (1) Brief acknowledgment that reflects what they shared (e.g. "Got it — I hear that."). '
            f'(2) Then ask exactly ONE new question **Q{next_q} — <short topic>**. '
            f"It MUST explore a fresh angle (resistance, avoidance, protector, fear, or cost) tied to goal "
            f'"{goal}" in the {label} domain. Do not repeat prior assistant question text verbatim.'
        )

    return json.dumps(
        {
            "instruction": instruction,
            "next_question_number": next_q,
            "answered_count": answered,
            "target_count": target_count,
            "ACTIVE_GOAL_CONTEXT": active_goal_context,
            "transcript": transcript,
        },
        indent=2,
    )


def _generate_question(
    *,
    system: str,
    user_payload: str,
    next_q: int,
    goal: str,
    last_answer_valid: bool = True,
    last_user: str = "",
    prompts: dict | None = None,
) -> tuple[str, dict]:
    parsed: dict = {}
    content = ""

    if last_answer_valid:
        format_hint = (
            "Reply with markdown only. Structure:\n"
            "(1) One brief sentence acknowledging or reflecting what the user shared.\n"
            "(2) Blank line.\n"
            f"(3) **Q{next_q} — topic** then the next question. One question only."
        )
    else:
        format_hint = (
            "Reply with markdown only. Structure:\n"
            "(1) One brief warm sentence — their reply was invalid or gibberish; "
            'say e.g. "Hmm, that doesn\'t look like a response I can work with — no worries." '
            'or "I\'m not sure that answers the question — let me rephrase."\n'
            "(2) Blank line.\n"
            f"(3) **Q{next_q} — topic** then the SAME question rephrased in new words with one example. "
            f"Do NOT use Q{next_q + 1}."
        )

    try:
        parsed = chat_json(system, user_payload)
        content = _extract_assistant_message(parsed)
    except Exception:
        parsed = {}

    if not content or not re.search(rf"\*\*Q{next_q}\b", content, re.I):
        try:
            text = chat_text(
                system + "\n\n" + format_hint,
                [{"role": "user", "content": user_payload}],
            )
            if text.strip():
                content = text.strip()
                parsed = {**parsed, "assistant_message": content}
        except Exception:
            pass

    if not content or not re.search(r"\*\*Q\d+", content, re.I):
        content = _fallback_question(
            next_q,
            goal,
            reask=not last_answer_valid,
            last_user=last_user,
            prompts=prompts,
        )
        parsed = {
            **parsed,
            "assistant_message": content,
            "last_question_number": next_q,
            "pending_question": True,
        }

    return content, parsed


def map_resistance_turn(
    *,
    active_goal_context: dict,
    transcript: list[dict] | None = None,
    target_count: int = 25,
    user_name: str = "there",
    prompts: dict | None = None,
    last_answer_valid: bool = True,
    stay_on_question: int | None = None,
) -> dict:
    transcript = list(transcript or [])
    domain = active_goal_context.get("active_domain") or "income"
    label = active_goal_context.get("domain_label") or domain
    goal = (
        active_goal_context.get("specific_goal")
        or active_goal_context.get("goal_name")
        or "your goal"
    )
    outcome = active_goal_context.get("measurable_outcome") or "your 90-day outcome"

    if transcript and transcript[-1].get("role") == "user":
        last_user_text = (transcript[-1].get("content") or "").strip()
        if not last_answer_valid or _is_obvious_gibberish(last_user_text):
            last_answer_valid = False

    if not transcript:
        welcome = WELCOME_TEMPLATE.format(
            name=user_name,
            label=label,
            goal=goal,
            outcome=outcome,
            target_count=target_count,
        )
        assistant = {"role": "assistant", "content": welcome}
        full = [assistant]
        return _pack_turn(full, target_count, pending_question=True)

    system = compose_map_resistance_turn_system(prompts)
    user_payload = _build_turn_user_payload(
        active_goal_context=active_goal_context,
        transcript=transcript,
        target_count=target_count,
        last_answer_valid=last_answer_valid,
        stay_on_question=stay_on_question,
    )
    next_q = _next_question_number(
        transcript,
        target_count,
        last_answer_valid=last_answer_valid,
    )
    if stay_on_question and stay_on_question > 0 and not last_answer_valid:
        next_q = stay_on_question

    last_user_text = ""
    if transcript and transcript[-1].get("role") == "user":
        last_user_text = (transcript[-1].get("content") or "").strip()

    if not last_answer_valid:
        prev_q = _find_last_assistant_question(transcript)
        content = _build_reask_from_previous(
            next_q, last_user_text, prev_q, goal, prompts=prompts
        )
        full = [*transcript, {"role": "assistant", "content": content}]
        answered = _count_answered(transcript, last_answer_valid=False)
        return _pack_turn(
            full,
            target_count,
            answered_count=answered,
            last_question_number=next_q,
            pending_question=True,
            finalize_ready=False,
        )

    answered_before = _count_answered(transcript, last_answer_valid=True)
    if answered_before >= target_count:
        content = _build_completion_message(target_count, goal)
        full = [*transcript, {"role": "assistant", "content": content}]
        return _pack_turn(
            full,
            target_count,
            answered_count=target_count,
            last_question_number=target_count,
            pending_question=False,
            finalize_ready=True,
        )

    content, parsed = _generate_question(
        system=system,
        user_payload=user_payload,
        next_q=next_q,
        goal=goal,
        last_answer_valid=last_answer_valid,
        last_user=last_user_text,
        prompts=prompts,
    )
    content = _expand_framework_codes(content)

    if not last_answer_valid and content:
        content = re.sub(r"\*\*Q\d+\b", f"**Q{next_q}", content, count=1, flags=re.I)
        content = re.sub(r"\bQ\d+\s*[—–-]", f"Q{next_q} —", content, count=1, flags=re.I)

    full = [*transcript, {"role": "assistant", "content": content}]
    answered = int(
        parsed.get("answered_count")
        or _count_answered(transcript, last_answer_valid=last_answer_valid)
    )
    last_q = int(parsed.get("last_question_number") or _last_q_number(full))
    pending = bool(parsed.get("pending_question", True))
    if not last_answer_valid:
        pending = True
        last_q = next_q
    finalize_ready = bool(parsed.get("finalize_ready")) or (
        answered >= target_count and not pending and last_answer_valid
    )

    return _pack_turn(
        full,
        target_count,
        answered_count=answered,
        last_question_number=last_q,
        pending_question=pending,
        finalize_ready=finalize_ready,
    )


def _pack_turn(
    transcript: list[dict],
    target_count: int,
    *,
    answered_count: int | None = None,
    last_question_number: int | None = None,
    pending_question: bool = False,
    finalize_ready: bool = False,
) -> dict:
    answered = answered_count if answered_count is not None else _count_answered(transcript)
    last_q = last_question_number if last_question_number is not None else _last_q_number(transcript)
    last_assistant = next(
        (m for m in reversed(transcript) if m.get("role") == "assistant"),
        None,
    )
    return {
        "nextMessage": last_assistant,
        "transcript": transcript,
        "messages": transcript,
        "answeredCount": answered,
        "pendingQuestion": pending_question,
        "progress": {
            "answered": answered,
            "total": target_count,
            "currentQuestion": last_q,
        },
        "intakeState": {
            "transcript": transcript,
            "answeredCount": answered,
            "lastQuestionNumber": last_q,
            "pendingQuestion": pending_question,
            "mode": "map_resistance",
        },
        "finalize_ready": finalize_ready,
    }


def extract_domain_structure(
    *,
    transcript: list[dict],
    active_goal_context: dict,
    domain: str,
    prompts: dict | None = None,
) -> dict:
    from app.services.prompt_compose import compose_map_extract_system

    instruction = MAP_RESISTANCE_EXTRACT_RULES
    payload = json.dumps(
        {
            "instruction": instruction,
            "ACTIVE_GOAL_CONTEXT": active_goal_context,
            "domain": domain,
            "transcript": transcript,
        },
        indent=2,
    )
    system = compose_map_extract_system(prompts)
    parsed = chat_json(system, payload, max_completion_tokens=4000)
    parsed["map_resistance_complete"] = True
    from app.services.resistance_narrative import enrich_resistance_narrative

    return enrich_resistance_narrative(parsed, active_goal_context=active_goal_context)
