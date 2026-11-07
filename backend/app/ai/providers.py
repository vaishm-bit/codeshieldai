"""LLM providers behind one small interface.

Standard library only (no vendor SDK), so there is nothing extra to install and the
code is easy to audit. API keys are only ever sent in request headers and are never
written to logs or error messages.
"""

import http.client
import json
import socket
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.ai.errors import (
    AINotConfiguredError,
    AIProviderError,
    AIRateLimitError,
    AIResponseError,
)

ANTHROPIC_URL = "https://api.anthropic.com"
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504, 529})
MAX_BACKOFF_SECONDS = 20.0
UNREACHABLE = "Could not reach the AI provider."


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "user" or "assistant"
    content: str


class LLMProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    def complete(self, *, system: str, messages: list[ChatTurn], max_tokens: int = 2000) -> str:
        """Return the model's text reply."""


# ------------------------------------------------------------------ HTTP plumbing
def _send(url: str, headers: dict[str, str], payload: dict, timeout: float):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, _lower(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:  # status >= 400: still a normal HTTP answer
        try:
            return exc.code, _lower(exc.headers.items() if exc.headers else []), exc.read()
        finally:
            exc.close()


def _lower(items) -> dict[str, str]:
    return {key.lower(): value for key, value in items}


def _is_timeout(reason: object) -> bool:
    return isinstance(reason, (TimeoutError, socket.timeout))


def _retry_after(headers: dict[str, str]) -> float | None:
    try:
        return max(0.0, float(headers["retry-after"]))
    except (KeyError, ValueError):
        return None


def _backoff(attempt: int, retry_after: float | None) -> float:
    delay = retry_after if retry_after is not None else float(2**attempt)
    return min(delay, MAX_BACKOFF_SECONDS)


def _detail(raw: bytes) -> str:
    try:
        error = json.loads(raw.decode("utf-8")).get("error")
        message = error.get("message") if isinstance(error, dict) else error
        return f": {str(message)[:200]}" if message else ""
    except (ValueError, AttributeError):
        return ""


def _error_for(status: int, raw: bytes, retry_after: float | None):
    if status == 429:
        return AIRateLimitError(
            "The AI provider rate limit was reached. Wait a moment and try again.", retry_after
        )
    if status in (401, 403):
        # Never echo provider text here: some providers repeat part of the key.
        return AIProviderError("The AI provider rejected the API key. Check your configuration.")
    return AIProviderError(f"The AI provider returned HTTP {status}{_detail(raw)}.")


class _HTTPProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._sleep = sleep

    def _post_json(self, url: str, headers: dict[str, str], payload: dict) -> dict[str, Any]:
        headers = {**headers, "content-type": "application/json", "user-agent": "codeshield-ai/0.1"}
        attempt = 0
        while True:
            timed_out = False
            try:
                status, response_headers, raw = _send(url, headers, payload, self._timeout)
            except urllib.error.URLError as exc:
                if not _is_timeout(exc.reason):
                    raise AIProviderError(UNREACHABLE) from exc
                timed_out = True
            except TimeoutError:
                timed_out = True
            except (OSError, http.client.HTTPException) as exc:
                raise AIProviderError(UNREACHABLE) from exc

            if timed_out:
                if attempt >= self._max_retries:
                    raise AIProviderError("The AI provider timed out. Try again.")
                self._sleep(_backoff(attempt, None))
                attempt += 1
                continue

            if status < 400:
                try:
                    data = json.loads(raw.decode("utf-8"))
                except ValueError as exc:
                    raise AIProviderError("The AI provider returned an unreadable response.") from exc
                if not isinstance(data, dict):
                    raise AIProviderError("The AI provider returned an unexpected response.")
                return data

            retry_after = _retry_after(response_headers)
            if status in RETRYABLE_STATUS and attempt < self._max_retries:
                self._sleep(_backoff(attempt, retry_after))
                attempt += 1
                continue
            raise _error_for(status, raw, retry_after)


class AnthropicProvider(_HTTPProvider):
    name = "anthropic"

    def __init__(self, *, base_url: str = ANTHROPIC_URL, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url = base_url.rstrip("/")

    def complete(self, *, system: str, messages: list[ChatTurn], max_tokens: int = 2000) -> str:
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"}
        data = self._post_json(f"{self._base_url}/v1/messages", headers, payload)
        blocks = data.get("content")
        text = ""
        if isinstance(blocks, list):
            text = "".join(
                b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
        if not text:
            raise AIResponseError("The AI provider returned an empty response.")
        return text


class OpenAICompatibleProvider(_HTTPProvider):
    """Works with OpenAI and servers that copy its /chat/completions API."""

    name = "openai_compatible"

    def __init__(self, *, base_url: str, max_tokens_param: str = "max_tokens", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url = base_url.rstrip("/")
        self._max_tokens_param = max_tokens_param

    def complete(self, *, system: str, messages: list[ChatTurn], max_tokens: int = 2000) -> str:
        payload = {
            "model": self.model,
            self._max_tokens_param: max_tokens,
            "messages": [{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
        }
        headers = {"authorization": f"Bearer {self._api_key}"}
        data = self._post_json(f"{self._base_url}/chat/completions", headers, payload)
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise AIResponseError("The AI provider returned an unexpected response.") from exc
        if not text:
            raise AIResponseError("The AI provider returned an empty response.")
        return text


# ------------------------------------------------------------------------ factory
def _secret(value: object) -> str:
    if value is None:
        return ""
    getter = getattr(value, "get_secret_value", None)
    return (getter() if getter else str(value)).strip()


def resolve_provider_choice(settings: Any) -> str:
    """Which provider the settings select: anthropic, openai_compatible or none."""
    choice = (settings.ai_provider or "auto").strip().lower()
    if choice == "openai":
        choice = "openai_compatible"
    if choice == "auto":
        if _secret(settings.anthropic_api_key):
            return "anthropic"
        if _secret(settings.openai_api_key):
            return "openai_compatible"
        return "none"
    return choice


def build_provider(settings: Any, *, sleep: Callable[[float], None] = time.sleep) -> LLMProvider:
    choice = resolve_provider_choice(settings)
    common = {
        "timeout": settings.ai_timeout_seconds,
        "max_retries": settings.ai_max_retries,
        "sleep": sleep,
    }
    if choice == "anthropic":
        key = _secret(settings.anthropic_api_key)
        if not key:
            raise AINotConfiguredError("ANTHROPIC_API_KEY is not set in backend/.env.")
        return AnthropicProvider(api_key=key, model=settings.anthropic_model, **common)
    if choice == "openai_compatible":
        key = _secret(settings.openai_api_key)
        if not key:
            raise AINotConfiguredError("OPENAI_API_KEY is not set in backend/.env.")
        if not settings.openai_model.strip():
            raise AINotConfiguredError("OPENAI_MODEL is not set in backend/.env.")
        return OpenAICompatibleProvider(
            api_key=key,
            model=settings.openai_model.strip(),
            base_url=settings.openai_base_url,
            max_tokens_param=settings.openai_max_tokens_param,
            **common,
        )
    if choice == "none":
        raise AINotConfiguredError(
            "No AI provider is configured. Set ANTHROPIC_API_KEY (or OPENAI_API_KEY and "
            "OPENAI_MODEL) in backend/.env and restart the server."
        )
    raise AINotConfiguredError(f"Unknown AI_PROVIDER '{choice}'.")
