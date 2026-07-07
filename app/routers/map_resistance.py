from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.map_resistance import extract_domain_structure, map_resistance_turn
from app.services.prompt_cache import resolve_prompts

router = APIRouter(prefix="/v1/map-resistance", tags=["map-resistance"])


class TurnRequest(BaseModel):
    active_goal_context: dict = Field(default_factory=dict)
    transcript: list[dict] = Field(default_factory=list)
    messages: list[dict] | None = None
    target_count: int = 25
    user_name: str = "there"
    prompts: dict | None = None
    prompts_cache_key: str | None = None
    last_answer_valid: bool = True
    stay_on_question: int | None = None


class FinalizeRequest(BaseModel):
    active_goal_context: dict = Field(default_factory=dict)
    transcript: list[dict] = Field(default_factory=list)
    domain: str = "income"
    prompts: dict | None = None
    prompts_cache_key: str | None = None


def _resolve_request_prompts(body) -> dict | None:
    if not body.prompts and not body.prompts_cache_key:
        return None
    resolved = resolve_prompts(body.prompts, body.prompts_cache_key)
    if resolved is None and body.prompts_cache_key:
        raise HTTPException(status_code=428, detail="prompt_cache_miss")
    return resolved


@router.post("/turn")
def post_turn(body: TurnRequest):
    transcript = body.transcript or body.messages or []
    prompts = _resolve_request_prompts(body)
    return map_resistance_turn(
        active_goal_context=body.active_goal_context,
        transcript=transcript,
        target_count=body.target_count,
        user_name=body.user_name,
        prompts=prompts,
        last_answer_valid=body.last_answer_valid,
        stay_on_question=body.stay_on_question,
    )


@router.post("/finalize")
def post_finalize(body: FinalizeRequest):
    prompts = _resolve_request_prompts(body)
    structure = extract_domain_structure(
        transcript=body.transcript,
        active_goal_context=body.active_goal_context,
        domain=body.domain,
        prompts=prompts,
    )
    return {"structure": structure, "domain_structure": structure}
