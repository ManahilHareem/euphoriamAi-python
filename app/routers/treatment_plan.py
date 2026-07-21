from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import merge_feature_flags
from app.engines.treatment_plan_30d import generate_treatment_plan_30d

router = APIRouter(prefix="/v1/treatment-plan", tags=["treatment-plan"])


class TreatmentPlanRequest(BaseModel):
    user_id: int | None = None
    domain_map: dict = Field(default_factory=dict)
    active_goal_context: dict | None = None
    state_vector_v2: dict | None = None
    prompts: dict | None = None
    feature_flags: dict | None = None


@router.post("/generate")
def post_generate_treatment_plan(body: TreatmentPlanRequest):
    flags = merge_feature_flags(body.feature_flags or (body.prompts or {}).get("feature_flags"))
    if not flags.get("treatment_plan_enabled"):
        raise HTTPException(status_code=403, detail="Treatment plan generation is not enabled")

    try:
        plan = generate_treatment_plan_30d(
            domain_map=body.domain_map,
            active_goal_context=body.active_goal_context,
            state_vector_v2=body.state_vector_v2,
            prompts=body.prompts,
        )
        return {
            "treatment_plan_30d": plan,
            "state_vector_v2": body.state_vector_v2,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
