"""LLM 呼び出しの抽象化。テストではフェイクに差し替える。"""
from __future__ import annotations

import logging
from typing import Protocol

from app.config import settings
from app.core.exceptions import AIServiceError

logger = logging.getLogger(__name__)


class AIUnavailableError(AIServiceError):
    def __init__(self, detail: str = "AI レビューは現在利用できません。時間をおいてお試しください"):
        super().__init__(detail)


class LLMClient(Protocol):
    async def complete_json(self, system_prompt: str, user_message: str) -> dict: ...


class BedrockLLMClient:
    """Amazon Bedrock (Claude) 経由で JSON を生成する。"""

    async def complete_json(self, system_prompt: str, user_message: str) -> dict:
        if not settings.AI_REVIEW_ENABLED:
            raise AIUnavailableError("この環境では AI レビューが無効になっています")
        # boto3 の初期化は認証情報の解決を伴うため、実際に使うときだけ行う
        from app.services.bedrock_service import BedrockService

        try:
            return await BedrockService().invoke_json(
                system_prompt=system_prompt, user_message=user_message, temperature=0.2
            )
        except Exception as e:  # 認証情報なし・スロットリング・JSON 不正など
            logger.warning("AI review failed: %s", type(e).__name__)
            raise AIUnavailableError() from e


def get_llm_client() -> LLMClient:
    return BedrockLLMClient()
