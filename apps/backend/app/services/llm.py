"""LLM 呼び出しの抽象化。テストではフェイクに差し替える。

LLM は API リクエストの中では呼ばない。呼ぶのはワーカー (app/worker) だけで、
使用量の記録と利用上限の確認は app/services/ai_usage.py の MeteredLLM が行う。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from app.config import settings
from app.core.exceptions import AIServiceError
from app.core.logging import get_logger

logger = get_logger(__name__)


class AIUnavailableError(AIServiceError):
    """LLM が一時的に使えない (認証情報なし・スロットリング・通信失敗)。ワーカーは再試行する。"""

    def __init__(self, detail: str = "AI 機能は現在利用できません。時間をおいてお試しください"):
        super().__init__(detail)


class AIOutputError(ValueError):
    """LLM の出力が JSON として読めない・スキーマに合わない。ワーカーは再試行する。"""


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMClient(Protocol):
    async def complete(self, system_prompt: str, user_message: str) -> LLMResponse: ...


JSON_ONLY_SUFFIX = "\n\nYou MUST respond with valid JSON only. No markdown fences, no explanation."


def parse_json_output(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1])
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise AIOutputError("AI の出力が JSON ではありません") from e
    if not isinstance(data, dict):
        raise AIOutputError("AI の出力が JSON オブジェクトではありません")
    return data


class AIConfigurationError(AIUnavailableError):
    """認証情報・モデルの利用許可・モデル ID などの設定の誤り。再試行しても直らない。"""

    def __init__(self, reason: str):
        super().__init__()
        self.reason = reason


def provider() -> str:
    """AI の呼び出し先。anthropic (Claude API) / bedrock (Claude in Amazon Bedrock)。"""
    value = settings.AI_PROVIDER.strip().lower()
    if value not in ("anthropic", "bedrock"):
        raise AIConfigurationError(f"AI_PROVIDER は anthropic か bedrock: {settings.AI_PROVIDER!r}")
    return value


def model_id() -> str:
    """呼び出し先に合わせたモデル ID (Bedrock は anthropic. の接頭辞付き)。"""
    return settings.ANTHROPIC_MODEL_ID if provider() == "anthropic" else settings.BEDROCK_MODEL_ID


class ClaudeLLMClient:
    """Claude を Anthropic SDK で呼ぶ。呼び出し先は AI_PROVIDER で切り替える。

    - anthropic: Claude API。ANTHROPIC_API_KEY を使う
    - bedrock: Claude in Amazon Bedrock (bedrock-mantle)。AWS_BEARER_TOKEN_BEDROCK
      (Bedrock API キー) があれば使い、なければ AWS の認証情報チェーン (AWS_ACCESS_KEY_ID など)
    .env の値は os.environ に入らないので、キーは Settings から明示的に渡す。
    再試行はワーカーが行うので SDK の再試行は 0 回 (呼び出しごとに使用量を記録するため)。
    """

    def __init__(self, client=None):
        self._client = client

    def _get_client(self):
        if self._client is None:
            common = {"max_retries": 0, "timeout": settings.AI_TASK_TIMEOUT_S * 0.8}
            if provider() == "anthropic":
                from anthropic import AsyncAnthropic

                if not settings.ANTHROPIC_API_KEY:
                    raise AIConfigurationError("ANTHROPIC_API_KEY が設定されていません")
                self._client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, **common)
            else:
                from anthropic import AsyncAnthropicBedrockMantle

                self._client = AsyncAnthropicBedrockMantle(
                    aws_region=settings.AWS_REGION,
                    # None なら SDK が環境変数 / AWS の認証情報チェーンから解決する
                    api_key=settings.AWS_BEARER_TOKEN_BEDROCK or None,
                    **common,
                )
        return self._client

    async def complete(self, system_prompt: str, user_message: str) -> LLMResponse:
        import anthropic

        if not settings.AI_REVIEW_ENABLED:
            raise AIConfigurationError("AI_REVIEW_ENABLED=false")
        try:
            # 現行モデルは temperature などのサンプリング設定を受け付けない (400)。
            # 思考は常に有効で、深さは effort で調整する
            response = await self._get_client().messages.create(
                model=model_id(),
                max_tokens=settings.BEDROCK_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
                output_config={"effort": settings.AI_EFFORT},
            )
        except (
            anthropic.AuthenticationError,
            anthropic.PermissionDeniedError,
            anthropic.NotFoundError,
            anthropic.BadRequestError,
        ) as e:
            message = e.body.get("error", {}).get("message", "") if isinstance(e.body, dict) else ""
            raise AIConfigurationError(
                f"{type(e).__name__}: status={e.status_code} {str(message)[:200]}".rstrip()
            ) from e
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            # 429 / 5xx / 通信失敗: 一時的なのでワーカーが再試行する
            logger.warning("llm_call_failed", error=type(e).__name__)
            raise AIUnavailableError() from e
        except AIConfigurationError:
            raise
        except Exception as e:  # 認証情報が見つからない (SigV4 の署名ができない) など
            # SDK のメッセージに秘密情報は含まれない (認証情報が見つからない旨など)
            raise AIConfigurationError(f"{type(e).__name__}: {str(e)[:200]}") from e

        if response.stop_reason == "refusal":
            raise AIOutputError("AI が応答を拒否しました")
        if response.stop_reason == "max_tokens":
            raise AIOutputError("AI の出力が上限で途中終了しました")
        # 思考ブロックは除き、本文 (text) だけを使う
        text = "".join(b.text for b in response.content if b.type == "text")
        usage = response.usage
        input_tokens = (
            usage.input_tokens
            + (getattr(usage, "cache_creation_input_tokens", None) or 0)
            + (getattr(usage, "cache_read_input_tokens", None) or 0)
        )
        return LLMResponse(text, input_tokens, usage.output_tokens, response.model)


# 既存の呼び出し元・テスト向けの旧名
BedrockLLMClient = ClaudeLLMClient

_llm_client: ClaudeLLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = ClaudeLLMClient()
    return _llm_client
