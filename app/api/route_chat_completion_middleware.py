import time

from fastapi import APIRouter, Depends, HTTPException
import litellm
from litellm import ModelResponse

from app.dependencies.auth import validate_developer_token
from app.schemas.chatMessage import ChatCompletionRequest
from app.settings import get_settings
from vicroads_guardrails.logger import estimate_cost, log_request
from vicroads_guardrails.redactor import redact_messages

settings = get_settings()
router = APIRouter()

# In-memory daily spend per developer. Replace with Redis + TTL in production.
_daily_spend: dict[str, float] = {}
DAILY_BUDGET_USD = 5.00


@router.post("/v1/chat/completions", tags=["Gateway"])
async def secure_chat_completion(
    request: ChatCompletionRequest,
    developer_token: str = Depends(validate_developer_token),
):
    developer_id = developer_token.removeprefix("Bearer ").strip()
    messages_dicts = [m.model_dump() for m in request.messages]

    # ── 1. PRE-FLIGHT: token count ────────────────────────────────────────────
    token_count = litellm.token_counter(
        model=request.model or settings.default_model,
        messages=messages_dicts,
    )
    if token_count > settings.llm_max_tokens:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "prompt_too_long",
                "prompt_tokens": token_count,
                "max_allowed": settings.llm_max_tokens,
            },
        )

    # ── 2. BUDGET: check daily spend before forwarding ────────────────────────
    spent = _daily_spend.get(developer_id, 0.0)
    if spent >= DAILY_BUDGET_USD:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "daily_budget_exceeded",
                "spent_usd": round(spent, 4),
                "limit_usd": DAILY_BUDGET_USD,
            },
        )

    # ── 3. REDACT: PII scrubbed in RAM before any HTTP packet is built ────────
    clean_messages, redacted_types = redact_messages(messages_dicts)

    # ── 4. FORWARD: timeout + fallback chain ─────────────────────────────────
    t0 = time.monotonic()
    response = await litellm.acompletion(
        model=request.model or settings.default_model,
        messages=clean_messages,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        timeout=settings.llm_timeout,
        num_retries=2,
        fallbacks=["gpt-3.5-turbo"],
    )
    latency_ms = (time.monotonic() - t0) * 1000

    # ── 5. COST: update spend ledger ─────────────────────────────────────────
    # acompletion without stream=True always returns ModelResponse.
    # The assert narrows the union type for pyright and guards at runtime.
    assert isinstance(response, ModelResponse), "expected non-streaming response"
    model_name = response.model or settings.default_model
    input_tok = response.usage.prompt_tokens  # type: ignore[union-attr]
    output_tok = response.usage.completion_tokens  # type: ignore[union-attr]
    cost = estimate_cost(model_name, input_tok, output_tok)
    _daily_spend[developer_id] = spent + cost

    # ── 6. AUDIT: emit structured JSON log ────────────────────────────────────
    log_request(
        developer_id=developer_id,
        model=model_name,
        pii_detected=bool(redacted_types),
        redacted_types=redacted_types,
        input_tokens=input_tok,
        output_tokens=output_tok,
        cost_usd=cost,
        latency_ms=latency_ms,
    )

    return response
