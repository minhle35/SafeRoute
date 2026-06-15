import time

from fastapi import FastAPI, Request

from app.api import exceptions
from app.api.route_chat_completion_middleware import router as chat_router
from app.settings import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.app_version)

# Register LiteLLM exception → structured JSON response handlers
exceptions.register(app)

# Mount routers
app.include_router(chat_router)


# =============================================================================
# MIDDLEWARE
# =============================================================================

@app.middleware("http")
async def latency_middleware(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    response.headers["X-Latency-Ms"] = str(round((time.monotonic() - start) * 1000, 2))
    return response


# =============================================================================
# HEALTH
# =============================================================================

@app.get("/health", tags=["Ops"])
async def health():
    return {"status": "ok", "guardrail": "active"}
