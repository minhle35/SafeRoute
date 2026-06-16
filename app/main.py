import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.api import exceptions
from app.api.route_chat_completion_middleware import router as chat_router
from app.settings import get_settings
from app.database import init_db

settings = get_settings()


def _configure_litellm() -> None:
    # pydantic-settings loads .env into the Settings object but does NOT write to
    # os.environ, so LiteLLM's env-var lookups find nothing. Set them explicitly here.
    if settings.openrouter_api_key:
        os.environ["OPENROUTER_API_KEY"] = settings.openrouter_api_key
    # OR_SITE_URL / OR_APP_NAME appear as HTTP-Referer / X-Title in OpenRouter requests
    # and show up in the OpenRouter dashboard for per-app usage tracking.
    os.environ.setdefault("OR_SITE_URL", settings.or_site_url)
    os.environ.setdefault("OR_APP_NAME", settings.or_app_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_litellm()
    await init_db(settings.database_url)
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

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
