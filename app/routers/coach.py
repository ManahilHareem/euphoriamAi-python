from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.coach import coach_reply, friction_rescue

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


@router.post("/reply")
def post_coach_reply(body: CoachReplyRequest):
    try:
        result = coach_reply(
            domain_map=body.domain_map,
            checkin=body.checkin,
            messages=body.messages,
            user_message=body.user_message,
            prompts=body.prompts,
            active_goal_context=body.active_goal_context,
            user_coach_context=body.user_coach_context,
        )
        return result
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


@router.post("/friction")
def post_friction(body: FrictionRequest):
    return friction_rescue(
        domain_map=body.domain_map,
        checkin=body.checkin,
        messages=body.messages,
        user_message=body.user_message,
        prompts=body.prompts,
        active_goal_context=body.active_goal_context,
        user_coach_context=body.user_coach_context,
    )
