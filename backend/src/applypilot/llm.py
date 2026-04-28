"""
Unified LLM client for ApplyPilot.

Auto-detects provider from environment:
  GEMINI_API_KEY  -> Google Gemini (default: gemini-2.5-flash)
  OPENAI_API_KEY  -> OpenAI (default: gpt-4o-mini)
  LLM_URL         -> Local llama.cpp / Ollama compatible endpoint

LLM_MODEL env var overrides the model name for any provider.
"""

import logging
import os
import threading
import time

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

def _detect_provider() -> tuple[str, str, str]:
    """Return (base_url, model, api_key) based on environment variables.

    Reads env at call time (not module import time) so that load_env() called
    in _bootstrap() is always visible here.
    """
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    local_url = os.environ.get("LLM_URL", "")
    model_override = os.environ.get("LLM_MODEL", "")

    if gemini_key and not local_url:
        return (
            "https://generativelanguage.googleapis.com/v1beta/openai",
            model_override or "gemini-2.5-flash",
            gemini_key,
        )

    if openai_key and not local_url:
        return (
            "https://api.openai.com/v1",
            model_override or "gpt-4o-mini",
            openai_key,
        )

    if local_url:
        return (
            local_url.rstrip("/"),
            model_override or "local-model",
            os.environ.get("LLM_API_KEY", ""),
        )

    raise RuntimeError(
        "No LLM provider configured. "
        "Set GEMINI_API_KEY, OPENAI_API_KEY, or LLM_URL in your environment."
    )


# ---------------------------------------------------------------------------
# Concurrency cap
# ---------------------------------------------------------------------------
#
# Cap concurrent in-flight LLM HTTP calls process-wide. Without this, a burst
# of requests can saturate the FastAPI threadpool — every thread blocks on a
# slow LLM call (especially during 429/503 retries with sleep backoff), and
# the API stops accepting new connections.
#
# Configurable via LLM_MAX_CONCURRENT env var (default: 8).

def _llm_semaphore_size() -> int:
    raw = os.environ.get("LLM_MAX_CONCURRENT", "")
    if raw:
        try:
            n = int(raw)
            if n > 0:
                return n
        except ValueError:
            pass
    return 8


_LLM_SEMAPHORE = threading.Semaphore(_llm_semaphore_size())


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class LLMUnavailable(RuntimeError):
    """Raised when the circuit breaker is open — fail fast, don't hit the network."""


class CircuitBreaker:
    """A minimal three-state circuit breaker.

    States:
      - closed:    requests pass through; consecutive failures are counted.
      - open:      requests are rejected immediately for `recovery_timeout` s.
      - half-open: one trial request is allowed; success → closed, failure → open.

    The breaker is global per process (not per provider) — simpler, and
    sufficient because ApplyPilot uses one provider per process.
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = self.STATE_CLOSED
        self._consecutive_failures = 0
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        # Recompute lazily — if recovery_timeout has elapsed since opening,
        # transition to half-open so a trial request can flow.
        with self._lock:
            if self._state == self.STATE_OPEN:
                if time.monotonic() - self._opened_at >= self.recovery_timeout:
                    self._state = self.STATE_HALF_OPEN
            return self._state

    def before_call(self) -> None:
        """Raise LLMUnavailable if the breaker is currently open."""
        if self.state == self.STATE_OPEN:
            raise LLMUnavailable(
                f"LLM circuit breaker is open (after {self._consecutive_failures} "
                f"consecutive failures). Will retry in "
                f"{max(0.0, self.recovery_timeout - (time.monotonic() - self._opened_at)):.0f}s."
            )

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0
            if self._state != self.STATE_CLOSED:
                log.info("LLM circuit breaker closed (recovered).")
            self._state = self.STATE_CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1
            if self._state == self.STATE_HALF_OPEN:
                # Half-open trial failed — re-open immediately.
                self._state = self.STATE_OPEN
                self._opened_at = time.monotonic()
                log.warning("LLM circuit breaker re-opened after half-open trial failed.")
                return
            if self._consecutive_failures >= self.failure_threshold:
                if self._state != self.STATE_OPEN:
                    log.warning(
                        "LLM circuit breaker opened after %d consecutive failures. "
                        "Failing fast for %.0fs.",
                        self._consecutive_failures, self.recovery_timeout,
                    )
                self._state = self.STATE_OPEN
                self._opened_at = time.monotonic()

    def reset(self) -> None:
        """Force-reset the breaker (mainly for tests)."""
        with self._lock:
            self._state = self.STATE_CLOSED
            self._consecutive_failures = 0
            self._opened_at = 0.0


_BREAKER = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

_MAX_RETRIES = 5
_TIMEOUT = 120  # seconds

# Base wait on first 429/503 (doubles each retry, caps at 60s).
# Gemini free tier is 15 RPM = 4s minimum between requests; 10s gives headroom.
_RATE_LIMIT_BASE_WAIT = 10


_GEMINI_COMPAT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
_GEMINI_NATIVE_BASE = "https://generativelanguage.googleapis.com/v1beta"


class LLMClient:
    """Thin LLM client supporting OpenAI-compatible and native Gemini endpoints.

    For Gemini keys, starts on the OpenAI-compat layer. On a 403/404 (model
    not exposed via compat or endpoint behavior mismatch), it automatically
    switches to the native generateContent API and stays there for the
    lifetime of the process.
    """

    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self._client = httpx.Client(timeout=_TIMEOUT)
        # True once we've confirmed the native Gemini API works for this model.
        # Mutated under _native_lock — multiple threads can race the first 403.
        self._use_native_gemini: bool = False
        self._native_lock = threading.Lock()
        self._is_gemini: bool = base_url.startswith(_GEMINI_COMPAT_BASE)

    # -- Native Gemini API --------------------------------------------------

    def _chat_native_gemini(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str:
        """Call the native Gemini generateContent API.

        Used automatically when the OpenAI-compat endpoint returns 403,
        which happens for preview/experimental models not exposed via compat.

        Converts OpenAI-style messages to Gemini's contents/systemInstruction
        format transparently.
        """
        contents: list[dict] = []
        system_parts: list[dict] = []

        for msg in messages:
            role = msg["role"]
            text = msg.get("content", "")
            if role == "system":
                system_parts.append({"text": text})
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": text}]})
            elif role == "assistant":
                # Gemini uses "model" instead of "assistant"
                contents.append({"role": "model", "parts": [{"text": text}]})

        gen_config: dict = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_mode:
            gen_config["responseMimeType"] = "application/json"

        payload: dict = {
            "contents": contents,
            "generationConfig": gen_config,
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}

        url = f"{_GEMINI_NATIVE_BASE}/models/{self.model}:generateContent"
        with _LLM_SEMAPHORE:
            resp = self._client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                params={"key": self.api_key},
            )
        resp.raise_for_status()
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        # Gemini 2.5+ thinking models return multiple parts:
        # thinking parts have {"thought": true, "text": "..."} and must be skipped.
        # The actual response is in the first non-thinking part.
        for part in parts:
            if not part.get("thought", False) and "text" in part:
                return part["text"]
        # Fallback: return first part regardless (older models, single-part responses)
        return parts[0]["text"]

    # -- OpenAI-compat API --------------------------------------------------

    def _chat_compat(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str:
        """Call the OpenAI-compatible endpoint."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        with _LLM_SEMAPHORE:
            resp = self._client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )

        # 403/404 on Gemini compat = model not available on compat layer
        # or compat endpoint mismatch for the selected model/account.
        # Raise a specific sentinel so chat() can switch to native API.
        if resp.status_code in (403, 404) and self._is_gemini:
            raise _GeminiCompatUnavailable(resp)

        return self._handle_compat_response(resp)

    @staticmethod
    def _handle_compat_response(resp: httpx.Response) -> str:
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    # -- public API ---------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        """Send a chat completion request and return the assistant message text."""
        # Qwen3 optimization: prepend /no_think to skip chain-of-thought
        # reasoning, saving tokens on structured extraction tasks.
        if "qwen" in self.model.lower() and messages:
            first = messages[0]
            if first.get("role") == "user" and not first["content"].startswith("/no_think"):
                messages = [{"role": first["role"], "content": f"/no_think\n{first['content']}"}] + messages[1:]

        # Fail fast if the breaker is open — don't enter the retry loop.
        _BREAKER.before_call()

        for attempt in range(_MAX_RETRIES):
            try:
                # Snapshot the flag under the lock so we route consistently.
                with self._native_lock:
                    use_native = self._use_native_gemini
                if use_native:
                    result = self._chat_native_gemini(messages, temperature, max_tokens, json_mode=json_mode)
                else:
                    result = self._chat_compat(messages, temperature, max_tokens, json_mode=json_mode)
                _BREAKER.record_success()
                return result

            except _GeminiCompatUnavailable as exc:
                # Model/endpoint not available on OpenAI-compat layer — switch to native.
                log.warning(
                    "Gemini compat endpoint returned %s for model '%s'. "
                    "Switching to native generateContent API. "
                    "(Some models are only available on native API for a given key.)",
                    exc.response.status_code,
                    self.model,
                )
                with self._native_lock:
                    self._use_native_gemini = True
                # Retry immediately with native — don't count as a rate-limit wait
                try:
                    result = self._chat_native_gemini(messages, temperature, max_tokens, json_mode=json_mode)
                    _BREAKER.record_success()
                    return result
                except httpx.HTTPStatusError as native_exc:
                    _BREAKER.record_failure()
                    raise RuntimeError(
                        f"Both Gemini endpoints failed. Compat: {exc.response.status_code}. "
                        f"Native: {native_exc.response.status_code} — "
                        f"{native_exc.response.text[:200]}"
                    ) from native_exc

            except httpx.HTTPStatusError as exc:
                resp = exc.response
                if resp.status_code in (429, 503) and attempt < _MAX_RETRIES - 1:
                    _BREAKER.record_failure()
                    # Respect Retry-After header if provided (Gemini sends this).
                    retry_after = (
                        resp.headers.get("Retry-After")
                        or resp.headers.get("X-RateLimit-Reset-Requests")
                    )
                    if retry_after:
                        try:
                            wait = float(retry_after)
                        except (ValueError, TypeError):
                            wait = _RATE_LIMIT_BASE_WAIT * (2 ** attempt)
                    else:
                        wait = min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), 60)

                    log.warning(
                        "LLM rate limited (HTTP %s). Waiting %ds before retry %d/%d. "
                        "Tip: Gemini free tier = 15 RPM. Consider a paid account "
                        "or switching to a local model.",
                        resp.status_code, wait, attempt + 1, _MAX_RETRIES,
                    )
                    # If recording the failure tripped the breaker, abort early —
                    # don't sleep for nothing.
                    if _BREAKER.state == CircuitBreaker.STATE_OPEN:
                        raise LLMUnavailable(
                            f"LLM circuit breaker opened mid-retry after HTTP {resp.status_code}."
                        ) from exc
                    time.sleep(wait)
                    continue
                _BREAKER.record_failure()
                raise

            except httpx.TimeoutException:
                if attempt < _MAX_RETRIES - 1:
                    _BREAKER.record_failure()
                    wait = min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), 60)
                    log.warning(
                        "LLM request timed out, retrying in %ds (attempt %d/%d)",
                        wait, attempt + 1, _MAX_RETRIES,
                    )
                    if _BREAKER.state == CircuitBreaker.STATE_OPEN:
                        raise LLMUnavailable("LLM circuit breaker opened mid-retry after timeout.")
                    time.sleep(wait)
                    continue
                _BREAKER.record_failure()
                raise

        _BREAKER.record_failure()
        raise RuntimeError("LLM request failed after all retries")

    def ask(self, prompt: str, **kwargs) -> str:
        """Convenience: single user prompt -> assistant response."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def close(self) -> None:
        self._client.close()


class _GeminiCompatUnavailable(Exception):
    """Sentinel: Gemini OpenAI-compat returned 403/404. Switch to native API."""
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        super().__init__(f"Gemini compat {response.status_code}: {response.text[:200]}")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: LLMClient | None = None
_instance_lock = threading.Lock()


def get_client() -> LLMClient:
    """Return (or create) the module-level LLMClient singleton."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                base_url, model, api_key = _detect_provider()
                log.info("LLM provider: %s  model: %s", base_url, model)
                _instance = LLMClient(base_url, model, api_key)
    return _instance
