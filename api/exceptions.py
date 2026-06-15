from fastapi import Request
from fastapi.responses import JSONResponse
from litellm.exceptions import (
    AuthenticationError,
    ContextWindowExceededError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

from app.settings import get_settings

settings = get_settings()


async def handle_model_unavailable(request: Request, exc: ServiceUnavailableError):
    return JSONResponse(status_code=503, content={
        "error": "model_unavailable",
        "detail": "All configured models are currently unavailable. Try again shortly.",
        "retry_after_seconds": 30,
    })


async def handle_rate_limit(request: Request, exc: RateLimitError):
    return JSONResponse(status_code=429, content={
        "error": "rate_limited",
        "detail": "Upstream provider rate limit reached. Apply exponential backoff.",
    })


async def handle_context_exceeded(request: Request, exc: ContextWindowExceededError):
    return JSONResponse(status_code=422, content={
        "error": "context_window_exceeded",
        "detail": "Prompt is too long for the selected model. Shorten your messages.",
    })


async def handle_timeout(request: Request, exc: Timeout):
    return JSONResponse(status_code=504, content={
        "error": "llm_timeout",
        "detail": f"LLM did not respond within {settings.llm_timeout}s.",
        "tip": "Use stream=true for long responses so tokens arrive incrementally.",
    })


async def handle_upstream_auth(request: Request, exc: AuthenticationError):
    return JSONResponse(status_code=401, content={
        "error": "upstream_auth_failed",
        "detail": "API key for the upstream LLM provider is invalid or expired.",
    })


def register(app) -> None:
    """Attach all LiteLLM exception handlers to the FastAPI app."""
    app.add_exception_handler(ServiceUnavailableError, handle_model_unavailable)
    app.add_exception_handler(RateLimitError,          handle_rate_limit)
    app.add_exception_handler(ContextWindowExceededError, handle_context_exceeded)
    app.add_exception_handler(Timeout,                 handle_timeout)
    app.add_exception_handler(AuthenticationError,     handle_upstream_auth)
