"""
End-to-end PII compliance guarantee tests.

Proves that raw citizen PII is structurally redacted *before* litellm.acompletion()
is called — i.e. sensitive data never leaves the local process.

Run: uv run pytest tests/test_pii_guarantee.py -v
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from litellm import ModelResponse
from litellm.utils import Usage
from unittest.mock import patch

from app.main import app
import app.database as _db
import app.api.route_chat_completion_middleware as _route

# ── Constants ─────────────────────────────────────────────────────────────────

_AUTH = {"X-Developer-Token": "dev-test"}
_MODEL = "openrouter/google/gemma-4-27b-it:free"

# ── Helpers ───────────────────────────────────────────────────────────────────


def _body(*turns: tuple[str, str]) -> dict:
    """Build a minimal chat completion request body."""
    return {
        "model": _MODEL,
        "messages": [{"role": role, "content": content} for role, content in turns],
    }


def _make_fake_llm(captured: list[list[str]]):
    """Return an async callable that records forwarded message content strings."""

    async def _fake(**kwargs):
        captured.append([m["content"] for m in kwargs.get("messages", [])])
        r = ModelResponse(id="chatcmpl-test", choices=[], model="gpt-3.5-turbo")
        r.usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        return r

    return _fake


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def client():
    """Full FastAPI app over ASGI with in-memory SQLite — no network required.

    httpx's ASGITransport does not trigger the ASGI lifespan, so we initialise
    the database directly before yielding the client.
    """
    _db._engine = None
    _db._AsyncSessionLocal = None
    await _db.init_db("sqlite+aiosqlite:///:memory:")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    if _db._engine:
        await _db._engine.dispose()
    _db._engine = None
    _db._AsyncSessionLocal = None


@pytest.fixture
def captured() -> list[list[str]]:
    return []


@pytest.fixture
def mock_llm(captured: list[list[str]]):
    """Patch litellm so no real API calls happen; captures forwarded messages."""
    with (
        patch("litellm.acompletion", new=_make_fake_llm(captured)),
        patch("litellm.token_counter", return_value=20),
    ):
        yield


# ── TestPIIGuarantee ──────────────────────────────────────────────────────────


class TestPIIGuarantee:
    """Core compliance: raw PII must never appear in the messages sent to the LLM."""

    @pytest.mark.anyio
    async def test_vic_dl_numeric_never_reaches_llm(self, client, mock_llm, captured):
        await client.post(
            "/v1/chat/completions",
            json=_body(("user", "My licence number is 123456789.")),
            headers=_AUTH,
        )
        assert len(captured) == 1
        assert all("123456789" not in c for c in captured[0])
        assert any("[REDACTED_VIC_DL]" in c for c in captured[0])

    @pytest.mark.anyio
    async def test_vic_dl_alpha_never_reaches_llm(self, client, mock_llm, captured):
        await client.post(
            "/v1/chat/completions",
            json=_body(("user", "Driver licence: A12345678")),
            headers=_AUTH,
        )
        assert all("A12345678" not in c for c in captured[0])
        assert any("[REDACTED_VIC_DL]" in c for c in captured[0])

    @pytest.mark.anyio
    async def test_email_never_reaches_llm(self, client, mock_llm, captured):
        await client.post(
            "/v1/chat/completions",
            json=_body(("user", "Please contact john.doe@example.com for details.")),
            headers=_AUTH,
        )
        assert all("john.doe@example.com" not in c for c in captured[0])
        assert any("[REDACTED_EMAIL]" in c for c in captured[0])

    @pytest.mark.anyio
    async def test_au_phone_never_reaches_llm(self, client, mock_llm, captured):
        await client.post(
            "/v1/chat/completions",
            json=_body(("user", "Call me on 0412 345 678 anytime.")),
            headers=_AUTH,
        )
        assert all("0412 345 678" not in c for c in captured[0])
        assert any("[REDACTED_PHONE]" in c for c in captured[0])

    @pytest.mark.anyio
    async def test_medicare_never_reaches_llm(self, client, mock_llm, captured):
        await client.post(
            "/v1/chat/completions",
            json=_body(("user", "Medicare number: 2123456701")),
            headers=_AUTH,
        )
        assert all("2123456701" not in c for c in captured[0])
        assert any("[REDACTED_MEDICARE]" in c for c in captured[0])

    @pytest.mark.anyio
    async def test_street_address_never_reaches_llm(self, client, mock_llm, captured):
        await client.post(
            "/v1/chat/completions",
            json=_body(("user", "I live at 42 Collins Street Melbourne.")),
            headers=_AUTH,
        )
        assert all("42 Collins Street" not in c for c in captured[0])

    @pytest.mark.anyio
    async def test_person_name_never_reaches_llm(self, client, mock_llm, captured):
        await client.post(
            "/v1/chat/completions",
            json=_body(("user", "The applicant John Smith submitted the renewal form.")),
            headers=_AUTH,
        )
        assert all("John Smith" not in c for c in captured[0])

    @pytest.mark.anyio
    async def test_pii_in_system_role_also_redacted(self, client, mock_llm, captured):
        """PII in system prompts is as dangerous as in user messages."""
        await client.post(
            "/v1/chat/completions",
            json=_body(
                ("system", "Admin contact: admin@vicroads.gov.au"),
                ("user", "What is the policy?"),
            ),
            headers=_AUTH,
        )
        assert all("admin@vicroads.gov.au" not in c for c in captured[0])

    @pytest.mark.anyio
    async def test_multiple_pii_types_all_redacted(self, client, mock_llm, captured):
        text = (
            "Licence 987654321, email jane@example.com, "
            "call 0498 765 432, Medicare 3456789011."
        )
        await client.post(
            "/v1/chat/completions", json=_body(("user", text)), headers=_AUTH
        )
        content = captured[0][0]
        assert "987654321" not in content
        assert "jane@example.com" not in content
        assert "0498 765 432" not in content
        assert "3456789011" not in content

    @pytest.mark.anyio
    async def test_clean_message_passes_through_unchanged(
        self, client, mock_llm, captured
    ):
        text = "What is the speed limit on a Victorian freeway?"
        await client.post(
            "/v1/chat/completions", json=_body(("user", text)), headers=_AUTH
        )
        assert captured[0][0] == text


# ── TestGatewayGuards ─────────────────────────────────────────────────────────


class TestGatewayGuards:
    """HTTP-level enforcement: auth, token preflight, daily budget."""

    @pytest.mark.anyio
    async def test_missing_auth_header_returns_401(self, client):
        r = await client.post("/v1/chat/completions", json=_body(("user", "Hello")))
        assert r.status_code == 401

    @pytest.mark.anyio
    async def test_invalid_token_prefix_returns_403(self, client):
        r = await client.post(
            "/v1/chat/completions",
            json=_body(("user", "Hello")),
            headers={"X-Developer-Token": "badtoken-123"},
        )
        assert r.status_code == 403

    @pytest.mark.anyio
    async def test_prompt_too_long_returns_422(self, client):
        with patch("litellm.token_counter", return_value=99_999):
            r = await client.post(
                "/v1/chat/completions",
                json=_body(("user", "Hello")),
                headers=_AUTH,
            )
        assert r.status_code == 422
        assert r.json()["detail"]["error"] == "prompt_too_long"

    @pytest.mark.anyio
    async def test_budget_exceeded_returns_402(self, client):
        with patch.dict(_route._daily_spend, {"dev-test": 999.0}):
            r = await client.post(
                "/v1/chat/completions",
                json=_body(("user", "Hello")),
                headers=_AUTH,
            )
        assert r.status_code == 402
        assert r.json()["detail"]["error"] == "daily_budget_exceeded"

    @pytest.mark.anyio
    async def test_health_endpoint_always_available(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["guardrail"] == "active"
