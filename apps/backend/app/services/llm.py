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
    async def complete(
        self, system_prompt: str, user_message: str, *, temperature: float = 0.3
    ) -> LLMResponse: ...


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


class BedrockLLMClient:
    """Amazon Bedrock (Claude) を呼ぶ。"""

    async def complete(
        self, system_prompt: str, user_message: str, *, temperature: float = 0.3
    ) -> LLMResponse:
        if not settings.AI_REVIEW_ENABLED:
            raise AIUnavailableError("この環境では AI 機能が無効になっています")
        # boto3 の初期化は認証情報の解決を伴うため、実際に使うときだけ行う
        from app.services.bedrock_service import BedrockService

        try:
            service = BedrockService()
            return await service.invoke_full(
                system_prompt=system_prompt, user_message=user_message, temperature=temperature
            )
        except Exception as e:  # 認証情報なし・スロットリング・通信失敗など
            logger.warning("llm_call_failed", error=type(e).__name__)
            raise AIUnavailableError() from e


def get_llm_client() -> LLMClient:
    return BedrockLLMClient()
