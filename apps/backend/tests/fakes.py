"""テスト用のフェイク (LLM・ワーカーの実行)。"""

from __future__ import annotations

import json

from app.services.llm import LLMResponse


class FakeLLM:
    """固定の応答を返す LLM。dict は JSON 文字列に、例外はそのまま送出する。"""

    def __init__(
        self,
        response: dict | str | Exception,
        input_tokens: int = 1000,
        output_tokens: int = 500,
    ) -> None:
        self.response = response
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls = 0
        self.messages: list[str] = []

    async def complete(self, system_prompt, user_message) -> LLMResponse:
        self.calls += 1
        self.messages.append(user_message)
        if isinstance(self.response, Exception):
            raise self.response
        text = (
            self.response
            if isinstance(self.response, str)
            else json.dumps(self.response, ensure_ascii=False)
        )
        return LLMResponse(text, self.input_tokens, self.output_tokens, "fake-model")


async def drain(session_factory, llm, limit: int = 50) -> int:
    """実行できるタスクがなくなるまでワーカーを回す。処理した件数を返す。"""
    from app.worker.worker import Worker

    worker = Worker(session_factory, llm)
    n = 0
    while n < limit and await worker.run_once():
        n += 1
    return n
