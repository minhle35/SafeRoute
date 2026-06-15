import time
from fastapi import FastAPI, Request

from fastapi.security.api_key import APIKeyHeader

from app.settings import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.app_version)

api_key_header = APIKeyHeader(name=settings.auth_header_name, auto_error=True)

# In-memory daily spend per developer token.
# Replace with Redis + TTL in production so it resets at midnight automatically.
_daily_spend: dict[str, float] = {}
DAILY_BUDGET_USD = 5.00


# =============================================================================
# MIDDLEWARE — capture request latency for every call
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
