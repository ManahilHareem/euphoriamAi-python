from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.coach import coach_reply, friction_rescue
from app.services.prompt_cache import resolve_prompts

router = APIRouter(prefix="/v1/coach", tags=["coach"])


class CoachReplyRequest(BaseModel):
    user_id: int | None = None
    domain_map: dict = Field(default_factory=dict)
    active_goal_context: dict | None = None
    user_coach_context: dict | None = None
    checkin: dict = Field(default_factory=dict)
    messages: list[dict] = Field(default_factory=list)
    user_message: str | None = None
    prompts: dict | None = None
    prompts_cache_key: str | None = None


def _resolve_request_prompts(body) -> dict | None:
    if not body.prompts and not body.prompts_cache_key:
        return None
    resolved = resolve_prompts(body.prompts, body.prompts_cache_key)
    if resolved is None and body.prompts_cache_key:
        raise HTTPException(status_code=428, detail="prompt_cache_miss")
    return resolved


@router.post("/reply")
def post_coach_reply(body: CoachReplyRequest):
    try:
        prompts = _resolve_request_prompts(body)
        result = coach_reply(
            domain_map=body.domain_map,
            checkin=body.checkin,
            messages=body.messages,
            user_message=body.user_message,
            prompts=prompts,
            active_goal_context=body.active_goal_context,
            user_coach_context=body.user_coach_context,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class FrictionRequest(BaseModel):
    domain_map: dict = Field(default_factory=dict)
    active_goal_context: dict | None = None
    user_coach_context: dict | None = None
    checkin: dict = Field(default_factory=dict)
    messages: list[dict] = Field(default_factory=list)
    user_message: str | None = None
    prompts: dict | None = None
    prompts_cache_key: str | None = None


@router.post("/friction")
def post_friction(body: FrictionRequest):
    prompts = _resolve_request_prompts(body)
    return friction_rescue(
        domain_map=body.domain_map,
        checkin=body.checkin,
        messages=body.messages,
        user_message=body.user_message,
        prompts=prompts,
        active_goal_context=body.active_goal_context,
        user_coach_context=body.user_coach_context,
    )
