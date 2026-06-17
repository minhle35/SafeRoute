# LiteLLM — Role in SafeRoute

## What LiteLLM Does Here

SafeRoute uses the **LiteLLM Python SDK** (not the LiteLLM Proxy CLI server). LiteLLM provides a single async call that can route to any LLM provider behind a unified OpenAI-compatible interface:

```python
response = await litellm.acompletion(
    model="openrouter/meta-llama/llama-3.1-8b-instruct:free",
    messages=clean_messages,
    max_tokens=request.max_tokens,
    temperature=request.temperature,
    timeout=settings.llm_timeout,
    num_retries=2,
    fallbacks=["openrouter/openai/gpt-3.5-turbo"],
)
```

## Key Design Decisions

### SDK vs Proxy

| | LiteLLM SDK | LiteLLM Proxy |
|---|---|---|
| Deployment | Embedded in our FastAPI process | Separate server process |
| `async_pre_call_hook` | **Never fires** | Fires on every request |
| Overhead | Zero — library call | Network hop to localhost |
| Control | Full (we own the code) | Limited to hook interface |
| Our choice | ✅ | — |

Because we use the SDK, PII redaction **cannot** be done in a hook. It is called explicitly in `route_chat_completion_middleware.py` as step 3, before `acompletion()` is ever called.

### Model Routing via OpenRouter

All models are prefixed with `openrouter/` which tells LiteLLM to route through OpenRouter's unified API rather than directly to each provider. This means:

- One API key (`OPENROUTER_API_KEY`) covers all models
- Model switching requires only a config change, not new provider credentials
- OpenRouter's dashboard provides per-app cost tracking (via `OR_SITE_URL` / `OR_APP_NAME` headers)

### Why pydantic-settings env vars need manual forwarding

`pydantic-settings` loads `.env` into the `Settings` object but does **not** write values to `os.environ`. LiteLLM reads API keys from `os.environ` at call time, so without the bridge they would be missing inside Docker. `_configure_litellm()` in `app/main.py` writes them explicitly at startup:

```python
def _configure_litellm() -> None:
    os.environ["OPENROUTER_API_KEY"] = settings.openrouter_api_key
    os.environ.setdefault("OR_SITE_URL", settings.or_site_url)
    os.environ.setdefault("OR_APP_NAME", settings.or_app_name)
```

### Token counting and fallback

Before forwarding, `litellm.token_counter()` counts prompt tokens against `LLM_MAX_TOKENS` (default 1600). Exceeding it returns `422` before any LLM call is made — preventing accidental cost overruns.

`num_retries=2` and `fallbacks=["openrouter/openai/gpt-3.5-turbo"]` mean transient provider errors are handled without surfacing to the developer.

### Cost estimation

LiteLLM returns `response.usage` (prompt + completion tokens). `estimate_cost()` in `vicroads_guardrails/logger.py` applies a per-model price table to compute USD cost, which is accumulated in `_daily_spend` and checked on each request. Exceeding `$5.00/day` per developer returns `402 Payment Required`.
