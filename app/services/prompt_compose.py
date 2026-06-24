"""Compose system prompts: hardcoded suite + DB product prompts (Coach Brain, Brain, optional overlays)."""
from __future__ import annotations

from app.services.prompts import (
    FRICTION_RESCUE_RULES,
    MAP_RESISTANCE_EXTRACT_RULES,
    MAP_RESISTANCE_TURN_RULES,
    _COACH_BARRIER_AND_LOOP_RULES,
    _COACH_CONTEXT_RULES,
    _COACH_DIRECTIVE_PROGRESSION_RULES,
    _COACH_HUMAN_TONE_RULES,
    _COACH_PROOF_INTEGRATION_RULES,
    _COACH_SESSION_PHASE_RULES,
    _COACH_WHAT_NEXT_RULES,
    _COACH_EVIDENCE_RULES,
    missing_prompt_notice,
)

_MAX_TURN_SECTION_CHARS = 8_000


def _section(title: str, body: str) -> str:
    return f"--- {title} ---\n{body.strip()}"


def _truncate(body: str, max_chars: int = _MAX_TURN_SECTION_CHARS) -> str:
    body = (body or "").strip()
    if len(body) <= max_chars:
        return body
    return (
        body[:max_chars]
        + "\n\n[... section truncated for map-resistance chat turn; full text used at finalize ...]"
    )


def compose_coach_system(prompts: dict | None) -> str:
    prompts = prompts or {}
    parts: list[str] = [
        _COACH_HUMAN_TONE_RULES,
        _COACH_DIRECTIVE_PROGRESSION_RULES,
        _COACH_EVIDENCE_RULES,
        _COACH_WHAT_NEXT_RULES,
        _COACH_BARRIER_AND_LOOP_RULES,
        _COACH_PROOF_INTEGRATION_RULES,
        _COACH_SESSION_PHASE_RULES,
        _COACH_CONTEXT_RULES,
    ]
    missing: list[str] = []

    if prompts.get("coach_brain_prompt"):
        parts.append(_section("COACH BRAIN PROMPT (Goal-Specific OS)", prompts["coach_brain_prompt"]))
    else:
        missing.append("Coach Brain Prompt")

    if prompts.get("brain_prompt"):
        parts.append(
            _section(
                "BRAIN PROMPT (Canonical library — signatures, reps, UC routing)",
                prompts["brain_prompt"],
            )
        )
    else:
        missing.append("Brain Prompt")

    if prompts.get("stage1_daily_coach"):
        parts.append(_section("DAILY COACH (admin overlay)", prompts["stage1_daily_coach"]))

    if missing:
        parts.append(missing_prompt_notice(*missing))
    return "\n\n".join(parts)


def compose_friction_system(prompts: dict | None) -> str:
    prompts = prompts or {}
    parts: list[str] = [FRICTION_RESCUE_RULES]
    missing: list[str] = []

    if prompts.get("coach_brain_prompt"):
        parts.append(_section("COACH BRAIN PROMPT", prompts["coach_brain_prompt"]))
    else:
        missing.append("Coach Brain Prompt")

    if prompts.get("brain_prompt"):
        parts.append(_section("BRAIN PROMPT", prompts["brain_prompt"]))
    else:
        missing.append("Brain Prompt")

    if prompts.get("stage1_friction_rescue"):
        parts.append(_section("FRICTION RESCUE (admin overlay)", prompts["stage1_friction_rescue"]))

    if missing:
        parts.append(missing_prompt_notice(*missing))
    return "\n\n".join(parts)


def compose_map_resistance_turn_system(prompts: dict | None) -> str:
    prompts = prompts or {}
    parts: list[str] = [MAP_RESISTANCE_TURN_RULES]
    missing: list[str] = []

    if prompts.get("stage1_map_resistance"):
        parts.append(_section("MAP RESISTANCE (admin overlay)", _truncate(prompts["stage1_map_resistance"])))

    if prompts.get("coach_brain_prompt"):
        parts.append(
            _section("COACH BRAIN PROMPT", _truncate(prompts["coach_brain_prompt"], 6_000))
        )
    else:
        missing.append("Coach Brain Prompt")

    if prompts.get("brain_prompt"):
        parts.append(_section("BRAIN PROMPT (truncated)", _truncate(prompts["brain_prompt"], 4_000)))
    else:
        missing.append("Brain Prompt")

    if missing:
        parts.append(missing_prompt_notice(*missing))
    return "\n\n".join(parts)


def compose_map_resistance_system(prompts: dict | None) -> str:
    return compose_map_resistance_turn_system(prompts)


def compose_map_extract_system(prompts: dict | None) -> str:
    prompts = prompts or {}
    parts: list[str] = [MAP_RESISTANCE_EXTRACT_RULES]
    missing: list[str] = []

    if prompts.get("stage1_map_resistance"):
        parts.append(_section("MAP RESISTANCE (admin overlay)", prompts["stage1_map_resistance"]))

    if prompts.get("coach_brain_prompt"):
        parts.append(_section("COACH BRAIN PROMPT", prompts["coach_brain_prompt"]))
    else:
        missing.append("Coach Brain Prompt")

    if prompts.get("brain_prompt"):
        parts.append(_section("BRAIN PROMPT", prompts["brain_prompt"]))
    else:
        missing.append("Brain Prompt")

    if missing:
        parts.append(missing_prompt_notice(*missing))
    return "\n\n".join(parts)
