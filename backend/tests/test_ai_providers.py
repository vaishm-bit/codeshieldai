from types import SimpleNamespace

import pytest

from app.ai.errors import (
    AINotConfiguredError,
    AIProviderError,
    AIRateLimitError,
    AIResponseError,
)
from app.ai.providers import (
    AnthropicProvider,
    ChatTurn,
    OpenAICompatibleProvider,
    build_provider,
    resolve_provider_choice,
)
from tests.ai_helpers import closed_port_url, fake_server, silent_server

KEY = "sk-test-secret-key-0000"
USER = [ChatTurn("user", "hi")]
ANTHROPIC_OK = {"content": [{"type": "text", "text": "Hello"}]}


def anthropic(url, sleeps=None, **kwargs):
    sleeps = sleeps if sleeps is not None else []
    options = {"max_retries": 0, "timeout": 5.0, **kwargs}
    return AnthropicProvider(
        api_key=KEY, model="test-model", base_url=url, sleep=sleeps.append, **options
    )


def test_anthropic_request_and_response():
    with fake_server([(200, {}, ANTHROPIC_OK)]) as (url, state):
        reply = anthropic(url).complete(system="be careful", messages=USER, max_tokens=500)
    assert reply == "Hello"
    request = state["requests"][0]
    assert request["path"] == "/v1/messages"
    assert request["headers"]["x-api-key"] == KEY
    assert request["headers"]["anthropic-version"] == "2023-06-01"
    assert request["json"] == {
        "model": "test-model",
        "max_tokens": 500,
        "system": "be careful",
        "messages": [{"role": "user", "content": "hi"}],
    }


def test_openai_compatible_request_and_response():
    body = {"choices": [{"message": {"content": " Hi there "}}]}
    with fake_server([(200, {}, body)]) as (url, state):
        provider = OpenAICompatibleProvider(
            api_key=KEY,
            model="m1",
            base_url=url + "/v1/",
            max_tokens_param="max_completion_tokens",
            max_retries=0,
            timeout=5.0,
        )
        reply = provider.complete(system="sys", messages=USER, max_tokens=300)
    assert reply == "Hi there"
    request = state["requests"][0]
    assert request["path"] == "/v1/chat/completions"
    assert request["headers"]["authorization"] == f"Bearer {KEY}"
    assert request["json"]["max_completion_tokens"] == 300
    assert "max_tokens" not in request["json"]
    assert request["json"]["messages"][0] == {"role": "system", "content": "sys"}


def test_rate_limit_retries_then_raises_with_retry_after():
    sleeps = []
    with fake_server([(429, {"Retry-After": "7"}, {"error": {"message": "slow down"}})]) as (url, state):
        provider = anthropic(url, sleeps, max_retries=1)
        with pytest.raises(AIRateLimitError) as caught:
            provider.complete(system="s", messages=USER)
    assert len(state["requests"]) == 2
    assert sleeps == [7.0]
    assert caught.value.retry_after == 7.0
    assert caught.value.status_code == 429
    assert caught.value.details == {"retry_after_seconds": 7.0}


def test_overloaded_then_success_uses_backoff():
    sleeps = []
    responses = [(529, {}, {"error": {"message": "overloaded"}}), (200, {}, ANTHROPIC_OK)]
    with fake_server(responses) as (url, _):
        reply = anthropic(url, sleeps, max_retries=2).complete(system="s", messages=USER)
    assert reply == "Hello"
    assert sleeps == [1.0]


def test_backoff_is_capped():
    sleeps = []
    with fake_server([(429, {"Retry-After": "999"}, {}), (200, {}, ANTHROPIC_OK)]) as (url, _):
        anthropic(url, sleeps, max_retries=1).complete(system="s", messages=USER)
    assert sleeps == [20.0]


def test_rejected_key_never_echoes_provider_text_or_key():
    body = {"error": {"message": f"Incorrect API key provided: {KEY}"}}
    with fake_server([(401, {}, body)]) as (url, _):
        with pytest.raises(AIProviderError) as caught:
            anthropic(url).complete(system="s", messages=USER)
    assert KEY not in caught.value.message
    assert "API key" in caught.value.message


def test_server_error_is_reported_with_short_detail():
    with fake_server([(500, {}, {"error": {"message": "boom"}})]) as (url, state):
        with pytest.raises(AIProviderError) as caught:
            anthropic(url).complete(system="s", messages=USER)
    assert "HTTP 500" in caught.value.message and "boom" in caught.value.message
    assert len(state["requests"]) == 1  # max_retries=0


def test_empty_and_malformed_responses():
    with fake_server([(200, {}, {"content": []})]) as (url, _):
        with pytest.raises(AIResponseError):
            anthropic(url).complete(system="s", messages=USER)
    with fake_server([(200, {}, "not json at all")]) as (url, _):
        with pytest.raises(AIProviderError):
            anthropic(url).complete(system="s", messages=USER)
    with fake_server([(200, {}, {"choices": []})]) as (url, _):
        provider = OpenAICompatibleProvider(
            api_key=KEY, model="m", base_url=url, max_retries=0, timeout=5.0
        )
        with pytest.raises(AIResponseError):
            provider.complete(system="s", messages=USER)


def test_timeout_is_retried_then_reported():
    sleeps = []
    with silent_server() as url:
        provider = anthropic(url, sleeps, max_retries=1, timeout=0.3)
        with pytest.raises(AIProviderError) as caught:
            provider.complete(system="s", messages=USER)
    assert "timed out" in caught.value.message
    assert sleeps == [1.0]


def test_unreachable_provider():
    with pytest.raises(AIProviderError) as caught:
        anthropic(closed_port_url()).complete(system="s", messages=USER)
    assert "Could not reach" in caught.value.message


# ------------------------------------------------------------------- factory
def make_settings(**overrides):
    values = dict(
        ai_provider="auto",
        anthropic_api_key=None,
        anthropic_model="claude-test",
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="",
        openai_max_tokens_param="max_tokens",
        ai_timeout_seconds=30.0,
        ai_max_retries=2,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeSecret:
    def __init__(self, value):
        self._value = value

    def get_secret_value(self):
        return self._value


def test_auto_picks_anthropic_then_openai_then_none():
    assert resolve_provider_choice(make_settings(anthropic_api_key=FakeSecret("k"))) == "anthropic"
    assert resolve_provider_choice(make_settings(openai_api_key=FakeSecret("k"))) == "openai_compatible"
    assert resolve_provider_choice(make_settings(anthropic_api_key=FakeSecret("  "))) == "none"
    assert resolve_provider_choice(make_settings(ai_provider="OpenAI")) == "openai_compatible"


def test_build_provider_anthropic():
    provider = build_provider(make_settings(anthropic_api_key=FakeSecret("k")))
    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-test"


def test_build_provider_openai_requires_model():
    settings = make_settings(openai_api_key=FakeSecret("k"))
    with pytest.raises(AINotConfiguredError) as caught:
        build_provider(settings)
    assert "OPENAI_MODEL" in caught.value.message
    provider = build_provider(make_settings(openai_api_key=FakeSecret("k"), openai_model="gpt-x"))
    assert isinstance(provider, OpenAICompatibleProvider)


def test_build_provider_not_configured():
    with pytest.raises(AINotConfiguredError) as caught:
        build_provider(make_settings())
    assert caught.value.status_code == 503
    with pytest.raises(AINotConfiguredError):
        build_provider(make_settings(ai_provider="anthropic"))
    with pytest.raises(AINotConfiguredError):
        build_provider(make_settings(ai_provider="mystery"))
