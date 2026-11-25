"""Claude in Amazon Bedrock クライアント (app.services.llm.BedrockLLMClient)。

本物の Bedrock は呼ばない。SDK のクライアントをフェイクに差し替え、要求の形と応答の扱いを確かめる。
"""

from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.config import settings
from app.services.llm import (
    AIConfigurationError,
    AIOutputError,
    AIUnavailableError,
    BedrockLLMClient,
)


def _response(stop_reason="end_turn", text='{"ok": true}'):
    return SimpleNamespace(
        stop_reason=stop_reason,
        model="anthropic.claude-opus-5-5",
        content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=text),
        ],
        usage=SimpleNamespace(
            input_tokens=1200,
            output_tokens=300,
            cache_creation_input_tokens=None,
            cache_read_input_tokens=0,
        ),
    )


class FakeMessages:
    def __init__(self, result):
        self.result = result
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _client(result) -> tuple[BedrockLLMClient, FakeMessages]:
    messages = FakeMessages(result)
    return BedrockLLMClient(client=SimpleNamespace(messages=messages)), messages


def _status_error(cls, status: int):
    request = httpx.Request("POST", "https://bedrock-mantle.ap-northeast-1.api.aws/")
    return cls("err", response=httpx.Response(status, request=request), body=None)


async def test_request_shape_and_text_extraction() -> None:
    llm, messages = _client(_response())
    res = await llm.complete("system", "user")
    assert res.text == '{"ok": true}'  # 思考ブロックは除く
    assert (res.input_tokens, res.output_tokens) == (1200, 300)
    kw = messages.kwargs
    assert kw["model"] == settings.BEDROCK_MODEL_ID
    assert kw["output_config"] == {"effort": settings.AI_EFFORT}
    # 現行モデルはサンプリング設定を送ると 400
    assert not {"temperature", "top_p", "top_k"} & set(kw)


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
async def test_incomplete_output_is_retryable(stop_reason) -> None:
    llm, _ = _client(_response(stop_reason=stop_reason))
    with pytest.raises(AIOutputError):
        await llm.complete("s", "u")


@pytest.mark.parametrize(
    ("cls", "status", "expected"),
    [
        (anthropic.AuthenticationError, 401, AIConfigurationError),
        (anthropic.PermissionDeniedError, 403, AIConfigurationError),
        (anthropic.NotFoundError, 404, AIConfigurationError),
        (anthropic.RateLimitError, 429, AIUnavailableError),
        (anthropic.InternalServerError, 500, AIUnavailableError),
    ],
)
async def test_error_mapping(cls, status, expected) -> None:
    llm, _ = _client(_status_error(cls, status))
    with pytest.raises(expected) as info:
        await llm.complete("s", "u")
    if expected is AIUnavailableError:
        assert not isinstance(info.value, AIConfigurationError)


async def test_disabled_is_configuration_error(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AI_REVIEW_ENABLED", False)
    llm, messages = _client(_response())
    with pytest.raises(AIConfigurationError):
        await llm.complete("s", "u")
    assert messages.kwargs is None
