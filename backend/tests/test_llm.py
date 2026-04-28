"""Tests for applypilot.llm — provider detection, fallback, retries, breaker.

These tests intentionally avoid the conftest fixtures (DB, Clerk, etc.) — the
LLM module is self-contained and only depends on env + httpx. We use
monkeypatch for env wiring and httpx.MockTransport to stub out the network.
"""

from __future__ import annotations

import importlib

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_llm(monkeypatch):
    """Return a freshly-imported applypilot.llm module with a clean breaker.

    The module-level _BREAKER and _instance singletons leak state across tests
    — re-import to reset, then explicitly reset the breaker as a belt-and-suspenders.
    """
    import applypilot.llm as llm_mod
    importlib.reload(llm_mod)
    llm_mod._BREAKER.reset()
    llm_mod._instance = None
    return llm_mod


def _clear_provider_env(monkeypatch):
    """Wipe all LLM-related env vars so _detect_provider is deterministic."""
    for var in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# _detect_provider precedence
# ---------------------------------------------------------------------------


def test_detect_provider_gemini_when_only_gemini_set(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    llm = _fresh_llm(monkeypatch)

    base_url, model, api_key = llm._detect_provider()
    assert "generativelanguage.googleapis.com" in base_url
    assert model == "gemini-2.5-flash"
    assert api_key == "test-gemini"


def test_detect_provider_openai_when_only_openai_set(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    llm = _fresh_llm(monkeypatch)

    base_url, model, api_key = llm._detect_provider()
    assert base_url == "https://api.openai.com/v1"
    assert model == "gpt-4o-mini"
    assert api_key == "test-openai"


def test_detect_provider_local_when_only_url_set(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("LLM_URL", "http://localhost:11434/v1/")
    llm = _fresh_llm(monkeypatch)

    base_url, model, api_key = llm._detect_provider()
    assert base_url == "http://localhost:11434/v1"
    assert model == "local-model"
    assert api_key == ""


def test_detect_provider_precedence(monkeypatch):
    """When all three are set (and LLM_URL is unset), Gemini wins.

    Note: setting LLM_URL flips the routing to local — that's by design
    (local explicit override). The intended precedence rule is
    Gemini > OpenAI when no local URL is configured.
    """
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    # LLM_URL deliberately unset — local is opt-in only.
    llm = _fresh_llm(monkeypatch)

    base_url, _, api_key = llm._detect_provider()
    assert "generativelanguage.googleapis.com" in base_url
    assert api_key == "g"


# ---------------------------------------------------------------------------
# Gemini compat → native fallback
# ---------------------------------------------------------------------------


def test_gemini_compat_falls_back_to_native_on_403(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    llm = _fresh_llm(monkeypatch)

    call_log: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/v1beta/openai/chat/completions" in url:
            call_log.append("compat")
            return httpx.Response(403, json={"error": "compat not available"})
        if ":generateContent" in url:
            call_log.append("native")
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {"content": {"parts": [{"text": "hello from native"}]}}
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    base_url, model, api_key = llm._detect_provider()
    client = llm.LLMClient(base_url, model, api_key)
    client._client = httpx.Client(transport=transport, timeout=5)

    # First call: hits compat (403) → flips flag → retries native → succeeds.
    out = client.chat([{"role": "user", "content": "hi"}])
    assert out == "hello from native"
    assert client._use_native_gemini is True
    assert call_log == ["compat", "native"]

    # Second call: should go directly to native, no compat hit.
    out2 = client.chat([{"role": "user", "content": "again"}])
    assert out2 == "hello from native"
    assert call_log == ["compat", "native", "native"]


# ---------------------------------------------------------------------------
# Retry / Retry-After handling
# ---------------------------------------------------------------------------


def test_429_respects_retry_after(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    llm = _fresh_llm(monkeypatch)

    sleep_calls: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        # Cap the actual wait so the test stays fast.
        if seconds > 2:
            return

    monkeypatch.setattr(llm.time, "sleep", fake_sleep)

    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1"}, json={"error": "rate limited"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    transport = httpx.MockTransport(handler)
    base_url, model, api_key = llm._detect_provider()
    client = llm.LLMClient(base_url, model, api_key)
    client._client = httpx.Client(transport=transport, timeout=5)

    out = client.chat([{"role": "user", "content": "hi"}])
    assert out == "ok"
    assert state["calls"] == 2
    # Retry-After of 1 → sleep at least 1.0s.
    assert sleep_calls and sleep_calls[0] >= 1.0


def test_max_retries_cap(monkeypatch):
    """Persistent 429 must not infinite-loop — eventually raises."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    llm = _fresh_llm(monkeypatch)

    # Skip real sleeping.
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "rate limited"})

    transport = httpx.MockTransport(handler)
    base_url, model, api_key = llm._detect_provider()
    client = llm.LLMClient(base_url, model, api_key)
    client._client = httpx.Client(transport=transport, timeout=5)

    # Either the breaker trips (LLMUnavailable) or all retries are exhausted (HTTPStatusError).
    # Both prove the call doesn't hang forever — that's what the cap guarantees.
    with pytest.raises((llm.LLMUnavailable, httpx.HTTPStatusError, RuntimeError)):
        client.chat([{"role": "user", "content": "hi"}])

    # Bounded by _MAX_RETRIES — at most _MAX_RETRIES network calls (5 in current config).
    assert state["calls"] <= llm._MAX_RETRIES


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_breaker_opens_after_consecutive_failures(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    llm = _fresh_llm(monkeypatch)

    # Force-record 5 failures so the breaker opens deterministically — no
    # need to actually drive HTTP calls (and avoids any retry-loop noise).
    for _ in range(5):
        llm._BREAKER.record_failure()

    assert llm._BREAKER.state == llm.CircuitBreaker.STATE_OPEN

    # Now any chat() call must short-circuit before hitting the network.
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "should not reach"}}]})

    transport = httpx.MockTransport(handler)
    base_url, model, api_key = llm._detect_provider()
    client = llm.LLMClient(base_url, model, api_key)
    client._client = httpx.Client(transport=transport, timeout=5)

    with pytest.raises(llm.LLMUnavailable):
        client.chat([{"role": "user", "content": "hi"}])

    assert state["calls"] == 0  # Network was not touched.


def test_circuit_breaker_recovers_on_success(monkeypatch):
    """Half-open trial that succeeds returns the breaker to closed."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    llm = _fresh_llm(monkeypatch)

    # Use a tiny recovery timeout so half-open kicks in instantly.
    llm._BREAKER = llm.CircuitBreaker(failure_threshold=3, recovery_timeout=0.01)

    for _ in range(3):
        llm._BREAKER.record_failure()
    assert llm._BREAKER.state == llm.CircuitBreaker.STATE_OPEN

    # Wait past recovery_timeout — state lookup transitions to half-open.
    import time as real_time
    real_time.sleep(0.02)
    assert llm._BREAKER.state == llm.CircuitBreaker.STATE_HALF_OPEN

    llm._BREAKER.record_success()
    assert llm._BREAKER.state == llm.CircuitBreaker.STATE_CLOSED
