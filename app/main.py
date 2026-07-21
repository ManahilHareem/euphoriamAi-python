from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import coach, extraction, lead_email, map_resistance, member_email, treatment_plan

# UptimeRobot and similar monitors use HEAD; no auth on these paths.
PUBLIC_MONITOR_PATHS = {"/", "/health"}

app = FastAPI(title="Euphoriam AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def optional_internal_key(request, call_next):
    if settings.ai_internal_key:
        key = request.headers.get("x-internal-key") or request.headers.get("X-Internal-Key")
        if key != settings.ai_internal_key and request.url.path not in PUBLIC_MONITOR_PATHS:
            raise HTTPException(status_code=401, detail="Invalid internal key")
    return await call_next(request)


@app.get("/")
def root():
    return {"ok": True, "service": "euphoriam-ai", "health": "/health"}


@app.head("/")
def root_head():
    return Response(status_code=200)


@app.get("/health")
def health():
    return {"ok": True, "service": "euphoriam-ai"}


@app.head("/health")
def health_head():
    return Response(status_code=200)


app.include_router(coach.router)
app.include_router(treatment_plan.router)
app.include_router(map_resistance.router)
app.include_router(extraction.router)
app.include_router(member_email.router)
app.include_router(lead_email.router)
