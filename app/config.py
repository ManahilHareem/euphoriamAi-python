from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_model_mini: str = "gpt-4o-mini"
    # Coach check-in only; empty falls back to openai_model. Env: COACH_OPENAI_MODEL
    coach_openai_model: str = ""
    ai_internal_key: str = ""
    port: int = 8000
    coach_cert_deep_enabled: bool = False
    brain_prompt_v2_shadow: bool = False
    treatment_plan_enabled: bool = False
    brain_prompt_rag_enabled: bool = False


settings = Settings()


def merge_feature_flags(payload_flags: dict | None) -> dict:
    """Node payload flags override env defaults."""
    base = {
        "coach_cert_deep_enabled": settings.coach_cert_deep_enabled,
        "brain_prompt_v2_shadow": settings.brain_prompt_v2_shadow,
        "treatment_plan_enabled": settings.treatment_plan_enabled,
        "brain_prompt_rag_enabled": settings.brain_prompt_rag_enabled,
    }
    if payload_flags:
        for key in base:
            if payload_flags.get(key) is not None:
                base[key] = bool(payload_flags[key])
    return base
